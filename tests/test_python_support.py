"""Guards that the package actually runs on the interpreters it claims to support.

The failure this exists to prevent: `typing.TypedDict` used as a pydantic field
type imports fine on 3.12 but raises PydanticUserError on 3.10/3.11. The developer
venv is 3.12, the Docker base image is 3.11, and nothing imported the package on
3.11 before it shipped -- so `docker build` stayed green and the pod
CrashLoopBackOff'd on `uvicorn rcsb_mcp.server:create_app`, before binding a port,
where the only symptom is a probe that never passes.

These checks are static so they run on every interpreter, but they are a backstop,
not the real fix: CI must exercise the Docker image's Python version.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "rcsb_mcp"

PY_SOURCES = sorted(SRC.rglob("*.py"))


def _python_floor() -> tuple[int, int]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'requires-python\s*=\s*"[^0-9]*(\d+)\.(\d+)', text)
    assert m, "pyproject.toml declares no requires-python"
    return int(m.group(1)), int(m.group(2))


def _dockerfile_python() -> tuple[int, int]:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    m = re.search(r"FROM\s+python:(\d+)\.(\d+)", text)
    assert m, "Dockerfile does not pin a python:X.Y base image"
    return int(m.group(1)), int(m.group(2))


def test_no_module_takes_typeddict_from_typing():
    """pydantic rejects typing.TypedDict as a field type below 3.12.

    typing_extensions.TypedDict behaves identically and is accepted everywhere,
    so there is never a reason to import it from `typing` in this package.
    """
    offenders = []
    for path in PY_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "typing":
                if any(a.name == "TypedDict" for a in node.names):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, (
        "import TypedDict from typing_extensions, not typing -- pydantic raises "
        f"PydanticUserError on Python < 3.12: {offenders}"
    )


def test_the_image_runs_a_supported_interpreter():
    """The Docker base image must not be below the declared floor."""
    assert _dockerfile_python() >= _python_floor(), (
        f"Dockerfile uses python:{'.'.join(map(str, _dockerfile_python()))} but "
        f"pyproject requires >={'.'.join(map(str, _python_floor()))}"
    )


def test_ci_exercises_the_image_interpreter():
    """CI must test the version the container actually runs.

    This is the check that would have caught the TypedDict break: the code was
    only ever imported on the developer's 3.12, never on the image's 3.11.
    """
    workflows = list((ROOT / ".github" / "workflows").glob("*.y*ml"))
    if not workflows:
        pytest.skip("no GitHub workflows in this checkout")

    image_py = ".".join(map(str, _dockerfile_python()))
    tested = set()
    for wf in workflows:
        tested.update(re.findall(r'"(\d+\.\d+)"', wf.read_text(encoding="utf-8")))

    assert image_py in tested, (
        f"Dockerfile runs python:{image_py} but the CI matrix tests {sorted(tested) or 'nothing'}. "
        "Add it, or the image's interpreter is never exercised before deploy."
    )
