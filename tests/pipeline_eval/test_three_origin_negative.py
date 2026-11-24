from hashlib import sha256
from pathlib import Path
import subprocess

import numpy as np
import pytest

from reports.ALGO08.v3 import three_origin_negative as probe


@pytest.fixture(scope="module")
def screen(tmp_path_factory):
    output = tmp_path_factory.mktemp("three-origin") / "score.so"
    source = Path(probe.__file__).with_suffix(".c")
    subprocess.run(["cc", "-std=c11", "-O3", "-Wall", "-Wextra", "-Werror",
                    "-fPIC", "-shared", source, "-o", output, "-lm"], check=True)
    return probe.Screen(output, sha256(output.read_bytes()).hexdigest())


def test_joint_burst_and_tone_at_same_aperture(screen):
    rng = np.random.default_rng(87)
    waveform = rng.integers(-3000, 3001, (45_000, 2, 2), dtype=np.int16)
    motif = rng.integers(-3000, 3001, (13_332, 2), dtype=np.int16)
    waveform[:13_332, 0] = motif
    waveform[13_333:26_665, 0, 0] = -motif[:, 1]
    waveform[13_333:26_665, 0, 1] = motif[:, 0]
    waveform[26_667:39_999, 0] = -motif
    t = np.arange(len(waveform)) * .3664
    waveform[:, 1, 0] = 4000*np.cos(t)
    waveform[:, 1, 1] = 4000*np.sin(t)
    assert screen.score(waveform, 0) > .95
    assert screen.score(waveform, 1) < 1e-5


def test_prefix_lane_isolation_and_indeterminate_fallback(screen):
    rng = np.random.default_rng(18)
    waveform = rng.integers(-3000, 3001, (45_000, 2, 2), dtype=np.int16)
    value = screen.score(waveform, 0)
    waveform[40_000:] = 0
    waveform[:, 1] = 0
    assert screen.score(waveform, 0) == value
    for values, lane in ((waveform, 1), (waveform, -1), (waveform[:39_999], 0), (waveform[::2], 0)):
        assert np.isnan(screen.score(values, lane))


def test_only_a_score_strictly_below_the_positive_floor_can_omit():
    def row(score, positive=False):
        return {"score": score, "positive": positive}

    threshold = probe.floor([row(.09, True), row(.17, True), row(None, True), row(.001)])
    assert threshold == .09
    assert probe.omit(row(.089), threshold)
    assert not any(probe.omit(row(value), threshold) for value in (.09, .091, None, float("nan")))
    assert not probe.omit(row(0), probe.floor([row(.001), row(None, True)]))


def test_original_scopes_have_independently_fixed_native_population():
    for case, short, positive in (("0008", 112, 61), ("0169", 86, 45)):
        _, packet = probe.reference(case)
        tally = packet["acquisition"]["receiver"]
        assert tally["native_calls"] == {"full": 16, "short_primary": short}
        assert tally["factors"]["short_primary"] == positive
    receipt = probe.verified_receipt("original-dense-intake.json.gz", probe.INTAKE_PIN)
    assert all(pair["first_use"]["inner_receiver"]["elapsed_s"] > .28 for pair in receipt["pairs"])
