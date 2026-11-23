from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import conservative_recovery as recovery
from leo.analysis.research.retained_track_likelihood import PERIOD, profile
from tools.pipeline_eval.variants import algo08_salvage_bound, v5_tiled_salvage as tiled


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import certified_salvage

    return certified_salvage


def test_interval_detects_interior_disagreement_and_respects_phase_visibility(trial):
    limit = np.ones(5)
    raw = np.array([[0., 0., 3., 0., 0.], [0., 0., 0., 0., 0.]])
    elevation = np.ones_like(raw)
    elevation[1, 1] = -1
    witness = algo08_salvage_bound.EndpointWitness(raw, elevation, limit)
    assert not witness.rejects(0, 5)
    assert trial.support_feasibility(witness, [(0, 5), (0, 2), (2, 5)]).tolist() == [False, True, True]
    raw[0, 2] = 2.
    assert trial.support_feasibility(witness, [(0, 5)]).tolist() == [True]


def test_fine_proof_keeps_stable_ties_and_gates_the_original_winner(trial):
    t = np.arange(0., 60., 2.)
    nominal = 4000 * np.sin(t / 9)
    y = nominal + 2 * PERIOD
    noise = np.ones_like(y) * 100

    def frequency(bank, times, labels, phases, *_):
        candidate = bank["position_km"][0, 0, 0]
        cfo = np.tile(nominal, len(phases))
        if candidate == 6:
            cfo[::2] += 1500
        return cfo, np.ones_like(cfo)

    sky = dict(time_s=t, position_km=np.arange(7.)[:, None, None], velocity_km_s=np.zeros((7, 1, 1)))
    scan = SimpleNamespace(sky=sky, norads=np.arange(100, 107))
    track = dict(times=t, values=y)
    kernel = SimpleNamespace(selected_supports=recovery.selected_supports, raw_curvature=recovery.raw_curvature,
                             profile=profile, paired_phase_frequency=frequency,
                             batch_noise_screen=lambda r, _: {"noise_screen_pass": np.ones(len(r), bool)})
    args = kernel, scan, track, y, noise, 1., set(range(7)), (0., 0.)
    expected = tiled.fine_alternatives(*args)
    counts = Counter()
    received = trial.fine_alternatives(tiled.fine_alternatives, counts, *args)
    assert received == expected
    assert [row["candidate_index"] for row in received[0]] == list(range(5))
    assert counts["profile_calls"] == 6
    assert counts["interval_rejected"] > 0 and counts["dominated"] > 0
    assert counts["support_trials"] == counts["profile_calls"] + counts["interval_rejected"] + counts["dominated"]


def test_unsupported_fine_input_calls_stock(trial):
    t = np.arange(13) * 2.
    track = dict(times=t, values=t)
    counts = Counter()
    kernel = SimpleNamespace(selected_supports=recovery.selected_supports, raw_curvature=lambda row: True,
                             profile=lambda *args: None)
    result = trial.fine_alternatives(lambda *args: ([], 3), counts, kernel, None, track, t, t, 1., {0}, (0., 0.))
    assert result == ([], 3)
    assert counts["fine_replays"] == 1


@pytest.mark.parametrize("byte_limit", (96 * 2**20, 1))
def test_shared_projection_gathers_identical_columns_with_original_order(trial, byte_limit):
    rng = np.random.default_rng(6)
    xyz = np.broadcast_to([6900., 20., 100.], (3, 11, 3)) + rng.normal(size=(3, 11, 3))
    bank = dict(time_s=np.arange(0., 110., 10.), position_km=xyz, velocity_km_s=rng.normal(size=xyz.shape))
    times = [np.array([22., 37., 37., 72.]), np.array([37., 50., 80.])]
    p = SimpleNamespace(members=[0, 1], slices=[slice(0, 4), slice(4, 7)])
    scan = SimpleNamespace(sky=bank, norads=[1, 2, 3], tracks=[dict(times=t) for t in times],
                           search_region=SimpleNamespace(latlon=lambda point: (34., -25.)))
    kernel = SimpleNamespace(prepare_phase_geometry=recovery.prepare_phase_geometry,
                             phase_linear_frequency=recovery.phase_linear_frequency,
                             repaired_fit=lambda: (p, {"parameters": np.zeros(2)}, [], {}))
    counts = Counter()
    proxy = trial.CommonProjection(kernel, scan, np.zeros(7, bool), counts, byte_limit)
    proxy.repaired_fit()
    for t in times:
        expected = kernel.phase_linear_frequency(kernel.prepare_phase_geometry(bank, t), 34., -25.)
        actual = proxy.phase_linear_frequency(proxy.prepare_phase_geometry(bank, t), 34., -25.)
        for wanted, received in zip(expected, actual, strict=True):
            assert received.flags.c_contiguous
            np.testing.assert_array_equal(received, wanted)
    if byte_limit == 1:
        assert counts["coarse_stock_preparations"] == 2
    else:
        assert counts["coarse_shared_preparations"] == 1
        assert counts["coarse_shared_gathers"] == 2
        assert counts["coarse_skipped_duplicate_columns"] == 2
