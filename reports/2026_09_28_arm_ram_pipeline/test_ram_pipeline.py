import json
import os
import pathlib
import subprocess


HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE / "ram_pipeline.c"


def test_standalone_ring_state_machine(tmp_path: pathlib.Path) -> None:
    binary = tmp_path / "ring-self-test"
    compiler = os.environ.get("CC", "cc")
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pthread",
            "-DRAM_PIPELINE_STANDALONE_TEST",
            str(SOURCE),
            "-o",
            str(binary),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    completed = subprocess.run(
        [str(binary), "--ring-self-test"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    receipt = json.loads(completed.stdout)
    assert receipt == {
        "schema": "org.leo.research.ram-ring-self-test/v1",
        "status": "pass",
        "forced_overruns": 1,
        "occupied_highwater": 2,
        "ready_highwater": 2,
        "generation_reuse_checked": True,
        "fresh_payload_checked": True,
    }


def test_standalone_refuses_benchmark_arguments(tmp_path: pathlib.Path) -> None:
    binary = tmp_path / "ring-self-test"
    subprocess.run(
        [
            os.environ.get("CC", "cc"),
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pthread",
            "-DRAM_PIPELINE_STANDALONE_TEST",
            str(SOURCE),
            "-o",
            str(binary),
        ],
        check=True,
    )
    refused = subprocess.run(
        [str(binary), "cases.txt", "2500000"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert refused.returncode == 2
    assert "--ring-self-test" in refused.stderr
