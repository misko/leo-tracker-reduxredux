"""Offline successor identity and frozen-window checks for the shared mint."""

import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "2026_10_08_ds17_post_ds16" / "mint.py"


def load():
    spec = importlib.util.spec_from_file_location("ds18_mint", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_successor_identity_and_boundaries():
    m = load()
    m.configure("DS18", "DS17", "/parent", "2026-10-08T14:36:56+00:00", "2026-10-08T23:08:51+00:00")
    row = dict(
        session_id="new",
        uncompressed_sha256="sha256:new",
        capture_start_utc_ns=m.LOW,
        finalized_utc_ns=m.HIGH,
    )
    assert m.merge([row], [], {"captures": []})[0]["dataset_label"] == "DS18-001"
    assert m.PARENT_DATASET == "DS17"
    assert Path("/parent") == m.PARENT
    assert m.eligible(m.LOW, m.HIGH)
    assert not m.eligible(m.LOW - 1, m.HIGH)
    assert not m.eligible(m.HIGH, m.HIGH)
    assert not m.eligible(m.LOW, m.HIGH + 1)


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-10-08T14:00:00", "2026-10-08T23:00:00+00:00"),
        ("2026-10-08T23:00:00+00:00", "2026-10-08T14:00:00+00:00"),
        ("2026-10-08T14:00:00+00:00", "2026-10-08T14:00:00+00:00"),
    ],
)
def test_rejects_ambiguous_or_empty_window(start, end):
    with pytest.raises(ValueError, match="timezone-aware"):
        load().configure("DS18", "DS17", "/parent", start, end)
