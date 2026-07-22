"""Searchable RCSB **structure** (text) attributes.

Curated catalog; see scripts/generate_chemical_attributes.py --verify-structure,
which regenerates this from the live metadata schema and asserts it reproduces
this file on attribute path, type, and operators.
"""

from rcsb_mcp.attribute_types import SearchAttribute

SEARCH_ATTRIBUTES: list[SearchAttribute] = [
    {
        "attribute": "pdbx_entity_nonpoly.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A name for the non-polymer entity"
    },
    {
        "attribute": "rcsb_nonpolymer_entity.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of special aspects of the entity."
    },
    {
        "attribute": "rcsb_nonpolymer_entity.formula_weight",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Formula mass (KDa) of the entity."
    },
    {
        "attribute": "rcsb_nonpolymer_entity.pdbx_description",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of the nonpolymer entity."
    },
    {
        "attribute": "rcsb_nonpolymer_entity.pdbx_number_of_molecules",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of molecules of the nonpolymer entity in the entry."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_annotation.annotation_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "An identifier for the annotation."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_annotation.comp_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Non-polymer(ligand) chemical component identifier for the entity."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_annotation.description",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description for the annotation."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_annotation.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A name for the annotation."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_annotation.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A type or category of the annotation. Allowed Values: SUBJECT_OF_INVESTIGATION"
    },
    {
        "attribute": "rcsb_nonpolymer_entity_annotation.annotation_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent lineage depth (1-N)"
    },
    {
        "attribute": "rcsb_nonpolymer_entity_annotation.annotation_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class identifiers."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_annotation.annotation_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class names."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_container_identifiers.chem_ref_def_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The chemical reference definition identifier for the entity in this container."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_container_identifiers.nonpolymer_comp_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Non-polymer(ligand) chemical component identifier for the entity in this container."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_container_identifiers.prd_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The BIRD identifier for the entity in this container."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_container_identifiers.rcsb_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A unique identifier for each object in this entity container formed by an underscore separated concatenation of entry and entity identifiers."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_feature.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A type or category of the feature. Allowed Values: SUBJECT_OF_INVESTIGATION"
    },
    {
        "attribute": "rcsb_nonpolymer_entity_feature_summary.count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The feature count."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_feature_summary.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Type or category of the feature. Allowed Values: SUBJECT_OF_INVESTIGATION"
    },
    {
        "attribute": "rcsb_nonpolymer_entity_keywords.text",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Keywords describing this non-polymer entity."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_name_com.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A common name for the nonpolymer entity."
    },
    {
        "attribute": "rcsb_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A unique identifier for each object in this entity container formed by an underscore separated concatenation of entry and entity identifiers."
    },
    {
        "attribute": "chem_comp.formula_weight",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Formula mass of the chemical component."
    },
    {
        "attribute": "chem_comp.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The full name of the component."
    },
    {
        "attribute": "chem_comp.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "For standard polymer components, the type of the monomer. Note that monomers that will form polymers are of three types: linking monomers, monomers with some type of N-terminal (or 5') cap and monomers with some type of C-terminal (or 3') cap. Allowed Values: D-beta-peptide, C-gamma linking, D-gamma-peptide, C-delta linking, D-peptide COOH carboxy terminus, D-peptide NH3 amino terminus, D-peptide linking, D-saccharide, D-saccharide, alpha linking, D-saccharide, beta linking, DNA OH 3 prime terminus, DNA OH 5 prime terminus, DNA linking, L-DNA linking, L-RNA linking, L-beta-peptide, C-gamma linking, L-gamma-peptide, C-delta linking, L-peptide COOH carboxy terminus, L-peptide NH3 amino terminus, L-peptide linking, L-saccharide, L-saccharide, alpha linking, L-saccharide, beta linking, RNA OH 3 prime terminus, RNA OH 5 prime terminus, RNA linking, non-polymer, other, peptide linking, peptide-like, saccharide"
    },
    {
        "attribute": "pdbx_reference_molecule.class",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Broadly defines the function of the entity. Allowed Values: Antagonist, Anthelmintic, Antibiotic, Antibiotic, Anthelmintic, Antibiotic, Antimicrobial, Antibiotic, Antineoplastic, Anticancer, Anticoagulant, Anticoagulant, Antithrombotic, Antifungal, Antigen, Antiinflammatory, Antimicrobial, Antimicrobial, Antiparasitic, Antibiotic, Antimicrobial, Antiretroviral, Antimicrobial, Antitumor, Antineoplastic, Antiparasitic, Antiretroviral, Antithrombotic, Antitumor, Antiviral, CASPASE inhibitor, Chaperone binding, Drug delivery, Enzyme inhibitor, Glycan component, Growth factor, Immunosuppressant, Inducer, Inhibitor, Lantibiotic, Metabolism, Metal transport, Nutrient, Oxidation-reduction, Protein binding, Receptor, Substrate analog, Synthetic opioid, Thrombin inhibitor, Thrombin inhibitor, Trypsin inhibitor, Toxin, Transition state mimetic, Transport activator, Trypsin inhibitor, Unknown, Water retention"
    },
    {
        "attribute": "pdbx_reference_molecule.description",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Description of this molecule."
    },
    {
        "attribute": "pdbx_reference_molecule.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A name of the entity."
    },
    {
        "attribute": "pdbx_reference_molecule.prd_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The value of _pdbx_reference_molecule.prd_id is the unique identifier for the reference molecule in this family.  By convention this ID uniquely identifies the reference molecule in in the PDB reference dictionary.  The ID has the template form PRD_dddddd (e.g. PRD_000001)"
    },
    {
        "attribute": "pdbx_reference_molecule.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Defines the structural classification of the entity. Allowed Values: Amino acid, Aminoglycoside, Ansamycin, Anthracycline, Anthraquinone, Chalkophore, Chalkophore, Polypeptide, Chromophore, Cyclic depsipeptide, Cyclic lipopeptide, Cyclic peptide, Glycopeptide, Heterocyclic, Imino sugar, Keto acid, Lipoglycopeptide, Lipopeptide, Macrolide, Non-polymer, Nucleoside, Oligopeptide, Oligosaccharide, Peptaibol, Peptide-like, Polycyclic, Polypeptide, Polysaccharide, Quinolone, Siderophore, Thiolactone, Thiopeptide, Unknown"
    },
    {
        "attribute": "pdbx_reference_molecule_family.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The entity family name."
    },
    {
        "attribute": "pdbx_reference_molecule_related_structures.db_code",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The database identifier code for the related structure reference."
    },
    {
        "attribute": "pdbx_reference_molecule_synonyms.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A synonym name for the entity."
    },
    {
        "attribute": "rcsb_chem_comp_annotation.annotation_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "An identifier for the annotation."
    },
    {
        "attribute": "rcsb_chem_comp_annotation.description",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description for the annotation."
    },
    {
        "attribute": "rcsb_chem_comp_annotation.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A name for the annotation."
    },
    {
        "attribute": "rcsb_chem_comp_annotation.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A type or category of the annotation. Allowed Values: ATC, Carbohydrate Anomer, Carbohydrate Isomer, Carbohydrate Primary Carbonyl Group, Carbohydrate Ring, Generating Enzyme, Modification Type, PSI-MOD"
    },
    {
        "attribute": "rcsb_chem_comp_annotation.annotation_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent lineage depth (1-N)"
    },
    {
        "attribute": "rcsb_chem_comp_annotation.annotation_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class identifiers."
    },
    {
        "attribute": "rcsb_chem_comp_annotation.annotation_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class names."
    },
    {
        "attribute": "rcsb_chem_comp_container_identifiers.comp_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The chemical component identifier."
    },
    {
        "attribute": "rcsb_chem_comp_container_identifiers.drugbank_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The DrugBank identifier corresponding to the chemical component."
    },
    {
        "attribute": "rcsb_chem_comp_container_identifiers.prd_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The BIRD definition identifier."
    },
    {
        "attribute": "rcsb_chem_comp_container_identifiers.rcsb_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A unique identifier for the chemical definition in this container."
    },
    {
        "attribute": "rcsb_chem_comp_descriptor.InChIKey",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Standard IUPAC International Chemical Identifier (InChI) descriptor key for the chemical component  InChI, the IUPAC International Chemical Identifier, by Stephen R Heller, Alan McNaught, Igor Pletnev, Stephen Stein and Dmitrii Tchekhovskoi, Journal of Cheminformatics, 2015, 7:23"
    },
    {
        "attribute": "rcsb_chem_comp_info.atom_count_chiral",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Chemical component chiral atom count"
    },
    {
        "attribute": "rcsb_chem_comp_info.atom_count_heavy",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Chemical component heavy atom count"
    },
    {
        "attribute": "rcsb_chem_comp_info.bond_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Chemical component total bond count"
    },
    {
        "attribute": "rcsb_chem_comp_info.bond_count_aromatic",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Chemical component aromatic bond count"
    },
    {
        "attribute": "rcsb_chem_comp_info.initial_deposition_date",
        "type": "date",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The date the chemical definition was first deposited in the PDB repository."
    },
    {
        "attribute": "rcsb_chem_comp_info.initial_release_date",
        "type": "date",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The initial date the chemical definition was released in the PDB repository."
    },
    {
        "attribute": "rcsb_chem_comp_related.resource_accession_code",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The resource identifier code for the related chemical reference."
    },
    {
        "attribute": "rcsb_chem_comp_related.resource_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The resource name for the related chemical reference. Allowed Values: CAS, CCDC/CSD, COD, ChEBI, ChEMBL, DrugBank, Pharos, PubChem, RESID"
    },
    {
        "attribute": "rcsb_chem_comp_synonyms.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The synonym of this particular chemical component."
    },
    {
        "attribute": "rcsb_chem_comp_synonyms.provenance_source",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The provenance of this synonym. Allowed Values: ACDLabs, Author, ChEBI, ChEMBL, DrugBank, GMML, Lexichem, OpenEye OEToolkits, OpenEye/Lexichem, PDB Reference Data, PDB Reference Data (Preferred), PDB-CARE, PubChem, RESID"
    },
    {
        "attribute": "rcsb_chem_comp_synonyms.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "This data item contains the synonym type. Allowed Values: Brand Name, Common Name, Condensed IUPAC Carbohydrate Symbol, IUPAC Carbohydrate Symbol, Preferred Common Name, Preferred Name, Preferred Synonym, SNFG Carbohydrate Symbol, Synonym, Systematic Name"
    },
    {
        "attribute": "rcsb_chem_comp_target.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The chemical component target name."
    },
    {
        "attribute": "pdbx_struct_assembly.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of special aspects of the macromolecular assembly.  In the PDB, 'representative helical assembly', 'complete point assembly', 'complete icosahedral assembly', 'software_defined_assembly', 'author_defined_assembly', and 'author_and_software_defined_assembly' are considered \"biologically relevant assemblies."
    },
    {
        "attribute": "pdbx_struct_assembly.oligomeric_details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Provides the details of the oligomeric state of the assembly."
    },
    {
        "attribute": "pdbx_struct_assembly.rcsb_details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A filtered description of the macromolecular assembly. Allowed Values: author_and_software_defined_assembly, author_defined_assembly, software_defined_assembly"
    },
    {
        "attribute": "pdbx_struct_assembly_auth_evidence.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Provides any additional information regarding the evidence of this assembly"
    },
    {
        "attribute": "pdbx_struct_assembly_auth_evidence.experimental_support",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Provides the experimental method to determine the state of this assembly Allowed Values: NMR Distance Restraints, NMR relaxation study, SAXS, assay for oligomerization, cross-linking, electron microscopy, equilibrium centrifugation, fluorescence resonance energy transfer, gel filtration, homology, immunoprecipitation, isothermal titration calorimetry, light scattering, mass spectrometry, microscopy, native gel electrophoresis, none, scanning transmission electron microscopy, surface plasmon resonance"
    },
    {
        "attribute": "rcsb_assembly_annotation.annotation_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "An identifier for the annotation."
    },
    {
        "attribute": "rcsb_assembly_annotation.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A name for the annotation."
    },
    {
        "attribute": "rcsb_assembly_annotation.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A type or category of the annotation. Allowed Values: MCSA"
    },
    {
        "attribute": "rcsb_assembly_container_identifiers.assembly_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Assembly identifier for the container."
    },
    {
        "attribute": "rcsb_assembly_container_identifiers.entry_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Entry identifier for the container."
    },
    {
        "attribute": "rcsb_assembly_container_identifiers.rcsb_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A unique identifier for each object in this assembly container formed by a dash separated concatenation of entry and assembly identifiers."
    },
    {
        "attribute": "rcsb_assembly_info.atom_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The assembly non-hydrogen atomic coordinate count."
    },
    {
        "attribute": "rcsb_assembly_info.branched_atom_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The assembly non-hydrogen branched entity atomic coordinate count."
    },
    {
        "attribute": "rcsb_assembly_info.branched_entity_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct branched entities in the generated assembly."
    },
    {
        "attribute": "rcsb_assembly_info.branched_entity_instance_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of branched instances in the generated assembly data set. This is the total count of branched entity instances generated in the assembly coordinate data."
    },
    {
        "attribute": "rcsb_assembly_info.deuterated_water_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The assembly deuterated water molecule count."
    },
    {
        "attribute": "rcsb_assembly_info.hydrogen_atom_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The assembly hydrogen atomic coordinate count."
    },
    {
        "attribute": "rcsb_assembly_info.modeled_polymer_monomer_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of modeled polymer monomers in the assembly coordinate data. This is the total count of monomers with reported coordinate data for all polymer entity instances in the generated assembly coordinate data."
    },
    {
        "attribute": "rcsb_assembly_info.na_polymer_entity_types",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Nucleic acid polymer entity type categories describing the generated assembly. Allowed Values: DNA (only), DNA/RNA (only), NA-hybrid (only), Other, RNA (only)"
    },
    {
        "attribute": "rcsb_assembly_info.nonpolymer_atom_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The assembly non-hydrogen non-polymer entity atomic coordinate count."
    },
    {
        "attribute": "rcsb_assembly_info.nonpolymer_entity_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct non-polymer entities in the generated assembly exclusive of solvent."
    },
    {
        "attribute": "rcsb_assembly_info.nonpolymer_entity_instance_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of non-polymer instances in the generated assembly data set exclusive of solvent. This is the total count of non-polymer entity instances generated in the assembly coordinate data."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_atom_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The assembly non-hydrogen polymer entity atomic coordinate count."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_composition",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Categories describing the polymer entity composition for the generated assembly. Allowed Values: DNA, DNA/RNA, NA-hybrid, NA/oligosaccharide, RNA, heteromeric protein, homomeric protein, oligosaccharide, other, other type composition, other type pair, protein/NA, protein/NA/oligosaccharide, protein/oligosaccharide"
    },
    {
        "attribute": "rcsb_assembly_info.polymer_entity_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct polymer entities in the generated assembly."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_entity_count_DNA",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct DNA polymer entities in the generated assembly."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_entity_count_RNA",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct RNA polymer entities in the generated assembly."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_entity_count_nucleic_acid",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct nucleic acid polymer entities (DNA or RNA) in the generated assembly."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_entity_count_nucleic_acid_hybrid",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct hybrid nucleic acid polymer entities in the generated assembly."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_entity_count_protein",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct protein polymer entities in the generated assembly."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_entity_instance_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of polymer instances in the generated assembly data set. This is the total count of polymer entity instances generated in the assembly coordinate data."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_entity_instance_count_DNA",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of DNA polymer instances in the generated assembly data set. This is the total count of DNA polymer entity instances generated in the assembly coordinate data."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_entity_instance_count_RNA",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of RNA polymer instances in the generated assembly data set. This is the total count of RNA polymer entity instances generated in the assembly coordinate data."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_entity_instance_count_nucleic_acid",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of nucleic acid polymer instances in the generated assembly data set. This is the total count of nucleic acid polymer entity instances generated in the assembly coordinate data."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_entity_instance_count_nucleic_acid_hybrid",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of hybrid nucleic acide polymer instances in the generated assembly data set. This is the total count of hybrid nucleic acid polymer entity instances generated in the assembly coordinate data."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_entity_instance_count_protein",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of protein polymer instances in the generated assembly data set. This is the total count of protein polymer entity instances generated in the assembly coordinate data."
    },
    {
        "attribute": "rcsb_assembly_info.polymer_monomer_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of polymer monomers in sample entity instances comprising the assembly data set. This is the total count of monomers for all polymer entity instances in the generated assembly coordinate data."
    },
    {
        "attribute": "rcsb_assembly_info.selected_polymer_entity_types",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Selected polymer entity type categories describing the generated assembly. Allowed Values: Nucleic acid (only), Other, Protein (only), Protein/NA"
    },
    {
        "attribute": "rcsb_assembly_info.solvent_atom_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The assembly non-hydrogen solvent atomic coordinate count."
    },
    {
        "attribute": "rcsb_assembly_info.solvent_entity_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct solvent entities in the generated assembly."
    },
    {
        "attribute": "rcsb_assembly_info.solvent_entity_instance_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of solvent instances in the generated assembly data set. This is the total count of solvent entity instances generated in the assembly coordinate data."
    },
    {
        "attribute": "rcsb_assembly_info.unmodeled_polymer_monomer_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of unmodeled polymer monomers in the assembly coordinate data. This is the total count of monomers with unreported coordinate data for all polymer entity instances in the generated assembly coordinate data."
    },
    {
        "attribute": "rcsb_struct_symmetry.kind",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The granularity at which the symmetry calculation is performed. In 'Global Symmetry' all polymeric subunits in assembly are used. In 'Local Symmetry' only a subset of polymeric subunits is considered. In 'Pseudo Symmetry' the threshold for subunits similarity is relaxed. Allowed Values: Global Symmetry, Local Symmetry, Pseudo Symmetry"
    },
    {
        "attribute": "rcsb_struct_symmetry.oligomeric_state",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Oligomeric state refers to a composition of polymeric subunits in quaternary structure. Quaternary structure may be composed either exclusively of several copies of identical subunits, in which case they are termed homo-oligomers, or alternatively by at least one copy of different subunits (hetero-oligomers). Quaternary structure composed of a single subunit is denoted as 'Monomer'."
    },
    {
        "attribute": "rcsb_struct_symmetry.symbol",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Symmetry symbol refers to point group or helical symmetry of identical polymeric subunits in Schoenflies notation. Contains point group symbol (e.g., C2, C5, D2, T, O, I) or H for helical symmetry."
    },
    {
        "attribute": "rcsb_struct_symmetry.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Symmetry type refers to point group or helical symmetry of identical polymeric subunits. Contains point group types (e.g. Cyclic, Dihedral) or Helical for helical symmetry. Allowed Values: Asymmetric, Cyclic, Dihedral, Helical, Icosahedral, Octahedral, Tetrahedral"
    },
    {
        "attribute": "rcsb_struct_symmetry.clusters.avg_rmsd",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Average RMSD between members of a given cluster."
    },
    {
        "attribute": "rcsb_struct_symmetry_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Hierarchy depth."
    },
    {
        "attribute": "rcsb_struct_symmetry_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Automatically assigned ID to uniquely identify the symmetry term in the Protein Symmetry Browser."
    },
    {
        "attribute": "rcsb_struct_symmetry_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A human-readable term describing protein symmetry."
    },
    {
        "attribute": "rcsb_repository_holdings_current.repository_content_types",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The list of content types associated with this entry. Allowed Values: 2fo-fc Map, Combined NMR data (NEF), Combined NMR data (NMR-STAR), FASTA sequence, Map Coefficients, NMR chemical shifts, NMR restraints V1, NMR restraints V2, assembly PDB, assembly mmCIF, entry PDB, entry PDB bundle, entry PDBML, entry mmCIF, fo-fc Map, structure factors, validation 2fo-fc coefficients, validation data mmCIF, validation fo-fc coefficients, validation report, validation slider image"
    },
    {
        "attribute": "pdbx_vrpt_summary_entity_fit_to_map.Q_score",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The calculated average Q-score."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_instance_container_identifiers.asym_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Instance identifier for this container."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_instance_container_identifiers.auth_asym_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Author instance identifier for this container."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_instance_container_identifiers.comp_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Component identifier for non-polymer entity instance."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_instance_container_identifiers.entity_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Entity identifier for the container."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_instance_container_identifiers.entry_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Entry identifier for the container."
    },
    {
        "attribute": "rcsb_nonpolymer_entity_instance_container_identifiers.rcsb_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A unique identifier for each object in this entity instance container formed by an 'dot' (.) separated concatenation of entry and entity instance identifiers."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_annotation.annotation_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "An identifier for the annotation."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_annotation.comp_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Non-polymer (ligand) chemical component identifier."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_annotation.description",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description for the annotation."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_annotation.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A name for the annotation."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_annotation.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A type or category of the annotation. Allowed Values: HAS_COVALENT_LINKAGE, HAS_METAL_COORDINATION_LINKAGE, HAS_NO_COVALENT_LINKAGE, IS_RSCC_OUTLIER, IS_RSRZ_OUTLIER"
    },
    {
        "attribute": "rcsb_nonpolymer_instance_annotation.annotation_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent lineage depth (1-N)"
    },
    {
        "attribute": "rcsb_nonpolymer_instance_annotation.annotation_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class identifiers."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_annotation.annotation_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class names."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_validation_score.Q_score",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The Q-score for the non-polymer instance."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_validation_score.RSCC",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The real space correlation coefficient (RSCC) for the non-polymer entity instance."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_validation_score.RSR",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The real space R-value (RSR) for the non-polymer entity instance."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_validation_score.intermolecular_clashes",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of intermolecular MolProbity clashes cacluated for reported atomic coordinate records."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_validation_score.is_best_instance",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "This molecular instance is ranked as the best quality instance of this nonpolymer entity. Allowed Values: N, Y"
    },
    {
        "attribute": "rcsb_nonpolymer_instance_validation_score.is_subject_of_investigation",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "This molecular entity is identified as the subject of the current study. Allowed Values: N, Y"
    },
    {
        "attribute": "rcsb_nonpolymer_instance_validation_score.mogul_angle_outliers",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Number of bond angle outliers obtained from a CCDC Mogul survey of bond angles in the CSD small molecule crystal structure database. Outliers are defined as bond angles that have a Z-score less than -2 or greater than 2."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_validation_score.mogul_angles_RMSZ",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The root-mean-square value of the Z-scores of bond angles for the non-polymer instance in degrees obtained from a CCDC Mogul survey of bond angles in the CSD small molecule crystal structure database."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_validation_score.mogul_bond_outliers",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Number of bond distance outliers obtained from a CCDC Mogul survey of bond lengths in the CSD small molecule crystal structure database. Outliers are defined as bond distances that have a Z-score less than -2 or greater than 2."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_validation_score.mogul_bonds_RMSZ",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The root-mean-square value of the Z-scores of bond lengths for the nonpolymer instance in Angstroms obtained from a CCDC Mogul survey of bond lengths in the CSD small molecule crystal structure database."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_validation_score.ranking_model_fit",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The ranking of the model fit score component."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_validation_score.ranking_model_geometry",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The ranking of the model geometry score component."
    },
    {
        "attribute": "rcsb_nonpolymer_instance_validation_score.stereo_outliers",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Number of stereochemical/chirality errors."
    },
    {
        "attribute": "rcsb_target_neighbors.distance",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Distance value for this target interaction."
    },
    {
        "attribute": "rcsb_target_neighbors.target_asym_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The entity instance identifier for the target of interaction."
    },
    {
        "attribute": "rcsb_target_neighbors.target_comp_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The chemical component identifier for the target of interaction."
    },
    {
        "attribute": "rcsb_target_neighbors.target_entity_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The entity identifier for the target of interaction."
    },
    {
        "attribute": "rcsb_target_neighbors.target_is_bound",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A flag to indicate the nature of the target interaction is covalent or metal-coordination. Allowed Values: N, Y"
    },
    {
        "attribute": "rcsb_uniprot_container_identifiers.reference_sequence_identifiers.database_accession",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Reference database accession code"
    },
    {
        "attribute": "rcsb_uniprot_container_identifiers.reference_sequence_identifiers.database_isoform",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Reference database identifier for the sequence isoform"
    },
    {
        "attribute": "rcsb_uniprot_container_identifiers.reference_sequence_identifiers.database_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Reference database name"
    },
    {
        "attribute": "rcsb_uniprot_protein.name.value",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Name that allows to unambiguously identify a protein."
    },
    {
        "attribute": "rcsb_uniprot_annotation.annotation_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "An identifier for the annotation."
    },
    {
        "attribute": "rcsb_uniprot_annotation.description",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description for the annotation."
    },
    {
        "attribute": "rcsb_uniprot_annotation.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A name for the annotation."
    },
    {
        "attribute": "rcsb_uniprot_annotation.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A type or category of the annotation. Allowed Values: disease, phenotype, GO, InterPro"
    },
    {
        "attribute": "rcsb_uniprot_annotation.annotation_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent lineage depth (1-N)"
    },
    {
        "attribute": "rcsb_uniprot_annotation.annotation_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class identifiers."
    },
    {
        "attribute": "rcsb_uniprot_annotation.annotation_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class names."
    },
    {
        "attribute": "rcsb_uniprot_external_reference.reference_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": " Allowed Values: IMPC, GTEX, PHAROS"
    },
    {
        "attribute": "rcsb_branched_entity_instance_container_identifiers.asym_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Instance identifier for this container."
    },
    {
        "attribute": "rcsb_branched_entity_instance_container_identifiers.auth_asym_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Author instance identifier for this container."
    },
    {
        "attribute": "rcsb_branched_entity_instance_container_identifiers.entity_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Entity identifier for the container."
    },
    {
        "attribute": "rcsb_branched_entity_instance_container_identifiers.entry_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Entry identifier for the container."
    },
    {
        "attribute": "rcsb_branched_entity_instance_container_identifiers.rcsb_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A unique identifier for each object in this entity instance container formed by an 'dot' (.) separated concatenation of entry and entity instance identifiers."
    },
    {
        "attribute": "rcsb_branched_instance_annotation.annotation_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "An identifier for the annotation."
    },
    {
        "attribute": "rcsb_branched_instance_annotation.description",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description for the annotation."
    },
    {
        "attribute": "rcsb_branched_instance_annotation.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A name for the annotation."
    },
    {
        "attribute": "rcsb_branched_instance_annotation.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A type or category of the annotation. Allowed Values: CATH, SCOP"
    },
    {
        "attribute": "rcsb_branched_instance_annotation.annotation_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent lineage depth (1-N)"
    },
    {
        "attribute": "rcsb_branched_instance_annotation.annotation_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class identifiers."
    },
    {
        "attribute": "rcsb_branched_instance_annotation.annotation_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class names."
    },
    {
        "attribute": "rcsb_branched_instance_feature_summary.count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The feature count."
    },
    {
        "attribute": "rcsb_branched_instance_feature_summary.coverage",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The fractional feature coverage relative to the full branched entity."
    },
    {
        "attribute": "rcsb_branched_instance_feature_summary.maximum_length",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The maximum feature length."
    },
    {
        "attribute": "rcsb_branched_instance_feature_summary.minimum_length",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The minimum feature length."
    },
    {
        "attribute": "rcsb_branched_instance_feature_summary.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Type or category of the feature. Allowed Values: BINDING_SITE, CATH, MOGUL_ANGLE_OUTLIER, MOGUL_BOND_OUTLIER, RSCC_OUTLIER, RSRZ_OUTLIER, SCOP, STEREO_OUTLIER, UNOBSERVED_ATOM_XYZ, UNOBSERVED_RESIDUE_XYZ, ZERO_OCCUPANCY_ATOM_XYZ, ZERO_OCCUPANCY_RESIDUE_XYZ"
    },
    {
        "attribute": "rcsb_ligand_neighbors.distance",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Distance value for this ligand interaction."
    },
    {
        "attribute": "rcsb_ligand_neighbors.ligand_asym_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The entity instance identifier for the ligand interaction."
    },
    {
        "attribute": "rcsb_ligand_neighbors.ligand_comp_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The chemical component identifier for the ligand interaction."
    },
    {
        "attribute": "rcsb_ligand_neighbors.ligand_entity_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The entity identifier for the ligand of interaction."
    },
    {
        "attribute": "rcsb_ligand_neighbors.ligand_is_bound",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A flag to indicate the nature of the ligand interaction is covalent or metal-coordination. Allowed Values: N, Y"
    },
    {
        "attribute": "pdbx_entity_branch.rcsb_branched_component_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Number of constituent chemical components in the branched entity."
    },
    {
        "attribute": "pdbx_entity_branch.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The type of this branched oligosaccharide. Allowed Values: oligosaccharide"
    },
    {
        "attribute": "pdbx_entity_branch_descriptor.descriptor",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "This data item contains the descriptor value for this entity."
    },
    {
        "attribute": "pdbx_entity_branch_descriptor.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "This data item contains the descriptor type. Allowed Values: Glycam Condensed Core Sequence, Glycam Condensed Sequence, LINUCS, WURCS"
    },
    {
        "attribute": "rcsb_branched_entity.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of special aspects of the branched entity."
    },
    {
        "attribute": "rcsb_branched_entity.formula_weight",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Formula mass (KDa) of the branched entity."
    },
    {
        "attribute": "rcsb_branched_entity.pdbx_description",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of the branched entity."
    },
    {
        "attribute": "rcsb_branched_entity.pdbx_number_of_molecules",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of molecules of the branched entity in the entry."
    },
    {
        "attribute": "rcsb_branched_entity_annotation.annotation_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "An identifier for the annotation."
    },
    {
        "attribute": "rcsb_branched_entity_annotation.description",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description for the annotation."
    },
    {
        "attribute": "rcsb_branched_entity_annotation.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A name for the annotation."
    },
    {
        "attribute": "rcsb_branched_entity_annotation.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A type or category of the annotation."
    },
    {
        "attribute": "rcsb_branched_entity_annotation.annotation_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent lineage depth (1-N)"
    },
    {
        "attribute": "rcsb_branched_entity_annotation.annotation_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class identifiers."
    },
    {
        "attribute": "rcsb_branched_entity_annotation.annotation_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class names."
    },
    {
        "attribute": "rcsb_branched_entity_container_identifiers.chem_comp_monomers",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Unique list of monomer chemical component identifiers in the entity in this container."
    },
    {
        "attribute": "rcsb_branched_entity_container_identifiers.chem_ref_def_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The chemical reference definition identifier for the entity in this container."
    },
    {
        "attribute": "rcsb_branched_entity_container_identifiers.entity_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Entity identifier for the container."
    },
    {
        "attribute": "rcsb_branched_entity_container_identifiers.entry_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Entry identifier for the container."
    },
    {
        "attribute": "rcsb_branched_entity_container_identifiers.prd_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The BIRD identifier for the entity in this container."
    },
    {
        "attribute": "rcsb_branched_entity_container_identifiers.rcsb_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A unique identifier for each object in this entity container formed by an underscore separated concatenation of entry and entity identifiers."
    },
    {
        "attribute": "rcsb_branched_entity_container_identifiers.reference_identifiers.resource_accession",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Reference resource accession code"
    },
    {
        "attribute": "rcsb_branched_entity_container_identifiers.reference_identifiers.resource_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Reference resource name Allowed Values: GlyCosmos, GlyGen, GlyTouCan"
    },
    {
        "attribute": "rcsb_branched_entity_feature_summary.count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The feature count."
    },
    {
        "attribute": "rcsb_branched_entity_feature_summary.coverage",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The fractional feature coverage relative to the full branched entity."
    },
    {
        "attribute": "rcsb_branched_entity_feature_summary.maximum_length",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The maximum feature length."
    },
    {
        "attribute": "rcsb_branched_entity_feature_summary.minimum_length",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The minimum feature length."
    },
    {
        "attribute": "rcsb_branched_entity_feature_summary.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Type or category of the feature. Allowed Values: mutation"
    },
    {
        "attribute": "rcsb_branched_entity_keywords.text",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Keywords describing this branched entity."
    },
    {
        "attribute": "rcsb_branched_entity_name_com.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A common name for the branched entity."
    },
    {
        "attribute": "rcsb_branched_entity_name_sys.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The systematic name for the branched entity."
    },
    {
        "attribute": "audit_author.identifier_ORCID",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The Open Researcher and Contributor ID (ORCID)."
    },
    {
        "attribute": "audit_author.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The name of an author of this data block. If there are multiple authors, _audit_author.name is looped with _audit_author.address. The family name(s), followed by a comma and including any dynastic components, precedes the first name(s) or initial(s)."
    },
    {
        "attribute": "cell.angle_alpha",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell angle alpha of the reported structure in degrees."
    },
    {
        "attribute": "cell.angle_beta",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell angle beta of the reported structure in degrees."
    },
    {
        "attribute": "cell.angle_gamma",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell angle gamma of the reported structure in degrees."
    },
    {
        "attribute": "cell.length_a",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell length a corresponding to the structure reported in angstroms."
    },
    {
        "attribute": "cell.length_b",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell length b corresponding to the structure reported in angstroms."
    },
    {
        "attribute": "cell.length_c",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell length c corresponding to the structure reported in angstroms."
    },
    {
        "attribute": "citation.book_title",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The title of the book in which the citation appeared; relevant for books or book chapters."
    },
    {
        "attribute": "citation.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The value of _citation.id must uniquely identify a record in the CITATION list.  The _citation.id 'primary' should be used to indicate the citation that the author(s) consider to be the most pertinent to the contents of the data block.  Note that this item need not be a number; it can be any unique identifier."
    },
    {
        "attribute": "citation.journal_abbrev",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Abbreviated name of the cited journal as given in the Chemical Abstracts Service Source Index."
    },
    {
        "attribute": "citation.journal_id_ASTM",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The American Society for Testing and Materials (ASTM) code assigned to the journal cited (also referred to as the CODEN designator of the Chemical Abstracts Service); relevant for journal articles."
    },
    {
        "attribute": "citation.journal_id_ISSN",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The International Standard Serial Number (ISSN) code assigned to the journal cited; relevant for journal articles."
    },
    {
        "attribute": "citation.pdbx_database_id_DOI",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Document Object Identifier used by doi.org to uniquely specify bibliographic entry."
    },
    {
        "attribute": "citation.rcsb_authors",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Names of the authors of the citation; relevant for journal articles, books and book chapters. Names are separated by vertical bars.  The family name(s), followed by a comma and including any dynastic components, precedes the first name(s) or initial(s)."
    },
    {
        "attribute": "citation.rcsb_is_primary",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Flag to indicate a primary citation. Allowed Values: N, Y"
    },
    {
        "attribute": "citation.rcsb_journal_abbrev",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Normalized journal abbreviation."
    },
    {
        "attribute": "citation.title",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The title of the citation; relevant for journal articles, books and book chapters."
    },
    {
        "attribute": "citation.unpublished_flag",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Flag to indicate that this citation will not be published. Allowed Values: N, Y"
    },
    {
        "attribute": "citation.year",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The year of the citation; relevant for journal articles, books and book chapters."
    },
    {
        "attribute": "database_2.database_code",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The code assigned by the database identified in _database_2.database_id."
    },
    {
        "attribute": "database_2.pdbx_database_accession",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Extended accession code issued for for _database_2.database_code assigned by the database identified in _database_2.database_id."
    },
    {
        "attribute": "diffrn.ambient_pressure",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The mean hydrostatic pressure in kilopascals at which the intensities were measured."
    },
    {
        "attribute": "diffrn.ambient_temp",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The mean temperature in kelvins at which the intensities were measured."
    },
    {
        "attribute": "diffrn.crystal_support",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The physical device used to support the crystal during data collection."
    },
    {
        "attribute": "diffrn.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Special details of the diffraction measurement process. Should include information about source instability, crystal motion, degradation and so on."
    },
    {
        "attribute": "diffrn.pdbx_serial_crystal_experiment",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Y/N if using serial crystallography experiment in which multiple crystals contribute to each diffraction frame in the experiment. Allowed Values: N, Y"
    },
    {
        "attribute": "diffrn_detector.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of special aspects of the radiation detector."
    },
    {
        "attribute": "diffrn_detector.detector",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The general class of the radiation detector."
    },
    {
        "attribute": "diffrn_detector.pdbx_collection_date",
        "type": "date",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The date of data collection."
    },
    {
        "attribute": "diffrn_detector.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The make, model or name of the detector device used."
    },
    {
        "attribute": "diffrn_radiation.collimation",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The collimation or focusing applied to the radiation."
    },
    {
        "attribute": "diffrn_radiation.monochromator",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The method used to obtain monochromatic radiation. If a mono- chromator crystal is used, the material and the indices of the Bragg reflection are specified."
    },
    {
        "attribute": "diffrn_radiation.pdbx_diffrn_protocol",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "SINGLE WAVELENGTH, LAUE, or MAD."
    },
    {
        "attribute": "diffrn_source.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of special aspects of the radiation source used."
    },
    {
        "attribute": "diffrn_source.pdbx_synchrotron_beamline",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Synchrotron beamline."
    },
    {
        "attribute": "diffrn_source.pdbx_synchrotron_site",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Synchrotron site."
    },
    {
        "attribute": "diffrn_source.source",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The general class of the radiation source."
    },
    {
        "attribute": "diffrn_source.type",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The make, model or name of the source of radiation."
    },
    {
        "attribute": "em_2d_crystal_entity.angle_gamma",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell angle gamma in degrees."
    },
    {
        "attribute": "em_2d_crystal_entity.c_sampling_length",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Length used to sample the reciprocal lattice lines in the c-direction."
    },
    {
        "attribute": "em_2d_crystal_entity.length_a",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell length a in angstroms."
    },
    {
        "attribute": "em_2d_crystal_entity.length_b",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell length b in angstroms."
    },
    {
        "attribute": "em_2d_crystal_entity.length_c",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Thickness of 2D crystal"
    },
    {
        "attribute": "em_3d_crystal_entity.angle_alpha",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell angle alpha in degrees."
    },
    {
        "attribute": "em_3d_crystal_entity.angle_beta",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell angle beta in degrees."
    },
    {
        "attribute": "em_3d_crystal_entity.angle_gamma",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell angle gamma in degrees."
    },
    {
        "attribute": "em_3d_crystal_entity.length_a",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell length a in angstroms."
    },
    {
        "attribute": "em_3d_crystal_entity.length_b",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell length b in angstroms."
    },
    {
        "attribute": "em_3d_crystal_entity.length_c",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Unit-cell length c in angstroms."
    },
    {
        "attribute": "em_3d_crystal_entity.space_group_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Space group name."
    },
    {
        "attribute": "em_3d_crystal_entity.space_group_num",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Space group number."
    },
    {
        "attribute": "em_3d_fitting.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Any additional details regarding fitting of atomic coordinates into the 3DEM volume, including data and considerations from other methods used in computation of the model."
    },
    {
        "attribute": "em_3d_fitting.method",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The method used to fit atomic coordinates into the 3dem reconstructed map."
    },
    {
        "attribute": "em_3d_fitting.overall_b_value",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The overall B (temperature factor) value for the 3d-em volume."
    },
    {
        "attribute": "em_3d_fitting.ref_protocol",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The refinement protocol used. Allowed Values: AB INITIO MODEL, BACKBONE TRACE, FLEXIBLE FIT, OTHER, RIGID BODY FIT"
    },
    {
        "attribute": "em_3d_fitting.ref_space",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A flag to indicate whether fitting was carried out in real or reciprocal refinement space. Allowed Values: REAL, RECIPROCAL"
    },
    {
        "attribute": "em_3d_fitting.target_criteria",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The measure used to assess quality of fit of the atomic coordinates in the 3DEM map volume."
    },
    {
        "attribute": "em_3d_fitting_list.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Details about the model used in fitting."
    },
    {
        "attribute": "em_3d_reconstruction.actual_pixel_size",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The actual pixel size of the projection set of images in Angstroms."
    },
    {
        "attribute": "em_3d_reconstruction.algorithm",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The reconstruction algorithm/technique used to generate the map."
    },
    {
        "attribute": "em_3d_reconstruction.method",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The algorithm method used for the 3d-reconstruction."
    },
    {
        "attribute": "em_3d_reconstruction.nominal_pixel_size",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The nominal pixel size of the projection set of images in Angstroms."
    },
    {
        "attribute": "em_3d_reconstruction.num_class_averages",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of classes used in the final 3d reconstruction"
    },
    {
        "attribute": "em_3d_reconstruction.num_particles",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of 2D projections or 3D subtomograms used in the 3d reconstruction"
    },
    {
        "attribute": "em_3d_reconstruction.refinement_type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Indicates details on how the half-map used for resolution determination (usually by FSC) have been generated. Allowed Values: HALF-MAPS REFINED AGAINST SAME DATA, HALF-MAPS REFINED INDEPENDENTLY, HALF-MAPS REFINED INDEPENDENTLY WITH FREQUENCY RANGE OMITTED, HALF-MAPS REFINED WITH FREQUENCY RANGE OMITTED, OTHER"
    },
    {
        "attribute": "em_3d_reconstruction.resolution",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The final resolution (in angstroms) of the 3D reconstruction."
    },
    {
        "attribute": "em_3d_reconstruction.resolution_method",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The method used to determine the final resolution of the 3d reconstruction. The Fourier Shell Correlation criterion as a measure of resolution is based on the concept of splitting the (2D) data set into two halves; averaging each and comparing them using the Fourier Ring Correlation (FRC) technique."
    },
    {
        "attribute": "em_3d_reconstruction.symmetry_type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The type of symmetry applied to the reconstruction Allowed Values: 2D CRYSTAL, 3D CRYSTAL, HELICAL, POINT"
    },
    {
        "attribute": "em_ctf_correction.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Any additional details about CTF correction"
    },
    {
        "attribute": "em_ctf_correction.type",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Type of CTF correction applied"
    },
    {
        "attribute": "em_diffraction.camera_length",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The camera length (in millimeters). The camera length is the product of the objective focal length and the combined magnification of the intermediate and projector lenses when the microscope is operated in the diffraction mode."
    },
    {
        "attribute": "em_diffraction_shell.fourier_space_coverage",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Completeness of the structure factor data within this resolution shell, in percent"
    },
    {
        "attribute": "em_diffraction_shell.high_resolution",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "High resolution limit for this shell (angstroms)"
    },
    {
        "attribute": "em_diffraction_shell.low_resolution",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Low resolution limit for this shell (angstroms)"
    },
    {
        "attribute": "em_diffraction_shell.multiplicity",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Multiplicity (average number of measurements) for the structure factors in this resolution shell"
    },
    {
        "attribute": "em_diffraction_shell.num_structure_factors",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Number of measured structure factors in this resolution shell"
    },
    {
        "attribute": "em_diffraction_shell.phase_residual",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Phase residual for this resolution shell, in degrees"
    },
    {
        "attribute": "em_diffraction_stats.fourier_space_coverage",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Completeness of the structure factor data within the defined space group at the reported resolution (percent)."
    },
    {
        "attribute": "em_diffraction_stats.high_resolution",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "High resolution limit of the structure factor data, in angstroms"
    },
    {
        "attribute": "em_diffraction_stats.num_intensities_measured",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Total number of diffraction intensities measured (before averaging)"
    },
    {
        "attribute": "em_diffraction_stats.num_structure_factors",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Number of structure factors obtained (merged amplitudes + phases)"
    },
    {
        "attribute": "em_diffraction_stats.overall_phase_error",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Overall phase error in degrees"
    },
    {
        "attribute": "em_diffraction_stats.overall_phase_residual",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Overall phase residual in degrees"
    },
    {
        "attribute": "em_diffraction_stats.r_merge",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Rmerge value (percent)"
    },
    {
        "attribute": "em_diffraction_stats.r_sym",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Rsym value (percent)"
    },
    {
        "attribute": "em_embedding.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Staining procedure used in the specimen preparation."
    },
    {
        "attribute": "em_embedding.material",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The embedding material."
    },
    {
        "attribute": "em_entity_assembly.parent_id",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The parent of this assembly. This data item is an internal category pointer to _em_entity_assembly.id. By convention, the full assembly (top of hierarchy) is assigned parent id 0 (zero)."
    },
    {
        "attribute": "em_entity_assembly.source",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The type of source (e.g., natural source) for the component (sample or sample subcomponent) Allowed Values: MULTIPLE SOURCES, NATURAL, RECOMBINANT, SYNTHETIC"
    },
    {
        "attribute": "em_experiment.aggregation_state",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The aggregation/assembly state of the imaged specimen. Allowed Values: 2D ARRAY, 3D ARRAY, CELL, FILAMENT, HELICAL ARRAY, PARTICLE, TISSUE"
    },
    {
        "attribute": "em_experiment.reconstruction_method",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The reconstruction method used in the EM experiment. Allowed Values: CRYSTALLOGRAPHY, HELICAL, SINGLE PARTICLE, SUBTOMOGRAM AVERAGING, TOMOGRAPHY"
    },
    {
        "attribute": "em_helical_entity.angular_rotation_per_subunit",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The angular rotation per helical subunit in degrees. Negative values indicate left-handed helices; positive values indicate right handed helices."
    },
    {
        "attribute": "em_helical_entity.axial_rise_per_subunit",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The axial rise per subunit in the helical assembly."
    },
    {
        "attribute": "em_helical_entity.axial_symmetry",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Symmetry of the helical axis, either cyclic (Cn) or dihedral (Dn), where n>=1."
    },
    {
        "attribute": "em_image_recording.average_exposure_time",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The average exposure time for each image."
    },
    {
        "attribute": "em_image_recording.avg_electron_dose_per_image",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The electron dose received by the specimen per image (electrons per square angstrom)."
    },
    {
        "attribute": "em_image_recording.detector_mode",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The detector mode used during image recording. Allowed Values: COUNTING, INTEGRATING, OTHER, SUPER-RESOLUTION"
    },
    {
        "attribute": "em_image_recording.film_or_detector_model",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The detector type used for recording images. Usually film , CCD camera or direct electron detector."
    },
    {
        "attribute": "em_image_recording.num_diffraction_images",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of diffraction images collected."
    },
    {
        "attribute": "em_image_recording.num_grids_imaged",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Number of grids in the microscopy session"
    },
    {
        "attribute": "em_image_recording.num_real_images",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of micrograph images collected."
    },
    {
        "attribute": "em_imaging.accelerating_voltage",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "A value of accelerating voltage (in kV) used for imaging."
    },
    {
        "attribute": "em_imaging.alignment_procedure",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The type of procedure used to align the microscope electron beam. Allowed Values: BASIC, COMA FREE, NONE, OTHER, ZEMLIN TABLEAU"
    },
    {
        "attribute": "em_imaging.c2_aperture_diameter",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The open diameter of the c2 condenser lens, in microns."
    },
    {
        "attribute": "em_imaging.calibrated_defocus_max",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The maximum calibrated defocus value of the objective lens (in nanometres) used to obtain the recorded images. Negative values refer to overfocus."
    },
    {
        "attribute": "em_imaging.calibrated_defocus_min",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The minimum calibrated defocus value of the objective lens (in nanometres) used to obtain the recorded images. Negative values refer to overfocus."
    },
    {
        "attribute": "em_imaging.calibrated_magnification",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The magnification value obtained for a known standard just prior to, during or just after the imaging experiment."
    },
    {
        "attribute": "em_imaging.cryogen",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Cryogen type used to maintain the specimen stage temperature during imaging in the microscope. Allowed Values: HELIUM, NITROGEN"
    },
    {
        "attribute": "em_imaging.date",
        "type": "date",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Date (YYYY-MM-DD) of imaging experiment or the date at which a series of experiments began."
    },
    {
        "attribute": "em_imaging.detector_distance",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The camera length (in millimeters). The camera length is the product of the objective focal length and the combined magnification of the intermediate and projector lenses when the microscope is operated in the diffraction mode."
    },
    {
        "attribute": "em_imaging.illumination_mode",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The mode of illumination. Allowed Values: FLOOD BEAM, OTHER, SPOT SCAN"
    },
    {
        "attribute": "em_imaging.microscope_model",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The name of the model of microscope. Allowed Values: FEI MORGAGNI, FEI POLARA 300, FEI TALOS ARCTICA, FEI TECNAI 10, FEI TECNAI 12, FEI TECNAI 20, FEI TECNAI ARCTICA, FEI TECNAI F20, FEI TECNAI F30, FEI TECNAI SPHERA, FEI TECNAI SPIRIT, FEI TITAN, FEI TITAN KRIOS, FEI/PHILIPS CM10, FEI/PHILIPS CM12, FEI/PHILIPS CM120T, FEI/PHILIPS CM200FEG, FEI/PHILIPS CM200FEG/SOPHIE, FEI/PHILIPS CM200FEG/ST, FEI/PHILIPS CM200FEG/UT, FEI/PHILIPS CM200T, FEI/PHILIPS CM300FEG/HE, FEI/PHILIPS CM300FEG/ST, FEI/PHILIPS CM300FEG/T, FEI/PHILIPS EM400, FEI/PHILIPS EM420, HITACHI EF2000, HITACHI EF3000, HITACHI H-9500SD, HITACHI H3000 UHVEM, HITACHI H7600, HITACHI HF2000, HITACHI HF3000, JEOL 1000EES, JEOL 100B, JEOL 100CX, JEOL 1010, JEOL 1200, JEOL 1200EX, JEOL 1200EXII, JEOL 1230, JEOL 1400, JEOL 1400/HR + YPS FEG, JEOL 2000EX, JEOL 2000EXII, JEOL 2010, JEOL 2010F, JEOL 2010HC, JEOL 2010HT, JEOL 2010UHR, JEOL 2011, JEOL 2100, JEOL 2100F, JEOL 2200FS, JEOL 2200FSC, JEOL 3000SFF, JEOL 3100FEF, JEOL 3100FFC, JEOL 3200FS, JEOL 3200FSC, JEOL 4000, JEOL 4000EX, JEOL CRYO ARM 200, JEOL CRYO ARM 300, JEOL KYOTO-3000SFF, SHUIMU TOTEM 120S, SHUIMU TOTEM 200S, SHUIMU TOTEM 300S, SIEMENS SULEIKA, TFS GLACIOS, TFS KRIOS, TFS TALOS, TFS TALOS F200C, TFS TALOS L120C, TFS TITAN THEMIS, TFS TUNDRA, ZEISS LEO912, ZEISS LIBRA120PLUS"
    },
    {
        "attribute": "em_imaging.mode",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The mode of imaging. Allowed Values: 4D-STEM, BRIGHT FIELD, DARK FIELD, DIFFRACTION, OTHER"
    },
    {
        "attribute": "em_imaging.nominal_cs",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The spherical aberration coefficient (Cs) in millimeters, of the objective lens."
    },
    {
        "attribute": "em_imaging.nominal_defocus_max",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The maximum defocus value of the objective lens (in nanometres) used to obtain the recorded images. Negative values refer to overfocus."
    },
    {
        "attribute": "em_imaging.nominal_defocus_min",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The minimum defocus value of the objective lens (in nanometres) used to obtain the recorded images. Negative values refer to overfocus."
    },
    {
        "attribute": "em_imaging.nominal_magnification",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The magnification indicated by the microscope readout."
    },
    {
        "attribute": "em_imaging.recording_temperature_maximum",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The specimen temperature maximum (kelvin) for the duration of imaging."
    },
    {
        "attribute": "em_imaging.recording_temperature_minimum",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The specimen temperature minimum (kelvin) for the duration of imaging."
    },
    {
        "attribute": "em_imaging.residual_tilt",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Residual tilt of the electron beam (in miliradians)"
    },
    {
        "attribute": "em_imaging.specimen_holder_model",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The name of the model of specimen holder used during imaging. Allowed Values: FEI TITAN KRIOS AUTOGRID HOLDER, FISCHIONE 2550, FISCHIONE INSTRUMENTS DUAL AXIS TOMOGRAPHY HOLDER, GATAN 626 SINGLE TILT LIQUID NITROGEN CRYO TRANSFER HOLDER, GATAN 910 MULTI-SPECIMEN SINGLE TILT CRYO TRANSFER HOLDER, GATAN 914 HIGH TILT LIQUID NITROGEN CRYO TRANSFER TOMOGRAPHY HOLDER, GATAN 915 DOUBLE TILT LIQUID NITROGEN CRYO TRANSFER HOLDER, GATAN CHDT 3504 DOUBLE TILT HIGH RESOLUTION NITROGEN COOLING HOLDER, GATAN CT3500 SINGLE TILT LIQUID NITROGEN CRYO TRANSFER HOLDER, GATAN CT3500TR SINGLE TILT ROTATION LIQUID NITROGEN CRYO TRANSFER HOLDER, GATAN ELSA 698 SINGLE TILT LIQUID NITROGEN CRYO TRANSFER HOLDER, GATAN HC 3500 SINGLE TILT HEATING/NITROGEN COOLING HOLDER, GATAN HCHDT 3010 DOUBLE TILT HIGH RESOLUTION HELIUM COOLING HOLDER, GATAN HCHST 3008 SINGLE TILT HIGH RESOLUTION HELIUM COOLING HOLDER, GATAN HELIUM, GATAN LIQUID NITROGEN, GATAN UHRST 3500 SINGLE TILT ULTRA HIGH RESOLUTION NITROGEN COOLING HOLDER, GATAN ULTDT ULTRA LOW TEMPERATURE DOUBLE TILT HELIUM COOLING HOLDER, GATAN ULTST ULTRA LOW TEMPERATURE SINGLE TILT HELIUM COOLING HOLDER, HOME BUILD, JEOL, JEOL 3200FSC CRYOHOLDER, JEOL CRYOSPECPORTER, OTHER, PHILIPS ROTATION HOLDER, SIDE ENTRY, EUCENTRIC"
    },
    {
        "attribute": "em_imaging.temperature",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The mean specimen stage temperature (in kelvin) during imaging in the microscope."
    },
    {
        "attribute": "em_imaging.tilt_angle_max",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The maximum angle at which the specimen was tilted to obtain recorded images."
    },
    {
        "attribute": "em_imaging.tilt_angle_min",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The minimum angle at which the specimen was tilted to obtain recorded images."
    },
    {
        "attribute": "em_particle_selection.num_particles_selected",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of particles selected from the projection set of images."
    },
    {
        "attribute": "em_single_particle_entity.point_symmetry",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Point symmetry symbol, either Cn, Dn, T, O, or I"
    },
    {
        "attribute": "em_software.category",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The purpose of the software. Allowed Values: CLASSIFICATION, CRYSTALLOGRAPHY MERGING, CTF CORRECTION, DIFFRACTION INDEXING, EWALD SPHERE CORRECTION, FINAL EULER ASSIGNMENT, IMAGE ACQUISITION, INITIAL EULER ASSIGNMENT, LATTICE DISTORTION CORRECTION, LAYERLINE INDEXING, MASKING, MODEL FITTING, MODEL REFINEMENT, MOLECULAR REPLACEMENT, OTHER, PARTICLE SELECTION, RECONSTRUCTION, SERIES ALIGNMENT, SYMMETRY DETERMINATION, VOLUME SELECTION"
    },
    {
        "attribute": "em_software.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The name of the software package used, e.g., RELION. Depositors are strongly encouraged to provide a value in this field."
    },
    {
        "attribute": "em_specimen.concentration",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The concentration (in milligrams per milliliter, mg/ml) of the complex in the sample."
    },
    {
        "attribute": "em_specimen.shadowing_applied",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "'YES' indicates that the specimen has been shadowed. Allowed Values: NO, YES"
    },
    {
        "attribute": "em_specimen.staining_applied",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "'YES' indicates that the specimen has been stained. Allowed Values: NO, YES"
    },
    {
        "attribute": "em_specimen.vitrification_applied",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "'YES' indicates that the specimen was vitrified by cryopreservation. Allowed Values: NO, YES"
    },
    {
        "attribute": "em_staining.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Staining procedure used in the specimen preparation."
    },
    {
        "attribute": "em_staining.material",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The staining material."
    },
    {
        "attribute": "em_staining.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "type of staining Allowed Values: NEGATIVE, NONE, POSITIVE"
    },
    {
        "attribute": "em_vitrification.chamber_temperature",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The temperature (in kelvin) of the sample just prior to vitrification."
    },
    {
        "attribute": "em_vitrification.cryogen_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "This is the name of the cryogen. Allowed Values: ETHANE, ETHANE-PROPANE, FREON 12, FREON 22, HELIUM, METHANE, NITROGEN, OTHER, PROPANE"
    },
    {
        "attribute": "em_vitrification.humidity",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Relative humidity (%) of air surrounding the specimen just prior to vitrification."
    },
    {
        "attribute": "em_vitrification.instrument",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The type of instrument used in the vitrification process. Allowed Values: CRYOSOL VITROJET, EMS-002 RAPID IMMERSION FREEZER, FEI VITROBOT MARK I, FEI VITROBOT MARK II, FEI VITROBOT MARK III, FEI VITROBOT MARK IV, GATAN CRYOPLUNGE 3, HOMEMADE PLUNGER, LEICA EM CPC, LEICA EM GP, LEICA KF80, LEICA PLUNGER, REICHERT-JUNG PLUNGER, SPOTITON, SPT LABTECH CHAMELEON, ZEISS PLUNGE FREEZER CRYOBOX"
    },
    {
        "attribute": "em_vitrification.method",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The procedure for vitrification."
    },
    {
        "attribute": "em_vitrification.temp",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The vitrification temperature (in kelvin), e.g., temperature of the plunge instrument cryogen bath."
    },
    {
        "attribute": "exptl.crystals_number",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The total number of crystals used in the measurement of intensities."
    },
    {
        "attribute": "exptl.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Any special information about the experimental work prior to the intensity measurement. See also _exptl_crystal.preparation."
    },
    {
        "attribute": "exptl.method",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The method used in the experiment. Allowed Values: ELECTRON CRYSTALLOGRAPHY, ELECTRON MICROSCOPY, EPR, FIBER DIFFRACTION, FLUORESCENCE TRANSFER, INFRARED SPECTROSCOPY, NEUTRON DIFFRACTION, POWDER DIFFRACTION, SOLID-STATE NMR, SOLUTION NMR, SOLUTION SCATTERING, THEORETICAL MODEL, X-RAY DIFFRACTION"
    },
    {
        "attribute": "exptl_crystal.density_Matthews",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The density of the crystal, expressed as the ratio of the volume of the asymmetric unit to the molecular mass of a monomer of the structure, in units of angstroms^3^ per dalton.  Ref: Matthews, B. W. (1968). J. Mol. Biol. 33, 491-497."
    },
    {
        "attribute": "exptl_crystal.density_meas",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Density values measured using standard chemical and physical methods. The units are megagrams per cubic metre (grams per cubic centimetre)."
    },
    {
        "attribute": "exptl_crystal.density_percent_sol",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Density value P calculated from the crystal cell and contents, expressed as per cent solvent.  P = 1 - (1.23 N MMass) / V  N = the number of molecules in the unit cell MMass = the molecular mass of each molecule (gm/mole) V = the volume of the unit cell (A^3^) 1.23 = a conversion factor evaluated as:  (0.74 cm^3^/g) (10^24^ A^3^/cm^3^) -------------------------------------- (6.02*10^23^) molecules/mole  where 0.74 is an assumed value for the partial specific volume of the molecule"
    },
    {
        "attribute": "exptl_crystal.pdbx_mosaicity",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Isotropic approximation of the distribution of mis-orientation angles specified in degrees of all the mosaic domain blocks in the crystal, represented as a standard deviation. Here, a mosaic block is a set of contiguous unit cells assumed to be perfectly aligned. Lower mosaicity indicates better ordered crystals. See for example:  Nave, C. (1998). Acta Cryst. D54, 848-853.  Note that many software packages estimate the mosaic rotation distribution differently and may combine several physical properties of the experiment into a single mosaic term. This term will help fit the modeled spots to the observed spots without necessarily being directly related to the physics of the crystal itself."
    },
    {
        "attribute": "exptl_crystal.pdbx_mosaicity_esd",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The uncertainty in the mosaicity estimate for the crystal."
    },
    {
        "attribute": "exptl_crystal_grow.method",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The method used to grow the crystals."
    },
    {
        "attribute": "exptl_crystal_grow.pH",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The pH at which the crystal was grown. If more than one pH was employed during the crystallization process, the final pH should be noted here and the protocol involving multiple pH values should be described in _exptl_crystal_grow.details."
    },
    {
        "attribute": "exptl_crystal_grow.pdbx_details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Text description of crystal growth procedure."
    },
    {
        "attribute": "exptl_crystal_grow.temp",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The temperature in kelvins at which the crystal was grown. If more than one temperature was employed during the crystallization process, the final temperature should be noted here and the protocol involving multiple temperatures should be described in _exptl_crystal_grow.details."
    },
    {
        "attribute": "ihm_entry_collection_mapping.collection_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Identifier for the entry collection. This data item is a pointer to _ihm_entry_collection.id in the IHM_ENTRY_COLLECTION category."
    },
    {
        "attribute": "pdbx_SG_project.full_name_of_center",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The value identifies the full name of center. Allowed Values: Accelerated Technologies Center for Gene to 3D Structure, Assembly, Dynamics and Evolution of Cell-Cell and Cell-Matrix Adhesions, Atoms-to-Animals: The Immune Function Network, Bacterial targets at IGS-CNRS, France, Berkeley Structural Genomics Center, Center for Eukaryotic Structural Genomics, Center for High-Throughput Structural Biology, Center for Membrane Proteins of Infectious Diseases, Center for Structural Biology of Infectious Diseases, Center for Structural Genomics of Infectious Diseases, Center for Structures of Membrane Proteins, Center for the X-ray Structure Determination of Human Transporters, Chaperone-Enabled Studies of Epigenetic Regulation Enzymes, Enzyme Discovery for Natural Product Biosynthesis, GPCR Network, Integrated Center for Structure and Function Innovation, Israel Structural Proteomics Center, Joint Center for Structural Genomics, Marseilles Structural Genomics Program @ AFMB, Medical Structural Genomics of Pathogenic Protozoa, Membrane Protein Structural Biology Consortium, Membrane Protein Structures by Solution NMR, Midwest Center for Macromolecular Research, Midwest Center for Structural Genomics, Mitochondrial Protein Partnership, Montreal-Kingston Bacterial Structural Genomics Initiative, Mycobacterium Tuberculosis Structural Proteomics Project, New York Consortium on Membrane Protein Structure, New York SGX Research Center for Structural Genomics, New York Structural GenomiX Research Consortium, New York Structural Genomics Research Consortium, Northeast Structural Genomics Consortium, Nucleocytoplasmic Transport: a Target for Cellular Control, Ontario Centre for Structural Proteomics, Oxford Protein Production Facility, Paris-Sud Yeast Structural Genomics, Partnership for Nuclear Receptor Signaling Code Biology, Partnership for Stem Cell Biology, Partnership for T-Cell Biology, Program for the Characterization of Secreted Effector Proteins, Protein Structure Factory, RIKEN Structural Genomics/Proteomics Initiative, Scottish Structural Proteomics Facility, Seattle Structural Genomics Center for Infectious Disease, South Africa Structural Targets Annotation Database, Southeast Collaboratory for Structural Genomics, Structural Genomics Consortium, Structural Genomics Consortium for Research on Gene Expression, Structural Genomics of Pathogenic Protozoa Consortium, Structural Proteomics in Europe, Structural Proteomics in Europe 2, Structure 2 Function Project, Structure, Dynamics and Activation Mechanisms of Chemokine Receptors, Structure-Function Analysis of Polymorphic CDI Toxin-Immunity Protein Complexes, Structure-Function Studies of Tight Junction Membrane Proteins, Structures of Mtb Proteins Conferring Susceptibility to Known Mtb Inhibitors, TB Structural Genomics Consortium, Transcontinental EM Initiative for Membrane Protein Structure, Transmembrane Protein Center"
    },
    {
        "attribute": "pdbx_SG_project.initial_of_center",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The value identifies the full name of center. Allowed Values: ATCG3D, BIGS, BSGC, BSGI, CEBS, CELLMAT, CESG, CHSAM, CHTSB, CSBID, CSGID, CSMP, GPCR, IFN, ISFI, ISPC, JCSG, MCMR, MCSG, MPID, MPP, MPSBC, MPSbyNMR, MSGP, MSGPP, MTBI, NESG, NHRs, NPCXstals, NYCOMPS, NYSGRC, NYSGXRC, NatPro, OCSP, OPPF, PCSEP, PSF, RSGI, S2F, SASTAD, SECSG, SGC, SGCGES, SGPP, SPINE, SPINE-2, SSGCID, SSPF, STEMCELL, TBSGC, TCELL, TEMIMPS, TJMP, TMPC, TransportPDB, UC4CDI, XMTB, YSG"
    },
    {
        "attribute": "pdbx_SG_project.project_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The value identifies the Structural Genomics project. Allowed Values: Enzyme Function Initiative, NIAID, National Institute of Allergy and Infectious Diseases, NPPSFA, National Project on Protein Structural and Functional Analyses, PSI, Protein Structure Initiative, PSI:Biology"
    },
    {
        "attribute": "pdbx_audit_support.country",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The country/region providing the funding support for the entry. Funding information is optionally provided for entries after June 2016."
    },
    {
        "attribute": "pdbx_audit_support.funding_organization",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The name of the organization providing funding support for the entry. Funding information is optionally provided for entries after June 2016."
    },
    {
        "attribute": "pdbx_audit_support.grant_number",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The grant number associated with this source of support."
    },
    {
        "attribute": "pdbx_database_PDB_obs_spr.replace_pdb_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The PDB identifier for the replaced (OLD) entry/entries."
    },
    {
        "attribute": "pdbx_database_related.content_type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The identifying content type of the related entry. Allowed Values: associated EM volume, associated NMR restraints, associated SAS data, associated structure factors, complete structure, consensus EM volume, derivative structure, ensemble, focused EM volume, minimized average structure, native structure, other, other EM volume, protein target sequence and/or protocol data, re-refinement, representative structure, split, unspecified"
    },
    {
        "attribute": "pdbx_database_related.db_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The identifying code in the related database."
    },
    {
        "attribute": "pdbx_database_related.db_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The name of the database containing the related entry. Allowed Values: BIOISIS, BMCD, BMRB, EMDB, NDB, PDB, PDB-Dev, SASBDB, TargetDB, TargetTrack"
    },
    {
        "attribute": "pdbx_database_status.pdb_format_compatible",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A flag indicating that the entry is compatible with the PDB format.  A value of 'N' indicates that the no PDB format data file is corresponding to this entry is available in the PDB archive. Allowed Values: N, Y"
    },
    {
        "attribute": "pdbx_deposit_group.group_description",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of the contents of entries in the collection."
    },
    {
        "attribute": "pdbx_deposit_group.group_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A unique identifier for a group of entries deposited as a collection."
    },
    {
        "attribute": "pdbx_deposit_group.group_title",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A title to describe the group of entries deposited in the collection."
    },
    {
        "attribute": "pdbx_deposit_group.group_type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Text to describe a grouping of entries in multiple collections Allowed Values: changed state, ground state, undefined"
    },
    {
        "attribute": "pdbx_initial_refinement_model.accession_code",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "This item identifies an accession code of the resource where the initial model is used"
    },
    {
        "attribute": "pdbx_initial_refinement_model.source_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "This item identifies the resource of initial model used for refinement Allowed Values: AlphaFold, ITasser, InsightII, ModelArchive, Modeller, Other, PDB, PDB-Dev, PHYRE, Robetta, RoseTTAFold, SwissModel"
    },
    {
        "attribute": "pdbx_initial_refinement_model.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "This item describes the type of the initial model was generated Allowed Values: experimental model, in silico model, integrative model, other"
    },
    {
        "attribute": "pdbx_molecule_features.class",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Broadly defines the function of the molecule. Allowed Values: Antagonist, Anthelmintic, Antibiotic, Antibiotic, Anthelmintic, Antibiotic, Antimicrobial, Antibiotic, Antineoplastic, Anticancer, Anticoagulant, Anticoagulant, Antithrombotic, Antifungal, Antigen, Antiinflammatory, Antimicrobial, Antimicrobial, Antiparasitic, Antibiotic, Antimicrobial, Antiretroviral, Antimicrobial, Antitumor, Antineoplastic, Antiparasitic, Antiretroviral, Antithrombotic, Antitumor, Antiviral, CASPASE inhibitor, Chaperone binding, Drug delivery, Enzyme inhibitor, Glycan component, Growth factor, Immunosuppressant, Inducer, Inhibitor, Lantibiotic, Metabolism, Metal transport, Nutrient, Oxidation-reduction, Protein binding, Receptor, Substrate analog, Synthetic opioid, Thrombin inhibitor, Thrombin inhibitor, Trypsin inhibitor, Toxin, Transition state mimetic, Transport activator, Trypsin inhibitor, Unknown, Water retention"
    },
    {
        "attribute": "pdbx_molecule_features.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Additional details describing the molecule."
    },
    {
        "attribute": "pdbx_molecule_features.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A name of the molecule."
    },
    {
        "attribute": "pdbx_molecule_features.prd_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The value of _pdbx_molecule_features.prd_id is the accession code for this reference molecule."
    },
    {
        "attribute": "pdbx_nmr_details.text",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Additional details describing the NMR experiment."
    },
    {
        "attribute": "pdbx_nmr_refine.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Additional details about the NMR refinement."
    },
    {
        "attribute": "pdbx_nmr_refine.method",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The method used to determine the structure."
    },
    {
        "attribute": "pdbx_nmr_sample_details.contents",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A complete description of each NMR sample. Include the concentration and concentration units for each component (include buffers, etc.). For each component describe the isotopic composition, including the % labeling level, if known.  For example: 1. Uniform (random) labeling with 15N: U-15N 2. Uniform (random) labeling with 13C, 15N at known labeling levels: U-95% 13C;U-98% 15N 3. Residue selective labeling: U-95% 15N-Thymine 4. Site specific labeling: 95% 13C-Ala18, 5. Natural abundance labeling in an otherwise uniformly labeled biomolecule is designated by NA: U-13C; NA-K,H"
    },
    {
        "attribute": "pdbx_nmr_sample_details.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Brief description of the sample providing additional information not captured by other items in the category."
    },
    {
        "attribute": "pdbx_nmr_sample_details.label",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A value that uniquely identifies this sample from the other samples listed in the entry."
    },
    {
        "attribute": "pdbx_nmr_software.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The name of the software used for the task."
    },
    {
        "attribute": "pdbx_nmr_spectrometer.field_strength",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The field strength in MHz of the spectrometer"
    },
    {
        "attribute": "pdbx_nmr_spectrometer.manufacturer",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The name of the manufacturer of the spectrometer."
    },
    {
        "attribute": "pdbx_nmr_spectrometer.model",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The model of the NMR spectrometer."
    },
    {
        "attribute": "pdbx_reflns_twin.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "There are two types of twinning: merohedral or hemihedral non-merohedral or epitaxial  For merohedral twinning the diffraction patterns from the different domains are completely superimposable. Hemihedral twinning is a special case of merohedral twinning. It only involves two distinct domains. Pseudo-merohedral twinning is a subclass merohedral twinning in which lattice is coincidentally superimposable.  In the case of non-merohedral or epitaxial twinning the reciprocal lattices do not superimpose exactly. In this case the diffraction pattern consists of two (or more) interpenetrating lattices, which can in principle be separated. Allowed Values: epitaxial, hemihedral, merohedral, non-merohedral, pseudo-merohedral, tetartohedral"
    },
    {
        "attribute": "pdbx_serial_crystallography_measurement.collimation",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The collimation or type of focusing optics applied to the radiation."
    },
    {
        "attribute": "pdbx_serial_crystallography_sample_delivery.description",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The description of the mechanism by which the specimen in placed in the path of the source."
    },
    {
        "attribute": "pdbx_serial_crystallography_sample_delivery.method",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The description of the mechanism by which the specimen in placed in the path of the source. Allowed Values: fixed target, injection"
    },
    {
        "attribute": "pdbx_serial_crystallography_sample_delivery_fixed_target.description",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "For a fixed target sample, a description of sample preparation"
    },
    {
        "attribute": "pdbx_serial_crystallography_sample_delivery_fixed_target.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Any details pertinent to the fixed sample target"
    },
    {
        "attribute": "pdbx_serial_crystallography_sample_delivery_injection.description",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "For continuous sample flow experiments, a description of the injector used to move the sample into the beam."
    },
    {
        "attribute": "pdbx_serial_crystallography_sample_delivery_injection.injector_nozzle",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The type of nozzle to deliver and focus sample jet"
    },
    {
        "attribute": "pdbx_serial_crystallography_sample_delivery_injection.preparation",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Details of crystal growth and preparation of the crystals"
    },
    {
        "attribute": "pdbx_soln_scatter.data_analysis_software_list",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A list of the software used in the data analysis"
    },
    {
        "attribute": "pdbx_soln_scatter.data_reduction_software_list",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A list of the software used in the data reduction"
    },
    {
        "attribute": "pdbx_soln_scatter.detector_specific",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The particular radiation detector. In general this will be a manufacturer, description, model number or some combination of these."
    },
    {
        "attribute": "pdbx_soln_scatter.detector_type",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The general class of the radiation detector."
    },
    {
        "attribute": "pdbx_soln_scatter.source_beamline",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The beamline name used for the experiment"
    },
    {
        "attribute": "pdbx_soln_scatter.source_beamline_instrument",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The instrumentation used on the beamline"
    },
    {
        "attribute": "pdbx_soln_scatter.source_class",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The general class of the radiation source."
    },
    {
        "attribute": "pdbx_soln_scatter.source_type",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The make, model, name or beamline of the source of radiation."
    },
    {
        "attribute": "pdbx_soln_scatter_model.conformer_selection_criteria",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of the conformer selection criteria used."
    },
    {
        "attribute": "pdbx_soln_scatter_model.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of any additional details concerning the experiment."
    },
    {
        "attribute": "pdbx_soln_scatter_model.method",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of the methods used in the modelling"
    },
    {
        "attribute": "pdbx_soln_scatter_model.software_list",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A list of the software used in the modeeling"
    },
    {
        "attribute": "pdbx_vrpt_summary_em.Q_score",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The overall Q-score of the fit of coordinates to the electron map. The Q-score is defined in Pintilie, GH. et al., Nature Methods, 17, 328-334 (2020)"
    },
    {
        "attribute": "pdbx_vrpt_summary_geometry.angles_RMSZ",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The overall root mean square of the Z-score for deviations of bond angles in comparison to \"standard geometry\" made using the MolProbity dangle program. Standard geometry parameters are taken from Engh and Huber (2001) and Parkinson et al. (1996). This value is for all chains in the structure."
    },
    {
        "attribute": "pdbx_vrpt_summary_geometry.bonds_RMSZ",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The overall root mean square of the Z-score for deviations of bond lengths in comparison to \"standard geometry\" made using the MolProbity dangle program. Standard geometry parameters are taken from Engh and Huber (2001) and Parkinson et al. (1996). This value is for all chains in the structure."
    },
    {
        "attribute": "pdbx_vrpt_summary_geometry.clashscore",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "This score is derived from the number of pairs of atoms in the PDB_model_num that are unusually close to each other. It is calculated by the MolProbity pdbx_vrpt_software and expressed as the number or such clashes per thousand atoms. For structures determined by NMR the clashscore value here will only consider label_atom_id pairs in the well-defined (core) residues from ensemble analysis."
    },
    {
        "attribute": "pdbx_vrpt_summary_geometry.percent_ramachandran_outliers",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The percentage of residues with Ramachandran outliers."
    },
    {
        "attribute": "pdbx_vrpt_summary_geometry.percent_rotamer_outliers",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The MolProbity sidechain outlier score (a percentage). Protein sidechains mostly adopt certain (combinations of) preferred torsion angle values (called rotamers or rotameric conformers), much like their backbone torsion angles (as assessed in the Ramachandran analysis). MolProbity considers the sidechain conformation of a residue to be an outlier if its set of torsion angles is not similar to any preferred combination. The sidechain outlier score is calculated as the percentage of residues with an unusual sidechain conformation with respect to the total number of residues for which the assessment is available. Example: percent-rota-outliers=\"2.44\". Specific to structure that contain protein chains and have sidechains modelled. For NMR structures only the well-defined (core) residues from ensemble analysis will be considered. The percentage of residues with rotamer outliers."
    },
    {
        "attribute": "rcsb_accession_info.deposit_date",
        "type": "date",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The entry deposition date."
    },
    {
        "attribute": "rcsb_accession_info.has_released_experimental_data",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A code indicating the current availibility of experimental data in the repository. Allowed Values: N, Y"
    },
    {
        "attribute": "rcsb_accession_info.initial_release_date",
        "type": "date",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The entry initial release date."
    },
    {
        "attribute": "rcsb_accession_info.revision_date",
        "type": "date",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The latest entry revision date."
    },
    {
        "attribute": "rcsb_binding_affinity.comp_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Ligand identifier."
    },
    {
        "attribute": "rcsb_binding_affinity.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Binding affinity measurement given in one of the following types: The concentration constants: IC50: the concentration of ligand that reduces enzyme activity by 50%; EC50: the concentration of compound that generates a half-maximal response; The binding constant: Kd: dissociation constant; Ka: association constant; Ki: enzyme inhibition constant; The thermodynamic parameters: delta G: Gibbs free energy of binding (for association reaction); delta H: change in enthalpy associated with a chemical reaction; delta S: change in entropy associated with a chemical reaction. Allowed Values: &Delta;G, &Delta;H, -T&Delta;S, EC50, IC50, Ka, Kd, Ki"
    },
    {
        "attribute": "rcsb_binding_affinity.value",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Binding affinity value between a ligand and its target molecule."
    },
    {
        "attribute": "rcsb_comp_model_provenance.entry_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Entry identifier corresponding to the computed structure model."
    },
    {
        "attribute": "rcsb_comp_model_provenance.source_db",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Source database for the computed structure model. Allowed Values: AlphaFoldDB, ModelArchive"
    },
    {
        "attribute": "rcsb_entry_container_identifiers.emdb_ids",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "List of EMDB identifiers for the 3D electron microscopy density maps used in the production of the structure model."
    },
    {
        "attribute": "rcsb_entry_container_identifiers.entry_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Entry identifier for the container."
    },
    {
        "attribute": "rcsb_entry_container_identifiers.rcsb_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A unique identifier for each object in this entry container."
    },
    {
        "attribute": "rcsb_entry_container_identifiers.related_emdb_ids",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "List of EMDB identifiers for the 3D electron microscopy density maps related to the structure model."
    },
    {
        "attribute": "rcsb_entry_group_membership.aggregation_method",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Method used to establish group membership Allowed Values: matching_deposit_group_id"
    },
    {
        "attribute": "rcsb_entry_group_membership.group_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A unique identifier for a group of entries"
    },
    {
        "attribute": "rcsb_entry_info.assembly_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of assemblies defined for this entry including the deposited assembly."
    },
    {
        "attribute": "rcsb_entry_info.branched_entity_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct branched entities in the structure entry."
    },
    {
        "attribute": "rcsb_entry_info.cis_peptide_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of cis-peptide linkages per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.deposited_atom_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of heavy atom coordinates records per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.deposited_deuterated_water_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of deuterated water molecules per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.deposited_hydrogen_atom_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of hydrogen atom coordinates records per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.deposited_model_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of model structures deposited."
    },
    {
        "attribute": "rcsb_entry_info.deposited_modeled_polymer_monomer_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of modeled polymer monomers in the deposited coordinate data. This is the total count of monomers with reported coordinate data for all polymer entity instances in the deposited coordinate data."
    },
    {
        "attribute": "rcsb_entry_info.deposited_nonpolymer_entity_instance_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of non-polymer instances in the deposited data set. This is the total count of non-polymer entity instances reported per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.deposited_polymer_entity_instance_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of polymer instances in the deposited data set. This is the total count of polymer entity instances reported per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.deposited_polymer_monomer_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of polymer monomers in sample entity instances in the deposited data set. This is the total count of monomers for all polymer entity instances reported per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.deposited_solvent_atom_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of heavy solvent atom coordinates records per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.deposited_unmodeled_polymer_monomer_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of unmodeled polymer monomers in the deposited coordinate data. This is the total count of monomers with unreported coordinate data for all polymer entity instances per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.diffrn_radiation_wavelength_maximum",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The maximum radiation wavelength in angstroms."
    },
    {
        "attribute": "rcsb_entry_info.diffrn_radiation_wavelength_minimum",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The minimum radiation wavelength in angstroms."
    },
    {
        "attribute": "rcsb_entry_info.disulfide_bond_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of disulfide bonds per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.entity_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct polymer, non-polymer, branched molecular, and solvent entities per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.experimental_method",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The category of experimental method(s) used to determine the structure entry. Allowed Values: EM, Integrative, Multiple methods, NMR, Neutron, Other, X-ray"
    },
    {
        "attribute": "rcsb_entry_info.experimental_method_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of experimental methods contributing data to the structure determination."
    },
    {
        "attribute": "rcsb_entry_info.ihm_multi_scale_flag",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Multi-scale modeling flag for integrative structures. Allowed Values: N, Y"
    },
    {
        "attribute": "rcsb_entry_info.ihm_multi_state_flag",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Multi-state modeling flag for integrative structures. Allowed Values: N, Y"
    },
    {
        "attribute": "rcsb_entry_info.ihm_ordered_state_flag",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Ordered-state modeling flag for integrative structures. Allowed Values: N, Y"
    },
    {
        "attribute": "rcsb_entry_info.ihm_structure_description",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Description of the integrative structure."
    },
    {
        "attribute": "rcsb_entry_info.inter_mol_covalent_bond_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of intermolecular covalent bonds."
    },
    {
        "attribute": "rcsb_entry_info.inter_mol_metalic_bond_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of intermolecular metalic bonds."
    },
    {
        "attribute": "rcsb_entry_info.molecular_weight",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The molecular mass (KDa) of polymer and non-polymer entities (exclusive of solvent) in the deposited structure entry."
    },
    {
        "attribute": "rcsb_entry_info.na_polymer_entity_types",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Nucleic acid polymer entity type categories describing the entry. Allowed Values: DNA (only), DNA/RNA (only), NA-hybrid (only), Other, RNA (only)"
    },
    {
        "attribute": "rcsb_entry_info.nonpolymer_entity_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct non-polymer entities in the structure entry exclusive of solvent."
    },
    {
        "attribute": "rcsb_entry_info.nonpolymer_molecular_weight_maximum",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The maximum molecular mass (KDa) of a non-polymer entity in the deposited structure entry."
    },
    {
        "attribute": "rcsb_entry_info.nonpolymer_molecular_weight_minimum",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The minimum molecular mass (KDa) of a non-polymer entity in the deposited structure entry."
    },
    {
        "attribute": "rcsb_entry_info.polymer_composition",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Categories describing the polymer entity composition for the entry. Allowed Values: DNA, DNA/RNA, NA-hybrid, NA/oligosaccharide, RNA, heteromeric protein, homomeric protein, oligosaccharide, other, other type composition, other type pair, protein/NA, protein/NA/oligosaccharide, protein/oligosaccharide"
    },
    {
        "attribute": "rcsb_entry_info.polymer_entity_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct polymer entities in the structure entry."
    },
    {
        "attribute": "rcsb_entry_info.polymer_entity_count_DNA",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct DNA polymer entities."
    },
    {
        "attribute": "rcsb_entry_info.polymer_entity_count_RNA",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct RNA polymer entities."
    },
    {
        "attribute": "rcsb_entry_info.polymer_entity_count_nucleic_acid",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct nucleic acid polymer entities (DNA or RNA)."
    },
    {
        "attribute": "rcsb_entry_info.polymer_entity_count_nucleic_acid_hybrid",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct hybrid nucleic acid polymer entities."
    },
    {
        "attribute": "rcsb_entry_info.polymer_entity_count_protein",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct protein polymer entities."
    },
    {
        "attribute": "rcsb_entry_info.polymer_entity_taxonomy_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct taxonomies represented among the polymer entities in the entry."
    },
    {
        "attribute": "rcsb_entry_info.polymer_molecular_weight_maximum",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The maximum molecular mass (KDa) of a polymer entity in the deposited structure entry."
    },
    {
        "attribute": "rcsb_entry_info.polymer_molecular_weight_minimum",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The minimum molecular mass (KDa) of a polymer entity in the deposited structure entry."
    },
    {
        "attribute": "rcsb_entry_info.polymer_monomer_count_maximum",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The maximum monomer count of a polymer entity per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.polymer_monomer_count_minimum",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The minimum monomer count of a polymer entity per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.resolution_combined",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Combined estimates of experimental resolution contributing to the refined structural model. Resolution reported in \"refine.ls_d_res_high\" is used for X-RAY DIFFRACTION, FIBER DIFFRACTION, POWDER DIFFRACTION, ELECTRON CRYSTALLOGRAPHY, and NEUTRON DIFFRACTION as identified in \"refine.pdbx_refine_id\". Resolution reported in \"em_3d_reconstruction.resolution\" is used for ELECTRON MICROSCOPY. The best value corresponding to \"em_3d_reconstruction.resolution_method\" == \"FSC 0.143 CUT-OFF\" is used, if available. If not, the best \"em_3d_reconstruction.resolution\" value is used. For structures that are not obtained from diffraction-based methods, the resolution values in \"refine.ls_d_res_high\" are ignored. Multiple values are reported only if multiple methods are used in the structure determination."
    },
    {
        "attribute": "rcsb_entry_info.selected_polymer_entity_types",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Selected polymer entity type categories describing the entry. Allowed Values: Nucleic acid (only), Oligosaccharide (only), Other, Protein (only), Protein/NA, Protein/Oligosaccharide"
    },
    {
        "attribute": "rcsb_entry_info.software_programs_combined",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Combined list of software programs names reported in connection with the production of this entry."
    },
    {
        "attribute": "rcsb_entry_info.solvent_entity_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct solvent entities per deposited structure model."
    },
    {
        "attribute": "rcsb_entry_info.structure_determination_methodology",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Indicates if the structure was determined using experimental or computational methods. Allowed Values: computational, experimental, integrative"
    },
    {
        "attribute": "rcsb_entry_info.structure_determination_methodology_priority",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Indicates the priority of the value in _rcsb_entry_info.structure_determination_methodology. The lower the number the higher the priority. Priority values for \"experimental\" structures is currently set to 10 and the values for \"computational\" structures is set to 100."
    },
    {
        "attribute": "rcsb_entry_info.diffrn_resolution_high.value",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The high resolution limit of data collection."
    },
    {
        "attribute": "rcsb_external_references.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Internal identifier for external resources Allowed Values: BMRB, EM DATA RESOURCE, NAKB, NDB, OLDERADO, PROTEIN DIFFRACTION, SB GRID"
    },
    {
        "attribute": "rcsb_ihm_dataset_list.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Name of input dataset used in integrative modeling. Allowed Values: 2DEM class average, 3DEM volume, CX-MS data, Comparative model, Crosslinking-MS data, DNA footprinting data, De Novo model, EM raw micrographs, EPR data, Ensemble FRET data, Experimental model, H/D exchange data, Hydroxyl radical footprinting data, Integrative model, Mass Spectrometry data, Mutagenesis data, NMR data, Other, Predicted contacts, Quantitative measurements of genetic interactions, SAS data, Single molecule FRET data, X-ray diffraction data, Yeast two-hybrid screening data"
    },
    {
        "attribute": "rcsb_ihm_dataset_source_db_reference.accession_code",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Accession code for the input dataset."
    },
    {
        "attribute": "rcsb_ihm_dataset_source_db_reference.db_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Name of the source database for the input dataset. Allowed Values: AlphaFoldDB, BMRB, BMRbig, BioGRID, EMDB, EMPIAR, MASSIVE, ModelArchive, Other, PDB, PDB-Dev, PRIDE, ProXL, ProteomeXchange, SASBDB, iProX, jPOSTrepo"
    },
    {
        "attribute": "rcsb_ma_qa_metric_global.ma_qa_metric_global.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The type of global QA metric. Allowed Values: PAE, contact probability, distance, energy, ipTM, normalized score, other, pLDDT, pLDDT all-atom, pLDDT all-atom in [0,1], pLDDT in [0,1], pTM, zscore"
    },
    {
        "attribute": "rcsb_ma_qa_metric_global.ma_qa_metric_global.value",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Value of the global QA metric."
    },
    {
        "attribute": "rcsb_primary_citation.book_title",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The title of the book in which the citation appeared; relevant for books or book chapters."
    },
    {
        "attribute": "rcsb_primary_citation.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The value of _rcsb_primary_citation.id must uniquely identify a record in the CITATION list.  The _rcsb_primary_citation.id 'primary' should be used to indicate the citation that the author(s) consider to be the most pertinent to the contents of the data block.  Note that this item need not be a number; it can be any unique identifier."
    },
    {
        "attribute": "rcsb_primary_citation.journal_abbrev",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Abbreviated name of the cited journal as given in the Chemical Abstracts Service Source Index."
    },
    {
        "attribute": "rcsb_primary_citation.journal_id_ASTM",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The American Society for Testing and Materials (ASTM) code assigned to the journal cited (also referred to as the CODEN designator of the Chemical Abstracts Service); relevant for journal articles."
    },
    {
        "attribute": "rcsb_primary_citation.journal_id_ISSN",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The International Standard Serial Number (ISSN) code assigned to the journal cited; relevant for journal articles."
    },
    {
        "attribute": "rcsb_primary_citation.pdbx_database_id_DOI",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Document Object Identifier used by doi.org to uniquely specify bibliographic entry."
    },
    {
        "attribute": "rcsb_primary_citation.rcsb_ORCID_identifiers",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The Open Researcher and Contributor ID (ORCID) identifiers for the citation authors."
    },
    {
        "attribute": "rcsb_primary_citation.rcsb_authors",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Names of the authors of the citation; relevant for journal articles, books and book chapters. Names are separated by vertical bars.  The family name(s), followed by a comma and including any dynastic components, precedes the first name(s) or initial(s)."
    },
    {
        "attribute": "rcsb_primary_citation.rcsb_journal_abbrev",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Normalized journal abbreviation."
    },
    {
        "attribute": "rcsb_primary_citation.title",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The title of the citation; relevant for journal articles, books and book chapters."
    },
    {
        "attribute": "rcsb_primary_citation.year",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The year of the citation; relevant for journal articles, books and book chapters."
    },
    {
        "attribute": "refine.B_iso_mean",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The mean isotropic displacement parameter (B value) for the coordinate set."
    },
    {
        "attribute": "refine.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Description of special aspects of the refinement process."
    },
    {
        "attribute": "refine.ls_R_factor_R_free",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Residual factor R for reflections that satisfy the resolution limits established by _refine.ls_d_res_high and _refine.ls_d_res_low and the observation limit established by _reflns.observed_criterion, and that were used as the test reflections (i.e. were excluded from the refinement) when the refinement included the calculation of a 'free' R factor. Details of how reflections were assigned to the working and test sets are given in _reflns.R_free_details.  sum|F~obs~ - F~calc~| R = --------------------- sum|F~obs~|  F~obs~ = the observed structure-factor amplitudes F~calc~ = the calculated structure-factor amplitudes  sum is taken over the specified reflections"
    },
    {
        "attribute": "refine.ls_R_factor_R_work",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Residual factor R for reflections that satisfy the resolution limits established by _refine.ls_d_res_high and _refine.ls_d_res_low and the observation limit established by _reflns.observed_criterion, and that were used as the working reflections (i.e. were included in the refinement) when the refinement included the calculation of a 'free' R factor. Details of how reflections were assigned to the working and test sets are given in _reflns.R_free_details.  _refine.ls_R_factor_obs should not be confused with _refine.ls_R_factor_R_work; the former reports the results of a refinement in which all observed reflections were used, the latter a refinement in which a subset of the observed reflections were excluded from refinement for the calculation of a 'free' R factor. However, it would be meaningful to quote both values if a 'free' R factor were calculated for most of the refinement, but all of the observed reflections were used in the final rounds of refinement; such a protocol should be explained in _refine.details.  sum|F~obs~ - F~calc~| R = --------------------- sum|F~obs~|  F~obs~ = the observed structure-factor amplitudes F~calc~ = the calculated structure-factor amplitudes  sum is taken over the specified reflections"
    },
    {
        "attribute": "refine.ls_R_factor_all",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Residual factor R for all reflections that satisfy the resolution limits established by _refine.ls_d_res_high and _refine.ls_d_res_low.  sum|F~obs~ - F~calc~| R = --------------------- sum|F~obs~|  F~obs~ = the observed structure-factor amplitudes F~calc~ = the calculated structure-factor amplitudes  sum is taken over the specified reflections"
    },
    {
        "attribute": "refine.ls_R_factor_obs",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Residual factor R for reflections that satisfy the resolution limits established by _refine.ls_d_res_high and _refine.ls_d_res_low and the observation limit established by _reflns.observed_criterion.  _refine.ls_R_factor_obs should not be confused with _refine.ls_R_factor_R_work; the former reports the results of a refinement in which all observed reflections were used, the latter a refinement in which a subset of the observed reflections were excluded from refinement for the calculation of a 'free' R factor. However, it would be meaningful to quote both values if a 'free' R factor were calculated for most of the refinement, but all of the observed reflections were used in the final rounds of refinement; such a protocol should be explained in _refine.details.  sum|F~obs~ - F~calc~| R = --------------------- sum|F~obs~|  F~obs~ = the observed structure-factor amplitudes F~calc~ = the calculated structure-factor amplitudes  sum is taken over the specified reflections"
    },
    {
        "attribute": "refine.pdbx_method_to_determine_struct",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Method(s) used to determine the structure."
    },
    {
        "attribute": "reflns.B_iso_Wilson_estimate",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The value of the overall isotropic displacement parameter estimated from the slope of the Wilson plot."
    },
    {
        "attribute": "reflns.R_free_details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of the method by which a subset of reflections was selected for exclusion from refinement so as to be used in the calculation of a 'free' R factor."
    },
    {
        "attribute": "reflns.d_resolution_high",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The smallest value in angstroms for the interplanar spacings for the reflection data. This is called the highest resolution."
    },
    {
        "attribute": "reflns.data_reduction_details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of special aspects of the data-reduction procedures."
    },
    {
        "attribute": "reflns.data_reduction_method",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The method used for data reduction.  Note that this is not the computer program used, which is described in the SOFTWARE category, but the method itself.  This data item should be used to describe significant methodological options used within the data-reduction programs."
    },
    {
        "attribute": "reflns.pdbx_Rmerge_I_obs",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The R value for merging intensities satisfying the observed criteria in this data set."
    },
    {
        "attribute": "reflns.pdbx_redundancy",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Overall redundancy for this data set."
    },
    {
        "attribute": "reflns.percent_possible_obs",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The percentage of geometrically possible reflections represented by reflections that satisfy the resolution limits established by _reflns.d_resolution_high and _reflns.d_resolution_low and the observation limit established by _reflns.observed_criterion."
    },
    {
        "attribute": "software.classification",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The classification of the program according to its major function."
    },
    {
        "attribute": "software.language",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The major computing language in which the software is coded. Allowed Values: Ada, Awk, Basic, C, C++, C/C++, Fortran, Fortran 77, Fortran 90, Fortran_77, Java, Java & Fortran, Other, Pascal, Perl, Python, Python/C++, Tcl, assembler, csh, ksh, sh"
    },
    {
        "attribute": "software.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The name of the software."
    },
    {
        "attribute": "software.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The classification of the software according to the most common types. Allowed Values: filter, jiffy, library, other, package, program"
    },
    {
        "attribute": "struct.pdbx_CASP_flag",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The item indicates whether the entry is a CASP target, a CASD-NMR target, or similar target participating in methods development experiments. Allowed Values: N, Y"
    },
    {
        "attribute": "struct.pdbx_model_details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Text description of the methodology which produced this model structure."
    },
    {
        "attribute": "struct.pdbx_model_type_details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of the type of structure model."
    },
    {
        "attribute": "struct.title",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A title for the data block. The author should attempt to convey the essence of the structure archived in the CIF in the title, and to distinguish this structural result from others."
    },
    {
        "attribute": "struct_keywords.pdbx_keywords",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Terms characterizing the macromolecular structure."
    },
    {
        "attribute": "struct_keywords.text",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Keywords describing this structure."
    },
    {
        "attribute": "symmetry.cell_setting",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The cell settings for this space-group symmetry. Allowed Values: cubic, hexagonal, monoclinic, orthorhombic, rhombohedral, tetragonal, triclinic, trigonal"
    },
    {
        "attribute": "symmetry.pdbx_full_space_group_name_H_M",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Used for PDB space group:  Example: 'C 1 2 1' (instead of C 2) 'P 1 2 1' (instead of P 2) 'P 1 21 1' (instead of P 21) 'P 1 1 21' (instead of P 21 -unique C axis) 'H 3' (instead of R 3 -hexagonal) 'H 3 2' (instead of R 3 2 -hexagonal)"
    },
    {
        "attribute": "symmetry.space_group_name_H_M",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Hermann-Mauguin space-group symbol. Note that the Hermann-Mauguin symbol does not necessarily contain complete information about the symmetry and the space-group origin. If used, always supply the FULL symbol from International Tables for Crystallography Vol. A (2002) and indicate the origin and the setting if it is not implicit. If there is any doubt that the equivalent positions can be uniquely deduced from this symbol, specify the _symmetry_equiv.pos_as_xyz or _symmetry.space_group_name_Hall data items as well. Leave spaces between symbols referring to different axes."
    },
    {
        "attribute": "symmetry.space_group_name_Hall",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Space-group symbol as described by Hall (1981). This symbol gives the space-group setting explicitly. Leave spaces between the separate components of the symbol.  Ref: Hall, S. R. (1981). Acta Cryst. A37, 517-525; erratum (1981) A37, 921."
    },
    {
        "attribute": "rcsb_polymer_entity_instance_container_identifiers.asym_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Instance identifier for this container."
    },
    {
        "attribute": "rcsb_polymer_entity_instance_container_identifiers.auth_asym_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Author instance identifier for this container."
    },
    {
        "attribute": "rcsb_polymer_entity_instance_container_identifiers.entity_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Entity identifier for the container."
    },
    {
        "attribute": "rcsb_polymer_entity_instance_container_identifiers.entry_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Entry identifier for the container."
    },
    {
        "attribute": "rcsb_polymer_entity_instance_container_identifiers.rcsb_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A unique identifier for each object in this entity instance container formed by an 'dot' (.) separated concatenation of entry and entity instance identifiers."
    },
    {
        "attribute": "rcsb_polymer_instance_annotation.annotation_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "An identifier for the annotation."
    },
    {
        "attribute": "rcsb_polymer_instance_annotation.description",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description for the annotation."
    },
    {
        "attribute": "rcsb_polymer_instance_annotation.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A name for the annotation."
    },
    {
        "attribute": "rcsb_polymer_instance_annotation.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A type or category of the annotation. Allowed Values: CATH, ECOD, GlyGen, SCOP, SCOP2"
    },
    {
        "attribute": "rcsb_polymer_instance_annotation.annotation_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent lineage depth (1-N)"
    },
    {
        "attribute": "rcsb_polymer_instance_annotation.annotation_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class identifiers."
    },
    {
        "attribute": "rcsb_polymer_instance_annotation.annotation_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class names."
    },
    {
        "attribute": "rcsb_polymer_instance_feature_summary.count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The feature count per polymer chain."
    },
    {
        "attribute": "rcsb_polymer_instance_feature_summary.coverage",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The fractional feature coverage relative to the full entity sequence."
    },
    {
        "attribute": "rcsb_polymer_instance_feature_summary.maximum_length",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The maximum feature length."
    },
    {
        "attribute": "rcsb_polymer_instance_feature_summary.minimum_length",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The minimum feature length."
    },
    {
        "attribute": "rcsb_polymer_instance_feature_summary.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Type or category of the feature. Allowed Values: ANGLE_OUTLIER, ANGLE_OUTLIERS, AVERAGE_OCCUPANCY, BEND, BINDING_SITE, BOND_OUTLIER, BOND_OUTLIERS, C-MANNOSYLATION_SITE, CATH, CHIRAL_OUTLIERS, CIS-PEPTIDE, CLASHES, ECOD, HELIX_P, HELX_LH_PP_P, HELX_RH_3T_P, HELX_RH_AL_P, HELX_RH_PI_P, LIGAND_COVALENT_LINKAGE, LIGAND_INTERACTION, LIGAND_METAL_COORDINATION_LINKAGE, MA_QA_METRIC_LOCAL_TYPE_CONTACT_PROBABILITY, MA_QA_METRIC_LOCAL_TYPE_DISTANCE, MA_QA_METRIC_LOCAL_TYPE_ENERGY, MA_QA_METRIC_LOCAL_TYPE_IPTM, MA_QA_METRIC_LOCAL_TYPE_NORMALIZED_SCORE, MA_QA_METRIC_LOCAL_TYPE_OTHER, MA_QA_METRIC_LOCAL_TYPE_PAE, MA_QA_METRIC_LOCAL_TYPE_PLDDT, MA_QA_METRIC_LOCAL_TYPE_PLDDT_ALL-ATOM, MA_QA_METRIC_LOCAL_TYPE_PLDDT_ALL-ATOM_[0,1], MA_QA_METRIC_LOCAL_TYPE_PLDDT_[0,1], MA_QA_METRIC_LOCAL_TYPE_PTM, MA_QA_METRIC_LOCAL_TYPE_ZSCORE, MEMBRANE_SEGMENT, MOGUL_ANGLE_OUTLIER, MOGUL_ANGLE_OUTLIERS, MOGUL_BOND_OUTLIER, MOGUL_BOND_OUTLIERS, MOGUL_RING_OUTLIERS, MOGUL_TORSION_OUTLIERS, N-GLYCOSYLATION_SITE, NATOMS_EDS, O-GLYCOSYLATION_SITE, OWAB, PLANE_OUTLIERS, Q_SCORE, RAMACHANDRAN_OUTLIER, ROTAMER_OUTLIER, RSCC, RSCC_OUTLIER, RSR, RSRZ, RSRZ_OUTLIER, S-GLYCOSYLATION_SITE, SABDAB_ANTIBODY_HEAVY_CHAIN_SUBCLASS, SABDAB_ANTIBODY_LIGHT_CHAIN_SUBCLASS, SABDAB_ANTIBODY_LIGHT_CHAIN_TYPE, SCOP, SCOP2B_SUPERFAMILY, SCOP2_FAMILY, SCOP2_SUPERFAMILY, SHEET, STEREO_OUTLIER, STRN, SYMM_CLASHES, TURN_TY1_P, UNASSIGNED_SEC_STRUCT, UNOBSERVED_ATOM_XYZ, UNOBSERVED_RESIDUE_XYZ, ZERO_OCCUPANCY_ATOM_XYZ, ZERO_OCCUPANCY_RESIDUE_XYZ"
    },
    {
        "attribute": "rcsb_polymer_struct_conn.connect_type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The connection type. Allowed Values: covalent bond, covalent modification of a nucleotide base, covalent modification of a nucleotide phosphate, covalent modification of a nucleotide sugar, covalent residue modification, disulfide bridge, hydrogen bond, ionic interaction, metal coordination, mismatched base pairs"
    },
    {
        "attribute": "rcsb_polymer_struct_conn.role",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The chemical or structural role of the interaction Allowed Values: C-Mannosylation, N-Glycosylation, O-Glycosylation, S-Glycosylation"
    },
    {
        "attribute": "rcsb_polymer_struct_conn.value_order",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The chemical bond order associated with the specified atoms in this contact. Allowed Values: doub, quad, sing, trip"
    },
    {
        "attribute": "rcsb_pubmed_container_identifiers.pubmed_id",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "UID assigned to each PubMed record."
    },
    {
        "attribute": "rcsb_pubmed_abstract_text",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A concise, accurate and factual mini-version of the paper contents."
    },
    {
        "attribute": "rcsb_pubmed_mesh_descriptors_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Identifier for MeSH classification term."
    },
    {
        "attribute": "rcsb_pubmed_mesh_descriptors_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "MeSH classification term."
    },
    {
        "attribute": "rcsb_pubmed_mesh_descriptors_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Hierarchy depth."
    },
    {
        "attribute": "entity_poly.rcsb_entity_polymer_type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A coarse-grained polymer entity type. Allowed Values: DNA, NA-hybrid, Other, Protein, RNA"
    },
    {
        "attribute": "entity_poly.rcsb_mutation_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Number of engineered mutations engineered in the sample sequence."
    },
    {
        "attribute": "entity_poly.rcsb_sample_sequence_length",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The monomer length of the sample sequence."
    },
    {
        "attribute": "entity_src_gen.gene_src_strain",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The strain of the natural organism from which the gene was obtained, if relevant."
    },
    {
        "attribute": "entity_src_gen.gene_src_tissue",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The tissue of the natural organism from which the gene was obtained."
    },
    {
        "attribute": "entity_src_gen.pdbx_description",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Information on the source which is not given elsewhere."
    },
    {
        "attribute": "entity_src_gen.pdbx_gene_src_atcc",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "American Type Culture Collection tissue culture number."
    },
    {
        "attribute": "entity_src_gen.pdbx_gene_src_cell",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Cell type."
    },
    {
        "attribute": "entity_src_gen.pdbx_gene_src_cell_line",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The specific line of cells."
    },
    {
        "attribute": "entity_src_gen.pdbx_gene_src_cellular_location",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Identifies the location inside (or outside) the cell."
    },
    {
        "attribute": "entity_src_gen.pdbx_gene_src_organ",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Organized group of tissues that carries on a specialized function."
    },
    {
        "attribute": "entity_src_gen.pdbx_gene_src_organelle",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Organized structure within cell."
    },
    {
        "attribute": "entity_src_gen.pdbx_host_org_atcc",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Americal Tissue Culture Collection of the expression system. Where full details of the protein production are available it would be expected that this item would be derived from _entity_src_gen_express.host_org_culture_collection"
    },
    {
        "attribute": "entity_src_gen.pdbx_host_org_cell",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Cell type from which the gene is derived. Where entity.target_id is provided this should be derived from details of the target."
    },
    {
        "attribute": "entity_src_gen.pdbx_host_org_cell_line",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A specific line of cells used as the expression system. Where full details of the protein production are available it would be expected that this item would be derived from entity_src_gen_express.host_org_cell_line"
    },
    {
        "attribute": "entity_src_gen.pdbx_host_org_cellular_location",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Identifies the location inside (or outside) the cell which expressed the molecule."
    },
    {
        "attribute": "entity_src_gen.pdbx_host_org_culture_collection",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Culture collection of the expression system. Where full details of the protein production are available it would be expected that this item would be derived somehwere, but exactly where is not clear."
    },
    {
        "attribute": "entity_src_gen.pdbx_host_org_organ",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Specific organ which expressed the molecule."
    },
    {
        "attribute": "entity_src_gen.pdbx_host_org_organelle",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Specific organelle which expressed the molecule."
    },
    {
        "attribute": "entity_src_gen.pdbx_host_org_tissue",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The specific tissue which expressed the molecule. Where full details of the protein production are available it would be expected that this item would be derived from _entity_src_gen_express.host_org_tissue"
    },
    {
        "attribute": "entity_src_gen.pdbx_host_org_tissue_fraction",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The fraction of the tissue which expressed the molecule."
    },
    {
        "attribute": "entity_src_gen.pdbx_host_org_vector",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Identifies the vector used. Where full details of the protein production are available it would be expected that this item would be derived from _entity_src_gen_clone.vector_name."
    },
    {
        "attribute": "entity_src_gen.pdbx_host_org_vector_type",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Identifies the type of vector used (plasmid, virus, or cosmid). Where full details of the protein production are available it would be expected that this item would be derived from _entity_src_gen_express.vector_type."
    },
    {
        "attribute": "entity_src_gen.plasmid_name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The name of the plasmid that produced the entity in the host organism. Where full details of the protein production are available it would be expected that this item would be derived from _pdbx_construct.name of the construct pointed to from _entity_src_gen_express.plasmid_id."
    },
    {
        "attribute": "entity_src_nat.details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of special aspects of the organism from which the entity was isolated."
    },
    {
        "attribute": "entity_src_nat.pdbx_atcc",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Americal Tissue Culture Collection number."
    },
    {
        "attribute": "entity_src_nat.pdbx_cell",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A particular cell type."
    },
    {
        "attribute": "entity_src_nat.pdbx_cell_line",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The specific line of cells."
    },
    {
        "attribute": "entity_src_nat.pdbx_cellular_location",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Identifies the location inside (or outside) the cell."
    },
    {
        "attribute": "entity_src_nat.pdbx_organ",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Organized group of tissues that carries on a specialized function."
    },
    {
        "attribute": "entity_src_nat.pdbx_organelle",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Organized structure within cell."
    },
    {
        "attribute": "entity_src_nat.pdbx_plasmid_details",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Details about the plasmid."
    },
    {
        "attribute": "entity_src_nat.pdbx_plasmid_name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The plasmid containing the gene."
    },
    {
        "attribute": "entity_src_nat.tissue",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The tissue of the organism from which the entity was isolated."
    },
    {
        "attribute": "entity_src_nat.tissue_fraction",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The subcellular fraction of the tissue of the organism from which the entity was isolated."
    },
    {
        "attribute": "rcsb_cluster_membership.cluster_id",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Identifier for a cluster at the specified level of sequence identity within the cluster data set."
    },
    {
        "attribute": "rcsb_cluster_membership.identity",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Sequence identity expressed as an integer percent value."
    },
    {
        "attribute": "rcsb_entity_host_organism.common_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The common name of the host organism"
    },
    {
        "attribute": "rcsb_entity_host_organism.ncbi_common_names",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Common names associated with this taxonomy code obtained from NCBI Taxonomy Database.  These names correspond to the taxonomy identifier assigned by the PDB depositor.  References:  Sayers EW, Barrett T, Benson DA, Bryant SH, Canese K, Chetvernin V, Church DM, DiCuccio M, Edgar R, Federhen S, Feolo M, Geer LY, Helmberg W, Kapustin Y, Landsman D, Lipman DJ, Madden TL, Maglott DR, Miller V, Mizrachi I, Ostell J, Pruitt KD, Schuler GD, Sequeira E, Sherry ST, Shumway M, Sirotkin K, Souvorov A, Starchenko G, Tatusova TA, Wagner L, Yaschenko E, Ye J (2009). Database resources of the National Center for Biotechnology Information. Nucleic Acids Res. 2009 Jan;37(Database issue):D5-15. Epub 2008 Oct 21.  Benson DA, Karsch-Mizrachi I, Lipman DJ, Ostell J, Sayers EW (2009). GenBank. Nucleic Acids Res. 2009 Jan;37(Database issue):D26-31. Epub 2008 Oct 21."
    },
    {
        "attribute": "rcsb_entity_host_organism.ncbi_parent_scientific_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The parent scientific name in the NCBI taxonomy hierarchy (depth=1) associated with this taxonomy code.  References:  Sayers EW, Barrett T, Benson DA, Bryant SH, Canese K, Chetvernin V, Church DM, DiCuccio M, Edgar R, Federhen S, Feolo M, Geer LY, Helmberg W, Kapustin Y, Landsman D, Lipman DJ, Madden TL, Maglott DR, Miller V, Mizrachi I, Ostell J, Pruitt KD, Schuler GD, Sequeira E, Sherry ST, Shumway M, Sirotkin K, Souvorov A, Starchenko G, Tatusova TA, Wagner L, Yaschenko E, Ye J (2009). Database resources of the National Center for Biotechnology Information. Nucleic Acids Res. 2009 Jan;37(Database issue):D5-15. Epub 2008 Oct 21.  Benson DA, Karsch-Mizrachi I, Lipman DJ, Ostell J, Sayers EW (2009). GenBank. Nucleic Acids Res. 2009 Jan;37(Database issue):D26-31. Epub 2008 Oct 21."
    },
    {
        "attribute": "rcsb_entity_host_organism.ncbi_scientific_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The scientific name associated with this taxonomy code aggregated by the NCBI Taxonomy Database.  This name corresponds to the taxonomy identifier assigned by the PDB depositor.   References:  Sayers EW, Barrett T, Benson DA, Bryant SH, Canese K, Chetvernin V, Church DM, DiCuccio M, Edgar R, Federhen S, Feolo M, Geer LY, Helmberg W, Kapustin Y, Landsman D, Lipman DJ, Madden TL, Maglott DR, Miller V, Mizrachi I, Ostell J, Pruitt KD, Schuler GD, Sequeira E, Sherry ST, Shumway M, Sirotkin K, Souvorov A, Starchenko G, Tatusova TA, Wagner L, Yaschenko E, Ye J (2009). Database resources of the National Center for Biotechnology Information. Nucleic Acids Res. 2009 Jan;37(Database issue):D5-15. Epub 2008 Oct 21.  Benson DA, Karsch-Mizrachi I, Lipman DJ, Ostell J, Sayers EW (2009). GenBank. Nucleic Acids Res. 2009 Jan;37(Database issue):D26-31. Epub 2008 Oct 21."
    },
    {
        "attribute": "rcsb_entity_host_organism.scientific_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The scientific name of the host organism"
    },
    {
        "attribute": "rcsb_entity_host_organism.taxonomy_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Members of the NCBI Taxonomy lineage as parent taxonomy lineage depth (1-N)"
    },
    {
        "attribute": "rcsb_entity_host_organism.taxonomy_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Members of the NCBI Taxonomy lineage as parent taxonomy idcodes."
    },
    {
        "attribute": "rcsb_entity_host_organism.taxonomy_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Members of the NCBI Taxonomy lineage as parent taxonomy names."
    },
    {
        "attribute": "rcsb_entity_source_organism.common_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The common name for the source organism assigned by the PDB depositor."
    },
    {
        "attribute": "rcsb_entity_source_organism.ncbi_common_names",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Common names associated with this taxonomy code aggregated by the NCBI Taxonomy Database.  These name correspond to the taxonomy identifier assigned by the PDB depositor.  References:  Sayers EW, Barrett T, Benson DA, Bryant SH, Canese K, Chetvernin V, Church DM, DiCuccio M, Edgar R, Federhen S, Feolo M, Geer LY, Helmberg W, Kapustin Y, Landsman D, Lipman DJ, Madden TL, Maglott DR, Miller V, Mizrachi I, Ostell J, Pruitt KD, Schuler GD, Sequeira E, Sherry ST, Shumway M, Sirotkin K, Souvorov A, Starchenko G, Tatusova TA, Wagner L, Yaschenko E, Ye J (2009). Database resources of the National Center for Biotechnology Information. Nucleic Acids Res. 2009 Jan;37(Database issue):D5-15. Epub 2008 Oct 21.  Benson DA, Karsch-Mizrachi I, Lipman DJ, Ostell J, Sayers EW (2009). GenBank. Nucleic Acids Res. 2009 Jan;37(Database issue):D26-31. Epub 2008 Oct 21."
    },
    {
        "attribute": "rcsb_entity_source_organism.ncbi_parent_scientific_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A parent scientific name in the NCBI taxonomy hierarchy of the source organism assigned by the PDB depositor. For cellular organism this corresponds to a superkingdom (e.g., Archaea, Bacteria, Eukaryota). For viruses this corresponds to a clade (e.g. Adnaviria, Bicaudaviridae, Clavaviridae). For other and unclassified entries this corresponds to the first level of any taxonomic rank below the root level.  References:  Sayers EW, Barrett T, Benson DA, Bryant SH, Canese K, Chetvernin V, Church DM, DiCuccio M, Edgar R, Federhen S, Feolo M, Geer LY, Helmberg W, Kapustin Y, Landsman D, Lipman DJ, Madden TL, Maglott DR, Miller V, Mizrachi I, Ostell J, Pruitt KD, Schuler GD, Sequeira E, Sherry ST, Shumway M, Sirotkin K, Souvorov A, Starchenko G, Tatusova TA, Wagner L, Yaschenko E, Ye J (2009). Database resources of the National Center for Biotechnology Information. Nucleic Acids Res. 2009 Jan;37(Database issue):D5-15. Epub 2008 Oct 21.  Benson DA, Karsch-Mizrachi I, Lipman DJ, Ostell J, Sayers EW (2009). GenBank. Nucleic Acids Res. 2009 Jan;37(Database issue):D26-31. Epub 2008 Oct 21."
    },
    {
        "attribute": "rcsb_entity_source_organism.ncbi_scientific_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The scientific name associated with this taxonomy code aggregated by the NCBI Taxonomy Database.  This name corresponds to the taxonomy identifier assigned by the PDB depositor.   References:  Sayers EW, Barrett T, Benson DA, Bryant SH, Canese K, Chetvernin V, Church DM, DiCuccio M, Edgar R, Federhen S, Feolo M, Geer LY, Helmberg W, Kapustin Y, Landsman D, Lipman DJ, Madden TL, Maglott DR, Miller V, Mizrachi I, Ostell J, Pruitt KD, Schuler GD, Sequeira E, Sherry ST, Shumway M, Sirotkin K, Souvorov A, Starchenko G, Tatusova TA, Wagner L, Yaschenko E, Ye J (2009). Database resources of the National Center for Biotechnology Information. Nucleic Acids Res. 2009 Jan;37(Database issue):D5-15. Epub 2008 Oct 21.  Benson DA, Karsch-Mizrachi I, Lipman DJ, Ostell J, Sayers EW (2009). GenBank. Nucleic Acids Res. 2009 Jan;37(Database issue):D26-31. Epub 2008 Oct 21."
    },
    {
        "attribute": "rcsb_entity_source_organism.scientific_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The scientific name of the source organism assigned by the PDB depositor."
    },
    {
        "attribute": "rcsb_entity_source_organism.source_type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The source type for the entity Allowed Values: genetically engineered, natural, synthetic"
    },
    {
        "attribute": "rcsb_entity_source_organism.taxonomy_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Members of the NCBI Taxonomy lineage as parent taxonomy lineage depth (1-N)"
    },
    {
        "attribute": "rcsb_entity_source_organism.taxonomy_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Members of the NCBI Taxonomy lineage as parent taxonomy idcodes."
    },
    {
        "attribute": "rcsb_entity_source_organism.taxonomy_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Memebers of the NCBI Taxonomy lineage as parent taxonomy names."
    },
    {
        "attribute": "rcsb_entity_source_organism.rcsb_gene_name.value",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Gene name."
    },
    {
        "attribute": "rcsb_genomic_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Automatically assigned ID that uniquely identifies taxonomy, chromosome or gene in the Genome Location Browser."
    },
    {
        "attribute": "rcsb_membrane_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Hierarchy depth."
    },
    {
        "attribute": "rcsb_membrane_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Automatically assigned ID for membrane classification term in the Membrane Protein Browser."
    },
    {
        "attribute": "rcsb_membrane_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Membrane protein classification term."
    },
    {
        "attribute": "rcsb_polymer_entity.formula_weight",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Formula mass (KDa) of the entity."
    },
    {
        "attribute": "rcsb_polymer_entity.pdbx_description",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description of the polymer entity."
    },
    {
        "attribute": "rcsb_polymer_entity.pdbx_number_of_molecules",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of molecules of the entity in the entry."
    },
    {
        "attribute": "rcsb_polymer_entity.rcsb_source_part_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of biological sources for the polymer entity. Multiple source contributions may come from the same organism (taxonomy)."
    },
    {
        "attribute": "rcsb_polymer_entity.rcsb_source_taxonomy_count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The number of distinct source taxonomies for the polymer entity. Commonly used to identify chimeric polymers."
    },
    {
        "attribute": "rcsb_polymer_entity.rcsb_ec_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Members of the enzyme classification lineage as parent classification hierarchy depth (1-N)."
    },
    {
        "attribute": "rcsb_polymer_entity.rcsb_ec_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Members of the enzyme classification lineage as parent classification codes."
    },
    {
        "attribute": "rcsb_polymer_entity.rcsb_ec_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Members of the enzyme classification lineage as parent classification names."
    },
    {
        "attribute": "rcsb_polymer_entity.rcsb_macromolecular_names_combined.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Combined list of macromolecular names."
    },
    {
        "attribute": "rcsb_polymer_entity.rcsb_enzyme_class_combined.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The enzyme classification hierarchy depth (1-N)."
    },
    {
        "attribute": "rcsb_polymer_entity.rcsb_enzyme_class_combined.ec",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Combined list of enzyme class assignments."
    },
    {
        "attribute": "rcsb_polymer_entity.rcsb_enzyme_class_combined.provenance_source",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Combined list of enzyme class associated provenance sources. Allowed Values: PDB Primary Data, UniProt"
    },
    {
        "attribute": "rcsb_polymer_entity.rcsb_polymer_name_combined.names",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Protein name annotated by the UniProtKB or macromolecular name assigned by the PDB."
    },
    {
        "attribute": "rcsb_polymer_entity_annotation.annotation_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "An identifier for the annotation."
    },
    {
        "attribute": "rcsb_polymer_entity_annotation.description",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A description for the annotation."
    },
    {
        "attribute": "rcsb_polymer_entity_annotation.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A name for the annotation."
    },
    {
        "attribute": "rcsb_polymer_entity_annotation.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A type or category of the annotation. Allowed Values: CARD, GO, GlyCosmos, GlyGen, InterPro, MemProtMD, OPM, PDBTM, Pfam, mpstruc"
    },
    {
        "attribute": "rcsb_polymer_entity_annotation.annotation_lineage.depth",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent lineage depth (1-N)"
    },
    {
        "attribute": "rcsb_polymer_entity_annotation.annotation_lineage.id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class identifiers."
    },
    {
        "attribute": "rcsb_polymer_entity_annotation.annotation_lineage.name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Members of the annotation lineage as parent class names."
    },
    {
        "attribute": "rcsb_polymer_entity_container_identifiers.chem_comp_monomers",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Unique list of monomer chemical component identifiers in the polymer entity in this container."
    },
    {
        "attribute": "rcsb_polymer_entity_container_identifiers.chem_ref_def_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The chemical reference definition identifier for the entity in this container."
    },
    {
        "attribute": "rcsb_polymer_entity_container_identifiers.entry_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Entry identifier for the container."
    },
    {
        "attribute": "rcsb_polymer_entity_container_identifiers.prd_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The BIRD identifier for the entity in this container."
    },
    {
        "attribute": "rcsb_polymer_entity_container_identifiers.rcsb_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A unique identifier for each object in this entity container formed by an underscore separated concatenation of entry and entity identifiers."
    },
    {
        "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Reference database accession code"
    },
    {
        "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_isoform",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Reference database identifier for the sequence isoform"
    },
    {
        "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_name",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Reference database name Allowed Values: EMBL, GenBank, NDB, NORINE, PDB, PIR, PRF, RefSeq, UniProt"
    },
    {
        "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.entity_sequence_coverage",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Indicates what fraction of this polymer entity sequence is covered by the reference sequence."
    },
    {
        "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.reference_sequence_coverage",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Indicates what fraction of the reference sequence is covered by this polymer entity sequence."
    },
    {
        "attribute": "rcsb_polymer_entity_feature_summary.count",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The feature count."
    },
    {
        "attribute": "rcsb_polymer_entity_feature_summary.coverage",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The fractional feature coverage relative to the full entity sequence. For instance, the fraction of features such as mutations, artifacts or modified monomers relative to the length of the entity sequence."
    },
    {
        "attribute": "rcsb_polymer_entity_feature_summary.maximum_length",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The maximum feature length."
    },
    {
        "attribute": "rcsb_polymer_entity_feature_summary.minimum_length",
        "type": "integer",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The minimum feature length."
    },
    {
        "attribute": "rcsb_polymer_entity_feature_summary.type",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Type or category of the feature. Allowed Values: CARD_MODEL, IMGT_ANTIBODY_DESCRIPTION, IMGT_ANTIBODY_DOMAIN_NAME, IMGT_ANTIBODY_GENE_ALLELE_NAME, IMGT_ANTIBODY_ORGANISM_NAME, IMGT_ANTIBODY_PROTEIN_NAME, IMGT_ANTIBODY_RECEPTOR_DESCRIPTION, IMGT_ANTIBODY_RECEPTOR_TYPE, Pfam, SABDAB_ANTIBODY_ANTIGEN_NAME, SABDAB_ANTIBODY_NAME, SABDAB_ANTIBODY_TARGET, artifact, modified_monomer, mutation"
    },
    {
        "attribute": "rcsb_polymer_entity_group_membership.aggregation_method",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Method used to establish group membership Allowed Values: matching_uniprot_accession, sequence_identity"
    },
    {
        "attribute": "rcsb_polymer_entity_group_membership.group_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "A unique identifier for a group of entities"
    },
    {
        "attribute": "rcsb_polymer_entity_group_membership.similarity_cutoff",
        "type": "number",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "Degree of similarity expressed as a floating-point number"
    },
    {
        "attribute": "rcsb_polymer_entity_keywords.text",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "Keywords describing this polymer entity."
    },
    {
        "attribute": "rcsb_polymer_entity_name_com.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "A common name for the polymer entity."
    },
    {
        "attribute": "rcsb_polymer_entity_name_sys.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The systematic name for the polymer entity."
    },
    {
        "attribute": "drugbank_container_identifiers.drugbank_id",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The DrugBank accession code"
    },
    {
        "attribute": "drugbank_info.affected_organisms",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The DrugBank drug affected organisms."
    },
    {
        "attribute": "drugbank_info.atc_codes",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The Anatomical Therapeutic Chemical Classification System (ATC) codes."
    },
    {
        "attribute": "drugbank_info.brand_names",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "DrugBank drug brand names."
    },
    {
        "attribute": "drugbank_info.cas_number",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The DrugBank assigned Chemical Abstracts Service identifier."
    },
    {
        "attribute": "drugbank_info.description",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The DrugBank drug description."
    },
    {
        "attribute": "drugbank_info.drug_categories",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The DrugBank drug categories."
    },
    {
        "attribute": "drugbank_info.drug_groups",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The DrugBank drug groups determine their drug development status. Allowed Values: approved, experimental, illicit, investigational, nutraceutical, vet_approved, withdrawn"
    },
    {
        "attribute": "drugbank_info.indication",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The DrugBank drug indication."
    },
    {
        "attribute": "drugbank_info.mechanism_of_action",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The DrugBank drug mechanism of actions."
    },
    {
        "attribute": "drugbank_info.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The DrugBank drug name."
    },
    {
        "attribute": "drugbank_info.pharmacology",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The DrugBank drug pharmacology."
    },
    {
        "attribute": "drugbank_info.synonyms",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "DrugBank drug name synonyms."
    },
    {
        "attribute": "drugbank_info.drug_products.approved",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "Indicates whether this drug has been approved by the regulating government. Allowed Values: N, Y"
    },
    {
        "attribute": "drugbank_info.drug_products.country",
        "type": "string",
        "operators": [
            "in",
            "exact_match",
            "exists"
        ],
        "description": "The country where this commercially available drug has been approved. Allowed Values: Canada, EU, US"
    },
    {
        "attribute": "drugbank_info.drug_products.ended_marketing_on",
        "type": "date",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The ending date for market approval."
    },
    {
        "attribute": "drugbank_info.drug_products.started_marketing_on",
        "type": "date",
        "operators": [
            "equals",
            "greater",
            "less",
            "greater_or_equal",
            "less_or_equal",
            "range",
            "exists"
        ],
        "description": "The starting date for market approval."
    },
    {
        "attribute": "drugbank_target.interaction_type",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The type of target interaction."
    },
    {
        "attribute": "drugbank_target.name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The target name."
    },
    {
        "attribute": "drugbank_target.organism_common_name",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The organism common name."
    },
    {
        "attribute": "drugbank_target.target_actions",
        "type": "string",
        "operators": [
            "contains_phrase",
            "contains_words",
            "exists"
        ],
        "description": "The actions of the target interaction."
    }
]