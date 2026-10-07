"""Archived-bank preservation and source-window checks without hardware."""
import hashlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import source_adapter as adapter


def candidate(rank, margin):
    return {"candidate_rank": rank, "integer_epoch_sample": 12, "acquired_cfo_hz": 57000.,
        "integer_exact_score": .1, "integer_control_score": .1 - margin,
        "integer_margin": margin, "integer_tracking_cfo_hz": 57020.,
        "fractional_epoch_offset_samples": .3}


def test_bank_preserves_negatives_and_unavailable_candidates_without_filtering():
    probe = {"candidate_count": 3, "candidates": [candidate(2, -.1), candidate(0, .04)],
             "unavailable_candidates": [{"candidate_rank": 1, "reason": "fractional_incomplete"}]}
    bank, coverage = adapter.normalize_bank(probe)
    assert [b["candidate_id"] for b in bank] == [2, 0]
    assert bank[0]["persisted_integer_margin"] == -.1
    assert coverage["saved_candidate_count"] == 3 and coverage["available_candidate_count"] == 2
    probe["candidate_count"] = 4
    with pytest.raises(ValueError, match="accounting"):
        adapter.normalize_bank(probe)


def test_no_later_window_selection_and_geometry_exact():
    raw = np.zeros((120, 2, 2), dtype="<i2")
    raw[:, 0, 0] = np.arange(120)
    first = adapter.ci16_window(raw, 1000, 0, 0)
    later = adapter.ci16_window(raw, 1000, 0, 40)
    np.testing.assert_array_equal(first, np.arange(20))
    np.testing.assert_array_equal(later, np.arange(40, 60))
    with pytest.raises(ValueError, match="geometry"):
        adapter.ci16_window(raw, 1000, 0, 110)


def test_source_digest_mismatch_fails_before_raw_read():
    from types import SimpleNamespace
    source = adapter.ArchivedSource(
        SimpleNamespace(inspect=lambda sid: SimpleNamespace(manifest_sha256="sha256:actual")),
        None, None)
    with (
        pytest.raises(ValueError, match="recording differs"),
        source.scan({"session_id": "test", "recording_manifest_sha256": "sha256:expected"}),
    ):
        raise AssertionError("must not admit mismatched source")


def test_actual_energy_vectors_and_immutable_matched_correlations():
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "src"))
    from leo.analysis.starlink import templates

    # Exercise the exact numerical implementation used in the archived replay.
    # Current main need not contain the experiment's workspace implementation.
    snapshot = Path(__file__).parent / "source_snapshots" / "pilot_methods.py"
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == (
        "7486c61084e02b6fb61b6e1c913aaa48df487a93c235ccf4771a9ca7cc32e451"
    )
    spec = importlib.util.spec_from_file_location("recent16_pilot_snapshot", snapshot)
    pm = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = pm
    spec.loader.exec_module(pm)
    rate, edge = 2_500_000, templates.StarlinkEdge.LOWER
    energies = adapter.template_energies(pm, templates, rate, edge)
    for vector, roll in zip(energies, (0, 17), strict=True):
        template = np.asarray(templates.qin_edge_pilot_frame(rate, edge, symbol_roll=roll), complex)
        reference = [np.sum(np.abs(template[round(s * 11):round((s + 1) * 11)]) ** 2)
                     for s in range(2, 66)]
        np.testing.assert_allclose(vector, reference, rtol=1e-12, atol=1e-12)
    rng = np.random.default_rng(55)
    samples = rng.normal(size=50_000) + 1j * rng.normal(size=50_000)
    exact, control = adapter.correlations64(pm, templates, samples, rate, edge, 15, 57_000.)
    assert exact.shape == control.shape and exact.shape[1] == 64 and len(exact) >= 2
    assert not exact.flags.writeable and not control.flags.writeable
