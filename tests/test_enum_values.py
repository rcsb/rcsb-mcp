"""A wrong filter VALUE must fail loudly, not return zero hits.

This is the one part of a filter nothing used to check, and the only one whose failure is
silent. A bad attribute path or operator is refused outright. A bad value builds a legal
query the Search API answers with `total_count: 0` — and an empty result on an attribute
filter is a legitimate answer that rcsb_query_attribute explicitly tells the agent to
report rather than work around. So the mistake is not merely undetected, it is actively
dressed up as a finding.

Measured against the live API when this was written:

    exptl.method = "X-RAY DIFFRACTION"                    206,170 hits
    exptl.method = "cryo-EM"                                    0 hits
    exptl.method = "crystallography"                            0 hits
    chem_comp.type = "D-beta-peptide, C-gamma linking"          3 hits
    chem_comp.type = "D-beta-peptide"                           0 hits

Every one of those wrong values is the FIRST thing a person or a model would write.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp import search  # noqa: E402
from rcsb_mcp.chemical_search_attributes import CHEMICAL_SEARCH_ATTRIBUTES  # noqa: E402
from rcsb_mcp.search_attributes import SEARCH_ATTRIBUTES  # noqa: E402
from rcsb_mcp.search import AttributeFilter, _validate_query_attributes  # noqa: E402

METHOD = "exptl.method"


def _filters(**kw):
    return [AttributeFilter(**kw)]


# --------------------------------------------------------------------------- #
# The failure this prevents
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", ["cryo-EM", "crystallography", "X-ray", "EM", "NMR spectroscopy"])
def test_a_plausible_wrong_value_is_rejected(bad):
    """Each of these returns 0 hits from the live API and reads as 'none exist'."""
    with pytest.raises(ValueError, match="is not a valid value"):
        _validate_query_attributes(
            attributes=_filters(attribute=METHOD, operator="exact_match", value=bad))


def test_the_rejection_always_lists_the_allowed_values():
    """The full vocabulary is the correction — a complaint alone leaves the agent stuck.

    It has to be the whole list, not just a fuzzy suggestion: "cryo-EM" is nowhere near
    "ELECTRON MICROSCOPY" by string similarity, so difflib offers nothing for the single
    most likely mistake. The enumerated values are what make it recoverable.
    """
    with pytest.raises(ValueError) as e:
        _validate_query_attributes(
            attributes=_filters(attribute=METHOD, operator="exact_match", value="cryo-EM"))
    msg = str(e.value)
    assert "Allowed values:" in msg
    assert "ELECTRON MICROSCOPY" in msg, "the correct value must appear, not just a complaint"
    assert "Did you mean" not in msg, "test premise: this one is too dissimilar to suggest"


@pytest.mark.parametrize("typo, expected", [
    ("X-RAY DIFFRACTON", "X-RAY DIFFRACTION"),
    ("ELECTRON MICROSCOPE", "ELECTRON MICROSCOPY"),
    ("SOLUTION-NMR", "SOLUTION NMR"),
])
def test_a_near_miss_also_gets_a_did_you_mean(typo, expected):
    """Where similarity does help, lead with it — same treatment guessed PATHS get."""
    with pytest.raises(ValueError) as e:
        _validate_query_attributes(
            attributes=_filters(attribute=METHOD, operator="exact_match", value=typo))
    suggestion = str(e.value).split("Did you mean:")[1]
    assert suggestion.strip().startswith(expected)


def test_a_correct_value_passes():
    _validate_query_attributes(
        attributes=_filters(attribute=METHOD, operator="exact_match", value="X-RAY DIFFRACTION"))


def test_case_insensitive_by_default_because_the_api_is():
    """The API's default is case-insensitive, so rejecting a case variant would be wrong."""
    _validate_query_attributes(
        attributes=_filters(attribute=METHOD, operator="exact_match", value="x-ray diffraction"))


def test_a_case_variant_IS_rejected_when_the_caller_asked_for_case_sensitivity():
    """case_sensitive=True + wrong case is another silent zero."""
    with pytest.raises(ValueError, match="case-sensitive"):
        _validate_query_attributes(attributes=_filters(
            attribute=METHOD, operator="exact_match", value="x-ray diffraction",
            case_sensitive=True))


def test_the_comma_case(monkeypatch):
    """A value containing a comma is indistinguishable from two values in prose.

    The GraphQL/schema descriptions render allowed values as a comma-joined list, so
    'D-beta-peptide, C-gamma linking' reads as two. Splitting it produces a value that
    returns nothing; the structured enum is what makes the boundary unambiguous.
    """
    rec = next(a for a in CHEMICAL_SEARCH_ATTRIBUTES + SEARCH_ATTRIBUTES
               if a["attribute"] == "chem_comp.type")
    assert any("," in v for v in rec["enum"]), "test premise: this vocabulary has comma-bearing values"
    whole = next(v for v in rec["enum"] if "," in v)
    half = whole.split(",")[0].strip()

    chemical = rec in CHEMICAL_SEARCH_ATTRIBUTES
    _validate_query_attributes(chemical=chemical, attributes=_filters(
        attribute="chem_comp.type", operator="exact_match", value=whole))
    with pytest.raises(ValueError, match="is not a valid value"):
        _validate_query_attributes(chemical=chemical, attributes=_filters(
            attribute="chem_comp.type", operator="exact_match", value=half))


# --------------------------------------------------------------------------- #
# Scope: only where a closed vocabulary exists, only where a whole value is compared
# --------------------------------------------------------------------------- #
def test_free_text_attributes_are_untouched():
    """Most attributes publish no vocabulary; nothing may start rejecting their values."""
    _validate_query_attributes(attributes=_filters(
        attribute="struct.title", operator="contains_phrase", value="anything at all"))


@pytest.mark.parametrize("operator", ["contains_words", "contains_phrase"])
def test_substring_operators_are_not_value_checked(operator):
    """These match text WITHIN a value, so a fragment is a legitimate query.

    em_imaging.microscope_model is one of the 7 attributes that publish a vocabulary AND
    accept substring matching: its values are full model names like "FEI TECNAI 12", so
    searching for "TECNAI" is exactly what a caller means to do. Value-checking here would
    reject a correct query. (exptl.method cannot be used for this — it is exact-match only,
    so the operator check fires first.)
    """
    _validate_query_attributes(attributes=_filters(
        attribute="em_imaging.microscope_model", operator=operator, value="TECNAI"))


def test_the_same_attribute_IS_value_checked_on_exact_match():
    """The exclusion is per-operator, not per-attribute."""
    with pytest.raises(ValueError, match="is not a valid value"):
        _validate_query_attributes(attributes=_filters(
            attribute="em_imaging.microscope_model", operator="exact_match", value="TECNAI"))


def test_exists_carries_no_value_to_check():
    _validate_query_attributes(attributes=_filters(attribute=METHOD, operator="exists"))


def test_in_validates_every_alternative():
    _validate_query_attributes(attributes=_filters(
        attribute=METHOD, operator="in", value=["X-RAY DIFFRACTION", "ELECTRON MICROSCOPY"]))
    with pytest.raises(ValueError, match="cryo-EM"):
        _validate_query_attributes(attributes=_filters(
            attribute=METHOD, operator="in", value=["X-RAY DIFFRACTION", "cryo-EM"]))


def test_a_negated_wrong_value_is_still_wrong():
    """`not cryo-EM` excludes nothing and quietly matches everything."""
    with pytest.raises(ValueError, match="is not a valid value"):
        _validate_query_attributes(attributes=_filters(
            attribute=METHOD, operator="exact_match", value="cryo-EM", negation=True))


# --------------------------------------------------------------------------- #
# Through the tool, and into what the agent can see up front
# --------------------------------------------------------------------------- #
def test_the_query_tool_refuses_before_anything_is_built(monkeypatch):
    sent = []

    async def fake_post(body):
        sent.append(body)
        return {"total_count": 0, "result_set": []}

    monkeypatch.setattr(search, "_post_search", fake_post)
    mcp = FastMCP("test")
    search.register_search_tools(mcp)
    with pytest.raises(Exception, match="is not a valid value"):
        asyncio.run(mcp.call_tool("rcsb_query_attribute", {"attributes": [
            {"attribute": METHOD, "operator": "exact_match", "value": "cryo-EM"}]}))
    assert not sent


def test_the_lookup_tool_shows_the_allowed_values():
    """The agent should be able to pick correctly, not just be corrected afterwards."""
    r = asyncio.run(search.rcsb_list_pdb_search_attributes(query="exptl.method"))
    rec = next(a for a in r["attributes"] if a["attribute"] == METHOD)
    assert "ELECTRON MICROSCOPY" in rec["enum"]


def test_enums_are_only_carried_where_a_vocabulary_exists():
    """If every attribute grew an enum, validation would start rejecting valid free text."""
    with_enum = [a for a in SEARCH_ATTRIBUTES if "enum" in a]
    assert 0 < len(with_enum) < len(SEARCH_ATTRIBUTES) // 2, (
        f"{len(with_enum)} of {len(SEARCH_ATTRIBUTES)} attributes carry an enum — "
        "that ratio suggests the generator started emitting them indiscriminately"
    )
    assert any(a["attribute"] == METHOD for a in with_enum)
