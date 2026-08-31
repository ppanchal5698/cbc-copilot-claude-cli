"""The dependency direction, asserted rather than described.

`api` held the business rules and `worker` ran Claude Code, and each imported the
other: `api.routers.settings` reached for `worker.runner` to test a provider,
while `worker.runner` reached back for `api.services.secrets` to redact what it
captured. Python allowed it because both edges were function-local imports, which
is the shape a cycle takes when nobody wants to admit to one.

The first fix put the CLI layer below both, in `cbc_core`. That left a subtler
version of the same problem: `api` still owned the configuration, the database
handle and every domain service, so `worker` had to import the web application to
reach them - an edge this file used to assert as *allowed*, because it was.

The domain now lives in `cbc`, under `src/`, and both applications sit above it in
`apps/`. The rule is one-way and there is no longer an exception to carve out:

    apps/api  ─┐
               ├─→  cbc  (config, db, schemas, services, core, catalog, documents)
    apps/worker┘

These tests fail if that inverts again - which is the only reliable way to keep a
layering rule, since a comment saying "do not import from apps here" has never
stopped anyone.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.shared import ROOT

SOURCE_DIRS = {
    "apps.api": ROOT / "apps" / "api",
    "apps.worker": ROOT / "apps" / "worker",
    "cbc": ROOT / "src" / "cbc",
    "cbc.core": ROOT / "src" / "cbc" / "core",
}


def _imported_roots(path: Path) -> set[str]:
    """Every dotted module prefix this file imports, wherever the import is written.

    Walks the whole tree rather than the module header, because an import inside
    a function body is still an edge - and was how both halves of the cycle hid.
    Returns full dotted paths (`apps.api.routers.jobs`), not just the first
    segment, so `apps.worker` importing `apps.worker.handlers` is distinguishable
    from it importing `apps.api`.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
    return modules


def _files(package: str) -> list[Path]:
    directory = SOURCE_DIRS[package]
    assert directory.is_dir(), f"{package} is not at {directory} - did the layout move?"
    return [path for path in directory.rglob("*.py") if "__pycache__" not in path.parts]


def _imports_into(package: str, prefix: str) -> dict[str, list[str]]:
    offenders = {}
    for path in _files(package):
        hits = sorted(
            module
            for module in _imported_roots(path)
            if module == prefix or module.startswith(prefix + ".")
        )
        if hits:
            offenders[path.relative_to(ROOT).as_posix()] = hits
    return offenders


@pytest.mark.parametrize("package", ["cbc", "cbc.core"])
def test_the_domain_never_imports_an_application(package: str) -> None:
    """It is the shared floor. The moment it imports upward, it is not."""
    offenders = _imports_into(package, "apps")
    assert not offenders, f"{package} imports upward: {offenders}"


def test_the_worker_does_not_import_the_api() -> None:
    """The edge this restructure existed to remove.

    The worker needed configuration, the database and the domain services. Those
    lived inside the web application, so it imported the web application. They are
    in `cbc` now, so it does not have to - and must not.
    """
    offenders = _imports_into("apps.worker", "apps.api")
    assert not offenders, f"the worker imports the api: {offenders}"


def test_the_api_does_not_import_the_worker() -> None:
    """This edge is the one that closed the original cycle."""
    offenders = _imports_into("apps.api", "apps.worker")
    assert not offenders, f"api imports worker: {offenders}"


@pytest.mark.parametrize("package", ["apps.api", "apps.worker"])
def test_each_application_actually_uses_the_domain(package: str) -> None:
    """Not a cycle - a direction, and one that is really taken.

    Asserted so the rule above is not satisfied trivially by an application that
    imports nothing at all.
    """
    users = [name for name, hits in _imports_into(package, "cbc").items() if hits]
    assert users, f"expected {package} to import the domain"


@pytest.mark.parametrize("package", ["apps.api", "apps.worker"])
def test_nothing_loads_an_mcp_server_in_process(package: str) -> None:
    """`load_server` execs a server module and juggles `sys.modules['tools']`.

    It exists for the test suite, which imports several servers into one process.
    Application code shares the domain functions through `cbc` instead, so the
    money math has one implementation without an application holding a transport
    artifact.
    """
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _files(package)
        if "load_server" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"{package} loads an MCP server in-process: {offenders}"
