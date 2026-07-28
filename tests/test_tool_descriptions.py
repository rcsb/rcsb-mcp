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
    "rcsb_search_fulltext": [
        "text-relevance, NOT biological importance",   # score is not quality
        "SORTABLE attributes",                          # sort_by only works on some paths
        "refused above 10000",                          # all_hits cap
        "AND/OR/NOT are NOT boolean",                   # query-string gotcha
    ],
    "rcsb_search_by_attribute": [
        "an empty result is a valid answer",            # don't fall back to keyword search
        "carries NO biological meaning",                # score caveat (attribute form)
        "EXCLUSIVE",                                     # range bound semantics
        "NESTED boolean groups are not supported",
    ],
    "rcsb_search_by_sequence": [
        "4HHB_1",                                        # returned id shape
        'return_type="mol_definition" are rejected',     # sort_by limitation
    ],
    "rcsb_search_by_chemical": [
        "fingerprint-similarity",                        # match_type option
        "sub-struct-graph",                              # substructure option
        "merely contain the",                            # match_subset semantics
    ],
    "rcsb_search_by_structure": [
        "mutually exclusive",                            # assembly_id vs asym_id
        "Defaults to assembly",
    ],
    "rcsb_search_by_seqmotif": [
        "prosite",
        "simple wildcards",
    ],
    "rcsb_search_strucmotif": [
        "mmCIF",                                         # label-vs-author id explanation
        "author numbers give wrong/no hits",
        "catalytic triads",                              # when-to-use routing
        "PSEUDO_ATOMS",                                  # atom_pairing_scheme option
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
        "rcsb_search_by_sequence",                       # id source hint
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

# Shared guidance the docstrings now DELEGATE to via "see the server instructions" —
# must survive in the always-on instructions block, or those pointers dangle.
REQUIRED_IN_INSTRUCTIONS = [
    "rcsb_find_disease_terms",                          # ontology resolver routing ...
    "rcsb_find_go_terms",
    "rcsb_find_interpro_domains",
    "rcsb_find_enzyme_classes",
    "rcsb_find_organisms",
    # The rcsb_find_* docstrings now DELEGATE the search-by-resolved-id recipe here, so the
    # instructions block is the SOLE home of these attribute paths. Trim them and the resolvers
    # silently lose the only documented way to use their output.
    "rcsb_polymer_entity_annotation.annotation_lineage.id",   # GO (term + descendants)
    'annotation_id exact_match "GO:..."',                     # GO exact-term-only path
    "rcsb_polymer_entity_annotation.annotation_id",           # InterPro (NOT lineage)
    "rcsb_polymer_entity.rcsb_ec_lineage.id",                 # EC (hierarchical)
    "rcsb_uniprot_annotation.annotation_lineage.id",          # MONDO (UniProt-derived)
    "rcsb_entity_source_organism.taxonomy_lineage.id",        # NCBI taxonomy
    'pass the id as a STRING ("9606", not 9606)',             # taxon id-typing gotcha
    "Return types",                                     # return-types + fetching note
    "polymer_entity_instance_count_protein",            # assembly / multimer attr paths
    "heteromeric",
    "group_by",                                         # grouping note
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


def test_shared_guidance_survives_in_instructions():
    instr = _norm(getattr(server.mcp, "instructions", ""))
    assert instr, "server has no instructions block"
    missing = [p for p in REQUIRED_IN_INSTRUCTIONS if _norm(p) not in instr]
    assert not missing, (
        "docstrings point to the server instructions for these, but they are missing "
        "there:\n  " + "\n  ".join(missing)
    )
