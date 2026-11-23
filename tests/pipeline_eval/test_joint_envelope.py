from pathlib import Path
import subprocess

import numpy as np

from reports.ALGO08.v3 import joint_envelope_trial as trial


def test_phase_matching_handles_wrap_without_double_counting():
    assert trial.supports([13332, 12, 0.25], [0, 12], 4) == [(1, 0), (2, 0.25)]
    assert trial.supports([13323], [0], 7) == []


def test_paired_phase_remains_independent_of_signed_cfo():
    stock = ([(0, 13332, 0.25, -601000, 1, 0)], [(1, 0, 0.1, 601000, 1, 0)])
    (err, signed_split, left_rank, right_rank), = trial.counterparts(stock, 4)
    assert err < 1.0
    assert signed_split == 1202000
    assert (left_rank, right_rank) == (0, 1)


def test_native_envelope_uses_common_absolute_time_with_distinct_lane_carriers(tmp_path):
    source = Path(trial.__file__).with_name("joint_envelope.c")
    library = tmp_path / "joint.so"
    subprocess.run(["cc", "-std=c11", "-O2", "-fPIC", "-shared", str(source),
                    "-lfftw3f", "-lm", "-o", str(library)], check=True)
    ticks = np.arange(40000)
    profile = np.zeros(40000, dtype=np.float32)
    profile[(ticks >= 6100) & (ticks < 7500)] = 1
    profile[(ticks >= 10100) & (ticks < 11400)] = 2
    profile[(ticks >= 20100) & (ticks < 20800)] = 1.5
    asset = np.zeros(4*trial.PERIOD + 81 + 2*len(profile), dtype=np.float32)
    asset[4*trial.PERIOD + 81::2] = profile
    sketch = trial.Envelope(library, asset)
    iq = np.empty((trial.POINTS, 2, 2), dtype="<i2")
    samples = np.arange(trial.POINTS)
    shared_epoch = 4996
    magnitude = 3000 * profile[(3*(samples - shared_epoch)) % 40000]
    try:
        for lane, hz in enumerate((-620000, 419000)):
            wave = magnitude * np.exp(2j*np.pi*hz*samples/10000000)
            iq[:, lane, 0] = np.rint(wave.real)
            iq[:, lane, 1] = np.rint(wave.imag)
        joint, _, _ = sketch.measure(iq, "joint")
        wrong, _, _ = sketch.measure(iq, "mismatched")
        assert trial.distance(joint[0][0], shared_epoch) <= 4
        assert len(joint) == len(wrong) == trial.KEEP
        assert trial.distance(wrong[0][0], shared_epoch) > 7
        iq[:, 1] = 0
        assert sketch.measure(iq, "joint")[0] == []
        assert trial.distance(sketch.measure(iq, "rx0")[0][0][0], shared_epoch) <= 4
    finally:
        sketch.close()
