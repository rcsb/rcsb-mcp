"""The per-attribute coverage the catalog generator counts, and what it does with it.

scripts/generate_search_attributes.py asks the live Search API how many objects hold a
value for each attribute. Two lists come out of it, vendored next to each catalog:

* UNPOPULATED_* -- an `exists` count of 0. In the schema, empty in the index: every
  condition on one is a legal query returning nothing, which reads as "no such
  structures". Dropped from the catalog and rejected by name (test_search_validation).
* SPARSE_* -- depositor-reported numbers many entries leave empty, each mapped to its
  category's most filled attribute (the "reports this category" anchor).
  rcsb_search_request counts what a filter on one dropped (test_filter_notes).

The rules are tested here on made-up counts; the vendored lists are checked for the
invariants the server relies on. No network.
"""

import importlib.util
import pathlib

from rcsb_mcp import chemical_search_attributes as chem
from rcsb_mcp import search_attributes as struct

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "generate_search_attributes.py"
_spec = importlib.util.spec_from_file_location("generate_search_attributes", _SCRIPT)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def rec(attribute, typ="number"):
    return {"attribute": attribute, "type": typ, "operators": ["exists"], "description": None}


def test_unpopulated_is_exactly_the_zero_counts():
    assert gen.unpopulated({"a.x": 0, "a.y": 3, "b.z": 0}) == ["a.x", "b.z"]


ENTRIES = 1000  # experimental entries, the UNIVERSAL_SHARE denominator


def test_sparse_is_relative_to_the_attributes_own_category():
    """pH is empty on 27% of X-ray entries but on ~42% of experimental entries (no NMR and
    almost no EM entry has a crystal); relative to the archive every crystal field would
    look sparse."""
    catalog = [rec("exptl_crystal_grow.pH"), rec("exptl_crystal_grow.temp"),
               rec("exptl_crystal_grow.pdbx_details", "string")]
    counts = {"exptl_crystal_grow.pH": 150, "exptl_crystal_grow.temp": 190,
              "exptl_crystal_grow.pdbx_details": 200}
    # pH 75% of its category -> sparse; temp 95% -> not; strings are never flagged. The
    # anchor is the category's most filled attribute, whatever its type.
    assert gen.sparse(catalog, counts, ENTRIES) == {
        "exptl_crystal_grow.pH": "exptl_crystal_grow.pdbx_details"}


def test_a_category_every_entry_reports_is_not_judged():
    """exptl.crystals_number is empty on every NMR and EM entry: 75% against exptl.method,
    though ~94% of the crystal entries have it. A universal category cannot tell "left out"
    from "does not apply"."""
    catalog = [rec("exptl.crystals_number"), rec("exptl.method", "string")]
    counts = {"exptl.crystals_number": 750, "exptl.method": 998}
    assert gen.sparse(catalog, counts, ENTRIES) == {}


def test_sparse_never_flags_what_rcsb_computes():
    """A computed number is absent because it does not apply (no ligand, not an enzyme),
    not because a depositor left it out."""
    catalog = [rec("rcsb_entry_info.nonpolymer_molecular_weight_maximum"),
               rec("rcsb_entry_info.resolution_combined"),
               rec("pdbx_vrpt_summary.clashscore"), rec("pdbx_vrpt_summary.percent_ramachandran_outliers")]
    counts = {"rcsb_entry_info.nonpolymer_molecular_weight_maximum": 75,
              "rcsb_entry_info.resolution_combined": 100,
              "pdbx_vrpt_summary.clashscore": 50, "pdbx_vrpt_summary.percent_ramachandran_outliers": 100}
    assert gen.sparse(catalog, counts, ENTRIES) == {}


def test_an_empty_attribute_is_unpopulated_not_sparse():
    catalog = [rec("reflns.B_iso_Wilson_estimate"), rec("reflns.d_resolution_high")]
    counts = {"reflns.B_iso_Wilson_estimate": 0, "reflns.d_resolution_high": 100}
    assert gen.sparse(catalog, counts, ENTRIES) == {}


# --------------------------------------------------------------------------- #
# the vendored lists
# --------------------------------------------------------------------------- #
CATALOGS = [
    (struct.SEARCH_ATTRIBUTES, struct.UNPOPULATED_SEARCH_ATTRIBUTES),
    (chem.CHEMICAL_SEARCH_ATTRIBUTES, chem.UNPOPULATED_CHEMICAL_SEARCH_ATTRIBUTES),
]


def test_no_unpopulated_attribute_is_offered():
    for catalog, empty in CATALOGS:
        assert empty == sorted(set(empty))
        assert not {a["attribute"] for a in catalog} & set(empty)


def test_sparse_attributes_are_offered_depositor_numbers_with_an_anchor():
    by_path = {a["attribute"]: a for a in struct.SEARCH_ATTRIBUTES}
    sparse = struct.SPARSE_SEARCH_ATTRIBUTES
    assert list(sparse) == sorted(sparse)
    for path, anchor in sparse.items():
        assert path in by_path, f"{path} is sparse but not in the catalog"
        assert by_path[path]["type"] in ("number", "integer")
        assert not path.startswith(gen._COMPUTED_PREFIXES)
        assert anchor in by_path and anchor.split(".")[0] == path.split(".")[0], (path, anchor)
    assert sparse["exptl_crystal_grow.pH"] == "exptl_crystal_grow.pdbx_details"
    assert "exptl.crystals_number" not in sparse, "a universal category must not be judged"


def test_the_vendored_modules_are_exactly_what_the_generator_renders():
    """Generated, never hand-edited: re-rendering the committed data reproduces the file."""
    for spec, module, catalog, empty, thin in (
        (gen.CATALOGS[0], struct, struct.SEARCH_ATTRIBUTES, struct.UNPOPULATED_SEARCH_ATTRIBUTES,
         struct.SPARSE_SEARCH_ATTRIBUTES),
        (gen.CATALOGS[1], chem, chem.CHEMICAL_SEARCH_ATTRIBUTES,
         chem.UNPOPULATED_CHEMICAL_SEARCH_ATTRIBUTES, {}),
    ):
        assert pathlib.Path(module.__file__).read_text() == gen.render_module(catalog, spec, empty, thin)
