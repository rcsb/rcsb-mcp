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
        lambda: queries.build_entries_query([]),  # empty id list
        lambda: queries.build_polymer_entities_query(["", "  "]),  # all blank
    ):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError("expected ValueError")
    print("ok: validation")


def test_graphql_entries():
    body = queries.build_entries_query(["4hhb", " 1mbn "])
    assert "entries(entry_ids: $ids)" in body["query"]
    # ids are passed through variables (no inlining); stripping is applied.
    assert body["variables"] == {"ids": ["4hhb", "1mbn"]}
    print("ok: graphql entries")


def test_graphql_polymer_entities():
    body = queries.build_polymer_entities_query(["4HHB_1"])
    assert "polymer_entities(entity_ids: $ids)" in body["query"]
    assert "pdbx_seq_one_letter_code_can" in body["query"]
    assert body["variables"] == {"ids": ["4HHB_1"]}
    print("ok: graphql polymer entities")


def test_graphql_chem_comps():
    body = queries.build_chem_comps_query(["HEM", "ATP"])
    assert "chem_comps(comp_ids: $ids)" in body["query"]
    assert body["variables"] == {"ids": ["HEM", "ATP"]}
    print("ok: graphql chem comps")


if __name__ == "__main__":
    test_fulltext()
    test_fulltext_with_computed()
    test_attribute()
    test_sequence()
    test_combined()
    test_combined_single_collapses()
    test_validation_errors()
    test_graphql_entries()
    test_graphql_polymer_entities()
    test_graphql_chem_comps()
    print("\nAll query-builder tests passed.")
