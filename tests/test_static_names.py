"""Static tripwire for the failure mode of moving code between modules.

A code move fails in two ways a green suite can hide, because neither needs a test
to *execute* the affected path:

* an **undefined name** — a moved function body references a global (e.g. ``asyncio``)
  that existed in the old module but was never imported into the new one; it only
  NameErrors at runtime, on whatever path the tests happen not to cover;
* an **unused import** — an import goes dead in the source module when code moves out.

pyflakes catches both statically, package-wide, in well under a second. This asserts
the package stays clean, so the next extraction (search, data, seqcoord) can't slip an
undefined/unused name past a passing suite — which is exactly how the resolver move's
missing ``import asyncio`` got through until the adversarial review found it.

Complements, does not replace, the behavioral guards (inventory, descriptions, prompt):
this one only checks that names resolve and imports are used, not that behavior held.
"""

import io
import pathlib

from pyflakes.api import checkRecursive
from pyflakes.reporter import Reporter

_ROOT = pathlib.Path(__file__).resolve().parent.parent
# Both src AND tests: a move that relocates a symbol also churns the test that patched or
# called it (server.X -> the-new-home.X), and can strand a now-dead `import server` in a
# test file — which src-only checking misses. Guard both.
_TARGETS = [str(_ROOT / "src" / "rcsb_mcp"), str(_ROOT / "tests")]


def test_package_has_no_undefined_names_or_unused_imports():
    out, err = io.StringIO(), io.StringIO()
    findings = checkRecursive(_TARGETS, Reporter(out, err))
    assert findings == 0, (
        "pyflakes found undefined names / unused imports (a code move likely dropped an "
        "import or left a dead one):\n" + out.getvalue() + err.getvalue()
    )
