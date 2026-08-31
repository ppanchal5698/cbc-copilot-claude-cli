"""Prompt templates for deep document indexing.

These lived in `cbc_core.llm`, which meant the shared floor held a path into this
package: `PROMPTS_DIR = <root>/document_index/prompts`. That is the dependency
arrow pointing the wrong way, and the layering test could not see it twice over -
its guard list named only the two application packages, and this was a filesystem
reference rather than an import.

`cbc_core.llm` is now a transport client that knows nothing about who is calling
it. The prompts live beside the code that sends them.
"""
from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"prompt template missing: {path}")
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, **values: str) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _demo() -> None:
    """Both shipped templates load, and substitution actually substitutes."""
    for name in ("schema_discovery.txt", "section_extraction.txt"):
        assert load_prompt(name).strip(), f"{name} is empty"
    assert render_prompt("a {{x}} c", x="b") == "a b c"
    try:
        load_prompt("no_such_template.txt")
    except FileNotFoundError:
        pass
    else:  # pragma: no cover - a missing template must not pass silently
        raise AssertionError("a missing template should raise")
    print("cbc.documents.templates OK")


if __name__ == "__main__":
    _demo()
