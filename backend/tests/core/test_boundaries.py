"""Isolation rule, checked on every test run:
a part may import bidwit.core, but never another part, the workflow or the API."""
import ast
from pathlib import Path

PARTS = Path(__file__).resolve().parents[2] / "bidwit" / "parts"
FORBIDDEN = ("bidwit.workflow", "bidwit.api")


def imports(py: Path):
    tree = ast.parse(py.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:                       # relative import: resolve against the file's package
                pkg = py.relative_to(PARTS.parent.parent).with_suffix("").parts[: -node.level]
                yield ".".join(pkg + ((node.module,) if node.module else ()))
            elif node.module:
                yield node.module


def test_parts_do_not_import_each_other():
    bad = []
    for part in [p for p in PARTS.iterdir() if p.is_dir() and not p.name.startswith("__")]:
        for py in part.rglob("*.py"):
            for mod in imports(py):
                other = mod.startswith("bidwit.parts.") and mod.split(".")[2] != part.name
                if other or mod.startswith(FORBIDDEN):
                    bad.append(f"{py.relative_to(PARTS)} imports {mod}")
    assert not bad, bad


def test_api_talks_only_to_the_workflow_and_core():
    api = PARTS.parent / "api"
    bad = [f"{py.name} imports {m}" for py in api.rglob("*.py") for m in imports(py) if m.startswith("bidwit.parts")]
    wf = PARTS.parent / "workflow"
    bad += [f"{py.name} imports {m}" for py in wf.rglob("*.py") for m in imports(py) if m.startswith("bidwit.api")]
    assert not bad, bad
