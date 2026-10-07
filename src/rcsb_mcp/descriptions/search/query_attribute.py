"""Argument descriptions for rcsb_query_attribute (see the package docstring for why).

Two levels, kept apart on purpose, so nothing is said twice in the schema:

* One condition -- ``AttributeFilter`` (``FILTER_*``): everything about a single condition's
  attribute, operator and value lives on that condition's own fields.
* The tool's arguments -- ``attributes`` carries only what is about the LIST of conditions
  and the call boundary (the nested-record rule), which no single condition can express.
"""

__all__ = [
    "ATTRIBUTES_DOC",
    "LOGICAL_OPERATOR_DOC",
    "CHEMICAL_ATTRIBUTES_DOC",
    "FILTER_DOC",
    "FILTER_ATTRIBUTE_DOC",
    "FILTER_OPERATOR_DOC",
    "FILTER_VALUE_DOC",
    "FILTER_NEGATION_DOC",
    "FILTER_CASE_SENSITIVE_DOC",
]

# --------------------------------------------------------------------------------------
# The tool's arguments
# --------------------------------------------------------------------------------------

ATTRIBUTES_DOC = """\
One or more conditions.
Attributes that carry a `nested_group` are stored in nested documents, and an object holds \
MANY: an entity has many binding affinities, many annotations. For these the CALL BOUNDARY \
chooses the semantics. Conditions built in one rcsb_query_attribute call, with nothing else \
in it, are matched against the SAME record; conditions in separate calls are matched \
independently, each against any record. Pick the one you mean:
  same record  — "a Kd below 1 nM": type=Kd and value<1 describe ONE measurement, so build \
them together and alone (303 entries; splitting them across calls gives 481, and adding an \
X-ray filter to their call gives 456)
  independently — "has InterPro IPR001128 AND some GO annotation": those are necessarily \
two different annotation records, so build them in separate calls (1,549 entities; together \
they describe one impossible record and return 0)"""

LOGICAL_OPERATOR_DOC = """\
Combine these conditions with "and" (default) or "or".
For several values of a SINGLE attribute use the attribute operator `in`.
For a query needing AND + OR — e.g. (high-resolution OR NMR) AND human — build each group \
separately and join them with rcsb_query_composer."""

CHEMICAL_ATTRIBUTES_DOC = (
    'Set True when the paths come from rcsb_list_pdb_search_attributes(schema="chemical") '
    '(e.g. "chem_comp.formula_weight"). Selects the chemical-component catalog rather than '
    "the structure one."
)

# --------------------------------------------------------------------------------------
# One condition: AttributeFilter (its docstring and its fields)
# --------------------------------------------------------------------------------------

FILTER_DOC = """\
One structured attribute condition — a single `text`/`text_chem` terminal.

A list of these expresses a flat multi-attribute query (combined with one AND/OR). Find a \
path/operators with rcsb_list_pdb_search_attributes."""

FILTER_ATTRIBUTE_DOC = "Dotted RCSB attribute path, e.g. 'rcsb_entry_info.resolution_combined'."

FILTER_OPERATOR_DOC = (
    "Comparison operator, type-specific (see rcsb_list_pdb_search_attributes): strings use "
    "exact_match/in or contains_words/contains_phrase; numbers/dates use greater/"
    "greater_or_equal/less/less_or_equal/equals/range; any type supports exists."
)

FILTER_VALUE_DOC = """\
Comparison value; omit for 'exists'. A list for 'in'; a \
{from,to,include_lower,include_upper} object for 'range', whose bounds are EXCLUSIVE unless \
the include flags say otherwise. A numeric string is coerced to a number for numeric \
operators; dates take an ISO-8601 string.
Some attributes accept only a FIXED SET of values — exptl.method is "X-RAY DIFFRACTION" / \
"ELECTRON MICROSCOPY" / ..., not "cryo-EM". Don't guess those: \
rcsb_list_pdb_search_attributes returns them as `enum`. A value outside the set is rejected, \
so you can correct it, rather than matching nothing and looking like an empty result."""

FILTER_NEGATION_DOC = "Invert the match (NOT)."

FILTER_CASE_SENSITIVE_DOC = "Match the value case-sensitively (default insensitive)."
