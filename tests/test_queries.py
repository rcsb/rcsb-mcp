"""Validate query bodies against the RCSB Search API v2 contract (no network).

Everything here drives the composer API — node builders plus build_search_request —
which is what the rcsb_query_* / rcsb_search_request tools call. The pre-composer
build_*_query entry points these tests used to exercise are gone; the assertions are
unchanged, because the bodies they produce are identical (proved case-by-case in
tests/test_query_baseline.py against a fixture frozen before the refactor).
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp import queries  # noqa: E402


# Thin adapters keeping the single-condition tests readable. `**kw` is the result-shaping
# envelope, passed straight to build_search_request under its own parameter names.
def _request(node, **kw):
    return queries.build_search_request(node, **kw)


def _ft(value, **kw):
    return _request(queries.fulltext_node(value), **kw)


def _attr(attribute, operator, value=None, *, negation=False, case_sensitive=False,
          chemical=False, **kw):
    f = {"attribute": attribute, "operator": operator}
    if operator != "exists":
        f["value"] = value
    if negation:
        f["negation"] = True
    if case_sensitive:
        f["case_sensitive"] = True
    return _request(queries.attribute_node([f], chemical=chemical), **kw)


def _and(*nodes, **kw):
    """A group of nodes joined by AND, then executed — the composer path."""
    return _request(queries.group_node(list(nodes), "and"), **kw)


def test_fulltext():
    q = _ft("hemoglobin", rows=5)
    assert q["query"]["service"] == "full_text"
    assert q["query"]["parameters"]["value"] == "hemoglobin"
    assert q["return_type"] == "entry"
    assert q["request_options"]["paginate"] == {"start": 0, "rows": 5}
    assert q["request_options"]["results_content_type"] == ["experimental"]
    print("ok: fulltext")


def test_fulltext_with_computed():
    q = _ft("kinase", include_computed=True)
    assert q["request_options"]["results_content_type"] == ["experimental", "computational"]
    print("ok: fulltext computed")


def test_attribute():
    q = _attr("rcsb_entry_info.resolution_combined", "less", 2.0)
    p = q["query"]["parameters"]
    assert q["query"]["service"] == "text"
    assert p == {
        "attribute": "rcsb_entry_info.resolution_combined",
        "operator": "less",
        "value": 2.0,
    }
    print("ok: attribute")


def test_sequence():
    q = _request(queries.sequence_node("mteyklv", identity_cutoff=0.9))
    p = q["query"]["parameters"]
    assert q["query"]["service"] == "sequence"
    assert p["value"] == "MTEYKLV"  # uppercased + stripped
    assert p["identity_cutoff"] == 0.9
    assert q["return_type"] == "polymer_entity"
    # sequence search projects onto any return_type (no polymer_entity-only limit)
    e = _request(queries.sequence_node("mteyklv"), return_type="entry")
    assert e["return_type"] == "entry"
    assert e["request_options"]["scoring_strategy"] == "sequence"
    try:
        _request(queries.sequence_node("mteyklv"), return_type="bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for bad return_type")
    print("ok: sequence")


def test_combined():
    q = _and(
        queries.fulltext_node("hemoglobin"),
        queries.attribute_node([
            {"attribute": "rcsb_entity_source_organism.ncbi_scientific_name",
             "operator": "exact_match", "value": "Homo sapiens"},
            {"attribute": "rcsb_entry_info.resolution_combined",
             "operator": "less", "value": 2.0},
        ]),
        sort_by="rcsb_entry_info.resolution_combined",
    )
    assert q["query"]["type"] == "group"
    assert q["query"]["logical_operator"] == "and"
    # the attribute group shares the outer AND, so it is spliced flat rather than nested
    assert len(q["query"]["nodes"]) == 3  # full_text + 2 filters
    assert q["query"]["nodes"][0]["service"] == "full_text"
    assert q["request_options"]["sort"] == [
        {"sort_by": "rcsb_entry_info.resolution_combined", "direction": "asc"}
    ]
    print("ok: combined")


def test_combined_single_collapses():
    # A single condition should not be wrapped in a group node.
    q = _request(queries.group_node([queries.fulltext_node("kinase")], "and"))
    assert q["query"]["type"] == "terminal"
    assert q["query"]["service"] == "full_text"
    print("ok: combined single")


def test_all_hits():
    # all_hits=True swaps paginate for return_all_hits; the default keeps paginate.
    for build in (
        lambda **k: _ft("baseplate", **k),
        lambda **k: _attr(
            "rcsb_entity_source_organism.ncbi_scientific_name", "exact_match",
            "Homo sapiens", **k),
        lambda **k: _request(queries.sequence_node("MVLS"), **k),
    ):
        opts = build(all_hits=True)["request_options"]
        assert opts["return_all_hits"] is True
        assert "paginate" not in opts
        # score sort is preserved alongside return_all_hits
        assert opts["sort"] == [{"sort_by": "score", "direction": "desc"}]
        # default still pages
        assert "return_all_hits" not in build()["request_options"]
        assert "paginate" in build()["request_options"]
    print("ok: all_hits")


def test_attribute_exists_and_flags():
    # "exists" carries no value; negation/case_sensitive add the right flags.
    q = _attr(
        "rcsb_nonpolymer_entity.pdbx_description", "exists",
        negation=True, case_sensitive=True,
    )
    p = q["query"]["parameters"]
    assert "value" not in p
    assert p["operator"] == "exists" and p["negation"] is True and p["case_sensitive"] is True
    # a normal operator keeps its value and omits the flags by default.
    p2 = _attr("a", "equals", 3)["query"]["parameters"]
    assert p2["value"] == 3 and "negation" not in p2 and "case_sensitive" not in p2
    print("ok: attribute exists/flags")


def test_value_coercion():
    # Coercion is driven by the attribute's declared TYPE (from the schema catalog),
    # not by the operator.
    def P(a, o, v):
        return _attr(a, o, v)["query"]["parameters"]
    # 'number' attribute: a numeric string becomes a float.
    pn = P("rcsb_entry_info.resolution_combined", "less", "2.0")
    assert pn["value"] == 2.0 and isinstance(pn["value"], float)
    # 'integer' attribute: becomes an int.
    pi = P("rcsb_assembly_info.polymer_entity_instance_count_protein", "greater_or_equal", "6")
    assert pi["value"] == 6 and isinstance(pi["value"], int)
    # 'date' attribute: NEVER coerced — even a bare-year value that looks numeric and shares
    # greater/less with integers stays a string (this is the type-vs-operator distinction).
    assert P("rcsb_accession_info.initial_release_date", "greater", "2024")["value"] == "2024"
    assert P("rcsb_accession_info.initial_release_date", "greater",
             "2024-01-01T00:00:00Z")["value"] == "2024-01-01T00:00:00Z"
    # 'string' attribute: never coerced (taxonomy_lineage.id "9606" must stay "9606").
    ps = P("rcsb_entity_source_organism.taxonomy_lineage.id", "exact_match", "9606")
    assert ps["value"] == "9606" and isinstance(ps["value"], str)
    # range bounds coerced to the attribute's type; the include flags pass through.
    pr = P("rcsb_entry_info.resolution_combined", "range",
           {"from": "1", "to": "2.5", "include_lower": True})
    assert pr["value"] == {"from": 1.0, "to": 2.5, "include_lower": True}
    # uncatalogued attribute: falls back to the numeric-operator heuristic.
    assert P("made.up.unknown_attr", "less", "2.0")["value"] == 2.0
    print("ok: value coercion (type-driven)")


def test_group_by_identity():
    q = _ft("kinase", return_type="polymer_entity", group_by="seqid_30")
    opts = q["request_options"]
    assert opts["group_by"] == {"aggregation_method": "sequence_identity", "similarity_cutoff": 30}
    assert opts["group_by_return_type"] == "representatives"
    # uniprot grouping.
    qu = _ft("x", return_type="polymer_entity", group_by="uniprot")
    assert qu["request_options"]["group_by"] == {"aggregation_method": "matching_uniprot_accession"}
    # per-filter negation survives into the terminal.
    q2 = _attr("a", "exact_match", "x", negation=True)
    assert q2["query"]["parameters"]["negation"] is True
    # group_by requires return_type="polymer_entity" (the text default is "entry").
    try:
        _ft("x", group_by="seqid_30")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for group_by without polymer_entity")
    print("ok: group_by identity")


def test_group_by_ranking():
    # each ranking maps to a fixed (sort_by, direction).
    cases = {
        "resolution": ("rcsb_entry_info.resolution_combined", "asc"),
        "released_date": ("rcsb_accession_info.initial_release_date", "desc"),
        "entity_residue_count": ("entity_poly.rcsb_sample_sequence_length", "desc"),
        "score": ("score", "desc"),
    }
    for ranking, (sort_by, direction) in cases.items():
        q = _ft("kinase", return_type="polymer_entity", group_by="seqid_30",
                group_by_ranking=ranking)
        assert q["request_options"]["group_by"]["ranking_criteria_type"] == {
            "sort_by": sort_by, "direction": direction,
        }, ranking
    # no ranking -> no ranking_criteria_type key.
    q4 = _attr("a", "exists", return_type="polymer_entity", group_by="seqid_30")
    assert "ranking_criteria_type" not in q4["request_options"]["group_by"]
    # ranking without group_by raises.
    try:
        _ft("x", return_type="polymer_entity", group_by_ranking="score")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for ranking without group_by")
    print("ok: group_by ranking")


def test_group_by_uniprot():
    q = _ft("kinase", return_type="polymer_entity", group_by="uniprot")
    assert q["request_options"]["group_by"] == {"aggregation_method": "matching_uniprot_accession"}
    assert q["request_options"]["group_by_return_type"] == "representatives"
    # "coverage" ranking: UniProt-only, emitted WITHOUT a direction.
    cov = _ft("x", return_type="polymer_entity", group_by="uniprot",
              group_by_ranking="coverage")
    assert cov["request_options"]["group_by"]["ranking_criteria_type"] == {"sort_by": "coverage"}
    # coverage with a non-uniprot grouping is rejected.
    try:
        _ft("x", return_type="polymer_entity", group_by="seqid_30",
            group_by_ranking="coverage")
    except ValueError:
        pass
    else:
        raise AssertionError('expected ValueError for coverage without group_by="uniprot"')
    print("ok: group_by uniprot")


def test_chemical():
    d = _request(queries.chemical_node("c1ccccc1", match_type="sub-struct-graph-relaxed"))
    p = d["query"]["parameters"]
    assert d["query"]["service"] == "chemical"
    assert p == {"type": "descriptor", "value": "c1ccccc1",
                 "descriptor_type": "SMILES", "match_type": "sub-struct-graph-relaxed"}
    assert d["return_type"] == "mol_definition"
    assert d["request_options"]["scoring_strategy"] == "chemical"
    f = _request(queries.chemical_node("Co4O4", query_type="formula", match_subset=True))
    # element-symbol case is preserved (not upper-cased).
    assert f["query"]["parameters"] == {"type": "formula", "value": "Co4O4", "match_subset": True}
    print("ok: chemical")


def test_structure():
    a = _request(queries.structure_node("4hhb", assembly_id="1"))
    assert a["query"]["service"] == "structure"
    assert a["query"]["parameters"]["value"] == {"entry_id": "4HHB", "assembly_id": "1"}
    assert a["return_type"] == "assembly"
    c = _request(queries.structure_node("4HHB", asym_id="A"))
    assert c["query"]["parameters"]["value"] == {"entry_id": "4HHB", "asym_id": "A"}
    assert c["return_type"] == "polymer_instance"
    print("ok: structure")


def test_seqmotif():
    q = _request(queries.seqmotif_node("C..H[LIVF]", pattern_type="regex"))
    p = q["query"]["parameters"]
    assert q["query"]["service"] == "seqmotif"
    assert p == {"value": "C..H[LIVF]", "pattern_type": "regex", "sequence_type": "protein"}
    assert q["return_type"] == "polymer_entity"
    print("ok: seqmotif")


def test_sort_across_every_service():
    # sort_by/sort_direction is a general Search-API request option: it threads into
    # request_options.sort from build_search_request, replacing the default score order,
    # regardless of which service the query node came from.
    res = "rcsb_entry_info.resolution_combined"
    want = [{"sort_by": res, "direction": "asc"}]
    two_residues = [{"label_asym_id": "A", "label_seq_id": 1},
                    {"label_asym_id": "A", "label_seq_id": 2}]
    cases = {
        "full_text": _ft("kinase", sort_by=res),
        "attribute": _attr("exptl.method", "exact_match", "X-RAY DIFFRACTION", sort_by=res),
        "sequence": _request(queries.sequence_node("MVLS"), sort_by=res),
        "structure": _request(queries.structure_node("4HHB", assembly_id="1"), sort_by=res),
        "seqmotif": _request(queries.seqmotif_node("C..H[LIVF]", pattern_type="regex"),
                             sort_by=res),
        "strucmotif": _request(queries.strucmotif_node("2MNR", two_residues), sort_by=res),
        # chemical must target a non-mol_definition return_type to be sortable (guard below)
        "chemical": _request(queries.chemical_node("c1ccccc1"),
                             return_type="polymer_entity", sort_by=res),
    }
    for name, q in cases.items():
        assert q["request_options"]["sort"] == want, name

    # sort_direction is honored
    q = _request(queries.sequence_node("MVLS"), sort_by=res, sort_direction="desc")
    assert q["request_options"]["sort"] == [{"sort_by": res, "direction": "desc"}]

    # omitting sort_by keeps the default score ordering
    assert _request(queries.structure_node("4HHB"))["request_options"]["sort"] == \
        [{"sort_by": "score", "direction": "desc"}]

    # a facet (aggregation-only) query returns no hit ordering — sort_by is not applied there
    fq = _request(
        queries.sequence_node("MVLS"), sort_by=res,
        facets=[{"name": "m", "aggregation_type": "terms", "attribute": "exptl.method"}])
    assert "sort" not in fq["request_options"]

    # group_by_ranking and the top-level sort are INDEPENDENT: a ranking must NOT leak into
    # the result ordering (regression guard against sort_by param/local shadowing). With no
    # caller sort_by, the top-level order stays the default score sort.
    g = _request(queries.sequence_node("MVLS"), return_type="polymer_entity",
                 group_by="seqid_90", group_by_ranking="resolution")
    assert g["request_options"]["sort"] == [{"sort_by": "score", "direction": "desc"}]
    assert g["request_options"]["group_by"]["ranking_criteria_type"] == \
        {"sort_by": res, "direction": "asc"}
    # a caller sort_by orders the representatives while the ranking still picks them
    gs = _request(queries.sequence_node("MVLS"), return_type="polymer_entity",
                  group_by="seqid_90", group_by_ranking="resolution",
                  sort_by="rcsb_accession_info.initial_release_date", sort_direction="desc")
    assert gs["request_options"]["sort"] == \
        [{"sort_by": "rcsb_accession_info.initial_release_date", "direction": "desc"}]
    assert gs["request_options"]["group_by"]["ranking_criteria_type"] == \
        {"sort_by": res, "direction": "asc"}
    print("ok: sort across every service")


def test_facets_suppress_hits_and_are_normalized():
    q = _request(
        queries.fulltext_node("hemoglobin"),
        facets=[
            {"name": "Methods", "aggregation_type": "terms", "attribute": "exptl.method"},
            {"name": "Res", "aggregation_type": "histogram",
             "attribute": "rcsb_entry_info.resolution_combined", "interval": 0.5,
             "min_interval_population": 1},
        ],
    )
    opts = q["request_options"]
    assert opts["paginate"] == {"start": 0, "rows": 0}  # hits suppressed
    assert q["query"]["service"] == "full_text"
    f = opts["facets"]
    assert f[0] == {"name": "Methods", "aggregation_type": "terms", "attribute": "exptl.method"}
    assert f[1]["interval"] == 0.5 and f[1]["min_interval_population"] == 1
    # nested facets are recursively validated/normalized.
    q3 = _request(
        queries.fulltext_node("x"),
        facets=[{"name": "byMethod", "aggregation_type": "terms", "attribute": "exptl.method",
                 "facets": [{"name": "byYear", "aggregation_type": "date_histogram",
                             "attribute": "rcsb_accession_info.initial_release_date",
                             "interval": "year"}]}],
    )
    assert q3["request_options"]["facets"][0]["facets"][0]["aggregation_type"] == "date_histogram"
    print("ok: facets")


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
    q = _request(queries.strucmotif_node(
        "2mnr",
        residue_ids=[
            {"label_asym_id": "A", "label_seq_id": 162},
            {"label_asym_id": "A", "label_seq_id": 193},
            {"label_asym_id": "A", "label_seq_id": 219, "struct_oper_id": "1"},
        ],
        rmsd_cutoff=1.5,
    ))
    p = q["query"]["parameters"]
    assert q["query"]["service"] == "strucmotif"
    assert p["value"]["entry_id"] == "2MNR"  # upper-cased
    assert len(p["value"]["residue_ids"]) == 3
    assert p["value"]["residue_ids"][2]["struct_oper_id"] == "1"
    assert p["rmsd_cutoff"] == 1.5
    assert p["atom_pairing_scheme"] == "SIDE_CHAIN" and p["motif_pruning_strategy"] == "KRUSKAL"
    # default is "assembly" (most general unit for a 3D motif; matches RCSB.org advanced search)
    assert q["return_type"] == "assembly"
    assert q["request_options"]["scoring_strategy"] == "strucmotif"
    # any other return_type may still be requested explicitly
    pe = _request(
        queries.strucmotif_node(
            "2mnr", residue_ids=[{"label_asym_id": "A", "label_seq_id": i} for i in (1, 2)]),
        return_type="polymer_entity")
    assert pe["return_type"] == "polymer_entity"
    print("ok: strucmotif")


def test_chemical_attribute_service():
    # chemical=True switches the attribute terminal to the text_chem service.
    q = _attr("chem_comp.formula_weight", "less", 300, chemical=True,
              return_type="mol_definition")
    assert q["query"]["service"] == "text_chem"
    assert q["return_type"] == "mol_definition"
    # structure attributes keep the default "text" service.
    assert _attr("a", "equals", 1)["query"]["service"] == "text"
    # composed with a keyword: filters use text_chem, the full-text term stays full_text.
    c = _and(
        queries.fulltext_node("aspirin"),
        queries.attribute_node(
            [{"attribute": "chem_comp.formula_weight", "operator": "less", "value": 300}],
            chemical=True),
    )
    assert c["query"]["nodes"][0]["service"] == "full_text"
    assert c["query"]["nodes"][1]["service"] == "text_chem"
    print("ok: chemical text_chem service")


def test_validation_errors():
    two = [{"label_asym_id": "A", "label_seq_id": 1}, {"label_asym_id": "A", "label_seq_id": 2}]
    for bad in (
        lambda: _ft("x", return_type="bogus"),
        lambda: _attr("a", "bogus_op", 1),
        lambda: queries.sequence_node("x", identity_cutoff=5),
        lambda: queries.sequence_node("x", sequence_type="zzz"),
        lambda: queries.fulltext_node(""),                     # no term
        lambda: queries.attribute_node([]),                    # no conditions
        lambda: queries.group_node([], "and"),                 # nothing to compose
        lambda: queries.group_node(
            [queries.fulltext_node("x"), queries.fulltext_node("y")], "xor"),
        lambda: queries.attribute_node([{"attribute": "a", "operator": "bogus", "value": 1}]),
        lambda: queries.build_data_query("entries", []),  # empty id list
        lambda: queries.build_data_query("polymer_entities", ["", "  "]),  # all blank
        lambda: queries.build_data_query("bogus_object", ["X"]),  # unknown object
        lambda: queries.build_data_query("uniprot", "  "),  # blank single id
        lambda: _ft("x", return_type="polymer_entity", group_by="seqid_42"),  # bad group_by
        lambda: queries.chemical_node("c1ccccc1", match_type="bogus"),  # bad match
        lambda: queries.chemical_node("x", descriptor_type="MOL"),  # bad desc type
        lambda: queries.chemical_node("x", query_type="bogus"),  # bad query type
        lambda: queries.structure_node("4HHB", assembly_id="1", asym_id="A"),  # both
        lambda: queries.seqmotif_node("X", pattern_type="bogus"),  # bad pattern
        # NB: `facets=[]` is NOT an error here. build_facet_query required a non-empty list
        # because faceting was its entire purpose; on build_search_request facets are
        # optional, so an empty list means the same as omitting it.
        lambda: _ft("x", facets=[{"name": "x", "aggregation_type": "bogus", "attribute": "a"}]),
        lambda: _ft("x", facets=[{"name": "x", "aggregation_type": "histogram",
                                  "attribute": "a"}]),  # histogram missing interval
        lambda: _ft("x", facets=[{"name": "x", "aggregation_type": "range",
                                  "attribute": "a"}]),  # range missing ranges
        lambda: _ft("x", facets=[{"aggregation_type": "terms", "attribute": "a"}]),  # no name
        lambda: queries.build_count_query(return_type="bogus"),  # bad return_type
        lambda: queries.strucmotif_node("2MNR", [{"label_asym_id": "A", "label_seq_id": 1}]),
        lambda: queries.strucmotif_node(
            "2MNR", [{"label_asym_id": "A", "label_seq_id": i} for i in range(11)]),
        lambda: queries.strucmotif_node("2MNR", two, atom_pairing_scheme="BOGUS"),
        lambda: queries.strucmotif_node("2MNR", two, backbone_distance_tolerance=9),
        lambda: queries.strucmotif_node(
            "2MNR", [{"label_asym_id": "A"}, {"label_asym_id": "A", "label_seq_id": 2}]),
        # sort_by on the default mol_definition return_type is rejected
        lambda: _request(queries.chemical_node("c1ccccc1"),
                         sort_by="rcsb_entry_info.resolution_combined"),
        lambda: _ft("x", return_type="mol_definition", sort_by="chem_comp.formula_weight"),
        lambda: _request(queries.sequence_node("x"),
                         sort_by="rcsb_entry_info.resolution_combined",
                         sort_direction="sideways"),  # bad sort_direction
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


def test_graphql_rcsb_id_injected():
    # A custom `fields` that omits top-level rcsb_id must still get it, or batch
    # results can't be mapped back to ids and everything reports as not_found.
    body = queries.build_data_query("entries", ["4HHB"], fields="struct{title} exptl{method}")
    assert "{ rcsb_id struct{title} exptl{method} }" in body["query"]
    # rcsb_id only nested (not top-level) still triggers injection at the top level
    nested = queries.build_data_query("entries", ["4HHB"], fields="polymer_entities{rcsb_id}")
    assert nested["query"].count("rcsb_id") == 2  # injected top-level + the nested one
    # already-present top-level rcsb_id is not duplicated
    once = queries.build_data_query("entries", ["4HHB"], fields="rcsb_id struct{title}")
    assert once["query"].count("rcsb_id") == 1
    print("ok: graphql rcsb_id injection")


def test_normalize_fields():
    nf = queries._normalize_fields
    # dotted paths expand into nested GraphQL braces
    assert nf("rcsb_polymer_entity.pdbx_description") == "rcsb_polymer_entity { pdbx_description }"
    # shared prefixes merge into one block
    assert nf("a.b a.c") == "a { b c }"
    # deeper nesting
    assert nf("a.b.c") == "a { b { c } }"
    # mix of plain names, dotted paths, and existing braces all normalize together
    assert nf("rcsb_id struct.title exptl{method}") == "rcsb_id struct { title } exptl { method }"
    # commas separate paths too (GraphQL treats them as insignificant whitespace), so an
    # agent's comma-separated list expands instead of hitting an ANTLR syntax error.
    assert nf("struct.title, exptl.method") == "struct { title } exptl { method }"
    assert nf("a.b,c.d") == "a { b } c { d }"          # no space after comma
    assert nf("a.b, a.c") == "a { b c }"               # comma + shared prefix still merges
    assert nf("struct.title , exptl.method ,") == "struct { title } exptl { method }"  # loose/trailing
    # the exact multi-field comma string the agent sent now expands (was an ANTLR error)
    agent_commas = ("struct.title, exptl.method, rcsb_entry_info.resolution_combined, "
                    "rcsb_entry_container_identifiers.polymer_entity_ids, "
                    "rcsb_entry_container_identifiers.entry_id, pdbx_database_related.details")
    out = nf(agent_commas)
    assert "." not in out, out
    assert "rcsb_entry_container_identifiers { polymer_entity_ids entry_id }" in out
    # no dots -> returned verbatim (valid GraphQL / plain names left untouched)
    assert nf("rcsb_id struct{title}") == "rcsb_id struct{title}"
    assert nf("rcsb_id") == "rcsb_id"
    # advanced GraphQL (args/aliases/directives/fragments) passes through unchanged
    assert nf("foo(first: 5){bar}") == "foo(first: 5){bar}"
    assert nf("alias: field.sub") == "alias: field.sub"
    # empty / None untouched
    assert nf("") == "" and nf(None) is None
    # the exact agent input that triggered the ANTLR error now yields valid GraphQL (no dots)
    agent = ("rcsb_id rcsb_polymer_entity.pdbx_description "
             "rcsb_entity_source_organism.ncbi_scientific_name "
             "rcsb_polymer_entity_container_identifiers.uniprot_ids "
             "entity_poly.rcsb_sample_sequence_length")
    body = queries.build_data_query("polymer_entities", ["8ATC_1"], fields=agent)
    selection = body["query"].split("polymer_entities(entity_ids: $ids) { ", 1)[1].rsplit(" }", 2)[0]
    assert "." not in selection, selection
    assert "rcsb_polymer_entity { pdbx_description }" in body["query"]
    assert "entity_poly { rcsb_sample_sequence_length }" in body["query"]
    # the override is applied via build_sc_alignments_query too (dotted -> braces)
    sc = queries.build_sc_alignments_query(
        "P69905", "UNIPROT", "PDB_ENTITY", fields="target_alignments.aligned_regions.query_begin"
    )
    assert "target_alignments { aligned_regions { query_begin } }" in sc["query"]
    print("ok: normalize fields (dotted -> graphql)")


def test_graphql_registry():
    # Every endpoint maps to a usable builder with a non-empty default selection.
    assert len(queries.DATA_OBJECTS) == 16
    batch = [k for k, s in queries.DATA_OBJECTS.items() if s.batch]
    single = [k for k, s in queries.DATA_OBJECTS.items() if not s.batch]
    assert len(batch) == 13 and len(single) == 3
    assert set(single) == {"uniprot", "pubmed", "group_provenance"}
    for key, spec in queries.DATA_OBJECTS.items():
        assert spec.default_fields.startswith("rcsb_id"), key
        assert spec.arg_type in {"String", "Int"}, key
        sample = "1" if spec.arg_type == "Int" else "X"
        ids = sample if not spec.batch else [sample]
        body = queries.build_data_query(key, ids)
        assert f"{spec.root_field}({spec.arg}: $ids)" in body["query"], key
    print("ok: graphql registry (16 endpoints)")


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


def test_service_refinement_and_facets():
    # A service search refined with attribute filters -> group(service terminal + text terminal).
    q = _and(
        queries.sequence_node("MTEY", identity_cutoff=0.9),
        queries.attribute_node([{"attribute": "rcsb_entity_source_organism.taxonomy_lineage.name",
                                 "operator": "exact_match", "value": "Homo sapiens"}]),
    )
    grp = q["query"]
    assert grp["type"] == "group" and grp["logical_operator"] == "and"
    assert [n["service"] for n in grp["nodes"]] == ["sequence", "text"]
    # refinement does not change which service drives the ranking
    assert q["request_options"]["scoring_strategy"] == "sequence"
    # No attributes -> bare service terminal (no wrapping group).
    bare = _request(queries.chemical_node("C8H10N4O2", query_type="formula"))
    assert bare["query"]["type"] == "terminal" and bare["query"]["service"] == "chemical"
    # facets on a service search -> rows 0 + validated facets, with the attribute filter applied.
    qf = _and(
        queries.structure_node("4HHB", assembly_id="1"),
        queries.attribute_node([{"attribute": "rcsb_entry_info.resolution_combined",
                                 "operator": "less", "value": 3.0}]),
        facets=[{"name": "M", "aggregation_type": "terms", "attribute": "exptl.method"}],
    )
    assert qf["request_options"]["paginate"] == {"start": 0, "rows": 0}
    assert qf["request_options"]["facets"][0]["attribute"] == "exptl.method"
    assert qf["query"]["type"] == "group"  # structure terminal + attribute terminal
    # facets on a plain text query too.
    qc = _ft("ribosome",
             facets=[{"name": "Y", "aggregation_type": "date_histogram",
                      "attribute": "rcsb_accession_info.initial_release_date",
                      "interval": "year"}])
    assert qc["request_options"]["paginate"] == {"start": 0, "rows": 0}
    assert "facets" in qc["request_options"]
    print("ok: service refinement + facets")


if __name__ == "__main__":
    test_fulltext()
    test_fulltext_with_computed()
    test_attribute()
    test_sequence()
    test_combined()
    test_combined_single_collapses()
    test_all_hits()
    test_attribute_exists_and_flags()
    test_value_coercion()
    test_group_by_identity()
    test_group_by_ranking()
    test_group_by_uniprot()
    test_chemical()
    test_structure()
    test_seqmotif()
    test_sort_across_every_service()
    test_facets_suppress_hits_and_are_normalized()
    test_count_query()
    test_strucmotif()
    test_service_refinement_and_facets()
    test_chemical_attribute_service()
    test_validation_errors()
    test_graphql_batch()
    test_graphql_single()
    test_graphql_fields_override()
    test_graphql_rcsb_id_injected()
    test_normalize_fields()
    test_graphql_registry()
    test_seqcoord_alignments()
    test_seqcoord_annotations()
    test_seqcoord_groups()
    test_seqcoord_validation()
    print("\nAll query-builder tests passed.")
