from collections import Counter
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import conservative_recovery
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD, profile
from leo.sky import frames

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from rescue_phase_prepare import ShadowMismatch
from salvage_projection import FineDopplerElevation, binding, compare


def make_bank():
    knots = np.r_[-40., -17., np.arange(0., 101.), 131.]
    position = np.stack([6900. + 15. * np.cos(knots / 15), 20. * knots, 200. + knots], axis=1)
    speeds = 2. * np.sin(knots / 10)
    velocity = np.stack([speeds, np.full(len(knots), 7.), np.full(len(knots), 0.5)], axis=1)
    return dict(time_s=knots, position_km=np.stack([position, position + [10., 300., 50.]]),
                velocity_km_s=np.stack([velocity, velocity + [0., 4., -1.]]))


def original(bank, times, phases, index, origin):
    full = dict(bank, **{name: np.repeat(bank[name][[index]], len(phases), axis=0)
                        for name in ("position_km", "velocity_km_s")})
    return paired_phase_frequency(full, np.tile(times, len(phases)), np.repeat(np.arange(len(phases)), len(times)),
                                  phases, *origin)


def test_consumed_binary64_planes_at_shifted_sites_and_duplicate_epochs():
    bank = make_bank()
    epochs = np.array([-25., -16.9, 0., 1.2, 1.2, 60.25, 116.])
    phases = np.linspace(-15, 15, 121)
    projector = FineDopplerElevation(bank, epochs, phases)
    for point in ((0., 0.), (0., -0.), (37.905, -122.545), (-89.9, 180.), (np.float32(1.25), 4.)):
        for candidate in range(len(bank["position_km"])):
            for first, second in zip(original(bank, epochs, phases, candidate, point),
                                     projector.project(candidate, point), strict=True):
                np.testing.assert_array_equal(first.view(np.uint64), second.ravel().view(np.uint64))


def test_exact_fine_entry_retains_certificates_and_signed_alternatives():
    import certified_salvage
    from tools.pipeline_eval.variants import v5_tiled_salvage

    sky = make_bank()
    times = np.arange(0., 80., 2.)
    point = (0., 0.)
    base, _ = original(sky, times, np.array([0.]), 0, point)
    data = base + PERIOD * 2
    errors = np.full(len(data), 60.)
    kernel = SimpleNamespace(selected_supports=conservative_recovery.selected_supports, raw_curvature=lambda _: True,
                             profile=profile, paired_phase_frequency=paired_phase_frequency,
                             batch_noise_screen=lambda residual, _: {"noise_screen_pass": np.ones(len(residual), bool)})
    scan = SimpleNamespace(sky=sky, norads=[1, 2])
    track = dict(times=times, values=data, key="sample")
    args = v5_tiled_salvage.fine_alternatives, Counter(), kernel, scan, track, data, errors, 1., {0, 1}, point
    ledger = []
    ordinary = certified_salvage.fine_alternatives
    expected = ordinary(*args)
    assert expected[0] and expected[0][0]["alias"] == -2
    with binding(audit=ledger):
        assert certified_salvage.fine_alternatives(*args) == expected
    with binding() as active:
        assert active and certified_salvage.fine_alternatives(*args) == expected
    assert certified_salvage.fine_alternatives is ordinary
    assert ledger[0]["counters"]["projected"]["prepared_satellites"] == 2


def test_unrecognized_runtime_does_not_bind(monkeypatch):
    import certified_salvage

    ordinary = certified_salvage.fine_alternatives
    monkeypatch.setattr(frames, "look_angles", lambda *_: None)
    with binding() as active:
        assert not active and certified_salvage.fine_alternatives is ordinary


def test_shadow_fails_closed_on_changed_counts_and_cycles_order():
    def evaluator(count, outcome=()):
        def run(_stock, counters, *_args):
            counters["profile_calls"] = count
            return outcome, 3
        return run

    ledger = []
    fn = compare(evaluator(4), evaluator(4), evaluator(4), ledger)
    actual = Counter()
    for _ in range(3):
        assert fn(None, actual, None, None, {"key": "x"}) == ((), 3)
    assert [row["order"][0] for row in ledger] == ["ordinary", "prepared", "projected"]
    assert actual == {"profile_calls": 12}
    with pytest.raises(ShadowMismatch):
        compare(evaluator(3), evaluator(4), evaluator(4), [])(None, Counter(), None, None, {"key": "x"})
