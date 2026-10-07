"""Argument descriptions for rcsb_get_nonpolymer_entities (see the package docstring for why).

`fields` uses the shared wording in shared.py; this module supplies its example.
"""

__all__ = [
    "ENTITY_IDS_DOC",
    "FIELDS_EXAMPLE",
]

ENTITY_IDS_DOC = (
    'entry + non-polymer entity number, e.g. ["4HHB_3"] — exactly what '
    'rcsb_search_request returns with return_type="non_polymer_entity". Unknown IDs '
    'are returned under "not_found". Do not guess the number: entity numbering is '
    'shared with the polymers and they take the low values, so a ligand is rarely "_1" '
    'and that guess lands in not_found. Take it from rcsb_entry_container_identifiers '
    '.non_polymer_entity_ids on rcsb_get_entries, or from a search hit.'
)

FIELDS_EXAMPLE = "rcsb_nonpolymer_entity.pdbx_description"
