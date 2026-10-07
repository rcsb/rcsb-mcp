"""Argument descriptions for rcsb_get_polymer_entities (see the package docstring for why).

`fields` uses the shared wording in shared.py; this module supplies its example.
"""

__all__ = [
    "ENTITY_IDS_DOC",
    "FIELDS_EXAMPLE",
]

ENTITY_IDS_DOC = (
    'entry + entity number, e.g. ["4HHB_1"] — exactly what rcsb_search_request returns '
    'with return_type="polymer_entity". Unknown IDs are returned under "not_found". '
    'NEVER form one by appending _1 to an entry id. Entity numbers are assigned per '
    'deposition and carry no meaning: "<ENTRY>_1" essentially always exists, so the '
    'guess returns valid data for whatever molecule happens to be numbered first — a '
    'DIFFERENT protein, or DNA/RNA — and nothing in the response marks it wrong. Take '
    'the number from a search hit, or from '
    'rcsb_entry_container_identifiers.polymer_entity_ids on rcsb_get_entries.'
)

FIELDS_EXAMPLE = "rcsb_polymer_entity.pdbx_description"
