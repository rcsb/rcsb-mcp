"""Deterministic guard for load-bearing tool-description content.

Tool descriptions and their input schemas are the only text the protocol always delivers
to the model: the server's ``instructions`` block is a map of the tool families that some
clients drop (checked at the end of this module), and prompts are opt-in. These
assertions lock in the cross-field rules and routing gotchas the JSON schema cannot encode,
so a future trim can't silently delete one.

"Delivered" is narrower than "present". Claude Code cuts each tool description at
DESCRIPTION_CUTOFF characters of whitespace-collapsed text, so a phrase past that point is
in the docstring but never reaches the model there. Input-schema descriptions are not cut,
which is why per-argument documentation lives in ``Field(description=...)`` (see
rcsb_mcp/descriptions/). The checks below therefore read two things:

* ``_descriptions()`` -- everything the model can read: description + schema descriptions.
  The "must not contain" scanners use it, so text moved into a schema stays guarded.
* ``_delivered()`` -- what actually arrives in Claude Code: the description up to the
  cutoff, plus the schema. The "must reach the model" checks use it.

No network, no API key, no model — this is the cheap CI gate. The behavioral A/B that
checks whether the model still *acts* on this text lives in ``evals/tool_selection/``.
"""
import asyncio
import fnmatch
import re

from rcsb_mcp import server

#: Claude Code truncates each MCP tool description here, counting whitespace-collapsed text.
#: Measured 2026-10-06: rcsb_search_request's 5,416-char description arrived cut at exactly
#: char 2,048 ("...request. Ignore... [truncated]"), losing 9 of its 14 guarded phrases.
DESCRIPTION_CUTOFF = 2048


def _norm(s: str) -> str:
    """Collapse whitespace so line-wrapping in a docstring never hides a phrase."""
    return re.sub(r"\s+", " ", s or "")


def _utf16_len(s: str) -> int:
    """String length as a JavaScript client counts it (UTF-16 code units)."""
    return len(s.encode("utf-16-le")) // 2


def _utf16_prefix(s: str, n: int) -> str:
    return s.encode("utf-16-le")[: 2 * n].decode("utf-16-le", "ignore")


def _schema_descriptions(node) -> list[str]:
    """The readable text of a JSON schema: property NAMES and every description string.

    Names count because the model reads them -- `group_by` used to be satisfied by the
    `group_by:` label of an Args section and is now a property name, delivered either way.
    The schema is not matched as JSON because escaping breaks phrases (`return_type=\\"...`).
    Only a ``description`` key whose value is a STRING counts, so a property that happens to
    be NAMED ``description`` (its value is a schema dict) is descended into, not collected.
    """
    if isinstance(node, dict):
        out: list[str] = []
        for key, value in node.items():
            if key == "description" and isinstance(value, str):
                out.append(value)
            else:
                if key == "properties" and isinstance(value, dict):
                    out.extend(value)  # the property names themselves
                out.extend(_schema_descriptions(value))
        return out
    if isinstance(node, list):
        return [d for item in node for d in _schema_descriptions(item)]
    return []


def _tools():
    return asyncio.run(server.mcp.list_tools())


def _collapsed(description: str | None) -> str:
    return _norm(description).strip()


def _descriptions():
    """Everything a model can read about each tool: description AND input-schema text."""
    return {
        t.name: _norm(" || ".join([t.description or "", *_schema_descriptions(t.inputSchema)]))
        for t in _tools()
    }


def _delivered():
    """What reaches the model in Claude Code: the description up to the cutoff + the schema."""
    return {
        t.name: _norm(" || ".join([
            _utf16_prefix(_collapsed(t.description), DESCRIPTION_CUTOFF),
            *_schema_descriptions(t.inputSchema),
        ]))
        for t in _tools()
    }


# Gotchas that must stay in the SPECIFIC tool's own description: they are not derivable
# from the schema, and no shared channel is guaranteed to arrive.
REQUIRED_IN_TOOL = {
    "rcsb_query_fulltext": [
        "text-relevance, NOT biological importance",   # score is not quality
        "AND/OR/NOT are NOT boolean",                   # query-string gotcha
        # Rare-term recall: resolve a biological CONCEPT to an ontology id before keyword
        # searching it. Moved off rcsb_search_assistant.md, which is optional and may never
        # be loaded — this is the only channel guaranteed to arrive.
        "resolve it to an ontology id",
    ],
    "rcsb_query_attribute": [
        "an empty result is a valid answer",            # don't fall back to keyword search
        "carries NO biological meaning",                # score caveat (attribute form)
        "EXCLUSIVE",                                     # range bound semantics
        "rcsb_query_composer",                          # where nested boolean groups go now
    ],
    "rcsb_query_sequence": [
        "rcsb_query_seqmotif",                           # routing: pattern vs full sequence
    ],
    "rcsb_query_chemical": [
        "fingerprint-similarity",                        # match_type option
        "sub-struct-graph",                              # substructure option
        "merely contain the",                            # match_subset semantics
    ],
    "rcsb_query_structure": [
        "mutually exclusive",                            # assembly_id vs asym_id
        "Defaults to assembly",
    ],
    "rcsb_query_seqmotif": [
        "prosite",
        "simple wildcards",
    ],
    "rcsb_query_strucmotif": [
        "mmCIF",                                         # label-vs-author id explanation
        "author numbers give wrong/no hits",
        "catalytic triads",                              # when-to-use routing
        "PSEUDO_ATOMS",                                  # atom_pairing_scheme option
    ],
    "rcsb_query_composer": [
        "`in` operator",                                 # don't OR a list of alternatives
        "mixes services",                                # the other reason to compose
    ],
    # The envelope prose now lives ONCE, here, instead of on every search tool. These are
    # the cross-field rules that used to be repeated seven times; if this tool's docstring
    # is trimmed they have no other home.
    "rcsb_search_request": [
        "SORTABLE attributes",                           # sort_by only works on some paths
        'return_type="mol_definition"',                  # sort_by limitation
        "refused above 10000",                           # all_hits cap
        "cannot be combined with offset",                # all_hits + paging
        "requires return_type=\"polymer_entity\"",       # group_by precondition
        "Nothing is searched until you call it",         # the layered-flow gotcha
        "IDENTIFIERS only",                              # results need a rcsb_get_* follow-up
        # return_type is chosen HERE, so every hint about it lives here and nowhere else:
        # the six values, the per-query default, the id shape, and the conversion trick.
        "4HHB_1",                                        # what a polymer_entity id looks like
        "Setting it CONVERTS the result",                # e.g. ligand filter -> entries
        "default implied by the query",                  # why omitting it is usually right
        # Picking a cluster representative by relevance score is a distinct mistake from
        # ranking hits by it; this caveat used to live in the guide's grouping section.
        "don't pick a cluster representative by it",
        # Faceting a result set to find what the hits SHARE is the discovery move that
        # turns a handful of hits into a re-searchable value. It was documented only as a
        # reporting device ("how many by X"), so agents reached for it when a COUNTING
        # question was asked and never when they needed to broaden or explore.
        "what your hits SHARE",
        # And the second half, which is what makes the first usable. A facet's population is
        # within the result set; nothing in the response says how common the value is in the
        # archive, and that is the only thing separating a useful value from a useless one at
        # EVERY membership level. Measured on 4 phrase hits for "receptor-like cytoplasmic
        # kinase": IPR050823 and IPR000719 both appear in 4/4 and are 8 vs 10,744 entities
        # archive-wide; GO:0002221 and GO:0005634 both appear in 1/4 and are 486 vs 104,027.
        # Bucket order is no help — it returned the 10,744 first and the 8 last. Without this
        # sentence the natural read of "what your hits share" is the top bucket.
        "archive-wide count is a",
        "distinctive or generic",
    ],
    # rcsb_get_* family: the `fields`-param mechanics were shortened to a pointer, but each
    # tool's cross-reference / drill-down guidance must survive the trim.
    "rcsb_get_entries": [
        "rcsb_entry_container_identifiers",              # component-id drill-down
        "compose them with the entry id",                # how to build sibling-tool ids
    ],
    # An agent reported constructing entity ids as <ENTRY>_1 rather than looking them up.
    # The composition rule above is correct and the ids ARE readable, which is exactly the
    # trap: the guess is never REJECTED, so nothing teaches the agent it was wrong.
    #
    #   polymer entity   <ENTRY>_1   exists ~always   SILENT: 6J5U_1 is an NLR immune
    #                                                 receptor, the RLCK is 6J5U_2
    #   instance         <ENTRY>.A   exists ~always   SILENT: 45-54% of matching instances
    #                                                 are not .A, and .A is the LABEL asym
    #                                                 id -- 6J5T.A is author chain I
    #   assembly         <ENTRY>-1   exists ~always   SILENT: 43% of matching assemblies
    #                                                 are not -1
    #   non-polymer      <ENTRY>_1   never exists     LOUD: lands in not_found
    #
    # Each warning names the CONSEQUENCE, not the rule: "do not invent ids" describes no
    # observable outcome, since a guessed id returns real data about a real molecule.
    "rcsb_get_polymer_entities": [
        # Where the ids come FROM. Was "rcsb_query_sequence" until 2026-08-06; that named a
        # BUILDER, which returns a query document and no ids at all — stale since the
        # builder/executor split. The executor is what yields them, so the hint has to name
        # it and the return_type that produces this id shape.
        "rcsb_search_request",
        'return_type="polymer_entity"',
        "NEVER form one by appending _1",
        "nothing in the response marks it wrong",
    ],
    "rcsb_get_polymer_entity_instances": [
        'Do not guess ".A"',
        "LABEL asym_id, not the author",
    ],
    "rcsb_get_assemblies": [
        'Do not guess "-1"',
        "the first is not necessarily the one",
    ],
    "rcsb_get_nonpolymer_entities": [
        "rcsb_get_chem_comps",                           # where to get the ligand chemistry
        # See the comment on rcsb_get_polymer_entities. This is the ONE of the four whose
        # guess fails loudly -- entity numbering is shared with the polymers and they take
        # the low values, so 0 of 6,495 HEM entities sit at _1 and "<ENTRY>_1" lands in
        # not_found. Kept anyway so the four ids are documented consistently.
        "entity numbering is shared with the",
    ],
    "rcsb_get_uniprot": [
        "rcsb_uniprot_annotation",                       # heavier optional annotation sets ...
        "rcsb_uniprot_feature",
    ],
    "rcsb_get_chem_comps": [
        "InChIKey",                                      # a default field callers rely on
    ],
    # ReportRequest.api_calls: resolver and discovery calls are listed too, without an editor.
    # The docstring's "Key fields" block said so until it moved into the schema, and the
    # first copy there dropped it.
    "rcsb_render_report": [
        "each with label and tool_name",
        "rcsb_find_*, rcsb_describe_*, rcsb_list_pdb_search_attributes",
    ],
    # rcsb_find_* resolvers: the search-by-id recipe was once delegated to the retired guide
    # (the old instructions block), but these bits always lived ONLY here. `namespace`/
    # `entry_type` are `str | None` (NOT Literals), so their allowed values never reach the
    # JSON schema — this docstring is their only home.
    "rcsb_find_go_terms": [
        # namespace's values are no longer guarded here: it is now a GoNamespace Literal, so the
        # schema ships the enum (incl. the mf/bp/cc aliases) and the prose is redundant.
        "are involved in",                               # trigger paraphrases (not in the retired guide)
        "localized to",
    ],
    "rcsb_find_interpro_domains": [
        # entry_type's values are no longer guarded here: it is now an InterProEntryType Literal,
        # so the schema ships the enum (incl. the "superfamily" alias) and the prose is redundant.
        "-containing proteins",                          # trigger paraphrase (not in the retired guide)
    ],
    "rcsb_find_enzyme_classes": [
        "break down / degrade",                          # fires when no enzyme is NAMED
    ],
    "rcsb_find_disease_terms": [
        "implicated in",                                 # trigger paraphrase
    ],
    "rcsb_find_organisms": [
        "disambiguates a species from its strains",      # not in the retired guide ('strain' absent)
    ],
    # rcsb_seqcoord_*: the reference VALUES are a Literal (SequenceRef), so the
    # schema ships them and the prose was cut. These are what the schema cannot express — the
    # per-system id FORMATS and the entity-level rule.
    "rcsb_seqcoord_alignments": [
        "entry_entityNumber",                            # PDB_ENTITY id format
        "entry.asym_id",                                 # PDB_INSTANCE id format
        "ENTITY-level",                                  # a bare entry id silently fails
        "only cross-references UniProt",                 # why not the Data API (routing)
    ],
}

# Guidance that used to live in the rcsb_mcp_guide prompt and is now asserted against the
# TOOL DESCRIPTIONS instead. This is a strictly stronger guarantee than the old one: a
# prompt arrives only if the client asks for it, so pointing a tool description at one and
# then checking the prompt still contains the answer verified the wrong half of the promise.
# tools/list always arrives, so if a phrase is here, the model received it.
REQUIRED_SOMEWHERE_IN_TOOL_DESCRIPTIONS = [
    # Ontology resolvers: each rcsb_find_* tool now carries its own attribute path, so a
    # resolved id has a documented way to be used no matter what the client loaded.
    "rcsb_polymer_entity_annotation.annotation_lineage.id",   # GO (term + descendants)
    "annotation_id",                                          # GO exact-term-only path
    "rcsb_polymer_entity_annotation.annotation_id",           # InterPro (NOT lineage)
    "rcsb_polymer_entity.rcsb_ec_lineage.id",                 # EC (hierarchical)
    "rcsb_uniprot_annotation.annotation_lineage.id",          # MONDO (UniProt-derived)
    "rcsb_entity_source_organism.taxonomy_lineage.id",        # NCBI taxonomy
    "HIERARCHICAL",                                           # lineage matching semantics
    'AS A STRING ("9606", not 9606',                          # taxon id-typing gotcha
    # Envelope guidance, now on rcsb_search_request.
    "group_by",
    "return_type",
    # `fields=` verification, now on the describe tools.
    "NEVER invent, guess, or infer a field path",
]

# Content from the retired guide that was deliberately NOT relocated, and is therefore
# reachable by no agent. Recorded rather than asserted so the gap stays visible: it is a
# decision, not an oversight. prompts/rcsb_mcp_guide.md keeps the prose to restore from.
NOT_RELOCATED = [
    "polymer_entity_instance_count_protein",   # assembly / multimer composition attributes
    "heteromeric",                             # "
    "A protein or gene NAME is a structured attribute, not a keyword",
]


def test_tool_gotchas_survive():
    delivered = _delivered()
    missing = []
    for tool, phrases in REQUIRED_IN_TOOL.items():
        assert tool in delivered, f"tool {tool} is not registered"
        for phrase in phrases:
            if _norm(phrase) not in delivered[tool]:
                missing.append(f"{tool}: {phrase!r}")
    assert not missing, (
        "load-bearing text does not reach the model: keep it in the tool's description "
        f"BEFORE the {DESCRIPTION_CUTOFF}-char cutoff, or move it into the input schema "
        "with Field(description=...):\n  " + "\n  ".join(missing)
    )


def test_every_description_fits_the_claude_code_cutoff():
    """Text past the cutoff is silently lost in Claude Code, and nothing else would say so.

    rcsb_search_request carried its Args and Returns past the cut for weeks while
    test_tool_gotchas_survive passed, because that test only checked the phrases were
    PRESENT. Per-argument documentation belongs in Field(description=...), which travels
    in the input schema and is not cut.
    """
    over = {
        t.name: _utf16_len(_collapsed(t.description))
        for t in _tools()
        if _utf16_len(_collapsed(t.description)) > DESCRIPTION_CUTOFF
    }
    assert not over, (
        f"tool descriptions longer than {DESCRIPTION_CUTOFF} chars (collapsed) are truncated "
        "in Claude Code; move per-argument docs into Field(description=...):\n  "
        + "\n  ".join(f"{name}: {n}" for name, n in sorted(over.items(), key=lambda kv: -kv[1]))
    )


def test_no_tool_description_has_an_args_section():
    """Argument documentation lives in the input schema, never in an ``Args:`` section.

    An Args section is what pushed five descriptions past DESCRIPTION_CUTOFF, silently dropping
    their tails in Claude Code. One rule for every tool: the description says what the tool is
    for and when to use it; each argument's text is a ``Field(description=...)`` whose wording
    lives in rcsb_mcp/descriptions/<module>/<tool>.py.
    """
    offenders = sorted(t.name for t in _tools() if re.search(r"^\s*Args:\s*$", t.description or "", re.M))
    assert not offenders, (
        "move these tools' argument docs into Field(description=...) "
        "(wording in rcsb_mcp/descriptions/):\n  " + "\n  ".join(offenders)
    )


def _schema_properties(node) -> set[str]:
    """Every property name anywhere in a JSON schema, $defs included."""
    if isinstance(node, dict):
        names = set(node.get("properties") or {}) if isinstance(node.get("properties"), dict) else set()
        return names.union(*(_schema_properties(v) for v in node.values()))
    if isinstance(node, list):
        return set().union(*(_schema_properties(v) for v in node))
    return set()


def _input_part(description: str | None) -> str:
    """A description up to its Returns section, which names OUTPUT fields."""
    return re.split(r"^[ \t]*Returns:[ \t]*$", description or "", maxsplit=1, flags=re.M)[0]


def test_no_tool_description_documents_a_schema_property():
    """An Args section under another heading is still an Args section.

    rcsb_render_report's "Key fields of ``report``:" listed five ReportRequest fields as
    `name: text` lines, so the ``Args:`` check above never saw it, and its copy had drifted
    from the schema's (it called result_type defaulted; the schema makes it REQUIRED). A line
    that starts with an input property's name and a colon is that pattern, whatever the
    heading: bare, bulleted (`-`/`*`), backticked, dotted (`report.title`) or typed
    (`title (str):`). The Returns section is left out, since output fields can share a name
    with an input.
    """
    offenders = []
    for t in _tools():
        text = _input_part(t.description)
        for name in sorted(_schema_properties(t.inputSchema)):
            line = (rf"^[ \t]*(?:[-*][ \t]+)?`{{0,2}}(?:[\w.]+\.)?{re.escape(name)}`{{0,2}}"
                    rf"(?:[ \t]*\([^)]*\))?[ \t]*:")
            if re.search(line, text, re.M):
                offenders.append(f"{t.name}: {name}")
    assert not offenders, (
        "these descriptions document input fields; put the text in the field's "
        "Field(description=...) instead:\n  " + "\n  ".join(offenders)
    )


def _refs(node) -> list[str]:
    """The $defs names a property schema points at, through arrays, tuples, maps and
    anyOf/oneOf/allOf."""
    if not isinstance(node, dict):
        return []
    out = [node["$ref"].split("/")[-1]] if "$ref" in node else []
    for key in ("items", "prefixItems", "additionalProperties", "anyOf", "oneOf", "allOf"):
        sub = node.get(key)
        for item in sub if isinstance(sub, list) else [sub] if sub else []:
            out += _refs(item)
    return out


#: Model fields left undescribed on purpose, as "<Model>.<field>". QueryDocument.query: its
#: $defs block is emitted into two tools, and their argument descriptions cover the pair
#: (see the comment on QueryDocument in search.py).
BARE_BY_DESIGN = {"QueryDocument.query"}


def _documented_through(prop: dict, defs: dict, seen: frozenset = frozenset()) -> bool:
    """True when every model an argument points at is documented and describes every one of
    its own fields, all the way down. A field left undescribed in a nested model is as
    undocumented as one at the top: ReportRequest.api_calls and .data_usage were, behind a
    one-level check."""
    for name in _refs(prop):
        target = defs.get(name)
        if not target or not target.get("description"):
            return False
        if name in seen:
            continue
        for fname, field in target.get("properties", {}).items():
            if not field.get("description") and f"{name}.{fname}" not in BARE_BY_DESIGN:
                return False
            if not _documented_through(field, defs, seen | {name}):
                return False
    return True


def test_every_argument_has_a_schema_description():
    """With Args sections gone, an argument without a schema description is undocumented.

    An argument that is a model may leave its own description to the model (rcsb_render_
    report's `params`, a ReportRequest wrapper); any argument pointing at models needs them
    documented all the way down, whether or not it carries a description itself.
    """
    missing = []
    for t in _tools():
        defs = t.inputSchema.get("$defs", {})
        for name, prop in t.inputSchema.get("properties", {}).items():
            refs = _refs(prop)
            if (refs and not _documented_through(prop, defs)) or (not refs and not prop.get("description")):
                missing.append(f"{t.name}.{name}")
    assert not missing, (
        "arguments with no schema description, or pointing at a model with an undescribed "
        "class or field -- add Field(description=...) with its wording in "
        "rcsb_mcp/descriptions/:\n  " + "\n  ".join(missing)
    )


def test_every_get_tool_fields_doc_names_the_object_the_tool_queries():
    """Each rcsb_get_* `fields` text is the shared template filled with one Data API object.

    It must be the object the tool's own code queries: naming another one sends the model to
    rcsb_describe_data_object for paths that then fail on this tool. Both sides are read
    from the source -- the description as delivered, the object from the tool's body -- so
    neither can drift alone.
    """
    import inspect

    from rcsb_mcp import data, queries

    problems = []
    for t in _tools():
        if not t.name.startswith("rcsb_get_"):
            continue
        named = re.search(
            r'rcsb_describe_data_object\("([a-z_]+)"\)',
            t.inputSchema["properties"]["fields"].get("description", ""),
        )
        queried = re.search(r'_query_(?:batch|single)\(\s*"([a-z_]+)"', inspect.getsource(getattr(data, t.name)))
        if not (named and queried):
            problems.append(f"{t.name}: could not read the object (named={named}, queried={queried})")
        elif named.group(1) != queried.group(1):
            problems.append(f"{t.name}: fields text names {named.group(1)!r}, code queries {queried.group(1)!r}")
        elif named.group(1) not in queries.DATA_OBJECTS:
            problems.append(f"{t.name}: {named.group(1)!r} is not a DATA_OBJECTS key")
    assert not problems, "\n  ".join(["fields text out of step with the tool:", *problems])


def test_relocated_guidance_reaches_the_model():
    """Every rule the retired guide used to hold must now be on a tool description.

    The guide was removed because a prompt is delivered only when the client asks for it.
    Anything that mattered had to move to tools/list, which always arrives — this checks
    it actually did, rather than that it survived somewhere no one may read.
    """
    everything = " || ".join(_delivered().values())
    missing = [p for p in REQUIRED_SOMEWHERE_IN_TOOL_DESCRIPTIONS if _norm(p) not in everything]
    assert not missing, (
        "these rules moved off the retired guide but reached no tool description:\n  "
        + "\n  ".join(missing)
    )


def test_the_unrelocated_gap_is_still_the_gap_we_think_it_is():
    """NOT_RELOCATED records what the retirement dropped. If a phrase turns up on a tool,
    it was relocated after all and belongs in the required list instead — otherwise the
    record drifts into fiction and stops being a usable to-do."""
    everything = " || ".join(_descriptions().values())
    resurfaced = [p for p in NOT_RELOCATED if _norm(p) in everything]
    assert not resurfaced, (
        "these are recorded as NOT relocated but now appear on a tool description; move "
        "them into REQUIRED_SOMEWHERE_IN_TOOL_DESCRIPTIONS:\n  " + "\n  ".join(resurfaced)
    )


def test_no_description_points_at_the_instructions_block():
    """Claude web drops the `instructions` block, so a description citing it sends the agent
    nowhere there. The block is a map of the tool families, not a place to look things up.

    Kept as a distinct assertion from the one above because the failure modes differ: that
    one catches guidance deleted from the guide, this one catches a REFERENCE to a channel
    that may never arrive. No tool text needs the word, so any use of it is caught, in any
    case and with or without backticks ("the server `instructions` block").
    """
    stale = sorted(n for n, d in _descriptions().items()
                   if re.search(r"\binstructions\b", d, re.IGNORECASE))
    assert not stale, (
        "these tool descriptions cite the `instructions` block, which some clients drop:\n  "
        + "\n  ".join(stale)
    )


# --------------------------------------------------------------------------- #
# The `instructions` block: a map of the tool families (server.INSTRUCTIONS)
# --------------------------------------------------------------------------- #
#: A ceiling on what the map may grow into, far below the 2048-char cut that cost the
#: retired guide 85% of its text. Past it the block is turning back into a guide, whose
#: rules belong on the tools that need them.
INSTRUCTIONS_BUDGET = 1000
INSTRUCTIONS_HEADER = "RCSB PDB tools, by family:"

#: A tool name or a family glob, whole (`rcsb_get_*`, `rcsb_*_groups`).
_MAP_CITATION = re.compile(r"\brcsb_[A-Za-z0-9_*]+")
#: A map line: "- <tool name or family glob>: <what it does>".
_MAP_LINE = re.compile(r"- (rcsb_[A-Za-z0-9_*]+): \S")


def _instructions() -> str:
    return server.mcp.instructions or ""


def _map_lines() -> tuple[str, list[str]]:
    header, *lines = _instructions().splitlines() or [""]
    return header, lines


def _map_heads() -> list[str]:
    """The tool name or family glob each map line is about."""
    return [m.group(1) for line in _map_lines()[1] if (m := _MAP_LINE.match(line))]


def test_the_instructions_block_is_a_short_map():
    """A fixed header, then one '- <name>: ...' line per family, within the budget. The shape
    is what keeps it a map: a rule or gotcha added here would arrive in Claude Code and
    nowhere in Claude web."""
    text = _instructions()
    assert text, "server.py passes no instructions= (see INSTRUCTIONS)"
    size = _utf16_len(_collapsed(text))
    assert size <= INSTRUCTIONS_BUDGET, (
        f"instructions is {size} chars, over its {INSTRUCTIONS_BUDGET}-char budget: it is a "
        "map of the tool families, and guidance belongs on the tool that needs it"
    )
    header, lines = _map_lines()
    assert header == INSTRUCTIONS_HEADER, f"the first line is the header, not {header!r}"
    off_shape = [line for line in lines if not _MAP_LINE.match(line)]
    assert lines and not off_shape, (
        "every line after the header names one tool or family: '- <name>: <what it does>'\n  "
        + "\n  ".join(off_shape)
    )
    heads = _map_heads()
    assert len(heads) == len(set(heads)), f"a family has two lines: {sorted(heads)}"


def test_the_map_carries_no_rule_known_to_be_on_no_tool():
    """NOT_RELOCATED lists guidance no tool description carries. In the map it would reach
    Claude Code only, which is the map-only content the contract forbids."""
    text = _norm(_instructions())
    found = [p for p in NOT_RELOCATED if _norm(p) in text]
    assert not found, (
        "the instructions map carries guidance no tool has; it belongs on the tool that "
        "needs it (see NOT_RELOCATED):\n  " + "\n  ".join(found)
    )


def test_every_name_the_map_cites_is_registered():
    """A renamed or removed tool must not leave the map pointing at it, and a family glob
    must match at least one tool."""
    registered = {t.name for t in _tools()}
    cited = set(_MAP_CITATION.findall(_instructions()))
    dangling = sorted(c for c in cited if "*" not in c and c not in registered)
    empty = sorted(g for g in cited if "*" in g
                   and not any(fnmatch.fnmatchcase(r, g) for r in registered))
    assert not dangling and not empty, (
        f"instructions cites unregistered tools {dangling} and families with no tool {empty}"
    )


def test_the_map_covers_every_registered_tool():
    """Every tool is named somewhere in the map or falls under a family glob that heads a
    line of its own, so a new tool or family cannot be missing from the one text a
    deferred-tool client shows before it loads any tool. A glob met only inside another
    line's text covers nothing."""
    cited = set(_MAP_CITATION.findall(_instructions()))
    names = {c for c in cited if "*" not in c}
    families = [h for h in _map_heads() if "*" in h]
    uncovered = sorted(t.name for t in _tools() if t.name not in names
                       and not any(fnmatch.fnmatchcase(t.name, g) for g in families))
    assert not uncovered, (
        "add these to INSTRUCTIONS in server.py (a new family needs its own line):\n  "
        + "\n  ".join(uncovered)
    )

# Tool-name prefixes, so a cross-reference can be told apart from an attribute path
# (rcsb_entry_info.*, rcsb_polymer_entity.*, ...) which shares the rcsb_ prefix.
_TOOL_NAME = re.compile(
    r"\brcsb_(?:search|query|get|find|describe|seqcoord|list|render)_[a-z_]+\b"
)


def test_no_description_cites_a_tool_that_is_not_registered():
    """A tool description naming a tool that does not exist sends the agent nowhere.

    This is the failure the rcsb_search_* -> rcsb_query_* rename can cause silently: the
    text still reads sensibly, the named tool just isn't there. Cross-references between
    tool descriptions are the one channel that always resolves, which is exactly why they
    have to actually resolve.
    """
    descs = _descriptions()
    registered = set(descs)
    dangling = []
    for name, desc in descs.items():
        for m in _TOOL_NAME.finditer(desc):
            cited = m.group(0)
            # `rcsb_get_*` and friends are family globs, not names: skip a match whose
            # next character is the wildcard.
            if desc[m.end():m.end() + 1] == "*":
                continue
            if cited not in registered:
                dangling.append(f"{name} cites {cited!r}")
    assert not dangling, (
        "tool descriptions name tools that are not registered:\n  " + "\n  ".join(sorted(dangling))
    )


def test_no_description_contains_a_near_miss_of_a_tool_name():
    """`_TOOL_NAME` only sees tokens that already look like tool names, so the likeliest
    way a reference goes wrong is invisible to it.

    `csb_query_seqmotif` — one dropped letter — shipped in rcsb_search_request's
    return_type table and every test passed, because the pattern requires the `rcsb_`
    prefix that the typo destroyed. `rcsb_qeury_attribute` would escape the same way: the
    family segment is part of the pattern too.

    So this looks for tokens that are CLOSE to a registered name without being one. The
    0.9 cutoff is tight enough that attribute paths (`rcsb_polymer_entity_annotation`) and
    field names do not trip it, which the companion test below pins.
    """
    import difflib
    import re

    descs = _descriptions()
    registered = set(descs)
    suspicious = []
    for name, desc in descs.items():
        for token in set(re.findall(r"\b[a-z][a-z0-9_]{8,}\b", desc)):
            if token in registered or "_" not in token:
                continue
            close = difflib.get_close_matches(token, registered, n=1, cutoff=0.9)
            if close:
                suspicious.append(f"{name}: {token!r} — did you mean {close[0]!r}?")
    assert not suspicious, "near-miss tool references:\n  " + "\n  ".join(suspicious)


def test_the_near_miss_check_does_not_fire_on_attribute_paths():
    """Attribute paths share the `rcsb_` prefix and plenty of substrings with tool names.
    If the cutoff were loose they would all be flagged and the guard would be turned off.
    """
    import difflib

    registered = set(_descriptions())
    for path in ("rcsb_polymer_entity_annotation", "rcsb_entity_source_organism",
                 "rcsb_entry_info", "rcsb_nonpolymer_entity_annotation",
                 "rcsb_polymer_instance_annotation", "rcsb_accession_info"):
        assert not difflib.get_close_matches(path, registered, n=1, cutoff=0.9), (
            f"{path!r} would be flagged as a typo'd tool name"
        )


def test_every_id_route_points_at_rcsb_get_entries_and_is_followable():
    """All four warnings send the agent to ONE tool, and each route must resolve there.

    Consistency is the point: an agent that has entry ids should not need a different
    lookup per id shape. rcsb_get_entries serves all four — but not uniformly, which is the
    trap this guards. Its container identifiers carry entity and assembly ids as plain
    fields, and NO chain letters at all; asym_ids hangs off the polymer entity, so the
    instance route needs a `fields` traversal into polymer_entities.

    An earlier draft named `rcsb_polymer_entity_container_identifiers.asym_ids` alongside
    `polymer_entity_ids` as though the two were symmetric. The field is real, but nothing on
    the entry exposes it, so the route dead-ended — worse than the guess it replaced, since
    the guess at least returns data.
    """
    d = _descriptions()
    for f in ("polymer_entity_ids", "non_polymer_entity_ids", "assembly_ids"):
        assert f in d["rcsb_get_entries"], f"rcsb_get_entries must name {f}"
    assert "asym_ids" not in d["rcsb_get_entries"], (
        "the entry container has no asym_ids; claiming it would send agents nowhere"
    )
    routes = {
        "rcsb_get_polymer_entities": "polymer_entity_ids",
        "rcsb_get_nonpolymer_entities": "non_polymer_entity_ids",
        "rcsb_get_assemblies": "assembly_ids",
        "rcsb_get_polymer_entity_instances": "asym_ids",
    }
    for tool, field in routes.items():
        assert "rcsb_get_entries" in d[tool], f"{tool} must route back to rcsb_get_entries"
        assert field in d[tool], f"{tool} must name the field that carries its ids"
    # The one that is not a plain entry field has to spell out the traversal.
    inst = d["rcsb_get_polymer_entity_instances"]
    assert "fields=" in inst and "polymer_entities{" in inst, (
        "asym_ids is reachable from the entry only through a fields traversal; naming it "
        "without that leaves the route unfollowable"
    )
