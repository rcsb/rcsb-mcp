"""A tool's description must not promise data the tool does not return.

This class of defect has surfaced three times in this codebase, each time found by a human
or an agent rather than by CI:

  * rcsb_get_polymer_entities said "metadata and biological annotations"; the default field
    selection contained no annotation field at all, so an agent that called it, saw none,
    and concluded the tool had none was reading the docs correctly.
  * include_computed_models was advertised on seven search tools and silently honoured by
    two.
  * the retired guide told agents to pass `facets` to "any rcsb_search_* tool" after those
    parameters had moved to rcsb_search_request.

They share a shape: prose and behaviour drift apart, and nothing fails. Every assertion
here derives its expectation from the CODE — the default field selections, the registered
tool names — so it keeps holding as both sides change, rather than pinning today's wording.
"""

from __future__ import annotations

import ast
import asyncio
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp import data, queries, resolvers, search, seqcoord, server  # noqa: E402

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "rcsb_mcp"

# A word a summary line may use to claim a KIND of data, and the evidence that the default
# field selection actually returns it. Deliberately small: only claims specific enough that
# a reader would expect a named field, and each is a substring match against the selection
# so a rename on either side does not silently pass.
# Only nouns that name a PAYLOAD. "citation" is deliberately absent: rcsb_get_pubmed
# fetches "the PubMed record for a citation", where the word names what the id refers to,
# not something the response carries. A vocabulary that cannot tell a payload from a
# referent produces failures nobody can act on, and a guard people disable is worse than
# no guard.
CLAIM_EVIDENCE = {
    "annotation": ("annotation",),
    "resolution": ("resolution",),
    "title": ("title",),
    "abstract": ("abstract",),
    "organism": ("organism",),
    "sequence": ("sequence", "entity_poly"),
    "formula": ("formula",),
}

# Parentheticals and "e.g." tails illustrate; they do not promise. "polymer entity groups
# (e.g. sequence clusters)" says what a group IS, not that a sequence comes back.
_ASIDE = re.compile(r"\([^)]*\)|,?\s*e\.g\..*$")


def _docstrings(module) -> dict[str, str]:
    tree = ast.parse(pathlib.Path(module.__file__).read_text())
    return {
        n.name: (ast.get_docstring(n) or "")
        for n in ast.walk(tree)
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
    }


def _summary(doc: str) -> str:
    """The first paragraph — what a reader takes as the tool's promise."""
    return " ".join(doc.split("\n\n")[0].split())


@pytest.mark.parametrize(
    "tool_name",
    sorted(n for n in _docstrings(data) if n.startswith("rcsb_get_")),
)
def test_a_get_tool_only_claims_data_its_default_returns(tool_name):
    """The summary line is a promise about the DEFAULT response, not about what exists.

    Anything reachable only via `fields=` has to say so — otherwise the tool looks broken
    to a caller who takes it at its word.
    """
    doc = _docstrings(data)[tool_name]
    summary = _ASIDE.sub("", _summary(doc)).lower()
    key = tool_name.replace("rcsb_get_", "")
    spec = queries.DATA_OBJECTS.get(key)
    assert spec is not None, f"{tool_name} has no DATA_OBJECTS entry"
    selection = spec.default_fields.lower()

    for claim, evidence in CLAIM_EVIDENCE.items():
        if claim not in summary:
            continue
        assert any(e in selection for e in evidence), (
            f"{tool_name}'s summary claims {claim!r}, but its default field selection "
            f"returns no matching field. Either add one, or move the claim out of the "
            f"summary and say it needs `fields=`.\n  summary:   {_summary(doc)}\n"
            f"  selection: {spec.default_fields}"
        )


def test_the_annotation_route_stays_reachable():
    """Regression: polymer entities carry annotations, but only when asked for by name.

    Nothing documented that until an agent found it the hard way — the tool claimed
    annotations and returned none, so a caller who believed the docs concluded they did not
    exist. What has to survive is the NAME: an agent that cannot see the field cannot ask
    for it, and rcsb_describe_data_object only helps once you know what to look for.

    Asserted against the default selection rather than against wording, so the prose can be
    rewritten freely; if the field is ever promoted INTO the default, this fails and says to
    drop the sentence rather than leave it describing a step nobody needs.
    """
    doc = _docstrings(data)["rcsb_get_polymer_entities"]
    selection = queries.DATA_OBJECTS["polymer_entities"].default_fields
    field = "rcsb_polymer_entity_annotation"

    assert field in doc, (
        f"{field} is how the archive's own GO/InterPro/Pfam terms are reached; the "
        "docstring must name it or the path is undiscoverable"
    )
    assert field not in selection, (
        f"{field} is now in the default selection — the docstring sentence telling callers "
        "to request it is obsolete; delete it and say so in the summary instead"
    )


# --------------------------------------------------------------------------- #
# No tool description or runtime note may name a tool that is not advertised
# --------------------------------------------------------------------------- #
# A tool NAME, not a family glob: "rcsb_get_*" and "rcsb_query_* tools" refer to a family
# and are matched here with a trailing underscore, so anything ending in `_` is excluded.
_TOOL_MENTION = re.compile(r"\brcsb_[a-z0-9_]*[a-z0-9]\b")

# Names that are documentation subjects rather than call targets.
_NOT_TOOLS = {"rcsb_id", "rcsb_mcp", "rcsb_mcp_guide"}


def _advertised() -> set[str]:
    return {t.name for t in asyncio.run(server.mcp.list_tools())}


@pytest.mark.parametrize("module", [data, resolvers, search, seqcoord],
                         ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_docstrings_never_point_at_an_unlisted_tool(module):
    """A cross-reference only helps if the client can see what it names.

    The rcsb_search_* -> rcsb_query_* rename left three of these behind in resolver
    RESPONSE notes, telling agents to call a tool that no longer appears in tools/list.
    """
    advertised = _advertised()
    known_prefixes = ("rcsb_get_", "rcsb_query_", "rcsb_find_", "rcsb_search_",
                      "rcsb_describe_", "rcsb_list_", "rcsb_seqcoord_", "rcsb_render_")
    # The superseded rcsb_search_* tools are dispatch-only: their descriptions are never
    # sent to any client, so what they cross-reference cannot mislead anyone. Excluded by
    # DERIVING the set from the registration code, so retiring one updates this too.
    unshipped = {fn.__name__ for fn in search._LEGACY_SEARCH_TOOLS}
    bad = []
    for fn_name, doc in _docstrings(module).items():
        if fn_name in unshipped:
            continue
        for mentioned in set(_TOOL_MENTION.findall(doc)):
            if mentioned in _NOT_TOOLS or mentioned in advertised:
                continue
            if not mentioned.startswith(known_prefixes):
                continue  # a field path like rcsb_polymer_entity_annotation, not a tool
            bad.append(f"{module.__name__}:{fn_name} -> {mentioned}")
    assert not bad, "docstrings name tools that tools/list does not advertise:\n  " + \
        "\n  ".join(sorted(bad))


def test_runtime_notes_never_point_at_an_unlisted_tool():
    """The same rule for text the agent reads in RESPONSES, not just descriptions.

    Docstring guards miss these: the resolver fallback notes are ordinary string literals
    built at call time.
    """
    advertised = _advertised()
    source = pathlib.Path(resolvers.__file__).read_text()
    tree = ast.parse(source)
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        for mentioned in set(_TOOL_MENTION.findall(node.value)):
            if (mentioned.startswith(("rcsb_query_", "rcsb_search_", "rcsb_get_", "rcsb_find_"))
                    and mentioned not in advertised):
                bad.append(f"line {node.lineno}: {mentioned}")
    assert not bad, "runtime notes name unlisted tools:\n  " + "\n  ".join(sorted(set(bad)))


# --------------------------------------------------------------------------- #
# Shared text may only say what is true for every caller
# --------------------------------------------------------------------------- #
#
# The five ontologies do NOT store their annotations in one place:
#
#   rcsb_polymer_entity_annotation      CARD, GO, GlyCosmos, GlyGen, InterPro,
#                                       MemProtMD, OPM, PDBTM, Pfam, mpstruc
#   rcsb_polymer_instance_annotation    CATH, ECOD, GlyGen, SCOP, SCOP2
#   rcsb_uniprot_annotation             disease, phenotype, GO, InterPro
#   rcsb_polymer_entity.rcsb_ec_lineage EC
#   rcsb_entity_source_organism         taxonomy (already in the default selection)
#
# So a concrete field named in the SHARED note is right for at most a couple of resolvers
# and wrong for the rest — an EC caller told to read rcsb_polymer_entity_annotation finds
# no EC there, ever. Field names belong on each rcsb_find_* tool, which knows its own
# ontology; the shared note may only carry the principle.
_FIELD_LIKE = re.compile(r"\brcsb_[a-z0-9_]*(annotation|lineage|organism)[a-z0-9_]*\b")


def test_the_shared_resolver_note_names_no_ontology_specific_field():
    notes = [
        resolvers._resolver_fallback_note([], "InterPro entry"),
        resolvers._resolver_fallback_note([{"id": "X", "pdb_entry_count": 0}], "GO term"),
        resolvers._resolver_fallback_note([{"id": "X", "pdb_entry_count": 1}], "EC number"),
    ]
    for note in notes:
        assert note is not None
        leaked = _FIELD_LIKE.findall(note)
        assert not leaked, (
            f"the shared resolver note names an ontology-specific field ({leaked}); it is "
            "emitted for all five rcsb_find_* tools, which store annotations in different "
            f"places.\n  note: {note}"
        )
