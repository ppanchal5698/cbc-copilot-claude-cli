"""Reference-library loaders re-read only when the file on disk changes."""
from __future__ import annotations

import os
from pathlib import Path

from cbc.core import calc
from cbc.services import reference_library as reflib


def _bump_mtime(path: Path) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))


def test_load_frame_depths_reads_once_until_mtime_changes(monkeypatch) -> None:
    reflib._json_at.cache_clear()
    calls = {"n": 0}
    original = Path.read_text

    def counting(self, *args, **kwargs):
        if self.resolve() == reflib.FRAME_DEPTHS_FILE.resolve():
            calls["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)

    first = reflib.load_frame_depths()
    second = reflib.load_frame_depths()
    assert first == second
    assert calls["n"] == 1

    _bump_mtime(reflib.FRAME_DEPTHS_FILE)
    reflib.load_frame_depths()
    assert calls["n"] == 2


def test_lite_kit_lookup_reads_once_until_mtime_changes(monkeypatch) -> None:
    if not calc.LITE_KIT_FILE.exists():
        import pytest

        pytest.skip("lite_kit_prices.json not present")
    calc._lite_kit_data_at.cache_clear()
    calls = {"n": 0}
    original = Path.read_text

    def counting(self, *args, **kwargs):
        if self.resolve() == calc.LITE_KIT_FILE.resolve():
            calls["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)

    calc.lookup_lite_kit_list_price(12, 12, pdf_page=30)
    calc.lookup_lite_kit_list_price(14, 14, pdf_page=30)
    assert calls["n"] == 1

    _bump_mtime(calc.LITE_KIT_FILE)
    calc.lookup_lite_kit_list_price(12, 12, pdf_page=30)
    assert calls["n"] == 2
