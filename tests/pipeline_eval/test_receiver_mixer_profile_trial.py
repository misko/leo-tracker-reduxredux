from collections import Counter
from importlib import import_module
from pathlib import Path

import numpy as np


def test_training_balances_mixer_centers_on_both_edges_and_lanes(tmp_path, monkeypatch):
    reports = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
    monkeypatch.syspath_prepend(str(reports))
    trial = import_module("receiver_mixer_profile_trial")
    frames = {edge: edge for edge in ("lower", "upper")}
    monkeypatch.setattr(trial.waveform, "pulse_bank", lambda: frames)
    monkeypatch.setattr(trial.waveform, "iq", lambda record, _, edge: (record, edge))
    for edge in frames:
        np.zeros(133413, dtype="<f4").tofile(tmp_path / f"{edge}.f32")

    observed = Counter()

    class Receiver:
        def __init__(self, binary, pilot):
            assert pilot.shape == (133413,)

        def timed(self, samples, lane, center):
            record, edge = samples
            for plant in record["planted"]:
                if plant is not None:
                    assert abs(plant["actual_cfo_hz"] - center) <= 800_000.
            observed[edge, lane, center] += 1
            return (), 0, 0

        def close(self):
            pass

    monkeypatch.setattr(trial, "Receiver", Receiver)
    receipt = trial.train(tmp_path / "training.so", tmp_path)
    assert len(receipt) == 32
    for edge in frames:
        for lane in (0, 1):
            assert observed[edge, lane, 0.] == 4
            assert observed[edge, lane, -100_000.] == observed[edge, lane, 100_000.] == 2
