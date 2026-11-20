import numpy as np

from tools.pipeline_eval.qualification import anchor_receiver_full_worker as native_worker
from tools.pipeline_eval.qualification.anchor_receiver_rf import shared_rows
from tools.pipeline_eval.variants import anchor_receiver_orbits as model


def _arc():
    t = np.linspace(0, 30, 30)
    phase = np.stack((40 + t, 70 - t))
    raw = np.stack((model.lean.PERIOD + 70 + 3 * phase[0], 170 * t - 800))
    tr = model.lean.Track(t, raw[0], 11.5e9, 0, True, t * 0, np.eye(30) / 150)
    return model.lean.Arc(
        tr, np.array([0, 1]), raw, np.zeros((2, len(t), 2)), phase, np.zeros(2), np.zeros(2)
    )


def test_late_samples_leave_nominations_unchanged_but_can_reject_prediction():
    arc = _arc()
    clean = model.prefix(arc)
    arc.residual[0, -5:] += 2000
    altered = model.prefix(arc)
    assert np.array_equal(clean.shape, altered.shape)
    assert np.array_equal(clean.level_hz, altered.level_hz)
    state = model.lean.State(np.zeros(2), np.array([70.0, 0.0, 0.0, 0.0]), np.zeros(4), np.zeros(2))
    loss, alias = model.forecast(altered, state)
    assert alias[0] == 1
    assert loss[0] > (model.LATE_RMS_HZ / model.CARRIER_SCALE_HZ) ** 2


def test_guard_uses_other_families_and_returns_no_fix_on_empty_input():
    profile = model.prefix(_arc())
    chosen = model.nominations([profile], model.clock_modes([profile]))
    assert model.validated(chosen, 2, 12.5) == []
    result = model.infer({"duration_s": 300, "tracks": []}, {"center": [1, 2]}, "")
    assert result["status"] == "withheld"
    assert not any(arm["latlon"] for arm in result["arms"].values())


def test_full_adapter_changes_only_fitter_and_preserves_memory_limit(monkeypatch):
    limits = []
    original = model.exact.infer

    def fake_worker(request):
        assert request == {"mode": "native"}
        assert model.exact.infer is model.infer
        duration = {"cpu_s": 0.0, "wall_s": 0.0}
        return {
            "stages": {"backend_import": duration, "same_exact_backend": duration},
            "result": {},
            "observation_sha256": "frozen projection",
        }

    monkeypatch.setattr(native_worker.native, "worker", fake_worker)
    monkeypatch.setattr(native_worker, "setrlimit", lambda _, cap: limits.append(cap))
    got = native_worker.worker({"mode": "native"})
    assert limits == [(512 * 1024**2, 512 * 1024**2)]
    assert model.exact.infer is original
    assert got["observation_sha256"] == "frozen projection"
    assert got["result"]["boundary"] == native_worker.BOUNDARY
    assert "anchor_backend" in got["stages"]


def test_shared_rf_excludes_ambiguous_keys_and_labels_different_aliases():
    a = dict(key=[0, 11e9, 1.0, 100.0], norad=11, lift=0, error=30.0)
    b = a | {"key": [0, 11e9, 2.0, 200.0]}
    got = list(
        shared_rows(
            {
                "anchor": [a, b],
                "joint": [a, a, b | {"lift": 1, "error": 40.0}],
                "exact": [a, b],
            }
        )
    )
    assert len(got) == 1
    assert got[0]["key"] == tuple(b["key"])
    assert got[0]["same_orbit"] and not got[0]["same_lift"]
    assert got[0]["residuals"]["joint"] == 40.0
