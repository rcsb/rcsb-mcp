"""Shared types for the RCSB Search attribute catalogs.

This module is a LEAF: it imports nothing from the package, so the catalog data
modules (search_attributes, chemical_search_attributes) can annotate themselves
with it without a cycle. Everything above them — queries, server — imports the
same names, so the operator vocabulary is declared exactly once.

Both catalogs publish the identical record shape, which the Search API's metadata
schema guarantees and tests/test_server.py::test_attribute_catalogs_conform pins.
"""

from __future__ import annotations

from typing import Any, Literal

# typing_extensions, not typing: pydantic refuses to build a schema from a
# typing.TypedDict on Python < 3.12, and SearchAttribute is used as a field type
# in server._AttributeListResult. That raises at IMPORT time, so on the 3.11 base
# image the server dies before binding its port. See tests/test_python_support.py.
from typing_extensions import NotRequired, TypedDict

# The value type of a searchable attribute, from the Search API metadata schema.
AttributeValueType = Literal["date", "integer", "number", "string"]

# The object a searchable attribute hangs off — its granularity. Derived from the Data
# API object graph by scripts/generate_attribute_scopes.py, NOT from the attribute path,
# which is a poor guide: every em_* root is entry-scoped without saying so, while
# entity_src_gen, entity_poly and rcsb_entity_source_organism are all finer than they read.
#
# This is a SUPERSET of queries.RETURN_TYPES: a search can be returned at six levels, but
# attributes live at nine. Branched entities and non-polymer/branched instances are real
# granularities with no return_type of their own, so conditions at those levels can be
# intersected too loosely with no return_type available to tighten them — a caller-facing
# note must say so rather than recommend a level the API would reject.
AttributeScope = Literal[
    "entry",
    "assembly", "polymer_entity", "non_polymer_entity", "branched_entity", "mol_definition",
    "polymer_instance", "non_polymer_instance", "branched_instance",
]


# The full set of attribute/text comparison operators from the spec enum. This is
# the single source: server.py types AttributeFilter.operator with it, queries.py
# derives its runtime membership set from it, and the catalogs are asserted to draw
# their `operators` lists from it — so the three can never drift apart.
TextOperator = Literal[
    "exact_match", "in", "contains_words", "contains_phrase", "greater",
    "greater_or_equal", "less", "less_or_equal", "equals", "range", "exists",
]


class SearchAttribute(TypedDict):
    """One searchable RCSB attribute, as published by the Search API metadata schema.

    `attribute` is unique within a catalog. Every key except `enum` is always present;
    the catalogs carry no other optional fields and no empty values.
    """

    attribute: str
    type: AttributeValueType
    operators: list[TextOperator]
    description: str
    # The nested container this attribute belongs to, on the 22% that have one. An object
    # holds MANY of these records, and GROUPING SELECTS THE SEMANTICS -- per the Search API
    # team, the boolean syntax is deliberately overloaded for nested fields so that callers
    # can choose. Conditions sharing a `nested_group`, alone together in one group, must hold
    # on the SAME record; anywhere else they are matched independently. NEITHER is an error:
    # type+value on a binding affinity describe one measurement, while an InterPro id and a
    # GO type are necessarily two different annotation records (grouped they give 0, apart
    # 1,549). So this field is not a constraint to enforce -- it marks where the caller has a
    # CHOICE that the query shape silently makes for them.
    #
    # What that choice costs when it is not the one intended, "a Kd below 1 nM":
    #     and[type=Kd, value<1]              303   SAME record
    #     and[ and[type=Kd], and[value<1] ]  481   independent -- and note nothing foreign is
    #                                              anywhere here, so a lone condition in a
    #                                              single-node group is enough to switch the
    #                                              semantics; that is what the composer
    #                                              builds from two separate calls
    #     and[type=Kd, value<1, XRAY]        456   independent -- one foreign terminal in the
    #                                              group switches it, and the count GROWS
    #                                              against 303 while a restriction was ADDED
    #     and[ and[type=Kd, value<1], XRAY]  287   same record, X-ray applied outside
    #     and[ and[type=Kd, value<1] ]       303   extra depth around an intact group is inert
    # Only the 456 row is likely to be unintended, and only because it looks like the 303 one.
    # Carried as the container PATH, not a boolean, because the path is what the caller
    # acts on and is not derivable: 22 structure attributes group under something that is
    # not their first path segment.
    nested_group: NotRequired[str]
    # The complete set of allowed values, on the ~15% of attributes that constrain them.
    # This is the only part of a filter nothing used to check, and the only one whose
    # failure is SILENT: a wrong path or operator is rejected, but a wrong VALUE builds a
    # query the API happily answers with zero hits — which reads as "no such structures
    # exist" rather than "you spelled it wrong". Measured: exptl.method="cryo-EM" returns
    # 0, where "ELECTRON MICROSCOPY" returns 35,660.
    enum: NotRequired[list[Any]]
