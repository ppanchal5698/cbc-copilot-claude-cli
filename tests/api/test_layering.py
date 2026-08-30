"""The dependency direction, asserted rather than described.

`api` held the business rules and `worker` ran Claude Code, and each imported the
other: `api.routers.settings` reached for `worker.runner` to test a provider,
while `worker.runner` reached back for `api.services.secrets` to redact what it
captured. Python allowed it because both edges were function-local imports, which
is the shape a cycle takes when nobody wants to admit to one.

The CLI layer now sits below both, in `cbc_core`. These tests fail if that
inverts again - which is the only reliable way to keep a layering rule, since a
comment saying "do not import from api here" has never stopped anyone.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.shared import ROOT

SOURCE_DIRS = {"api": ROOT / "api", "worker": ROOT / "worker", "cbc_core": ROOT / "cbc_core"}


def _imported_roots(path: Path) -> set[str]:
    """Every top-level package this file imports, wherever the import is written.

    Walks the whole tree rather than the module header, because an import inside
    a function body is still an edge - and was how both halves of the cycle hid.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _files(package: str) -> list[Path]:
    return [
        path
        for path in SOURCE_DIRS[package].rglob("*.py")
        if "__pycache__" not in path.parts
    ]


def test_cbc_core_depends_on_neither_side() -> None:
    """It is the shared floor. The moment it imports upward, it is not."""
    offenders = {
        path.relative_to(ROOT).as_posix(): sorted(_imported_roots(path) & {"api", "worker"})
        for path in _files("cbc_core")
    }
    offenders = {name: roots for name, roots in offenders.items() if roots}
    assert not offenders, f"cbc_core imports upward: {offenders}"


def test_the_api_does_not_import_the_worker() -> None:
    """This edge is the one that closed the cycle."""
    offenders = {
        path.relative_to(ROOT).as_posix(): sorted(_imported_roots(path) & {"worker"})
        for path in _files("api")
    }
    offenders = {name: roots for name, roots in offenders.items() if roots}
    assert not offenders, f"api imports worker: {offenders}"


def test_the_worker_may_still_use_the_api() -> None:
    """Not a cycle - a direction. The worker is a consumer of the domain.

    Asserted so the intent is on the record: this edge is allowed, the other is
    not, and the test above is not simply "nothing imports anything".
    """
    importers = [
        path.relative_to(ROOT).as_posix()
        for path in _files("worker")
        if "api" in _imported_roots(path)
    ]
    assert importers, "expected the worker to use the API's services"


@pytest.mark.parametrize("package", ["api", "worker"])
def test_nothing_loads_an_mcp_server_in_process(package: str) -> None:
    """`load_server` execs a server module and juggles `sys.modules['tools']`.

    It exists for the test suite, which imports several servers into one process.
    Application code shares the domain functions through `cbc_core` instead, so
    the money math has one implementation without the API holding a transport
    artifact.
    """
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _files(package)
        if "load_server" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"{package} loads an MCP server in-process: {offenders}"
