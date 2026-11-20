import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tools.pipeline_eval.qualification import differential_arm
from tools.pipeline_eval.qualification import differential_pilot_eval as fixtures
from tools.pipeline_eval.variants import differential_pilot as reference


@pytest.fixture(scope="module")
def standalone(tmp_path_factory):
    root = tmp_path_factory.mktemp("portable-scout")
    binary = root / "scout"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O2",
            "-ffp-contract=off",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(differential_arm.SOURCE.parent),
            str(differential_arm.ADAPTER),
            "-lfftw3f",
            "-lm",
            "-o",
            binary,
        ],
        timeout=12,
        check=True,
        env=os.environ | {"TMPDIR": str(root)},
    )
    return Path(binary)


def arguments(tmp_path, standalone, edge, signal):
    samples, _ = fixtures.synthetic(edge, signal)
    ports = reference.filters(edge)
    files = [tmp_path / k for k in ("input.ci16", "filters.c8", "energy.f64")]
    samples.tofile(files[0])
    np.stack([k for k, _ in ports], dtype="<c8").tofile(files[1])
    np.stack([e for _, e in ports], dtype="<f8").tofile(files[2])
    return [standalone, *files, "2"], samples


@pytest.mark.parametrize(("edge", "signal"), (("upper", "one-frame"), ("lower", "zero")))
def test_standalone_all_epochs_and_ordered_centers(tmp_path, standalone, edge, signal):
    argv, samples = arguments(tmp_path, standalone, edge, signal)
    run = subprocess.run(argv, capture_output=True, check=True, timeout=5)
    receipt = json.loads(run.stderr)
    grid = np.frombuffer(run.stdout, dtype="<f8").reshape(2, 13333)
    exact = reference.surface(samples, edge)
    relative_error = np.max(np.abs(grid - exact)) / max(1.0, np.max(np.abs(exact)))
    assert relative_error < 1e-5
    assert len(receipt["calls"]) == 2
    assert receipt["top_16"] == [reference.ranked_centers(lane) for lane in exact]
    if signal == "zero":
        assert receipt["top_16"] == [[], []]
    else:
        assert [lane[0] for lane in receipt["top_16"]] == [735, 735]


def test_standalone_rejects_wrong_ci16_length_and_unbounded_repeats(tmp_path, standalone):
    argv, _ = arguments(tmp_path, standalone, "upper", "zero")
    result = subprocess.run([*argv[:-1], "9"], capture_output=True, timeout=5)
    assert result.returncode and b"repetition cap" in result.stderr
    argv[1].write_bytes(b"truncated")
    result = subprocess.run(argv, capture_output=True, timeout=5)
    assert result.returncode and not result.stdout and b"fixed-size input" in result.stderr
