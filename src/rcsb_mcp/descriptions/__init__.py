"""Argument descriptions for the MCP tools, one module per tool, mirroring the source modules.

Tool ``rcsb_<name>`` defined in ``rcsb_mcp/<module>.py`` keeps its argument descriptions in
``descriptions/<module>/<name>.py`` (e.g. rcsb_search_request -> descriptions/search/
search_request.py). Text shared by several tools of one module goes in that module's folder,
as ``shared.py``; it may be a template with blanks the tool module fills (data/shared.py's
``FIELDS_DOC``), so the filling -- logic -- stays out of this package.

No tool documents its arguments in an ``Args:`` section, and every argument carries a schema
description -- from a module here or, for an argument that is itself a documented model
(rcsb_render_report's ``params``), from that model. tests/test_tool_descriptions.py enforces
both, keeps every description under the cutoff below, and checks each rcsb_get_* ``fields``
text names the object its tool queries.

The tool attaches each description with ``Annotated[..., Field(description=...)]``, so it
travels in the input schema as ``inputSchema.properties.<arg>.description`` rather than in
the docstring. A model used only by that tool's arguments keeps its text there too (its
docstring via ``__doc__ = ...`` and its fields' descriptions): the model class owns
validation, this package owns wording -- no imports, no logic.

Why: Claude Code cuts every MCP tool description at 2,048 characters of whitespace-collapsed
text. Argument docs written as an ``Args:`` section pushed several descriptions past that,
so everything after the cut -- in rcsb_search_request, 9 of the 14 phrases
tests/test_tool_descriptions.py guards as load-bearing -- never reached the model there.
Schema descriptions are not cut, and their line breaks survive (a description's do not), so
tables stay tables.

Edit the wording here; the tool modules only wire it in.
"""
