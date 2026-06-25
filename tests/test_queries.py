"""Validate query bodies against the RCSB Search API v2 contract (no network)."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp import queries  # noqa: E402


def test_fulltext():
    q = queries.build_fulltext_query("hemoglobin", rows=5)
    assert q["query"]["service"] == "full_text"
    assert q["query"]["parameters"]["value"] == "hemoglobin"
    assert q["return_type"] == "entry"
    assert q["request_options"]["paginate"] == {"start": 0, "rows": 5}
    assert q["request_options"]["results_content_type"] == ["experimental"]
    print("ok: fulltext")


def test_fulltext_with_computed():
    q = queries.build_fulltext_query("kinase", include_computed=True)
    assert q["request_options"]["results_content_type"] == ["experimental", "computational"]
    print("ok: fulltext computed")


def test_attribute():
    q = queries.build_attribute_query(
        "rcsb_entry_info.resolution_combined", "less", 2.0
    )
    p = q["query"]["parameters"]
    assert q["query"]["service"] == "text"
    assert p == {
        "attribute": "rcsb_entry_info.resolution_combined",
        "operator": "less",
        "value": 2.0,
    }
    print("ok: attribute")


def test_sequence():
    q = queries.build_sequence_query("mteyklv", identity_cutoff=0.9)
    p = q["query"]["parameters"]
    assert q["query"]["service"] == "sequence"
    assert p["value"] == "MTEYKLV"  # uppercased + stripped
    assert p["identity_cutoff"] == 0.9
    assert q["return_type"] == "polymer_entity"
    print("ok: sequence")


def test_combined():
    q = queries.build_combined_query(
        full_text="hemoglobin",
        filters=[
            {"attribute": "rcsb_entity_source_organism.ncbi_scientific_name",
             "operator": "exact_match", "value": "Homo sapiens"},
            {"attribute": "rcsb_entry_info.resolution_combined",
             "operator": "less", "value": 2.0},
        ],
        sort_by="rcsb_entry_info.resolution_combined",
    )
    assert q["query"]["type"] == "group"
    assert q["query"]["logical_operator"] == "and"
    assert len(q["query"]["nodes"]) == 3  # full_text + 2 filters
    assert q["query"]["nodes"][0]["service"] == "full_text"
    assert q["request_options"]["sort"] == [
        {"sort_by": "rcsb_entry_info.resolution_combined", "direction": "asc"}
    ]
    print("ok: combined")


def test_combined_single_collapses():
    # A single condition should not be wrapped in a group node.
    q = queries.build_combined_query(full_text="kinase")
    assert q["query"]["type"] == "terminal"
    assert q["query"]["service"] == "full_text"
    print("ok: combined single")


def test_attribute_exists_and_flags():
    # "exists" carries no value; negation/case_sensitive add the right flags.
    q = queries.build_attribute_query(
        "rcsb_nonpolymer_entity.pdbx_description", "exists",
        negation=True, case_sensitive=True,
    )
    p = q["query"]["parameters"]
    assert "value" not in p
    assert p["operator"] == "exists" and p["negation"] is True and p["case_sensitive"] is True
    # a normal operator keeps its value and omits the flags by default.
    p2 = queries.build_attribute_query("a", "equals", 3)["query"]["parameters"]
    assert p2["value"] == 3 and "negation" not in p2 and "case_sensitive" not in p2
    print("ok: attribute exists/flags")


def test_group_by_identity():
    q = queries.build_fulltext_query("kinase", return_type="polymer_entity", group_by_identity=30)
    opts = q["request_options"]
    assert opts["group_by"] == {"aggregation_method": "sequence_identity", "similarity_cutoff": 30}
    assert opts["group_by_return_type"] == "representatives"
    # combined filters accept per-filter negation.
    q2 = queries.build_combined_query(
        filters=[{"attribute": "a", "operator": "exact_match", "value": "x", "negation": True}]
    )
    assert q2["query"]["parameters"]["negation"] is True
    print("ok: group_by identity")


def test_group_by_ranking():
    # ranking_criteria_type picks the cluster representative; direction always emitted.
    q = queries.build_fulltext_query(
        "kinase", return_type="polymer_entity", group_by_identity=30,
        group_by_ranking="rcsb_entry_info.resolution_combined", group_by_ranking_direction="asc",
    )
    assert q["request_options"]["group_by"]["ranking_criteria_type"] == {
        "sort_by": "rcsb_entry_info.resolution_combined", "direction": "asc",
    }
    # "score" is a valid sort_by; default direction is "desc".
    q2 = queries.build_combined_query(full_text="x", group_by_identity=90, group_by_ranking="score")
    assert q2["request_options"]["group_by"]["ranking_criteria_type"] == {
        "sort_by": "score", "direction": "desc",
    }
    # no ranking -> no ranking_criteria_type key (unchanged default behavior).
    q3 = queries.build_attribute_query("a", "exists", group_by_identity=30)
    assert "ranking_criteria_type" not in q3["request_options"]["group_by"]
    # ranking without group_by_identity, and bad direction, both raise.
    for bad in (
        lambda: queries.build_fulltext_query("x", group_by_ranking="score"),
        lambda: queries.build_fulltext_query(
            "x", group_by_identity=30, group_by_ranking="score", group_by_ranking_direction="up"),
    ):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError("expected ValueError")
    print("ok: group_by ranking")


def test_group_by_uniprot():
    q = queries.build_fulltext_query("kinase", return_type="polymer_entity", group_by_uniprot=True)
    assert q["request_options"]["group_by"] == {"aggregation_method": "matching_uniprot_accession"}
    assert q["request_options"]["group_by_return_type"] == "representatives"
    # uniprot grouping honors ranking_criteria_type.
    q2 = queries.build_combined_query(
        full_text="x", group_by_uniprot=True,
        group_by_ranking="rcsb_entry_info.resolution_combined", group_by_ranking_direction="asc",
    )
    assert q2["request_options"]["group_by"]["ranking_criteria_type"] == {
        "sort_by": "rcsb_entry_info.resolution_combined", "direction": "asc",
    }
    # identity + uniprot together is rejected.
    try:
        queries.build_fulltext_query("x", group_by_identity=30, group_by_uniprot=True)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for identity+uniprot")
    # "coverage" ranking: UniProt-only, emitted WITHOUT a direction.
    cov = queries.build_fulltext_query("x", group_by_uniprot=True, group_by_ranking="coverage")
    assert cov["request_options"]["group_by"]["ranking_criteria_type"] == {"sort_by": "coverage"}
    # coverage without group_by_uniprot (e.g. with identity) is rejected.
    try:
        queries.build_fulltext_query("x", group_by_identity=30, group_by_ranking="coverage")
    except ValueError:
        pass
    else:
        raise AssertionError('expected ValueError for coverage without group_by_uniprot')
    print("ok: group_by uniprot")


def test_chemical():
    d = queries.build_chemical_query("c1ccccc1", match_type="sub-struct-graph-relaxed")
    p = d["query"]["parameters"]
    assert d["query"]["service"] == "chemical"
    assert p == {"type": "descriptor", "value": "c1ccccc1",
                 "descriptor_type": "SMILES", "match_type": "sub-struct-graph-relaxed"}
    assert d["return_type"] == "mol_definition"
    assert d["request_options"]["scoring_strategy"] == "chemical"
    f = queries.build_chemical_query("Co4O4", query_type="formula", match_subset=True)
    # element-symbol case is preserved (not upper-cased).
    assert f["query"]["parameters"] == {"type": "formula", "value": "Co4O4", "match_subset": True}
    print("ok: chemical")


def test_structure():
    a = queries.build_structure_query("4hhb", assembly_id="1")
    assert a["query"]["service"] == "structure"
    assert a["query"]["parameters"]["value"] == {"entry_id": "4HHB", "assembly_id": "1"}
    assert a["return_type"] == "assembly"
    c = queries.build_structure_query("4HHB", asym_id="A")
    assert c["query"]["parameters"]["value"] == {"entry_id": "4HHB", "asym_id": "A"}
    assert c["return_type"] == "polymer_instance"
    print("ok: structure")


def test_seqmotif():
    q = queries.build_seqmotif_query("C..H[LIVF]", pattern_type="regex")
    p = q["query"]["parameters"]
    assert q["query"]["service"] == "seqmotif"
    assert p == {"value": "C..H[LIVF]", "pattern_type": "regex", "sequence_type": "protein"}
    assert q["return_type"] == "polymer_entity"
    print("ok: seqmotif")


def test_facet_query():
    q = queries.build_facet_query(
        facets=[
            {"name": "Methods", "aggregation_type": "terms", "attribute": "exptl.method"},
            {"name": "Res", "aggregation_type": "histogram",
             "attribute": "rcsb_entry_info.resolution_combined", "interval": 0.5,
             "min_interval_population": 1},
        ],
        full_text="hemoglobin",
    )
    opts = q["request_options"]
    assert opts["paginate"] == {"start": 0, "rows": 0}  # hits suppressed
    assert q["query"]["service"] == "full_text"
    f = opts["facets"]
    assert f[0] == {"name": "Methods", "aggregation_type": "terms", "attribute": "exptl.method"}
    assert f[1]["interval"] == 0.5 and f[1]["min_interval_population"] == 1
    # match-all when no full_text/filters: the query key is omitted entirely.
    q2 = queries.build_facet_query(
        facets=[{"name": "M", "aggregation_type": "terms", "attribute": "exptl.method"}]
    )
    assert "query" not in q2
    # nested facets are recursively validated/normalized.
    q3 = queries.build_facet_query(
        facets=[{"name": "byMethod", "aggregation_type": "terms", "attribute": "exptl.method",
                 "facets": [{"name": "byYear", "aggregation_type": "date_histogram",
                             "attribute": "rcsb_accession_info.initial_release_date",
                             "interval": "year"}]}]
    )
    assert q3["request_options"]["facets"][0]["facets"][0]["aggregation_type"] == "date_histogram"
    print("ok: facet query")


def test_count_query():
    q = queries.build_count_query(full_text="hemoglobin")
    assert q["request_options"]["return_counts"] is True
    assert "paginate" not in q["request_options"]
    assert q["query"]["service"] == "full_text"
    # match-all count omits the query key.
    q2 = queries.build_count_query()
    assert "query" not in q2 and q2["request_options"]["return_counts"] is True
    print("ok: count query")


def test_strucmotif():
    q = queries.build_strucmotif_query(
        "2mnr",
        residue_ids=[
            {"label_asym_id": "A", "label_seq_id": 162},
            {"label_asym_id": "A", "label_seq_id": 193},
            {"label_asym_id": "A", "label_seq_id": 219, "struct_oper_id": "1"},
        ],
        rmsd_cutoff=1.5,
    )
    p = q["query"]["parameters"]
    assert q["query"]["service"] == "strucmotif"
    assert p["value"]["entry_id"] == "2MNR"  # upper-cased
    assert len(p["value"]["residue_ids"]) == 3
    assert p["value"]["residue_ids"][2]["struct_oper_id"] == "1"
    assert p["rmsd_cutoff"] == 1.5
    assert p["atom_pairing_scheme"] == "SIDE_CHAIN" and p["motif_pruning_strategy"] == "KRUSKAL"
    assert q["return_type"] == "polymer_entity"
    assert q["request_options"]["scoring_strategy"] == "strucmotif"
    print("ok: strucmotif")


def test_chemical_attribute_service():
    # chemical=True switches the attribute terminal to the text_chem service.
    q = queries.build_attribute_query(
        "chem_comp.formula_weight", "less", 300, chemical=True, return_type="mol_definition"
    )
    assert q["query"]["service"] == "text_chem"
    assert q["return_type"] == "mol_definition"
    # structure attributes keep the default "text" service.
    assert queries.build_attribute_query("a", "equals", 1)["query"]["service"] == "text"
    # in a combined query, filters use text_chem but the full-text term stays full_text.
    c = queries.build_combined_query(
        full_text="aspirin",
        filters=[{"attribute": "chem_comp.formula_weight", "operator": "less", "value": 300}],
        chemical=True,
    )
    assert c["query"]["nodes"][0]["service"] == "full_text"
    assert c["query"]["nodes"][1]["service"] == "text_chem"
    print("ok: chemical text_chem service")


def test_validation_errors():
    for bad in (
        lambda: queries.build_fulltext_query("x", return_type="bogus"),
        lambda: queries.build_attribute_query("a", "bogus_op", 1),
        lambda: queries.build_sequence_query("x", identity_cutoff=5),
        lambda: queries.build_sequence_query("x", sequence_type="zzz"),
        lambda: queries.build_combined_query(),  # no conditions
        lambda: queries.build_combined_query(full_text="x", logical_operator="xor"),
        lambda: queries.build_combined_query(
            filters=[{"attribute": "a", "operator": "bogus", "value": 1}]
        ),
        lambda: queries.build_data_query("entries", []),  # empty id list
        lambda: queries.build_data_query("polymer_entities", ["", "  "]),  # all blank
        lambda: queries.build_data_query("bogus_object", ["X"]),  # unknown object
        lambda: queries.build_data_query("uniprot", "  "),  # blank single id
        lambda: queries.build_fulltext_query("x", group_by_identity=42),  # bad cutoff
        lambda: queries.build_chemical_query("c1ccccc1", match_type="bogus"),  # bad match
        lambda: queries.build_chemical_query("x", descriptor_type="MOL"),  # bad desc type
        lambda: queries.build_chemical_query("x", query_type="bogus"),  # bad query type
        lambda: queries.build_structure_query("4HHB", assembly_id="1", asym_id="A"),  # both
        lambda: queries.build_seqmotif_query("X", pattern_type="bogus"),  # bad pattern
        lambda: queries.build_facet_query(facets=[]),  # no facets
        lambda: queries.build_facet_query(
            facets=[{"name": "x", "aggregation_type": "bogus", "attribute": "a"}]
        ),  # bad aggregation_type
        lambda: queries.build_facet_query(
            facets=[{"name": "x", "aggregation_type": "histogram", "attribute": "a"}]
        ),  # histogram missing interval
        lambda: queries.build_facet_query(
            facets=[{"name": "x", "aggregation_type": "range", "attribute": "a"}]
        ),  # range missing ranges
        lambda: queries.build_facet_query(
            facets=[{"aggregation_type": "terms", "attribute": "a"}]
        ),  # missing name
        lambda: queries.build_count_query(return_type="bogus"),  # bad return_type
        lambda: queries.build_strucmotif_query(
            "2MNR", [{"label_asym_id": "A", "label_seq_id": 1}]
        ),  # only one residue
        lambda: queries.build_strucmotif_query(
            "2MNR", [{"label_asym_id": "A", "label_seq_id": i} for i in range(11)]
        ),  # too many residues
        lambda: queries.build_strucmotif_query(
            "2MNR",
            [{"label_asym_id": "A", "label_seq_id": 1}, {"label_asym_id": "A", "label_seq_id": 2}],
            atom_pairing_scheme="BOGUS",
        ),  # bad enum
        lambda: queries.build_strucmotif_query(
            "2MNR",
            [{"label_asym_id": "A", "label_seq_id": 1}, {"label_asym_id": "A", "label_seq_id": 2}],
            backbone_distance_tolerance=9,
        ),  # tolerance out of range
        lambda: queries.build_strucmotif_query(
            "2MNR", [{"label_asym_id": "A"}, {"label_asym_id": "A", "label_seq_id": 2}]
        ),  # residue missing label_seq_id
    ):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError("expected ValueError")
    print("ok: validation")


def test_graphql_batch():
    body = queries.build_data_query("entries", ["4hhb", " 1mbn "])
    assert "entries(entry_ids: $ids)" in body["query"]
    assert "query Q($ids: [String!]!)" in body["query"]
    # ids ride in variables (no inlining), stripped and upper-cased.
    assert body["variables"] == {"ids": ["4HHB", "1MBN"]}
    # a single id is accepted as a scalar and wrapped into the list.
    assert queries.build_data_query("chem_comps", "hem")["variables"] == {"ids": ["HEM"]}
    print("ok: graphql batch")


def test_graphql_single():
    body = queries.build_data_query("uniprot", "p69905")
    assert "uniprot(uniprot_id: $ids)" in body["query"]
    assert "query Q($ids: String!)" in body["query"]
    assert body["variables"] == {"ids": "P69905"}
    # pubmed takes an Int id (coerced, not upper-cased).
    pm = queries.build_data_query("pubmed", "6726807")
    assert "query Q($ids: Int!)" in pm["query"]
    assert pm["variables"] == {"ids": 6726807}
    # opaque group/provenance tokens are case-sensitive: case is preserved.
    gp = queries.build_data_query("group_provenance", "provenance_sequence_identity")
    assert gp["variables"] == {"ids": "provenance_sequence_identity"}
    grp = queries.build_data_query("entry_groups", ["Foo_1"])
    assert grp["variables"] == {"ids": ["Foo_1"]}
    print("ok: graphql single")


def test_graphql_fields_override():
    body = queries.build_data_query("entries", ["4HHB"], fields="rcsb_id struct{title}")
    assert "{ rcsb_id struct{title} }" in body["query"]
    assert "resolution_combined" not in body["query"]  # default not used
    print("ok: graphql fields override")


def test_graphql_registry():
    # Every endpoint maps to a usable builder with a non-empty default selection.
    assert len(queries.DATA_OBJECTS) == 18
    batch = [k for k, s in queries.DATA_OBJECTS.items() if s.batch]
    single = [k for k, s in queries.DATA_OBJECTS.items() if not s.batch]
    assert len(batch) == 15 and len(single) == 3
    assert set(single) == {"uniprot", "pubmed", "group_provenance"}
    for key, spec in queries.DATA_OBJECTS.items():
        assert spec.default_fields.startswith("rcsb_id"), key
        assert spec.arg_type in {"String", "Int"}, key
        sample = "1" if spec.arg_type == "Int" else "X"
        ids = sample if not spec.batch else [sample]
        body = queries.build_data_query(key, ids)
        assert f"{spec.root_field}({spec.arg}: $ids)" in body["query"], key
    print("ok: graphql registry (18 endpoints)")


def test_seqcoord_alignments():
    body = queries.build_sc_alignments_query("p69905", "UNIPROT", "PDB_ENTITY", seq_range=[1, 50])
    assert "alignments(from: $from, to: $to, queryId: $queryId, range: $range)" in body["query"]
    assert "target_alignments{" in body["query"]
    assert body["variables"] == {
        "from": "UNIPROT", "to": "PDB_ENTITY", "queryId": "p69905", "range": [1, 50],
    }
    print("ok: seqcoord alignments")


def test_seqcoord_annotations():
    body = queries.build_sc_annotations_query("4HHB_1", "PDB_ENTITY", ["UNIPROT", "PDB_ENTITY"])
    assert "annotations(queryId: $queryId, reference: $reference, sources: $sources" in body["query"]
    v = body["variables"]
    assert v["queryId"] == "4HHB_1" and v["reference"] == "PDB_ENTITY"
    assert v["sources"] == ["UNIPROT", "PDB_ENTITY"] and v["range"] is None
    print("ok: seqcoord annotations")


def test_seqcoord_groups():
    a = queries.build_sc_group_alignments_query("MATCHING_UNIPROT_ACCESSION", "P69905")
    assert "group_alignments(group: $group, groupId: $groupId, filter: $filter)" in a["query"]
    # the summary flag swaps the root field name.
    g = queries.build_sc_group_annotations_query("SEQUENCE_IDENTITY", "X", ["UNIPROT"])
    assert "group_annotations(" in g["query"] and "summary" not in g["query"]
    s = queries.build_sc_group_annotations_query(
        "SEQUENCE_IDENTITY", "X", ["UNIPROT"], summary=True
    )
    assert "group_annotations_summary(" in s["query"]
    print("ok: seqcoord groups")


def test_seqcoord_validation():
    for bad in (
        lambda: queries.build_sc_alignments_query("P1", "BOGUS", "UNIPROT"),
        lambda: queries.build_sc_alignments_query("", "UNIPROT", "PDB_ENTITY"),
        lambda: queries.build_sc_annotations_query("X", "UNIPROT", []),  # no sources
        lambda: queries.build_sc_annotations_query("X", "UNIPROT", ["BOGUS"]),  # bad source
        lambda: queries.build_sc_alignments_query("P1", "UNIPROT", "UNIPROT", seq_range=["a"]),
        lambda: queries.build_sc_group_alignments_query("BOGUS", "X"),
        lambda: queries.build_sc_group_annotations_query("SEQUENCE_IDENTITY", "X", ["NOPE"]),
    ):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError("expected ValueError")
    print("ok: seqcoord validation")


if __name__ == "__main__":
    test_fulltext()
    test_fulltext_with_computed()
    test_attribute()
    test_sequence()
    test_combined()
    test_combined_single_collapses()
    test_attribute_exists_and_flags()
    test_group_by_identity()
    test_group_by_ranking()
    test_group_by_uniprot()
    test_chemical()
    test_structure()
    test_seqmotif()
    test_facet_query()
    test_count_query()
    test_strucmotif()
    test_chemical_attribute_service()
    test_validation_errors()
    test_graphql_batch()
    test_graphql_single()
    test_graphql_fields_override()
    test_graphql_registry()
    test_seqcoord_alignments()
    test_seqcoord_annotations()
    test_seqcoord_groups()
    test_seqcoord_validation()
    print("\nAll query-builder tests passed.")
