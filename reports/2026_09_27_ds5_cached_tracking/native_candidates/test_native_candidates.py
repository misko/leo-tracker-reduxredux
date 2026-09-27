from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from native_candidates import NativeCandidates, build_library  # noqa: E402


@pytest.fixture(scope="module", params=(1, 2))
def candidate_library(request) -> tuple[int, Path]:
    budget = request.param
    return budget, build_library(budget)


def _science(row) -> tuple:
    return (
        row.receiver, row.probe_index, row.probe_start_sample,
        row.local_epoch_sample, row.dwell_epoch_sample,
        row.acquired_cfo_hz, row.tracking_cfo_hz, row.margin,
        row.fractional_complete, row.supported, row.fitted,
        row.candidate_index, row.exact_score, row.control_score,
        row.support_frames, row.valid_bounds, row.status,
    )


def test_build_receipt_pins_budget_binary_and_complete_sources(candidate_library):
    budget, library = candidate_library
    receipt = json.loads(library.with_name(library.name + ".build.json").read_text())
    assert receipt["candidate_budget"] == budget
    assert receipt["profile_override"] == {"LEO_PRESENCE_CANDIDATES": budget}
    assert f"-DLEO_PRESENCE_CANDIDATES={budget}" in receipt["command"]
    assert hashlib.sha256(library.read_bytes()).hexdigest() == receipt["binary_sha256"]
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
               for path, digest in receipt["sources_sha256"].items())


@pytest.mark.parametrize("bad", (0, 3, 4, True, 1.0))
def test_only_existing_safe_capacities_are_accepted(bad):
    with pytest.raises(ValueError, match="exactly 1 or 2"):
        build_library(bad)


@pytest.mark.parametrize("rate", (2_500_000, 5_000_000))
def test_zero_input_is_immutable_and_has_no_invented_candidates(rate):
    raw = np.zeros((rate * 120 // 1000, 2, 2), dtype=np.int16)
    before = raw.copy()
    with NativeCandidates(rate, "lower", 2) as engine:
        screen = engine.screen(raw, receiver=1)
        observations = engine.blind(raw, receiver=1, screen=screen)
    assert observations == ()
    assert all(window.score == 0 for window in screen.windows)
    assert np.array_equal(raw, before)


def test_k1_is_scientific_prefix_of_k2_on_constructed_input():
    rate = 2_500_000
    raw = np.random.default_rng(92711).integers(
        -32768, 32768, (rate * 120 // 1000, 2, 2), dtype=np.int16
    )
    before = raw.copy()
    inventories = {}
    screens = {}
    for budget in (1, 2):
        with NativeCandidates(rate, "upper", budget) as engine:
            screens[budget] = engine.screen(raw, receiver=0)
            inventories[budget] = engine.blind(raw, receiver=0, screen=screens[budget])
    assert tuple((w.projected_epoch_sample, w.score) for w in screens[1].windows) == tuple(
        (w.projected_epoch_sample, w.score) for w in screens[2].windows
    )
    k1_by_probe = {row.probe_index: row for row in inventories[1]}
    k2_first = {row.probe_index: row for row in inventories[2] if row.candidate_index == 0}
    assert k1_by_probe.keys() == k2_first.keys()
    assert all(_science(k1_by_probe[probe]) == _science(k2_first[probe])
               for probe in k1_by_probe)
    assert all(row.candidate_index < 2 for row in inventories[2])
    assert any(row.candidate_index == 1 for row in inventories[2])
    assert np.array_equal(raw, before)
