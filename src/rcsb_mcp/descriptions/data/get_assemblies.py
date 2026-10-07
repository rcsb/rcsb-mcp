"""Argument descriptions for rcsb_get_assemblies (see the package docstring for why).

`fields` uses the shared wording in shared.py; this module supplies its example.
"""

__all__ = [
    "ASSEMBLY_IDS_DOC",
    "FIELDS_EXAMPLE",
]

ASSEMBLY_IDS_DOC = (
    "entry-assembly, e.g. [\"4HHB-1\"] — exactly what rcsb_search_request returns with "
    "return_type=\"assembly\". Unknown IDs are returned under \"not_found\". Do not guess "
    "\"-1\". Assembly 1 essentially always exists, so the guess succeeds silently, but "
    "an entry's assemblies differ in composition and the first is not necessarily the "
    "one carrying what you searched for. Take it from an assembly search hit, or from "
    "rcsb_entry_container_identifiers.assembly_ids on rcsb_get_entries."
)

FIELDS_EXAMPLE = "rcsb_assembly_info.polymer_entity_instance_count"
