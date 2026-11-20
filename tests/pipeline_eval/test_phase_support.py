from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import phase_support_replay as replay
from tools.pipeline_eval.variants import joint_orbits, phase_support, phase_support_history
from tools.pipeline_eval.variants import robust_em as lean


def test_three_sigma_envelope_has_baseline_floor_and_interpolation_padding():
    sd, bounds = phase_support.envelopes([1.0, 3.5, 1000])
    assert np.array_equal(sd, [2.5, 3.5, 7.5])
    assert np.array_equal(bounds, [7.5, 10.5, 22.5])
    t = phase_support.knots(300, 0.5, 22.5)
    assert t[0] == -22.5 and t[-1] > 322.5
    assert np.all(np.diff(t) == 0.5)


def test_adaptive_support_can_change_joint_assignment_with_same_candidates():
    arc = SimpleNamespace(track=SimpleNamespace(t=np.arange(10)), orbit=np.array([0, 1]))
    matches = [[joint_orbits.Match(0, (100, 10, 1), 0), joint_orbits.Match(1, (9, 0, 1), 0)]]
    fixed, _ = phase_support.associate([arc], matches, 6.25, [1 / 2.5**2] * 2, [7.5] * 2)
    adapted, _ = phase_support.associate(
        [arc], matches, 6.25, [1 / 7.5**2, 1 / 2.5**2], [22.5, 7.5]
    )
    assert fixed[0].orbit == 1 and adapted[0].orbit == 0


def test_bvls_updates_width_and_bounds_for_only_the_active_orbit(monkeypatch):
    rows = [SimpleNamespace(orbit=1)]
    a = np.diag([7, 2, 1 / lean.PHASE_SD_S])
    upper = np.array([1, 6, lean.PHASE_BOUND_S])

    def stock(_rows, _n, _half, _arm):
        return lean.lsq_linear(a, [1, 2, 0], bounds=(-upper, upper), method="bvls")

    def solve(matrix, right, *, bounds, method):
        assert np.array_equal(matrix, np.diag([7, 2, 1 / 4.0]))
        assert np.array_equal(bounds[0], [-1, -6, -12])
        assert np.array_equal(bounds[1], [1, 6, 12])
        assert right == [1, 2, 0] and method == "bvls"
        return "kept"

    assert (
        phase_support.fit_with_support(
            stock, solve, np.array([2.5, 4.0]), np.array([7.5, 12]), rows, 2, 12.5, "c0"
        )
        == "kept"
    )
    assert upper[-1] == 7.5


def test_encoded_epoch_and_future_history_rejection(tmp_path):
    ns = phase_support_history.NS
    epoch = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=299, hours=12)
    assert phase_support_history.epoch_ns(b"26300.50000000") == int(epoch.timestamp()) * ns
    metadata = dict(anchor_utc_ns=100 * ns, cutoff_utc_ns=99 * ns, catalog_timestamp_ns=98 * ns)
    number = SimpleNamespace(satnum=99, jdsatepoch=2440587.5, jdsatepochF=0)
    with pytest.raises(ValueError, match="future or out-of-window"):
        phase_support_history.widths([number], metadata, [dict(collection_ns=99 * ns)], {})
    audit = {}
    widths = phase_support_history.widths([number], metadata, [], audit)
    assert widths.tolist() == [2.5] and audit["fallback_orbits"] == 1


def test_replay_resolves_omitted_only_recording_without_changing_plan(monkeypatch):
    roof, omitted = object(), object()
    jobs = [(({"recording": "roof"}, {}), "causal"), (({"recording": "omitted"}, {}), "wide")]
    plan = {"scheduled": ["roof", "omitted"]}
    monkeypatch.setattr(replay, "_frozen_setup", lambda full, bundle: ({"roof": roof}, jobs, plan))

    def read(recording):
        assert recording == "omitted"
        return omitted

    monkeypatch.setattr(replay.trial.base.native, "_load_case", read)
    inputs, actual_jobs, actual_plan = replay.setup(True, object())
    assert inputs == {"roof": roof, "omitted": omitted}
    assert actual_jobs is jobs and actual_plan is plan
