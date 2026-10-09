"""Plain words for feature types whose names do not say what they are. Hand-written.

FeaturesType names such as HELIX_P, RSRZ or OWAB are codes, and the APIs describe none of them
(the Data API lists the values, Sequence Coordinates returns them; neither explains them), so
nothing here could be generated. Feature-type search (queries.find_feature_types, behind the
suggestions a wrong name gets from rcsb_seqcoord_annotations) matches these words with the
names, so "secondary structure" finds HELIX_P and "electron density fit" finds RSRZ.

Only names an agent could not match from a concept are covered: PHOSPHORYLATION or
SIGNAL_PEPTIDE need nothing. tests/test_feature_types.py checks every key is a real type.
"""

# What the types of each Data API field are (feature_types.FEATURE_TYPES_BY_FIELD), searched
# for every type the field lists: "bond" finds the struct_conn types, "modification" the
# protein modification types.
FIELD_NOTES = {
    "interface.rcsb_interface_partner.interface_partner_feature.type": "interface between chains",
    "uniprot.rcsb_uniprot_feature.type": "UniProt sequence annotation",
    "polymer_entity.rcsb_polymer_entity_feature.type": "entity sequence annotation",
    "polymer_entity_instance.rcsb_polymer_instance_feature.type": "chain structure annotation",
    "polymer_entity_instance.rcsb_polymer_struct_conn.connect_type": "bond or connection between residues",
    "polymer_entity_instance.pdbx_modification_feature.category": "protein chemical modification category",
    "polymer_entity_instance.pdbx_modification_feature.type": "protein chemical modification",
}

# Families named by a common prefix.
PREFIX_NOTES = {
    "MA_QA_METRIC_LOCAL_TYPE_": "per-residue quality or confidence of a computed model (AlphaFold, ModelArchive)",
    "IMGT_ANTIBODY_": "antibody immunoglobulin annotation (IMGT)",
    "SABDAB_ANTIBODY_": "antibody annotation (SAbDab)",
    "MOGUL_": "geometry outlier of a non-standard or modified residue in the chain (Mogul), structure validation",
}

FEATURE_TYPE_NOTES = {
    # secondary structure
    "HELIX_P": "helix: alpha, 3-10 or pi helices, secondary structure",
    "HELX_LH_PP_P": "left-handed polyproline helix, secondary structure",
    "HELX_RH_3_T_P": "right-handed 3-10 helix, secondary structure",
    "HELX_RH_AL_P": "right-handed alpha helix, secondary structure",
    "HELX_RH_PI_P": "right-handed pi helix, secondary structure",
    "SHEET": "beta strands of a beta sheet, secondary structure",
    "STRN": "beta strand, secondary structure",
    "TURN_TY_1_P": "turn, secondary structure",
    "BEND": "bend, secondary structure",
    # domains and families
    "CATH": "structural domain classification (CATH)",
    "ECOD": "structural domain classification (ECOD)",
    "SCOP": "structural domain classification (SCOPe)",
    "SCOP_2_FAMILY": "structural domain family (SCOP2)",
    "SCOP_2_SUPERFAMILY": "structural domain superfamily (SCOP2)",
    "SCOP_2_B_SUPERFAMILY": "structural domain superfamily (SCOP2B)",
    "PFAM": "protein family domain (Pfam)",
    "DOMAIN": "domain (UniProt)",
    # ligands, surface, membrane, interfaces
    "LIGAND_INTERACTION": "ligand binding residues, contacts with a ligand",
    "LIGAND_COVALENT_LINKAGE": "residue covalently bound to a ligand",
    "LIGAND_METAL_COORDINATION_LINKAGE": "residue coordinating a metal ion",
    "ASA": "solvent accessible surface area, exposed or buried residues",
    "ASA_BOUND": "accessible surface area of each residue in the complex; buried surface is "
                 "ASA_UNBOUND minus ASA_BOUND, interface",
    "ASA_UNBOUND": "accessible surface area of each residue of the chain alone; buried surface is "
                   "ASA_UNBOUND minus ASA_BOUND, interface",
    "MEMBRANE_SEGMENT": "transmembrane segment in the structure (PDBTM)",
    # what the model covers, and how well
    "UNOBSERVED_RESIDUE_XYZ": "missing unmodeled residues without coordinates, gaps or chain breaks",
    "UNOBSERVED_ATOM_XYZ": "partially modeled residues missing atoms",
    "ZERO_OCCUPANCY_RESIDUE_XYZ": "residues modeled with zero occupancy",
    "ZERO_OCCUPANCY_ATOM_XYZ": "atoms modeled with zero occupancy",
    "AVERAGE_OCCUPANCY": "average occupancy per residue",
    "OWAB": "B-factor, occupancy-weighted average temperature factor",
    "RSR": "real-space R, fit to electron density, structure validation",
    "RSRZ": "real-space R Z-score, fit to electron density, structure validation",
    "RSRZ_OUTLIER": "real-space R Z-score outlier, fit to electron density, structure validation",
    "RSCC": "real-space correlation coefficient, fit to electron density, structure validation",
    "RSCC_OUTLIER": "real-space correlation outlier, fit to electron density, structure validation",
    "NATOMS_EDS": "atoms in electron density, structure validation",
    "Q_SCORE": "cryo-EM map-model fit, resolvability, structure validation",
    "CLASHES": "steric clashes, structure validation",
    "SYMM_CLASHES": "symmetry-related steric clashes, structure validation",
    "ANGLE_OUTLIER": "bond angle geometry outlier, structure validation",
    "ANGLE_OUTLIERS": "bond angle geometry outliers, structure validation",
    "BOND_OUTLIER": "bond length geometry outlier, structure validation",
    "BOND_OUTLIERS": "bond length geometry outliers, structure validation",
    "CHIRAL_OUTLIERS": "chirality outliers, structure validation",
    "PLANE_OUTLIERS": "planarity outliers, structure validation",
    "RAMACHANDRAN_OUTLIER": "backbone torsion Ramachandran outlier, structure validation",
    "ROTAMER_OUTLIER": "side-chain rotamer outlier, structure validation",
    "STEREO_OUTLIER": "stereochemistry outlier, structure validation",
    "CIS_PEPTIDE": "cis peptide bond",
    "METAL_COORDINATION": "metal ion coordination bond, e.g. zinc, iron or calcium",
    "MA_QA_METRIC_LOCAL_TYPE_PTM": "predicted TM-score (pTM) of a computed model",
    "MA_QA_METRIC_LOCAL_TYPE_IPTM": "interface predicted TM-score (ipTM) of a computed model",
    "HEME_HEME_LIKE": "covalently attached heme, e.g. cytochrome c, protein modification category",
    # entity annotations
    "ARTIFACT": "expression tag, linker or cloning artifact",
    "CARD_MODEL": "antibiotic resistance annotation (CARD)",
    "DISORDER": "predicted intrinsically disordered region (IUPred)",
    "DISORDER_BINDING": "predicted disordered binding region (ANCHOR)",
    "HYDROPATHY": "hydropathy, hydrophobicity profile",
    "MUTATION": "engineered mutation relative to the reference sequence",
    "MODIFIED_MONOMER": "modified residue in the sequence",
    "NON_STANDARD_MONOMER": "non-standard residue and its parent residue",
    # UniProt annotations
    "ACTIVE_SITE": "enzyme active site, catalytic residues",
    "BINDING_SITE": "binding site of a ligand, metal ion, calcium or nucleotide",
    "METAL_ION_BINDING_SITE": "older UniProt category, current entries use BINDING_SITE",
    "CALCIUM_BINDING_REGION": "older UniProt category, current entries use BINDING_SITE",
    "NUCLEOTIDE_PHOSPHATE_BINDING_REGION": "older UniProt category, current entries use BINDING_SITE",
    "CHAIN": "mature protein chain",
    "PEPTIDE": "released active peptide",
    "PROPEPTIDE": "propeptide removed on maturation",
    "SITE": "functional site, e.g. cleavage site",
    "CROSS_LINK": "covalent cross-link, e.g. isopeptide (ubiquitination, SUMOylation) or thioether",
    "MODIFIED_RESIDUE": "post-translational modification (PTM), e.g. phosphorylation or acetylation",
    "MUTAGENESIS_SITE": "experimental mutation and its effect",
    "SEQUENCE_VARIANT": "natural variant, polymorphism or disease mutation",
    "SPLICE_VARIANT": "isoform sequence difference",
    "SEQUENCE_CONFLICT": "sequence difference between reports",
    "NON_TERMINAL_RESIDUE": "sequence fragment boundary",
    "UNSURE_RESIDUE": "uncertain residue in the sequence",
    "NON_STANDARD_AMINO_ACID": "selenocysteine or pyrrolysine",
    "TOPOLOGICAL_DOMAIN": "membrane topology: cytoplasmic or extracellular region",
    "TRANSIT_PEPTIDE": "organelle targeting peptide",
    "LIPID_MOIETY_BINDING_REGION": "lipidation, e.g. palmitoylation, myristoylation, prenylation "
                                   "(farnesyl, geranylgeranyl) or GPI anchor",
    "GLYCOSYLATION_SITE": "glycosylation site, N-linked or O-linked glycan",
    "INITIATOR_METHIONINE": "removed initiator methionine",
    "COMPOSITIONALLY_BIASED_REGION": "low-complexity region",
    "REGION_OF_INTEREST": "region of interest, e.g. disordered or interaction region",
    "SHORT_SEQUENCE_MOTIF": "short sequence motif",
    # glycosylation recorded on chains
    "N_GLYCOSYLATION_SITE": "N-linked glycosylation site",
    "O_GLYCOSYLATION_SITE": "O-linked glycosylation site",
    "S_GLYCOSYLATION_SITE": "S-linked glycosylation site",
    "C_MANNOSYLATION_SITE": "C-mannosylation site, glycosylation",
}


# UniProt categories replaced by another type in current entries (UniProt folded metal, calcium
# and nucleotide binding into "Binding site" in 2022): still valid names, ranked after every
# current type so "metal binding" leads with BINDING_SITE.
SUPERSEDED = {
    "METAL_ION_BINDING_SITE": "BINDING_SITE",
    "CALCIUM_BINDING_REGION": "BINDING_SITE",
    "NUCLEOTIDE_PHOSPHATE_BINDING_REGION": "BINDING_SITE",
}


def note_for(name: str) -> str:
    """The plain words for a feature type, or "" when its name says it."""
    if name in FEATURE_TYPE_NOTES:
        return FEATURE_TYPE_NOTES[name]
    return next((note for prefix, note in PREFIX_NOTES.items() if name.startswith(prefix)), "")
