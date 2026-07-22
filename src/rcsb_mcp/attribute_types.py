"""Shared types for the RCSB Search attribute catalogs.

This module is a LEAF: it imports nothing from the package, so the catalog data
modules (search_attributes, chemical_search_attributes) can annotate themselves
with it without a cycle. Everything above them — queries, server — imports the
same names, so the operator vocabulary is declared exactly once.

Both catalogs publish the identical record shape, which the Search API's metadata
schema guarantees and tests/test_server.py::test_attribute_catalogs_conform pins.
"""

from __future__ import annotations

from typing import Literal, TypedDict

# The value type of a searchable attribute, from the Search API metadata schema.
AttributeValueType = Literal["date", "integer", "number", "string"]

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

    Every key is always present: the catalogs carry no optional fields and no empty
    values. `attribute` is unique within a catalog.
    """

    attribute: str
    type: AttributeValueType
    operators: list[TextOperator]
    description: str
