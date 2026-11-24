import importlib
from pathlib import Path

import pytest


def test_full_retry_charges_the_already_paid_scout(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    screen = importlib.import_module("aperture_route_screen")
    price = screen.cost(2.0, 1.5)
    assert price["gross_cpu_s"] == 0.5
    assert price["whole_primary_retry_break_even"] == 0.25
    assert screen.cost(1.0, 1.25)["whole_primary_retry_break_even"] == 0.0


def test_unknown_receipt_bytes_fail_binding(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    screen = importlib.import_module("aperture_route_screen")
    changed = tmp_path / "native.json"
    changed.write_bytes(b"{}")
    with pytest.raises(ValueError, match="sealed source changed"):
        screen.checked_bytes(changed, "a"*64)
