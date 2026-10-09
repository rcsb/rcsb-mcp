#!/usr/bin/env python3
"""Generate the Sequence Coordinates FEATURE TYPE catalog from the live APIs.

rcsb_seqcoord_annotations filters on a feature's TYPE, which the Sequence Coordinates GraphQL
schema enumerates (`FeaturesType`, ~345 values). The filter is case-sensitive and an unknown
name is not an error -- it silently matches nothing ("ACTIVE SITE" and "active_site" both
return 0 features where ACTIVE_SITE returns 3), and the names are not guessable
(_4_PHOSPHOPANTETHEINE, DISULFIDE_BRIDGE_ beside DISULFIDE_BRIDGE). So the vocabulary is
vendored, like the attribute catalogs, so that types can be checked and looked up locally.

Four things come out, in src/rcsb_mcp/feature_types.py:

    FEATURE_TYPES          every FeaturesType value, from the Sequence Coordinates schema. The
                           UNION of INTROSPECTIONS spaced calls: during a rollout pods answer
                           with different schemas (2026-10-09: 138 or 345 values, about 1 call
                           in 3 the older one, in runs; the 207 extra are the per-residue protein
                           modifications released 2026-10-13), and the union is the newer one.
                           A split is reported. The union only helps while some call reaches a
                           newer pod, so a run during a rollout can still see only the old one.
    FEATURE_TYPE_SOURCES   every FEATURE_TYPES value -> the annotation sources (UNIPROT,
                           PDB_ENTITY, PDB_INSTANCE, PDB_INTERFACE) that can emit it. Asking the
                           wrong source silently returns nothing (ACTIVE_SITE exists only in
                           UNIPROT), and the Sequence Coordinates schema does not say which is
                           which -- but FeaturesType is built as the allOf of the JSON-schema
                           enumerations in TYPE_FIELDS, each the feature type of one source's
                           Data API object. The Data API GraphQL schema lists each field's
                           values ("Allowable values: ..."), so every name can be traced back
                           to the field, and so the source, it came from.
    FEATURE_TYPE_FILTER_SPELLING
                           name -> the spelling a TYPE filter has to use, where it is not the
                           name. The API returns FeaturesType names but matches a filter
                           against the STORED type: the Data API value upper-cased, spaces,
                           hyphens and digit runs kept. 1CRN_1 (2026-10-09): DISULFIDE_BRIDGE
                           finds 0 features, "DISULFIDE BRIDGE" the 3 it returns as
                           DISULFIDE_BRIDGE. Both case twins share one stored spelling.
    FEATURE_TYPES_BY_FIELD Data API field -> the names it lists (a name can be in two), so a
                           search can tell a bond (rcsb_polymer_struct_conn) or a protein
                           modification (pdbx_modification_feature) from the other instance
                           features without a hand-made grouping.

The trace converts each Data API value to its FeaturesType name (enum_name). Two values whose
names differ only in letter case (struct_conn "disulfide bridge", modification category
"Disulfide bridge") stay distinct: the later TYPE_FIELDS entry takes a trailing "_". That
choice changes nothing while both values belong to one source (both pairs today: PDB_INSTANCE);
a pair across two sources stops the generator, since the order alone would then pick the
sources of a name.

FEATURE_TYPES is the authority. A Data API value whose name is not a FeaturesType value is
reported and left out: the two APIs release separately (2026-10-09 the Data API already listed
the 207 modification values Sequence Coordinates adds on 2026-10-13). A FeaturesType value no
field traces to stops the generator, apart from KNOWN_UNTRACED: it means the naming rule, the
allOf, or a schema changed -- a broken rule shows up here, as the name it failed to produce.
The sources say what CAN be emitted, not that the archive holds any (ANGLE_OUTLIER is listed
beside ANGLE_OUTLIERS, but only the plural has data).

Usage:
    python scripts/generate_feature_types.py            # (re)write the module
    python scripts/generate_feature_types.py --check    # exit 1 if stale (no write)
"""
from __future__ import annotations

import argparse
import http.client
import json
import pathlib
import re
import time
import urllib.error
import urllib.request

_OUT = pathlib.Path(__file__).resolve().parents[1] / "src" / "rcsb_mcp" / "feature_types.py"
SEQCOORD_URL = "https://sequence-coordinates.rcsb.org/graphql"
DATA_URL = "https://data.rcsb.org/graphql"

SOURCES = ["UNIPROT", "PDB_ENTITY", "PDB_INSTANCE", "PDB_INTERFACE"]
INTROSPECTIONS = 8
_INTROSPECTION_GAP = 0.5  # seconds between calls: the old-schema answers come in runs

# The allOf behind FeaturesType, IN ITS ORDER (the order decides which case-only twin takes the
# trailing "_"): Data API query root, field path to the enumerated value, and the annotation
# source that object is. Mirrors the JSON-schema $refs of the Sequence Coordinates schema.
TYPE_FIELDS = [
    ("interface", "rcsb_interface_partner.interface_partner_feature.type", "PDB_INTERFACE"),
    ("uniprot", "rcsb_uniprot_feature.type", "UNIPROT"),
    ("polymer_entity", "rcsb_polymer_entity_feature.type", "PDB_ENTITY"),
    ("polymer_entity_instance", "rcsb_polymer_instance_feature.type", "PDB_INSTANCE"),
    ("polymer_entity_instance", "rcsb_polymer_struct_conn.connect_type", "PDB_INSTANCE"),
    ("polymer_entity_instance", "pdbx_modification_feature.category", "PDB_INSTANCE"),
    ("polymer_entity_instance", "pdbx_modification_feature.type", "PDB_INSTANCE"),
]

# FeaturesType values no TYPE_FIELDS entry lists, with why. They keep an empty source list (no
# source emits them); a new one stops the generator until it is understood and added here.
KNOWN_UNTRACED = {
    "PROTEIN_BINDING": "added to FeaturesType by hand, no longer used",  # RCSB, 2026-10-09
}
# FeaturesType values a field DOES list but Sequence Coordinates does not serve, with why. They
# keep an empty source list too, so the tool refuses them instead of answering "none here".
# UNASSIGNED_SEC_STRUCT: the search index holds it for 557,759 entities; Sequence Coordinates
# returned it from no source (2026-10-09), and RCSB confirmed the removal was intended.
NOT_SERVED = {
    "UNASSIGNED_SEC_STRUCT": "removed from Sequence Coordinates on purpose",  # RCSB, 2026-10-09
}

_TYPE_REF = "type { kind name ofType { kind name ofType { kind name ofType { name } } } }"


def _post(url: str, query: str, what: str) -> dict:
    """POST a GraphQL query with retries. Fatal after the last attempt: a catalog generated
    from partial answers would be committed as if it were complete."""
    data = json.dumps({"query": query}).encode()
    attempts = 5
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                answer = json.loads(resp.read().decode())
            if answer.get("errors") or not answer.get("data"):
                raise RuntimeError(f"{what}: {(answer.get('errors') or [{}])[0].get('message', answer)}")
            return answer["data"]
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"{what} failed: HTTP {exc.code}") from None
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError):
            pass
        if attempt < attempts - 1:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{what} kept failing; nothing was written")


def feature_types() -> tuple[list[str], list[int]]:
    """Every FeaturesType value, unioned over INTROSPECTIONS calls (see module docstring), and
    the size of each answer, so a split between pods can be reported."""
    seen: set[str] = set()
    sizes: list[int] = []
    for i in range(INTROSPECTIONS):
        if i:
            time.sleep(_INTROSPECTION_GAP)
        answer = _post(SEQCOORD_URL, '{ __type(name: "FeaturesType") { enumValues { name } } }',
                       f"FeaturesType introspection {i + 1}")
        names = {v["name"] for v in answer["__type"]["enumValues"]}
        seen |= names
        sizes.append(len(names))
    return sorted(seen), sizes


def _named(type_ref: dict) -> str:
    while type_ref.get("ofType"):
        type_ref = type_ref["ofType"]
    return type_ref["name"]


def allowed_values(description: str, what: str) -> list[str]:
    """The values a Data API field description lists after "Allowable values:"."""
    head, sep, tail = description.partition("Allowable values:")
    if not sep or not tail.strip():
        raise RuntimeError(f"{what}: description lists no allowable values: {description[:120]!r}")
    return [v.strip() for v in tail.strip().split(", ")]


def field_values() -> list[tuple[str, list[str]]]:
    """(source, allowed values) for every TYPE_FIELDS entry, in allOf order."""
    roots = {f["name"]: _named(f["type"]) for f in
             _post(DATA_URL, "{ __schema { queryType { fields { name %s } } } }" % _TYPE_REF,
                   "Data API query roots")["__schema"]["queryType"]["fields"]}
    fields_of: dict[str, dict] = {}
    out = []
    for root, path, source in TYPE_FIELDS:
        type_name, field = roots.get(root), None
        for name in path.split("."):
            if type_name not in fields_of:
                found = _post(DATA_URL, '{ __type(name: "%s") { fields { name description %s } } }'
                              % (type_name, _TYPE_REF), f"Data API type {type_name}")["__type"]
                fields_of[type_name] = {f["name"]: f for f in (found or {}).get("fields") or []}
            field = fields_of[type_name].get(name)
            if field is None:
                raise RuntimeError(f"Data API has no {root}.{path} (stopped at {name} on {type_name})")
            type_name = _named(field["type"])
        out.append((source, allowed_values(field.get("description") or "", f"{root}.{path}")))
    return out


def enum_name(value: str) -> str:
    """A Data API value as the FeaturesType name it becomes: AMPylation -> AM_PYLATION,
    SCOP2B_SUPERFAMILY -> SCOP_2_B_SUPERFAMILY, "disulfide bridge" -> DISULFIDE_BRIDGE,
    4-Phosphopantetheine -> _4_PHOSPHOPANTETHEINE."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)    # aB, 2B   -> a_B, 2_B
    s = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", s)       # AMPyl    -> AM_Pyl
    s = re.sub(r"([A-Za-z])([0-9])", r"\1_\2", s)         # TY1      -> TY_1
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()
    return "_" + s if s[:1].isdigit() else s


def type_sources(types: list[str], fields: list[tuple[str, list[str]]]
                 ) -> tuple[dict[str, list[str]], list[str], dict[str, str]]:
    """Every FeaturesType value -> the sources whose field lists it; the derived names that are
    not FeaturesType values (left out); and the filter spelling of each name that differs from
    it (see module docstring)."""
    owner, by_name, _ = _trace(fields)
    untraced = sorted(set(types) - set(by_name) - set(KNOWN_UNTRACED))
    if untraced:
        raise RuntimeError(f"FeaturesType names no Data API field lists: {untraced}. Find their "
                           "origin, then add a TYPE_FIELDS entry or a KNOWN_UNTRACED one.")
    strays = sorted(set(by_name) - set(types))
    spellings = {t: owner[t][0].upper() for t in types if t in owner and owner[t][0].upper() != t}
    served = {t: [s for s in SOURCES if s in by_name.get(t, ())] if t not in NOT_SERVED else []
              for t in types}
    return served, strays, spellings


def types_by_field(types: list[str], fields: list[tuple[str, list[str]]]) -> dict[str, list[str]]:
    """TYPE_FIELDS path -> the FeaturesType names its values become, in allOf order."""
    _, _, in_fields = _trace(fields)
    return {f"{root}.{path}": [t for t in types if i in in_fields.get(t, ())]
            for i, (root, path, _) in enumerate(TYPE_FIELDS)}


def _trace(fields: list[tuple[str, list[str]]]
           ) -> tuple[dict[str, tuple[str, str]], dict[str, set[str]], dict[str, set[int]]]:
    """Every Data API value as its FeaturesType name: name -> (value, source) that took it first,
    name -> sources, and name -> indexes of the fields listing it."""
    owner: dict[str, tuple[str, str]] = {}
    by_name: dict[str, set[str]] = {}
    in_fields: dict[str, set[int]] = {}
    for i, (source, values) in enumerate(fields):
        for value in values:
            name = enum_name(value)
            while name in owner and owner[name][0] != value:
                taken_by, taken_in = owner[name]
                if taken_in != source:
                    raise RuntimeError(
                        f"{value!r} ({source}) and {taken_by!r} ({taken_in}) both become {name}; "
                        "which one keeps it would rest on the TYPE_FIELDS order alone. Check that "
                        "order against the Sequence Coordinates schema's allOf, then decide here.")
                name += "_"
            owner.setdefault(name, (value, source))
            by_name.setdefault(name, set()).add(source)
            in_fields.setdefault(name, set()).add(i)
    return owner, by_name, in_fields


def render_module(types: list[str], sources: dict[str, list[str]], spellings: dict[str, str],
                  by_field: dict[str, list[str]]) -> str:
    untraced = [t for t in types if not sources[t]]
    entries = ",\n".join(f"    {json.dumps(t)}: {json.dumps(sources[t])}" for t in types)
    spelled = ",\n".join(f"    {json.dumps(t)}: {json.dumps(spellings[t])}" for t in sorted(spellings))
    return (
        '"""Sequence Coordinates feature types: the FeaturesType vocabulary rcsb_seqcoord_annotations\n'
        "filters on, and which annotation sources can emit each.\n\n"
        "Auto-generated by scripts/generate_feature_types.py from the Sequence Coordinates schema\n"
        f"({SEQCOORD_URL}) and the Data API field enumerations\n"
        f"it is built from ({DATA_URL}).\n"
        "Do not edit by hand; re-run the generator to refresh.\n"
        '"""\n\n'
        f"# Every FeaturesType value ({len(types)}): the names the API returns as a feature's `type`.\n"
        "# A TYPE filter matches the stored spelling, which differs for FEATURE_TYPE_FILTER_SPELLING.\n"
        f"FEATURE_TYPES: list[str] = {json.dumps(types, indent=4)}\n\n"
        "# Every FEATURE_TYPES value -> the sources (in UNIPROT, PDB_ENTITY, PDB_INSTANCE, PDB_INTERFACE\n"
        "# order) whose Data API feature field lists it: what a source CAN emit, not that data exists.\n"
        f"# Empty (no source emits it) for: {'; '.join(f'{t}, {(KNOWN_UNTRACED | NOT_SERVED)[t]}' for t in untraced) or 'none'}.\n"
        f"FEATURE_TYPE_SOURCES: dict[str, list[str]] = {{\n{entries}\n}}\n\n"
        "# FEATURE_TYPES values a TYPE filter only matches in another spelling: the stored type, the\n"
        "# Data API value upper-cased. The API returns the name; a filter on the name finds nothing.\n"
        f"FEATURE_TYPE_FILTER_SPELLING: dict[str, str] = {{\n{spelled}\n}}\n\n"
        "# Data API field -> the FEATURE_TYPES values it lists, in the allOf order.\n"
        f"FEATURE_TYPES_BY_FIELD: dict[str, list[str]] = {json.dumps(by_field, indent=4)}\n"
    )


def generate() -> tuple[str, list[str], dict[str, list[str]], list[str], list[int]]:
    types, sizes = feature_types()
    fields = field_values()
    sources, strays, spellings = type_sources(types, fields)
    return render_module(types, sources, spellings, types_by_field(types, fields)), types, sources, strays, sizes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit non-zero if the committed module is stale")
    args = ap.parse_args()
    module, types, sources, strays, sizes = generate()
    if len(set(sizes)) > 1:
        split = ", ".join(f"{sizes.count(n)} saw {n}" for n in sorted(set(sizes)))
        print(f"note: pods disagree ({split} of {len(sizes)} calls); using the union of "
              f"{len(types)}. Re-run once the rollout finishes.")
    if strays:
        print(f"note: {len(strays)} Data API values are not FeaturesType values and were left out "
              f"(an API ahead of the other?): {', '.join(strays[:8])}{' ...' if len(strays) > 8 else ''}")
    per_source = ", ".join(f"{s} {sum(s in v for v in sources.values())}" for s in SOURCES)
    sizes = f"{len(types)} types; {per_source}; no source {[t for t in types if not sources[t]]}"
    if args.check:
        current = _OUT.read_text() if _OUT.exists() else ""
        if current != module:
            print(f"STALE: {_OUT.name} differs from the live APIs ({sizes})")
            return 1
        print(f"OK: {_OUT.name} up to date ({sizes})")
        return 0
    _OUT.write_text(module)
    print(f"wrote {_OUT.name} ({sizes})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
