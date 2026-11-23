"""The full-catalogue association inputs survive reuse bit-for-bit."""

from collections import Counter
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.scan import ScanLikelihood
from leo.analysis.research.retained_track_likelihood import profile, whitening
from tools.pipeline_eval.variants.algo08_sparse_rank_projection import ProjectedRows

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from cold_track_row_reuse import CentreRows, associate_with_rows
from cold_track_row_trial import same_proof
from cold_track_row_entry import rank_with_centre_rows


@pytest.fixture
def table():
    rng = np.random.default_rng(275)
    frequency = rng.normal(400_000, 4000, size=(23, 19))
    elevation = rng.uniform(-15, 23, size=frequency.shape)
    elevation[9] = 0.0
    times = np.linspace(0, 30, 8)
    indices = np.array([0, 2, 5, 6, 8, 12, 14, 16])
    track = dict(key="track", times=times, rf_hz=11.95e9)
    base = frequency, elevation
    q = track["rf_hz"] / 11.5e9
    cur = q * frequency[:, indices], elevation[:, indices].min(axis=1) >= 0
    tables = SimpleNamespace(current=base, nominal=base, tracks={"track": (times, q, cur)})
    return track, indices, tables


@pytest.mark.parametrize("active", [[], [0], [2, 9, 22]])
def test_exact_reuse_including_signed_profile(active, table):
    track, indices, tables = table
    q = track["rf_hz"] / 11.5e9
    counts = Counter()
    active = np.asarray(active, dtype=np.intp)
    freq, elev = tables.current
    moved = freq[active] * .9, elev[active] - 10
    stock_counts = Counter()
    f = ProjectedRows(freq, active, moved[0], stock_counts)
    e = ProjectedRows(elev, active, moved[1], stock_counts)
    original = q * f[:, indices], e[:, indices].min(axis=1) >= 0
    candidate = CentreRows(tables, ProjectedRows, counts)(track, indices, f, e)
    for expected, actual in zip(original, candidate, strict=True):
        assert expected.tobytes() == actual.tobytes()
        assert expected.strides == actual.strides
    assert candidate[1][9] == (9 not in active)
    white, volume = whitening(track["times"])
    y = original[0][9] - np.linspace(224_000, 230_000, len(indices))
    left, right = (profile(y, prediction, white, volume) for prediction in (original[0], candidate[0]))
    assert all(left[key].tobytes() == right[key].tobytes() for key in left)
    assert counts["reused_requests"] == 1 and counts["released_requests"] == 0
    assert counts["shifted_cells"] == len(active) * len(indices)


@pytest.mark.parametrize("why", ["corner", "times", "phase_rows", "layout", "materialized", "plain_arrays"])
def test_original_gathers_when_binding_is_unavailable(why, table):
    track, indices, tables = table
    freq, elev = tables.current
    q = track["rf_hz"] / 11.5e9
    times, _, (values, visible) = tables.tracks[track["key"]]
    phase = np.array([1, 5])
    counts = Counter()
    f, e = (ProjectedRows(base, phase, base[phase].copy(), Counter()) for base in (freq, elev))
    if why == "corner":
        tables.current = freq.copy(), elev.copy()
    elif why == "times":
        track["times"] = times.copy()
    elif why == "phase_rows":
        e.changed_rows = phase.copy()
    elif why == "layout":
        tables.tracks[track["key"]] = times, q, (np.ascontiguousarray(values), visible)
    elif why == "materialized":
        f.dense()[0, :] += 100
    elif why == "plain_arrays":
        f, e = freq, elev
    predicted, visibility = CentreRows(tables, ProjectedRows, counts)(track, indices, f, e)
    assert np.array_equal(predicted, q * f[:, indices])
    assert np.array_equal(visibility, e[:, indices].min(axis=1) >= 0)
    assert counts["reused_requests"] == 0 and counts["released_requests"] == 1


def test_released_association_port_compiles_its_class_method():
    work = associate_with_rows(ScanLikelihood.association, object())
    assert work.__name__ == "association"


def test_proof_matches_sealed_json_only_for_the_same_counts():
    reference = {"receiver_points": {"1": 5, "2": 10}}
    assert same_proof({"receiver_points": {1: 5, 2: 10}}, reference)
    assert not same_proof({"receiver_points": {1: 10, 2: 5}}, reference)


def test_installed_fallback_can_rank_without_the_shared_centre_cache():
    class Other:
        def projection(self):
            raise AssertionError("The selector must leave the projection alone")

    discovery = SimpleNamespace(phase_linear_frequency=Other().projection)
    scan, counts = object(), Counter()
    rank = rank_with_centre_rows(lambda current: [current], discovery, counts)
    assert rank(scan) == [scan]
    assert counts == {"ordinary_ranks": 1}
