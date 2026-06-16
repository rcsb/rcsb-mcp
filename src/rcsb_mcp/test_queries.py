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


if __name__ == "__main__":
    test_fulltext()
    test_fulltext_with_computed()
    test_attribute()
    test_sequence()
    test_combined()
    test_combined_single_collapses()
    test_validation_errors()
    test_graphql_batch()
    test_graphql_single()
    test_graphql_fields_override()
    test_graphql_registry()
    print("\nAll query-builder tests passed.")
