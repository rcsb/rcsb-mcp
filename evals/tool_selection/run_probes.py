"""Tool-selection probe runner for rcsb-mcp (see README.md and probes.xml).

Loads the ACTUAL tool schemas + the guide from a given checkout of the server, asks a model
to act on each prompt in probes.xml, and grades the model's FIRST tool call against that
probe's <expect> assertion. Run it twice — once with --src pointing at the pre-change
server, once at the current one — and compare the pass rates with --compare.

`--guide` picks the delivery channel to simulate (the rcsb_mcp_guide prompt by default,
`assistant` for guide+policy, `none` for a client that loads neither). It is a real
variable: the server no longer ships an `instructions` block, so what the model receives
depends on what the client chooses to load.

A rate is computed over the samples that actually REACHED the model, never over --k, and
attrition is reported. Anything else scores a dropped connection as a wrong tool choice —
see "Known harness bugs" in ../README.md, bug 4.

Usage:
  # strong model / current tree
  ANTHROPIC_API_KEY=... python run_probes.py --backend anthropic --model claude-haiku-4-5-20251001 --k 5
  # a local vLLM (OpenAI-compatible endpoint; usually needs no key)
  python run_probes.py --backend openai --base-url http://localhost:8000 --model <id> --k 5
  # A/B against a pre-change checkout, then diff
  python run_probes.py ... --src /tmp/old/src --out /tmp/old.json
  python run_probes.py ... --src src          --out /tmp/new.json
  python run_probes.py --compare /tmp/old.json /tmp/new.json

Only the tool DECISION is graded; the RCSB API is never called. No secrets are logged.
"""
import argparse
import asyncio
import importlib
import json
import os
import sys
import time
import xml.etree.ElementTree as ET

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
PROBES_XML = os.path.join(HERE, "probes.xml")


# --------------------------------------------------------------------------- #
# probes.xml -> probes + the <expect> interpreter
# --------------------------------------------------------------------------- #
def load_probes(path=PROBES_XML):
    root = ET.parse(path).getroot()
    probes = []
    for p in root.findall("probe"):
        probes.append({
            "id": p.get("id"),
            "probes": p.get("probes") or "",
            # Ordered <turn role="..."> elements appended after the prompt. The graded call
            # is always the model's FIRST, so seeding is the only way to grade a tool that
            # is never called first -- see build_messages.
            "turns": [{"role": t.get("role", "user"), "content": (t.text or "").strip(),
                       "tool": t.get("tool"), "args": t.get("args")}
                      for t in p.findall("turn")],
            "prompt": (p.findtext("prompt") or "").strip(),
            "expect": p.find("expect"),
        })
    return probes


def _eq(actual, expected, ignore_case=False):
    """Compare an arg value to an expected string; "true"/"false" compare against booleans."""
    if isinstance(actual, bool):
        return actual == (str(expected).strip().lower() == "true")
    a, e = str(actual), str(expected)
    if ignore_case:
        a, e = a.lower(), e.lower()
    return a == e


def check(expect, tool, args):
    """Evaluate a probe's <expect> assertion against the model's first tool call."""
    if expect is None:
        return False
    if expect.get("tool") and tool != expect.get("tool"):
        return False
    if expect.get("tool-in") and tool not in [x.strip() for x in expect.get("tool-in").split(",")]:
        return False
    if expect.get("tool-not") and tool == expect.get("tool-not"):
        return False

    for el in expect:
        if el.tag == "arg":
            name = el.get("name")
            val = args.get(name, el.get("default")) if el.get("default") is not None else args.get(name)
            if el.get("set") == "true":
                if val is None or val == "" or val == [] or val == {}:
                    return False
            elif el.get("equals") is not None:
                if val is None or not _eq(val, el.get("equals"), el.get("ignore-case") == "true"):
                    return False
            elif el.get("contains") is not None:
                if el.get("contains") not in str(val if val is not None else ""):
                    return False
        elif el.tag == "attribute":
            path, op = el.get("path"), el.get("operator")
            hit = False
            for a in args.get("attributes") or []:
                if isinstance(a, dict) and path in str(a.get("attribute", "")):
                    if op is None or a.get("operator") == op:
                        hit = True
                        break
            if not hit:
                return False
    return True


# --------------------------------------------------------------------------- #
# server under test + model backends
# --------------------------------------------------------------------------- #
def load_server(src_path, guide="guide"):
    """Fresh-import rcsb_mcp.server from a specific src dir; return (system_prompt, tools).

    `guide` selects WHICH delivery channel the run simulates, because that is a real
    variable now and not an implementation detail:

      "guide"     the rcsb_mcp_guide prompt        — what a client that loads the guide sees
      "assistant" rcsb_search_assistant            — guide + search/report policy
      "none"      nothing                          — a client that loads neither

    This used to read `server.mcp.instructions`, which the server no longer ships (see the
    comment at the FastMCP() call). Left alone it silently degraded to "", so every run
    would have measured the "none" arm while looking exactly like the historical runs that
    had the full guide — an invisible change of what the number means. Falls back to
    `instructions` so this runner still works against an OLD --src checkout that has it.
    """
    src_path = os.path.abspath(src_path)
    sys.path.insert(0, src_path)
    for m in [k for k in list(sys.modules) if k.startswith("rcsb_mcp")]:
        del sys.modules[m]
    server = importlib.import_module("rcsb_mcp.server")
    tools = asyncio.run(server.mcp.list_tools())
    if guide == "none":
        system = ""
    elif guide == "assistant":
        system = server.rcsb_search_assistant()
    else:
        system = (getattr(server, "rcsb_mcp_guide", lambda: "")()
                  or getattr(server.mcp, "instructions", "") or "")
        if not system:
            raise SystemExit(f"--src {src_path} exposes neither rcsb_mcp_guide nor instructions")
    sys.path.remove(src_path)
    return system, [{"name": t.name, "description": t.description or "", "schema": t.inputSchema} for t in tools]


# ONE client for the whole run. Previously every sample used module-level `httpx.post`,
# which builds a fresh Client and so a fresh TLS handshake — 60-96 handshakes in quick
# succession per run. That is the most likely source of the SSLV3_ALERT_BAD_RECORD_MAC
# storm that made a 14-point regression appear out of nothing (see README bug 4): all 54
# errored samples across four runs were that one TLS integrity fault. Pooling removes the
# churn; the retry below covers what pooling doesn't.
_CLIENT = httpx.Client(timeout=120, limits=httpx.Limits(max_keepalive_connections=4))


class AuthError(RuntimeError):
    """Credentials rejected — never a probe result, so never scored as one."""


class Throttled(RuntimeError):
    """Rate-limited or overloaded; retryable after a wait."""


def _raise_for_status(r):
    """Turn HTTP status into a CLASSIFIED failure.

    `raise_for_status()` alone made a 401 and a wrong tool choice indistinguishable: both
    became a caught Exception and a scored-as-failed sample, so a bad key printed
    "OVERALL mean pass-rate: 0.00" instead of saying the key was bad.
    """
    if r.status_code in (401, 403):
        raise AuthError(f"HTTP {r.status_code}: credentials rejected by the API")
    if r.status_code in (429, 529) or r.status_code >= 500:
        raise Throttled(f"HTTP {r.status_code}")
    r.raise_for_status()


def call_anthropic(system, tools, messages, model, temperature):
    body = {
        "model": model, "max_tokens": 1024, "system": system, "temperature": temperature,
        "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["schema"]} for t in tools],
        "tool_choice": {"type": "auto"}, "messages": messages,
    }
    r = _CLIENT.post("https://api.anthropic.com/v1/messages", json=body, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    _raise_for_status(r)
    return [(b["name"], b.get("input", {})) for b in r.json().get("content", []) if b.get("type") == "tool_use"]


def call_openai(base_url, system, tools, messages, model, temperature):
    body = {
        "model": model, "temperature": temperature, "tool_choice": "auto",
        "tools": [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                    "parameters": t["schema"]}} for t in tools],
        "messages": [{"role": "system", "content": system}] + messages,
    }
    r = _CLIENT.post(base_url.rstrip("/") + "/v1/chat/completions", json=body,
                     headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', 'x')}"})
    _raise_for_status(r)
    out = []
    for c in r.json()["choices"][0]["message"].get("tool_calls") or []:
        try:
            out.append((c["function"]["name"], json.loads(c["function"].get("arguments") or "{}")))
        except json.JSONDecodeError:
            out.append((c["function"]["name"], {}))
    return out


# Retry only what is genuinely transient. An AuthError is re-raised immediately: a run that
# cannot authenticate must abort loudly, not grind out a confident 0.00.
_RETRYABLE = (httpx.TransportError, Throttled)


def sample_once(call, attempts=3):
    """Run one sample, retrying transport faults and throttling with linear backoff.

    Returns (calls, None) on success or (None, error_string) once the attempts are spent.
    The caller must NOT treat an error as a failed probe — see `run`.
    """
    last = None
    for attempt in range(attempts):
        try:
            return call(), None
        except AuthError:
            raise
        except _RETRYABLE as e:
            last = f"{type(e).__name__}: {e}"
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
        except Exception as e:  # noqa: BLE001 — malformed body, unexpected shape: not retryable
            return None, f"{type(e).__name__}: {str(e)[:100]}"
    return None, last


def build_messages(probe, backend="anthropic"):
    """The prompt, plus any <turn> elements the probe seeds after it.

    Seeding carries the whole weight of grading the EXECUTOR. Only the model's first tool
    call is scored, and since the builder/executor split the first call in a real search is
    always an rcsb_query_* builder -- so return_type, group_by, sort_by and all_hits, which
    live only on rcsb_search_request, are invisible to an unseeded probe. A probe that seeds
    the builder step as already done puts rcsb_search_request in the graded position.

    A turn carrying tool=/args= is emitted as a REAL tool call plus its result, in whichever
    wire format the backend uses. That distinction is not cosmetic. The first version of this
    narrated the step in prose ("I built the query with rcsb_query_attribute, which returned
    ..."), and models re-did the work instead of continuing from it: 30-50% of samples called
    a builder or a resolver rather than the executor, in BOTH arms of an A/B, which gutted the
    statistical power of the probes that need seeding most. A tool_use/tool_result pair is a
    completed step; a sentence about one is just context.

    This also replaced a single hardcoded seed that named rcsb_search_by_attribute, a tool
    that no longer exists.
    """
    msgs = [{"role": "user", "content": probe["prompt"]}]
    for i, turn in enumerate(probe.get("turns") or []):
        if not turn.get("tool"):
            msgs.append({"role": turn["role"], "content": turn["content"]})
            continue
        call_id = f"seed_{i}"
        args = turn.get("args") or "{}"
        if backend == "anthropic":
            msgs.append({"role": "assistant", "content": [
                {"type": "tool_use", "id": call_id, "name": turn["tool"], "input": json.loads(args)}]})
            msgs.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": call_id, "content": turn["content"]}]})
        else:
            msgs.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": call_id, "type": "function",
                 "function": {"name": turn["tool"], "arguments": args}}]})
            msgs.append({"role": "tool", "tool_call_id": call_id, "content": turn["content"]})
    return msgs


# --------------------------------------------------------------------------- #
def run(args):
    instr, tools = load_server(args.src, args.guide)
    only = {x for x in (args.only or "").split(",") if x}
    results = {}
    for probe in load_probes():
        if only and probe["id"] not in only:
            continue
        passes, errs, observed = 0, [], []
        for _ in range(args.k):
            msgs = build_messages(probe, args.backend)
            call = (lambda: call_anthropic(instr, tools, msgs, args.model, args.temperature)) \
                if args.backend == "anthropic" else \
                (lambda: call_openai(args.base_url, instr, tools, msgs, args.model, args.temperature))
            calls, err = sample_once(call, attempts=args.attempts)
            if err is not None:
                errs.append(err)
                continue
            tool, targs = calls[0] if calls else ("<none>", {})
            ok = bool(check(probe["expect"], tool, targs))
            passes += ok
            observed.append({"tool": tool, "args": targs, "pass": ok})
        # Divide by the samples that actually REACHED the model. Dividing by args.k scored a
        # dropped connection identically to a wrong tool choice, and because errors cluster
        # (see README bug 4) that penalised whichever arm of an A/B ran second — the same
        # change once read 0.92->0.78 one way and 0.67->0.80 with the order reversed.
        graded = len(observed)
        rate = passes / graded if graded else float("nan")
        results[probe["id"]] = {"rate": rate, "graded": graded, "requested": args.k,
                                "probes": probe["probes"], "errors": errs, "calls": observed}
        if not graded:
            flag, shown = "  <-- NO DATA (every sample errored)", " n/a"
        else:
            flag = "" if rate == 1 else ("  <-- FAIL" if rate == 0 else "  <-- flaky")
            shown = f"{int(rate * 100):3d}%"
        lost = f"  [{len(errs)} errored]" if errs else ""
        print(f"  {probe['id']:16} {shown} ({passes}/{graded}){lost}{flag}   {probe['probes']}")

    scored = [v["rate"] for v in results.values() if v["graded"]]
    overall = sum(scored) / len(scored) if scored else float("nan")
    total_err = sum(len(v["errors"]) for v in results.values())
    total_req = sum(v["requested"] for v in results.values())
    print(f"\n  OVERALL mean pass-rate: {overall:.2f}   "
          f"(src={args.src}, model={args.model}, k={args.k}, guide={args.guide})")
    print(f"  graded {sum(v['graded'] for v in results.values())}/{total_req} samples"
          + (f", {total_err} errored after {args.attempts} attempts" if total_err else ""))
    # Loud, because a heavily-degraded run must never be mistaken for a clean one.
    if total_err > total_req * 0.05:
        print(f"  !! {100*total_err/total_req:.0f}% of samples never reached the model — this run is "
              f"NOT comparable; investigate before reading any delta")
    if args.out:
        json.dump({"src": args.src, "model": args.model, "k": args.k, "guide": args.guide,
                   "attempts": args.attempts, "errored": total_err, "results": results},
                  open(args.out, "w"), indent=2)
        print(f"  saved -> {args.out}")
    return results


def compare(old_path, new_path):
    """Diff two result files. A regression = a probe whose pass-rate DROPPED old->new."""
    old, new = json.load(open(old_path)), json.load(open(new_path))
    o, n = old["results"], new["results"]
    print(f"A/B  old_src={old['src']}  new_src={new['src']}  model={new['model']}  k={new['k']}\n")

    # Refuse to compare arms that did not see the same guide, or that lost samples. Both
    # produce a plausible-looking delta about something other than the change under test.
    og, ng = old.get("guide", "?"), new.get("guide", "?")
    if og != ng:
        print(f"  !! guide differs between arms (old={og}, new={ng}) — not comparable\n")
    for label, d in (("old", old), ("new", new)):
        errored = d.get("errored")
        if errored:
            req = sum(v.get("requested", d.get("k", 0)) for v in d["results"].values())
            print(f"  !! {label} arm lost {errored}/{req} samples to errors — a rate built on "
                  f"fewer samples is noisier, and clustered loss biases the diff\n")

    regress, improved, unchanged, preexisting = [], [], [], []
    for pid, nr in n.items():
        if pid not in o:
            continue
        ro, rn = o[pid]["rate"], nr["rate"]
        if ro != ro or rn != rn:  # NaN: a probe with no graded samples has no rate to diff
            print(f"  skipped     {pid:16} no graded samples on one arm")
            continue
        if rn < ro:
            regress.append((pid, ro, rn, nr["probes"]))
        elif rn > ro:
            improved.append((pid, ro, rn))
        else:
            (preexisting if rn < 1.0 else unchanged).append(pid)
    for pid, ro, rn, probes in regress:
        print(f"  REGRESSION  {pid:16} {int(ro*100):3d}% -> {int(rn*100):3d}%   {probes}")
    for pid, ro, rn in improved:
        print(f"  improved    {pid:16} {int(ro*100):3d}% -> {int(rn*100):3d}%")
    if preexisting:
        print(f"  (pre-existing <100% on both, not change-caused: {', '.join(preexisting)})")
    print(f"\n  {len(regress)} regression(s), {len(improved)} improved, "
          f"{len(unchanged)+len(preexisting)} unchanged")
    print("  VERDICT:", "SAFE — no regressions" if not regress else "REVIEW — behaviour changed above")
    return regress


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--compare", nargs=2, metavar=("OLD", "NEW"), help="diff two result files and exit")
    p.add_argument("--backend", choices=["anthropic", "openai"])
    p.add_argument("--model")
    p.add_argument("--base-url", default="http://localhost:8000", help="openai backend only")
    p.add_argument("--src", default="src", help="server src dir to load tools from (point at an old checkout for A/B)")
    p.add_argument("--k", type=int, default=5, help="samples per probe (compare RATES, not single runs)")
    p.add_argument("--temperature", type=float, default=1.0)
    # Default is "none": the rcsb_mcp_guide prompt was retired and every rule moved onto the
    # tool descriptions, so a client that loads nothing is the SUPPORTED configuration, not a
    # degraded one — and it is what a public MCP client actually sees. "guide" is kept only
    # for running against an old --src checkout that still exposes the prompt; against this
    # tree it exits with a clear error rather than silently measuring the "none" arm.
    p.add_argument("--guide", choices=["guide", "assistant", "none"], default="none",
                   help="which delivery channel to simulate: nothing (default -- what a "
                        "public MCP client sees), rcsb_search_assistant, or the retired "
                        "rcsb_mcp_guide prompt (old --src checkouts only)")
    p.add_argument("--attempts", type=int, default=3,
                   help="tries per sample before recording a transport/throttle error")
    p.add_argument("--only", default="", help="comma-separated probe ids to run (default: all)")
    p.add_argument("--out", default="")
    a = p.parse_args()
    if a.compare:
        sys.exit(1 if compare(*a.compare) else 0)
    if not a.backend or not a.model:
        p.error("--backend and --model are required (unless --compare)")
    try:
        run(a)
    except AuthError as e:
        # A config problem, not a result. Exit clean so it reads as "fix your key", not as
        # a stack trace to debug — and emphatically not as a pass-rate.
        sys.exit(f"\n  ABORTED: {e}\n  No score was produced. Check the API key for "
                 f"--backend {a.backend}.")
