"""Argument descriptions for rcsb_query_strucmotif (see the package docstring for why)."""

__all__ = [
    "ENTRY_ID_DOC",
    "RESIDUE_IDS_DOC",
    "BACKBONE_DISTANCE_TOLERANCE_DOC",
    "SIDE_CHAIN_DISTANCE_TOLERANCE_DOC",
    "ANGLE_TOLERANCE_DOC",
    "RMSD_CUTOFF_DOC",
    "ATOM_PAIRING_SCHEME_DOC",
    "MOTIF_PRUNING_STRATEGY_DOC",
    "EXCHANGES_DOC",
]

ENTRY_ID_DOC = 'Reference PDB entry defining the motif, e.g. "2MNR".'

RESIDUE_IDS_DOC = """\
2-10 residues defining the motif, each \
{"label_asym_id": <chain>, "label_seq_id": <int>, "struct_oper_id"?: <str>}.
IMPORTANT: these are the mmCIF *label* identifiers (the internal numbering), which often \
DIFFER from the author residue numbers seen in papers and on the PDB site. If you only have \
author numbering, resolve it first (e.g. via rcsb_get_polymer_entity_instances) — author \
numbers give wrong/no hits.
Example (enolase catalytic residues):
[{"label_asym_id":"A","label_seq_id":162},
 {"label_asym_id":"A","label_seq_id":193},
 {"label_asym_id":"A","label_seq_id":219}]"""

BACKBONE_DISTANCE_TOLERANCE_DOC = "Backbone distance tolerance in A, integer 0-3 (default 1)."

SIDE_CHAIN_DISTANCE_TOLERANCE_DOC = "Side-chain distance tolerance in A, integer 0-3 (default 1)."

ANGLE_TOLERANCE_DOC = "Angle tolerance in multiples of 20 degrees, integer 0-3 (default 1)."

RMSD_CUTOFF_DOC = "Maximum RMSD of accepted hits (default 2.0)."

ATOM_PAIRING_SCHEME_DOC = "ALL, BACKBONE, SIDE_CHAIN (default), or PSEUDO_ATOMS."

MOTIF_PRUNING_STRATEGY_DOC = "NONE or KRUSKAL (default)."

EXCHANGES_DOC = (
    'Optional per-position residue alternatives, each {"residue_id": {...}, "allowed": '
    "[<3-letter codes>]}, to match variants of the motif."
)
