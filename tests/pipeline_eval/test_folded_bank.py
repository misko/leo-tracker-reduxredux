"""Check overlap-save against the original folded kernel and bounded partial overlaps."""

import os
import subprocess

import numpy as np

from tools.pipeline_eval.qualification import capture_board_folded as capture
from tools.pipeline_eval.qualification import folded_bank_trial as trial


def build(directory, implementation, fftw=False):
    directory.mkdir()
    (directory / capture.GRID).write_bytes(implementation.read_bytes())
    path = directory / "bank"
    command = ["cc", "-std=c11", "-O2", "-I", str(directory), str(capture.HARNESS)]
    if fftw:
        command.append("-lfftw3")
    subprocess.run(
        [*command, "-lm", "-o", path],
        timeout=15,
        check=True,
        env=dict(os.environ, TMPDIR=str(directory)),
    )
    return path


def test_overlapping_frames_and_different_fir_lengths_match_direct_grid(tmp_path):
    rng = np.random.default_rng(1333335)
    sample_count, epoch_count = 1762, 779
    samples = rng.normal(size=sample_count) + 1j * rng.normal(size=sample_count)
    samples[410:603] = 0
    template = rng.normal(size=64) + 1j * rng.normal(size=64)
    inputs = dict(
        samples=samples.astype("<c16"),
        template=template.astype("<c16"),
        frequencies=np.array([-200_000.0, 50000.0, 240_000.0], dtype="<f8"),
        starts=np.array([0, 6, 20], dtype="<i8"),
        stops=np.array([6, 17, 63], dtype="<i8"),
        frame_offsets=np.array([0, 260, 1050, 1733], dtype="<i8"),
        prefix=np.r_[0.0, np.cumsum(samples.real**2 + samples.imag**2)].astype("<f8"),
    )
    fixture = capture.binary_fixture(inputs, 10_000_000.0, epoch_count)
    path = tmp_path / "case.input"
    path.write_bytes(fixture)
    direct = build(tmp_path / "direct", capture.REPORT / capture.GRID)
    accelerated = build(tmp_path / "fft", trial.KERNEL, fftw=True)
    tag = capture.fixture_tag(fixture)
    shape = (len(inputs["frequencies"]), epoch_count)
    _, baseline = trial.attempt(direct, [], path, tag, shape)
    clocks, output = trial.attempt(accelerated, [], path, tag, shape)
    np.testing.assert_allclose(output, baseline, rtol=0, atol=1e-12)
    assert clocks["bank"]["input_ffts"] == 4
    assert clocks["bank"]["filter_ffts"] == 9
    assert clocks["bank"]["inverse_ffts"] > clocks["bank"]["input_ffts"]
