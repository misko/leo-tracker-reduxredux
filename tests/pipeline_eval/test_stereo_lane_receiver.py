import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest


def test_skipped_lane_never_invokes_a_kernel_and_remains_in_original_probe_order(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    receiver = importlib.import_module("stereo_lane_receiver")
    binding = ModuleType("tools.pipeline_eval.qualification.blind_compact_run")
    binding._probe = lambda window, lane, candidates: (lane, candidates)
    binding.factor_candidate = lambda rank, epoch, **values: dict(candidate_rank=rank, passed_fractional_margin_gate=True,
                                                                 fractional_margin=values["margin"], epoch=epoch)
    monkeypatch.setitem(sys.modules, binding.__name__, binding)
    monkeypatch.setattr(receiver, "verified", lambda path, digest: bytes(133413 * 4))
    calls, closed = [], []

    class Engine:
        def __init__(self, library, asset, mode):
            self.mode = mode

        def run(self, samples, lane, center):
            calls.append((self.mode, lane))
            return [(0, 123 + lane, 0., 100., 1., .1)], (1, 2)

        def close(self):
            closed.append(self.mode)

    monkeypatch.setattr(receiver, "NativePath", Engine)
    candidate = receiver.StereoLaneReceiver(tmp_path / "short", "pin", "target")
    samples = np.zeros((200_000, 2, 2), dtype="<i2")
    window = SimpleNamespace(receiver_ids=(0, 1), sample_rate_hz=10_000_000, samples=samples,
                             target=dict(channel=1, edge="lower", lnb_lo_hz=1., rf_center_hz=2.),
                             acquisition=dict(actual_if_center_hz=1., sample_start=0))
    with candidate.detector("cancellation", "lower", binary="full", pilot="pilot") as receive:
        for n in range(17):
            window.acquisition["sample_start"] = n
            before = len(calls)
            probes = receive(window)
            assert [lane for lane, _ in probes] == [0, 1]
            active = [lane for lane, factors in probes if factors]
            assert [lane for _, lane in calls[before:]] == active
            if n % 8 == 0:
                assert active == [0, 1]
            assert active
        with pytest.raises(ValueError, match="Chronological"):
            receive(window)
    assert set(closed) == {"full", "short_primary"}
    with pytest.raises(RuntimeError, match="closed"):
        receive(window)
    audit = candidate.receipt()
    assert sum(audit["omitted_by_radio"].values()) == 10
    assert audit["native_calls"] == {"full": 6, "short_primary": 18}
    assert audit["native_cpu_ns"] == audit["native_calls"]
