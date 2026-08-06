"""Deterministic guard for load-bearing tool-description content.

The search-tool docstrings were deduplicated — shared config detail (return types,
grouping, paging, faceting, ontology-resolver routing, assembly attributes) was moved
into the FastMCP ``instructions=`` block, and each docstring left a pointer. These
assertions lock in the cross-field rules and routing gotchas the JSON schema cannot
encode, so a future trim can't silently delete one (or gut the block a pointer targets).

No network, no API key, no model — this is the cheap CI gate. The behavioral A/B that
checks whether the model still *acts* on this text lives in ``evals/tool_selection/``.
"""
import asyncio
import re

from rcsb_mcp import server


def _norm(s: str) -> str:
    """Collapse whitespace so line-wrapping in a docstring never hides a phrase."""
    return re.sub(r"\s+", " ", s or "")


def _descriptions():
    tools = asyncio.run(server.mcp.list_tools())
    return {t.name: _norm(t.description) for t in tools}


# Gotchas that must stay in the SPECIFIC tool's own description: they are not derivable
# from the schema and are not shared enough to live in the instructions block.
REQUIRED_IN_TOOL = {
    "rcsb_query_fulltext": [
        "text-relevance, NOT biological importance",   # score is not quality
        "AND/OR/NOT are NOT boolean",                   # query-string gotcha
        # Rare-term recall: resolve a biological CONCEPT to an ontology id before keyword
        # searching it. Moved off rcsb_search_assistant.md, which is optional and may never
        # be loaded — this is the only channel guaranteed to arrive.
        "resolve it to an ontology id",
    ],
    "rcsb_query_attribute": [
        "an empty result is a valid answer",            # don't fall back to keyword search
        "carries NO biological meaning",                # score caveat (attribute form)
        "EXCLUSIVE",                                     # range bound semantics
        "rcsb_query_composer",                          # where nested boolean groups go now
    ],
    "rcsb_query_sequence": [
        "rcsb_query_seqmotif",                           # routing: pattern vs full sequence
    ],
    "rcsb_query_chemical": [
        "fingerprint-similarity",                        # match_type option
        "sub-struct-graph",                              # substructure option
        "merely contain the",                            # match_subset semantics
    ],
    "rcsb_query_structure": [
        "mutually exclusive",                            # assembly_id vs asym_id
        "Defaults to assembly",
    ],
    "rcsb_query_seqmotif": [
        "prosite",
        "simple wildcards",
    ],
    "rcsb_query_strucmotif": [
        "mmCIF",                                         # label-vs-author id explanation
        "author numbers give wrong/no hits",
        "catalytic triads",                              # when-to-use routing
        "PSEUDO_ATOMS",                                  # atom_pairing_scheme option
    ],
    "rcsb_query_composer": [
        "`in` operator",                                 # don't OR a list of alternatives
        "mixes services",                                # the other reason to compose
    ],
    # The envelope prose now lives ONCE, here, instead of on every search tool. These are
    # the cross-field rules that used to be repeated seven times; if this tool's docstring
    # is trimmed they have no other home.
    "rcsb_search_request": [
        "SORTABLE attributes",                           # sort_by only works on some paths
        'return_type="mol_definition"',                  # sort_by limitation
        "refused above 10000",                           # all_hits cap
        "cannot be combined with offset",                # all_hits + paging
        "requires return_type=\"polymer_entity\"",       # group_by precondition
        "Nothing is searched until you call it",         # the layered-flow gotcha
        "IDENTIFIERS only",                              # results need a rcsb_get_* follow-up
        # return_type is chosen HERE, so every hint about it lives here and nowhere else:
        # the six values, the per-query default, the id shape, and the conversion trick.
        "4HHB_1",                                        # what a polymer_entity id looks like
        "Setting it CONVERTS the result",                # e.g. ligand filter -> entries
        "default implied by the query",                  # why omitting it is usually right
        # Picking a cluster representative by relevance score is a distinct mistake from
        # ranking hits by it; this caveat used to live in the guide's grouping section.
        "don't pick a cluster representative by it",
        # Faceting a result set to find what the hits SHARE is the discovery move that
        # turns a handful of hits into a re-searchable value. It was documented only as a
        # reporting device ("how many by X"), so agents reached for it when a COUNTING
        # question was asked and never when they needed to broaden or explore.
        "what your hits SHARE",
        # And the second half, which is what makes the first usable. A facet's population is
        # within the result set; nothing in the response says how common the value is in the
        # archive, and that is the only thing separating a useful value from a useless one at
        # EVERY membership level. Measured on 4 phrase hits for "receptor-like cytoplasmic
        # kinase": IPR050823 and IPR000719 both appear in 4/4 and are 8 vs 10,744 entities
        # archive-wide; GO:0002221 and GO:0005634 both appear in 1/4 and are 486 vs 104,027.
        # Bucket order is no help — it returned the 10,744 first and the 8 last. Without this
        # sentence the natural read of "what your hits share" is the top bucket.
        "archive-wide count is a",
        "distinctive or generic",
    ],
    # rcsb_get_* family: the `fields`-param mechanics were shortened to a pointer, but each
    # tool's cross-reference / drill-down guidance must survive the trim.
    "rcsb_get_entries": [
        "rcsb_entry_container_identifiers",              # component-id drill-down
        "compose them with the entry id",                # how to build sibling-tool ids
    ],
    "rcsb_get_nonpolymer_entities": [
        "rcsb_get_chem_comps",                           # where to get the ligand chemistry
    ],
    "rcsb_get_polymer_entities": [
        "rcsb_query_sequence",                           # id source hint (renamed with the layer)
    ],
    "rcsb_get_uniprot": [
        "rcsb_uniprot_annotation",                       # heavier optional annotation sets ...
        "rcsb_uniprot_feature",
    ],
    "rcsb_get_chem_comps": [
        "InChIKey",                                      # a default field callers rely on
    ],
    # rcsb_find_* resolvers: the search-by-id recipe was delegated to the instructions block,
    # but these bits live ONLY here. `namespace`/`entry_type` are `str | None` (NOT Literals),
    # so their allowed values never reach the JSON schema — this docstring is their only home.
    "rcsb_find_go_terms": [
        # namespace's values are no longer guarded here: it is now a GoNamespace Literal, so the
        # schema ships the enum (incl. the mf/bp/cc aliases) and the prose is redundant.
        "are involved in",                               # trigger paraphrases (not in instructions)
        "localized to",
    ],
    "rcsb_find_interpro_domains": [
        # entry_type's values are no longer guarded here: it is now an InterProEntryType Literal,
        # so the schema ships the enum (incl. the "superfamily" alias) and the prose is redundant.
        "-containing proteins",                          # trigger paraphrase (not in instructions)
    ],
    "rcsb_find_enzyme_classes": [
        "break down / degrade",                          # fires when no enzyme is NAMED
    ],
    "rcsb_find_disease_terms": [
        "implicated in",                                 # trigger paraphrase
    ],
    "rcsb_find_organisms": [
        "disambiguates a species from its strains",      # not in instructions ('strain' absent)
    ],
    # rcsb_seqcoord_*: the ref/group/source VALUES are Literals (SequenceRef/GroupRef/
    # AnnotationRef), so the schema ships them and the prose was cut. These are what the schema
    # cannot express — the per-system id FORMATS and the entity-level rule.
    "rcsb_seqcoord_alignments": [
        "entry_entityNumber",                            # PDB_ENTITY id format
        "entry.asym_id",                                 # PDB_INSTANCE id format
        "ENTITY-level",                                  # a bare entry id silently fails
        "only cross-references UniProt",                 # why not the Data API (routing)
    ],
}

# Guidance that used to live in the rcsb_mcp_guide prompt and is now asserted against the
# TOOL DESCRIPTIONS instead. This is a strictly stronger guarantee than the old one: a
# prompt arrives only if the client asks for it, so pointing a tool description at one and
# then checking the prompt still contains the answer verified the wrong half of the promise.
# tools/list always arrives, so if a phrase is here, the model received it.
REQUIRED_SOMEWHERE_IN_TOOL_DESCRIPTIONS = [
    # Ontology resolvers: each rcsb_find_* tool now carries its own attribute path, so a
    # resolved id has a documented way to be used no matter what the client loaded.
    "rcsb_polymer_entity_annotation.annotation_lineage.id",   # GO (term + descendants)
    "annotation_id",                                          # GO exact-term-only path
    "rcsb_polymer_entity_annotation.annotation_id",           # InterPro (NOT lineage)
    "rcsb_polymer_entity.rcsb_ec_lineage.id",                 # EC (hierarchical)
    "rcsb_uniprot_annotation.annotation_lineage.id",          # MONDO (UniProt-derived)
    "rcsb_entity_source_organism.taxonomy_lineage.id",        # NCBI taxonomy
    "HIERARCHICAL",                                           # lineage matching semantics
    'AS A STRING ("9606", not 9606',                          # taxon id-typing gotcha
    # Envelope guidance, now on rcsb_search_request.
    "group_by",
    "return_type",
    # `fields=` verification, now on the describe tools.
    "NEVER invent, guess, or infer a field path",
]

# Content from the retired guide that was deliberately NOT relocated, and is therefore
# reachable by no agent. Recorded rather than asserted so the gap stays visible: it is a
# decision, not an oversight. prompts/rcsb_mcp_guide.md keeps the prose to restore from.
NOT_RELOCATED = [
    "polymer_entity_instance_count_protein",   # assembly / multimer composition attributes
    "heteromeric",                             # "
    "A protein or gene NAME is a structured attribute, not a keyword",
]


def test_tool_gotchas_survive():
    descs = _descriptions()
    missing = []
    for tool, phrases in REQUIRED_IN_TOOL.items():
        assert tool in descs, f"tool {tool} is not registered"
        for phrase in phrases:
            if _norm(phrase) not in descs[tool]:
                missing.append(f"{tool}: {phrase!r}")
    assert not missing, (
        "load-bearing text was removed from a tool description "
        "(move it to the instructions block or keep it):\n  " + "\n  ".join(missing)
    )


def test_relocated_guidance_reaches_the_model():
    """Every rule the retired guide used to hold must now be on a tool description.

    The guide was removed because a prompt is delivered only when the client asks for it.
    Anything that mattered had to move to tools/list, which always arrives — this checks
    it actually did, rather than that it survived somewhere no one may read.
    """
    everything = " || ".join(_descriptions().values())
    missing = [p for p in REQUIRED_SOMEWHERE_IN_TOOL_DESCRIPTIONS if _norm(p) not in everything]
    assert not missing, (
        "these rules moved off the retired guide but reached no tool description:\n  "
        + "\n  ".join(missing)
    )


def test_the_unrelocated_gap_is_still_the_gap_we_think_it_is():
    """NOT_RELOCATED records what the retirement dropped. If a phrase turns up on a tool,
    it was relocated after all and belongs in the required list instead — otherwise the
    record drifts into fiction and stops being a usable to-do."""
    everything = " || ".join(_descriptions().values())
    resurfaced = [p for p in NOT_RELOCATED if _norm(p) in everything]
    assert not resurfaced, (
        "these are recorded as NOT relocated but now appear on a tool description; move "
        "them into REQUIRED_SOMEWHERE_IN_TOOL_DESCRIPTIONS:\n  " + "\n  ".join(resurfaced)
    )


def test_no_description_points_at_the_removed_instructions_block():
    """The `instructions` channel is gone; a docstring still citing it sends the agent nowhere.

    Kept as a distinct assertion from the one above because the failure modes differ: that
    one catches guidance deleted from the guide, this one catches a REFERENCE left behind
    when the destination moved.
    """
    stale = sorted(n for n, d in _descriptions().items()
                   if "server instructions" in d or "instructions block" in d)
    assert not stale, (
        "these tool descriptions still cite the removed `instructions` block:\n  "
        + "\n  ".join(stale)
    )


def test_the_server_ships_no_instructions_block():
    """Deliberate: see the comment at the FastMCP() call in server.py.

    Guarded so that re-adding it is a decision someone makes on purpose, rather than a
    plausible-looking one-line 'fix' that silently reintroduces a channel the tool
    descriptions are no longer allowed to depend on.
    """
    assert not getattr(server.mcp, "instructions", None), (
        "server.py passes instructions= again — the guide is delivered as the "
        "rcsb_mcp_guide prompt, which arrives whole or not at all"
    )


# Tool-name prefixes, so a cross-reference can be told apart from an attribute path
# (rcsb_entry_info.*, rcsb_polymer_entity.*, ...) which shares the rcsb_ prefix.
_TOOL_NAME = re.compile(
    r"\brcsb_(?:search|query|get|find|describe|seqcoord|list|render)_[a-z_]+\b"
)


def test_no_description_cites_a_tool_that_is_not_registered():
    """A tool description naming a tool that does not exist sends the agent nowhere.

    This is the failure the rcsb_search_* -> rcsb_query_* rename can cause silently: the
    text still reads sensibly, the named tool just isn't there. Cross-references between
    tool descriptions are the one channel that always resolves, which is exactly why they
    have to actually resolve.
    """
    descs = _descriptions()
    registered = set(descs)
    dangling = []
    for name, desc in descs.items():
        for m in _TOOL_NAME.finditer(desc):
            cited = m.group(0)
            # `rcsb_get_*` and friends are family globs, not names: skip a match whose
            # next character is the wildcard.
            if desc[m.end():m.end() + 1] == "*":
                continue
            if cited not in registered:
                dangling.append(f"{name} cites {cited!r}")
    assert not dangling, (
        "tool descriptions name tools that are not registered:\n  " + "\n  ".join(sorted(dangling))
    )


def test_no_description_contains_a_near_miss_of_a_tool_name():
    """`_TOOL_NAME` only sees tokens that already look like tool names, so the likeliest
    way a reference goes wrong is invisible to it.

    `csb_query_seqmotif` — one dropped letter — shipped in rcsb_search_request's
    return_type table and every test passed, because the pattern requires the `rcsb_`
    prefix that the typo destroyed. `rcsb_qeury_attribute` would escape the same way: the
    family segment is part of the pattern too.

    So this looks for tokens that are CLOSE to a registered name without being one. The
    0.9 cutoff is tight enough that attribute paths (`rcsb_polymer_entity_annotation`) and
    field names do not trip it, which the companion test below pins.
    """
    import difflib
    import re

    descs = _descriptions()
    registered = set(descs)
    suspicious = []
    for name, desc in descs.items():
        for token in set(re.findall(r"\b[a-z][a-z0-9_]{8,}\b", desc)):
            if token in registered or "_" not in token:
                continue
            close = difflib.get_close_matches(token, registered, n=1, cutoff=0.9)
            if close:
                suspicious.append(f"{name}: {token!r} — did you mean {close[0]!r}?")
    assert not suspicious, "near-miss tool references:\n  " + "\n  ".join(suspicious)


def test_the_near_miss_check_does_not_fire_on_attribute_paths():
    """Attribute paths share the `rcsb_` prefix and plenty of substrings with tool names.
    If the cutoff were loose they would all be flagged and the guard would be turned off.
    """
    import difflib

    registered = set(_descriptions())
    for path in ("rcsb_polymer_entity_annotation", "rcsb_entity_source_organism",
                 "rcsb_entry_info", "rcsb_nonpolymer_entity_annotation",
                 "rcsb_polymer_instance_annotation", "rcsb_accession_info"):
        assert not difflib.get_close_matches(path, registered, n=1, cutoff=0.9), (
            f"{path!r} would be flagged as a typo'd tool name"
        )
