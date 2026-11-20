"""Check the portable fixture, clocks, and actual small C-kernel entry point."""

import io
import json
import os
import struct
import subprocess
import tarfile

import numpy as np
import pytest

from tools.pipeline_eval.qualification import capture_board_folded as capture


def small_fixture():
    return capture.binary_fixture(
        dict(
            samples=np.array([1, 2j, -3, -4j], dtype="<c16"),
            template=np.array([1], dtype="<c16"),
            frequencies=np.array([0], dtype="<f8"),
            starts=np.array([0], dtype="<i8"),
            stops=np.array([1], dtype="<i8"),
            frame_offsets=np.array([0], dtype="<i8"),
            prefix=np.array([0, 1, 5, 14, 30], dtype="<f8"),
        ),
        10_000_000.0,
        4,
    )


def test_authenticated_c_source_executes_small_signal_and_rejects_short_input(tmp_path):
    locked = json.loads((capture.REPORT / "source-lock.json").read_bytes())
    kernel = capture.REPORT / capture.GRID
    assert capture.file_sha(kernel) == locked["sources"][capture.GRID]
    binary = tmp_path / "capture-board-folded"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-I",
            str(kernel.parent),
            str(capture.HARNESS),
            "-lm",
            "-o",
            str(binary),
        ],
        check=True,
        timeout=10,
        env=dict(os.environ, TMPDIR=str(tmp_path)),
    )
    data = small_fixture()
    fixture = tmp_path / "folded.input"
    fixture.write_bytes(data)
    result = subprocess.run([binary, fixture], capture_output=True, check=True, timeout=5)
    assert struct.unpack("<4d", result.stdout) == (1.0, 1.0, 1.0, 1.0)
    timing = json.loads(result.stderr)
    capture.verify_clock(timing, tag=capture.fixture_tag(data), cells=4)
    with pytest.raises(ValueError, match="fixture binding"):
        capture.verify_clock(timing, tag="different data", cells=4)
    timing["total"]["observed"]["cpu_ns"] += 1
    with pytest.raises(ValueError, match="stage clocks"):
        capture.verify_clock(timing, tag=capture.fixture_tag(data), cells=4)

    fixture.write_bytes(data[:-1])
    short = subprocess.run([binary, fixture], capture_output=True, timeout=5, check=False)
    assert (short.returncode, short.stdout, short.stderr) == (2, b"", b"truncated fixture\n")


def test_published_elf_and_fixture_bind_to_measured_receipt():
    root = capture.REPORT
    lock = json.loads((root / "source-lock.json").read_bytes())
    receipt = json.loads((root / "receipt.json").read_bytes())
    blob = (root / "cortex-a9-offline.tar.gz").read_bytes()
    assert receipt["source_lock_sha256"] == capture.file_sha(root / "source-lock.json")
    assert receipt["target_distribution_sha256"] == capture.digest(blob)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        arm = archive.extractfile("capture-board-folded").read()
        fixture = archive.extractfile("folded.input").read()
        assert archive.getmember("capture-board-folded").mode == 0o755
    assert arm[:6] == b"\x7fELF\x01\x01"
    assert struct.unpack_from("<H", arm, 18) == (40,)
    assert struct.unpack_from("<I", arm, 36) == (0x05000400,)
    assert capture.digest(arm) == lock["builds"]["arm"]["sha256"]
    assert capture.digest(fixture) == lock["packed_input_sha256"]
