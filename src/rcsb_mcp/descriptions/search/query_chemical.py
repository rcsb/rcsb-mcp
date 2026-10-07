"""Argument descriptions for rcsb_query_chemical (see the package docstring for why)."""

__all__ = [
    "VALUE_DOC",
    "QUERY_TYPE_DOC",
    "DESCRIPTOR_TYPE_DOC",
    "MATCH_TYPE_DOC",
    "MATCH_SUBSET_DOC",
]

VALUE_DOC = (
    'The descriptor (SMILES like "CC(=O)Oc1ccccc1C(=O)O", or an InChI string) or the formula '
    '(e.g. "C9H8O4"). Case is preserved — element symbols and SMILES are case-sensitive.'
)

QUERY_TYPE_DOC = '"descriptor" (default) or "formula".'

DESCRIPTOR_TYPE_DOC = '"SMILES" (default) or "InChI"; descriptor queries only.'

MATCH_TYPE_DOC = (
    "How strictly to match the graph (descriptor queries only). Whole-molecule: graph-exact / "
    "graph-strict / graph-relaxed (default) / graph-relaxed-stereo, or fingerprint-similarity "
    'for "chemically similar". Substructure — find larger molecules CONTAINING this fragment '
    '— use a sub-struct-graph-* variant (e.g. "sub-struct-graph-relaxed").'
)

MATCH_SUBSET_DOC = (
    "Formula queries only. True matches components that merely contain the given atoms (and "
    "possibly others); False (default) requires the formula to match exactly."
)
