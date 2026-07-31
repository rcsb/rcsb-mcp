"""Declarative search cases, and the composer pipeline that renders them.

`tests/fixtures/query_bodies_baseline.json` holds the Search API body each case must
produce. Those bodies were generated BEFORE the composer refactor, from the flat
build_*_query entry points, and committed -- so the fixture is a frozen record of
pre-refactor behaviour that the current code has to keep reproducing. The flat builders
themselves are gone; the fixture is what outlived them.

Each case describes a search in the composer's own terms: a QUERY half (one service
node, or a group of nodes joined by and/or) and a CONFIG half (the result-shaping
envelope). `body_via_pipeline` walks that exactly as the tool chain does -- one node per
rcsb_query_* builder, groups joined by rcsb_query_composer, the envelope applied once by
rcsb_search_request.

Deliberately NOT in the fixture: genuinely nested groups -- (A OR B) AND (C OR D) -- and
multi-service combinations. The flat builders could not express either, so there was no
prior behaviour to freeze. Those are new capability, covered in test_query_compose.py and
test_query_tools.py against the Search API contract.

Regenerating REWRITES the record of pre-refactor behaviour with whatever the tree does
today, which is the one thing this file exists to prevent. Do it only to bless a change
you have reviewed body-by-body in the diff:
    python tests/query_cases.py
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp import queries  # noqa: E402

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "query_bodies_baseline.json"

# A protein fragment long enough to be a realistic sequence-search payload.
SEQ = "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSHGSAQVKGHGKKVADALTNAVAHVDDMPNAL"

# Attribute conditions reused across cases (the shapes AttributeFilter emits).
HUMAN = {"attribute": "rcsb_entity_source_organism.ncbi_scientific_name",
         "operator": "exact_match", "value": "Homo sapiens"}
XRAY = {"attribute": "exptl.method", "operator": "exact_match", "value": "X-RAY DIFFRACTION"}
HIRES = {"attribute": "rcsb_entry_info.resolution_combined", "operator": "less", "value": 2.0}


def _q(kind: str, **payload: Any) -> dict[str, Any]:
    return {"kind": kind, **payload}


def _group(op: str, *nodes: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "group", "logical_operator": op, "nodes": list(nodes)}


# --------------------------------------------------------------------------- #
# The cases. `config` carries only what the case exercises; defaults elsewhere.
# --------------------------------------------------------------------------- #
CASES: list[dict[str, Any]] = [
    # --- full-text ---------------------------------------------------------
    {"name": "fulltext-plain",
     "query": _q("fulltext", value="CRISPR Cas9"), "config": {"limit": 5}},
    {"name": "fulltext-phrase-and-computed-models",
     "query": _q("fulltext", value='"DNA polymerase"'),
     "config": {"include_computed_models": True}},
    {"name": "fulltext-with-attributes",
     "query": _group("and", _q("fulltext", value="hemoglobin"), _q("attribute", attributes=[HIRES])),
     "config": {}},

    # --- attribute ---------------------------------------------------------
    {"name": "attribute-single-numeric",
     "query": _q("attribute", attributes=[HIRES]), "config": {}},
    {"name": "attribute-multi-and",
     "query": _q("attribute", attributes=[HUMAN, XRAY, HIRES]), "config": {}},
    {"name": "attribute-multi-or",
     "query": _q("attribute", attributes=[HUMAN, XRAY], logical_operator="or"), "config": {}},
    {"name": "attribute-exists",
     "query": _q("attribute", attributes=[
         {"attribute": "rcsb_nonpolymer_entity.pdbx_description", "operator": "exists"}]),
     "config": {}},
    {"name": "attribute-negation-and-case-sensitive",
     "query": _q("attribute", attributes=[
         {**HUMAN, "negation": True, "case_sensitive": True}]),
     "config": {}},
    {"name": "attribute-range",
     "query": _q("attribute", attributes=[{
         "attribute": "rcsb_entry_info.resolution_combined", "operator": "range",
         "value": {"from": 1.5, "to": 2.5, "include_lower": True, "include_upper": False}}]),
     "config": {}},
    {"name": "attribute-in-list",
     "query": _q("attribute", attributes=[{
         "attribute": "exptl.method", "operator": "in",
         "value": ["X-RAY DIFFRACTION", "ELECTRON MICROSCOPY"]}]),
     "config": {}},
    {"name": "attribute-numeric-string-coercion",
     "query": _q("attribute", attributes=[{
         "attribute": "rcsb_entry_info.resolution_combined", "operator": "less", "value": "2.0"}]),
     "config": {}},
    {"name": "attribute-date",
     "query": _q("attribute", attributes=[{
         "attribute": "rcsb_accession_info.initial_release_date", "operator": "greater",
         "value": "2024-01-01T00:00:00Z"}]),
     "config": {}},
    {"name": "attribute-chemical-namespace",
     "query": _q("attribute", attributes=[{
         "attribute": "chem_comp.formula_weight", "operator": "greater", "value": 300}],
         chemical_attributes=True),
     "config": {"return_type": "mol_definition"}},

    # --- sequence ----------------------------------------------------------
    {"name": "sequence-protein-defaults",
     "query": _q("sequence", sequence=SEQ), "config": {}},
    {"name": "sequence-strict-cutoffs",
     "query": _q("sequence", sequence=SEQ, identity_cutoff=0.9, evalue_cutoff=0.001),
     "config": {"return_type": "polymer_entity", "limit": 25}},
    {"name": "sequence-with-attributes",
     "query": _group("and", _q("sequence", sequence=SEQ), _q("attribute", attributes=[HIRES])),
     "config": {}},

    # --- chemical ----------------------------------------------------------
    {"name": "chemical-smiles-descriptor",
     "query": _q("chemical", value="CC(=O)Oc1ccccc1C(=O)O", query_type="descriptor",
                 descriptor_type="SMILES", match_type="graph-relaxed"),
     "config": {}},
    {"name": "chemical-inchi-substructure",
     "query": _q("chemical", value="InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3",
                 query_type="descriptor", descriptor_type="InChI",
                 match_type="sub-struct-graph-relaxed"),
     "config": {}},
    {"name": "chemical-formula",
     "query": _q("chemical", value="C9H8O4", query_type="formula", match_subset=True),
     "config": {}},

    # --- structure (3D shape) ---------------------------------------------
    {"name": "structure-assembly",
     "query": _q("structure", entry_id="4HHB", assembly_id="1"), "config": {}},
    {"name": "structure-chain",
     "query": _q("structure", entry_id="4HHB", asym_id="A"),
     "config": {"return_type": "polymer_instance"}},

    # --- sequence motif ----------------------------------------------------
    {"name": "seqmotif-prosite",
     "query": _q("seqmotif", pattern="C-x(2,4)-C-x(3)-[LIVMFYWC]", pattern_type="prosite"),
     "config": {}},
    {"name": "seqmotif-regex-dna",
     "query": _q("seqmotif", pattern="TATA[AT]A", pattern_type="regex", sequence_type="dna"),
     "config": {}},
    {"name": "seqmotif-simple",
     "query": _q("seqmotif", pattern="CXCXXL", pattern_type="simple"), "config": {}},

    # --- structure motif (residue geometry) -------------------------------
    {"name": "strucmotif-catalytic-triad",
     "query": _q("strucmotif", entry_id="2MNR", residue_ids=[
         {"label_asym_id": "A", "label_seq_id": 162},
         {"label_asym_id": "A", "label_seq_id": 193},
         {"label_asym_id": "A", "label_seq_id": 219}]),
     "config": {}},
    {"name": "strucmotif-loose-tolerances",
     "query": _q("strucmotif", entry_id="2MNR", residue_ids=[
         {"label_asym_id": "A", "label_seq_id": 162},
         {"label_asym_id": "A", "label_seq_id": 193}],
         backbone_distance_tolerance=3, side_chain_distance_tolerance=2,
         angle_tolerance=2, rmsd_cutoff=3.0, atom_pairing_scheme="ALL",
         motif_pruning_strategy="NONE"),
     "config": {}},

    # --- envelope (config half) -------------------------------------------
    {"name": "config-paging-offset",
     "query": _q("attribute", attributes=[HIRES]), "config": {"limit": 50, "offset": 100}},
    {"name": "config-all-hits",
     "query": _q("attribute", attributes=[HUMAN]), "config": {"all_hits": True}},
    {"name": "config-sort-desc",
     "query": _q("attribute", attributes=[XRAY]),
     "config": {"sort_by": "rcsb_accession_info.initial_release_date",
                "sort_direction": "desc"}},
    {"name": "config-sort-asc-on-fulltext",
     "query": _q("fulltext", value="kinase"),
     "config": {"sort_by": "rcsb_entry_info.resolution_combined", "sort_direction": "asc"}},
    {"name": "config-group-by-identity",
     "query": _q("attribute", attributes=[HUMAN]),
     "config": {"return_type": "polymer_entity", "group_by": "seqid_95"}},
    {"name": "config-group-by-ranking",
     "query": _q("attribute", attributes=[HUMAN]),
     "config": {"return_type": "polymer_entity", "group_by": "seqid_30",
                "group_by_ranking": "resolution"}},
    {"name": "config-group-by-uniprot",
     "query": _q("attribute", attributes=[HUMAN]),
     "config": {"return_type": "polymer_entity", "group_by": "uniprot",
                "group_by_ranking": "released_date"}},
    # `coverage` is the odd one out: UniProt-only, and its ranking_criteria_type carries
    # no `direction` (the API rejects the extra key). Pin that branch.
    {"name": "config-group-by-uniprot-coverage",
     "query": _q("attribute", attributes=[HUMAN]),
     "config": {"return_type": "polymer_entity", "group_by": "uniprot",
                "group_by_ranking": "coverage"}},
    {"name": "config-facets",
     "query": _q("attribute", attributes=[HUMAN]),
     "config": {"facets": [{"name": "by_method", "aggregation_type": "terms",
                            "attribute": "exptl.method"}]}},
    {"name": "config-facets-on-fulltext",
     "query": _q("fulltext", value="ribosome"),
     "config": {"facets": [{"name": "by_year", "aggregation_type": "date_histogram",
                            "attribute": "rcsb_accession_info.initial_release_date",
                            "interval": "year"}]}},
    {"name": "config-computed-models-on-sequence",
     "query": _q("sequence", sequence=SEQ), "config": {"include_computed_models": True}},
]


# --------------------------------------------------------------------------- #
# Adapter: case -> rcsb_query_* -> rcsb_query_composer -> rcsb_search_request
#
# This walks the case's query tree exactly as the tool chain will: one node per
# builder call, groups joined by the composer, the envelope applied once at the end.
# It deliberately does NOT reuse _flatten -- reproducing the baseline through the
# same shortcut the old builders took would prove nothing.
# --------------------------------------------------------------------------- #
_NODE_BUILDERS = {
    "fulltext": lambda p: queries.fulltext_node(p["value"]),
    "attribute": lambda p: queries.attribute_node(
        p["attributes"], p.get("logical_operator", "and"),
        chemical=p.get("chemical_attributes", False)),
    "sequence": lambda p: queries.sequence_node(**p),
    "chemical": lambda p: queries.chemical_node(**p),
    "structure": lambda p: queries.structure_node(**p),
    "seqmotif": lambda p: queries.seqmotif_node(**p),
    "strucmotif": lambda p: queries.strucmotif_node(**p),
}


def _node_via_pipeline(query: dict[str, Any]) -> dict[str, Any]:
    """Render one query-half node the way the tool chain would."""
    kind = query["kind"]
    if kind == "group":
        return queries.group_node(
            [_node_via_pipeline(n) for n in query["nodes"]], query["logical_operator"]
        )
    payload = {k: v for k, v in query.items() if k != "kind"}
    return _NODE_BUILDERS[kind](payload)


def body_via_pipeline(case: dict[str, Any]) -> dict[str, Any]:
    """Render a case through the composer pipeline."""
    cfg = case["config"]
    return queries.build_search_request(
        _node_via_pipeline(case["query"]),
        return_type=cfg.get("return_type"),
        rows=cfg.get("limit", 10),
        start=cfg.get("offset", 0),
        all_hits=cfg.get("all_hits", False),
        include_computed=cfg.get("include_computed_models", False),
        sort_by=cfg.get("sort_by"),
        sort_direction=cfg.get("sort_direction", "asc"),
        group_by=cfg.get("group_by"),
        group_by_ranking=cfg.get("group_by_ranking"),
        facets=cfg.get("facets"),
    )


def load_baseline() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())


def _regenerate() -> None:
    names = [c["name"] for c in CASES]
    assert len(names) == len(set(names)), "case names must be unique"
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    bodies = {c["name"]: body_via_pipeline(c) for c in CASES}
    FIXTURE.write_text(json.dumps(bodies, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(bodies)} bodies to {FIXTURE}")


if __name__ == "__main__":
    _regenerate()
