"""SIGNATURE-ONLY prototype of the unified `rcsb_search` tool (shape C).

Exists to measure two things before committing to the 7 -> 1 merge:
  * what pydantic actually emits as the inputSchema, vs the 5,938 tok the seven
    rcsb_search_* schemas cost today;
  * how big the ONE docstring has to be, given it replaces 5,027 tok of prose and
    absorbs the guide sections that no longer arrive via `instructions`.

The body is deliberately unimplemented. The plan is DELEGATION: dispatch on the
discriminator to the existing module-level rcsb_search_* functions in search.py,
which stay tested and untouched. That is also what preserves the per-service
`return_type` defaults (entry / polymer_entity / assembly / mol_definition) — omit
return_type here and the delegate's own default applies, so the four defaults one
schema field cannot express keep living where they already live.

Shape C = a discriminated union on `search_type`. The alternative (a `search_type`
enum beside one optional sub-model per modality) cannot express which params go with
which mode, so `search_type="chemical"` alongside `sequence={...}` would be a runtime
error someone has to write. Measured cost of the constraint: ~65 tok.

Nothing here is registered. Import it, hand it to a throwaway FastMCP, measure.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

from rcsb_mcp.search import AttributeFilter


# --------------------------------------------------------------------------- #
# Per-modality payloads. Field types/defaults/bounds mirror the current
# rcsb_search_* signatures exactly, so the measurement is honest.
# --------------------------------------------------------------------------- #
class FulltextSearch(BaseModel):
    search_type: Literal["fulltext"]
    query: str
    chemical: bool = False
    include_computed_models: bool = False


class AttributeSearch(BaseModel):
    # No payload of its own beyond `chemical`: attribute search is the BASE case, driven
    # by the shared `attributes` filter list. Kept as a named variant anyway so
    # search_type is always explicit rather than implied by omission.
    search_type: Literal["attribute"]
    chemical: bool = False


class SequenceSearch(BaseModel):
    search_type: Literal["sequence"]
    sequence: str
    sequence_type: Literal["protein", "dna", "rna"] = "protein"
    identity_cutoff: Annotated[float, Field(ge=0.0, le=1.0)] = 0.3
    evalue_cutoff: Annotated[float, Field(ge=0.0)] = 1.0


class SeqmotifSearch(BaseModel):
    search_type: Literal["seqmotif"]
    pattern: str
    pattern_type: Literal["simple", "prosite", "regex"] = "prosite"
    sequence_type: Literal["protein", "dna", "rna"] = "protein"


class StructureSearch(BaseModel):
    search_type: Literal["structure"]
    entry_id: str
    assembly_id: str | None = None
    asym_id: str | None = None


class StrucmotifSearch(BaseModel):
    search_type: Literal["strucmotif"]
    entry_id: str
    residue_ids: list[dict[str, Any]]
    backbone_distance_tolerance: Annotated[int, Field(ge=0, le=3)] = 1
    side_chain_distance_tolerance: Annotated[int, Field(ge=0, le=3)] = 1
    angle_tolerance: Annotated[int, Field(ge=0, le=3)] = 1
    rmsd_cutoff: Annotated[float, Field(ge=0.0)] = 2.0
    atom_pairing_scheme: Literal["ALL", "BACKBONE", "SIDE_CHAIN", "PSEUDO_ATOMS"] = "SIDE_CHAIN"
    motif_pruning_strategy: Literal["NONE", "KRUSKAL"] = "KRUSKAL"


class ChemicalSearch(BaseModel):
    search_type: Literal["chemical"]
    value: str
    query_type: Literal["descriptor", "formula"] = "descriptor"
    descriptor_type: Literal["SMILES", "InChI"] = "SMILES"
    match_type: Literal[
        "graph-exact", "graph-strict", "graph-relaxed", "graph-relaxed-stereo",
        "fingerprint-similarity", "sub-struct-graph-exact", "sub-struct-graph-strict",
        "sub-struct-graph-relaxed", "sub-struct-graph-relaxed-stereo",
    ] = "graph-relaxed"
    match_subset: bool = False


SearchSpec = Annotated[
    Union[
        FulltextSearch, AttributeSearch, SequenceSearch, SeqmotifSearch,
        StructureSearch, StrucmotifSearch, ChemicalSearch,
    ],
    Field(discriminator="search_type"),
]

ReturnType = Literal[
    "entry", "polymer_entity", "non_polymer_entity", "polymer_instance", "assembly",
    "mol_definition",
]
GroupBy = Literal["seqid_30", "seqid_50", "seqid_70", "seqid_90", "seqid_95", "uniprot"]
GroupByRanking = Literal["resolution", "released_date", "entity_residue_count", "score", "coverage"]


async def rcsb_search(
    search: SearchSpec,
    attributes: list[AttributeFilter] | None = None,
    logical_operator: Literal["and", "or"] = "and",
    return_type: ReturnType | None = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 10,
    offset: Annotated[int, Field(ge=0)] = 0,
    all_hits: bool = False,
    sort_by: str | None = None,
    sort_direction: Literal["asc", "desc"] = "asc",
    facets: list[dict[str, Any]] | None = None,
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
) -> dict[str, Any]:
    """Find PDB identifiers, selecting search_type: fulltext (keyword), attribute,
    sequence, seqmotif (sequence pattern), structure (3D shape), strucmotif (3D residue
    geometry), chemical.

    [DRAFT IN PROGRESS — one section at a time. Settled so far: the opening line above.
    Still to write: the routing block (which search_type to pick), the per-variant Args,
    and the guide sections that must be inlined here because `instructions` is gone
    (faceting, grouping, assembly composition, return-type semantics).]

    Args:
        search: The search to run — pick the variant matching what you have.
        attributes: Structured conditions ANDed/ORed with the search.
        logical_operator: How to combine `attributes` with each other and the search.
        return_type: What kind of identifier to return. Omit to get the natural default
            for this search_type.
        limit: Hits per page.
        offset: Page offset.
        all_hits: Return every match instead of one page.
        sort_by: Sortable attribute path.
        sort_direction: Sort order.
        facets: Aggregate into buckets instead of returning hits.
        group_by: De-duplicate into clusters.
        group_by_ranking: Which cluster member represents the group.

    Returns:
        {total_count, hits|facets, ...} — same shape the rcsb_search_* tools return.
    """
    raise NotImplementedError("signature-only prototype; delegate to search.rcsb_search_*")
