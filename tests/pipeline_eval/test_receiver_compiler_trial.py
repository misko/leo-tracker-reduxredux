from importlib import import_module
from types import SimpleNamespace

import numpy as np
import pytest


trial = import_module("reports.ALGO08.single-core-2x.receiver_compiler_trial")


def test_training_uses_the_same_cfo_and_strengths_on_both_edges():
    rows = list(trial.training_rows())
    lower = [record for edge, record in rows if edge == "lower"]
    assert lower == [record for edge, record in rows if edge == "upper"]
    assert {row["planted"][0]["actual_cfo_hz"] for row in lower} == {-675000, -225000, 225000, 675000}
    assert any(row["planted"][1] is None for row in lower)
    assert any(row["planted"][1] is not None for row in lower)


def test_dual_training_calls_both_real_entry_points_on_each_lane(tmp_path, monkeypatch):
    asset = np.zeros(133413, dtype="<f4")
    for edge in ("upper", "lower"):
        asset.tofile(tmp_path / f"{edge}.f32")
    monkeypatch.setattr(trial.waveform, "pulse_bank", lambda: {"lower": None, "upper": None})
    monkeypatch.setattr(trial.waveform, "iq", lambda *_: None)
    kernels = [SimpleNamespace(argtypes=[], restype=int) for _ in range(2)]
    calls = []

    class Receiver:
        def __init__(self, binary, pilot):
            self.run = kernels[0]
            self.lib = SimpleNamespace(cancellation_primary_factors=kernels[1])

        def timed(self, samples, lane, center):
            calls.append((self.run is kernels[1], lane, center))
            return (), 0, 0

        def close(self):
            pass

    monkeypatch.setattr(trial, "Receiver", Receiver)
    rows = trial.train(tmp_path / "test.so", tmp_path, dual=True)
    assert calls == [(primary, lane, 0) for _ in range(8) for primary in (False, True) for lane in (0, 1)]
    assert all(r["entry"] == ("primary" if primary else "full")
               for r, (primary, _, _) in zip(rows, calls, strict=True))


@pytest.mark.parametrize("integer_fir", [True, False])
def test_build_rejects_a_changed_control_before_collecting_counters(tmp_path, monkeypatch, integer_fir):
    monkeypatch.setattr(trial.receiver_build, "build", lambda path, **_: path.write_bytes(b"unexpected"))
    with pytest.raises(ValueError, match="frozen receiver"):
        trial.build(tmp_path / "run", tmp_path, integer_fir=integer_fir)
