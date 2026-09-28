import json
import os
from pathlib import Path
import subprocess

import pytest


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "sd_writer.c"


@pytest.fixture()
def writer(tmp_path: Path) -> Path:
    executable = tmp_path / "sd-writer"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(SOURCE),
            "-lm",
            "-o",
            str(executable),
        ],
        check=True,
    )
    return executable


def first_allowed_core() -> int:
    if not hasattr(os, "sched_getaffinity"):
        pytest.skip("explicit CPU affinity requires Linux")
    allowed = os.sched_getaffinity(0)
    if not allowed:
        pytest.skip("process has no allowed CPU")
    return min(allowed)


def test_writes_byte_exact_paced_output(writer: Path, tmp_path: Path) -> None:
    payload = bytes(range(251)) * 17
    input_path = tmp_path / "input.ci16"
    output_path = tmp_path / "output.ci16"
    input_path.write_bytes(payload)

    result = subprocess.run(
        [str(writer), str(input_path), str(output_path), "2", "120", str(first_allowed_core())],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )

    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert [record["type"] for record in records] == ["ready", "write", "write", "complete"]
    assert records[0]["input_bytes"] == len(payload)
    assert records[0]["total_bytes"] == 2 * len(payload)
    assert records[0]["core"] == first_allowed_core()
    writes = records[1:3]
    assert [record["index"] for record in writes] == [0, 1]
    assert all(record["bytes"] == len(payload) for record in writes)
    assert writes[1]["due_ms"] - writes[0]["due_ms"] == pytest.approx(120.0)
    assert all(record["end_ms"] >= record["start_ms"] >= record["due_ms"] for record in writes)
    assert records[-1]["jobs"] == 2
    assert records[-1]["bytes"] == 2 * len(payload)
    assert records[-1]["sync_wall_ms"] >= 0
    assert output_path.read_bytes() == payload * 2


def test_refuses_to_overwrite_existing_output(writer: Path, tmp_path: Path) -> None:
    input_path = tmp_path / "input.ci16"
    output_path = tmp_path / "output.ci16"
    input_path.write_bytes(b"new payload")
    output_path.write_bytes(b"keep this")

    result = subprocess.run(
        [str(writer), str(input_path), str(output_path), "1", "120", str(first_allowed_core())],
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert "open output" in result.stderr
    assert output_path.read_bytes() == b"keep this"
