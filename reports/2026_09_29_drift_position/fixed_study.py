"""Freeze and launch eighteen bounded scoring-only drift comparisons."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / "2026_09_29_hard_cone_scoring_v2"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"


def read(p):
    return json.loads(p.read_text())


def save(p, value):
    with p.open("x") as f:
        json.dump(value, f, indent=2, allow_nan=False)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify(bindings):
    for name, value in bindings.items():
        assert digest(ROOT / name) == value, name


def prepare():
    bindings = read(PRIOR / "input-seal.json")["sha256"]
    bindings.update(read(HERE / "coverage-seal.json")["sha256"])
    verify(bindings)
    prior = read(PRIOR / "plan.json")
    plan = {
        "config": prior["config"],
        "units": prior["units"],
        "arms": ["none", "symmetric", "rx0_anchor", "rx1_anchor"],
        "coherence": "reports/2026_09_29_rx_track_coherence/result.json",
    }
    command = [
        "sudo",
        "-n",
        "env",
        "OPENBLAS_NUM_THREADS=1",
        PYTHON,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(HERE),
        "-p",
        "test_correction.py",
        "-v",
    ]
    with (HERE / "fixed-tests.log").open("x") as f:
        outcome = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    save(HERE / "fixed-test-receipt.json", {"command": command, "exit_code": outcome.returncode})
    assert outcome.returncode == 0
    save(HERE / "fixed-plan.json", plan)
    for name in (
        "correction.py",
        "test_correction.py",
        "fixed_score.py",
        "fixed_study.py",
        "FIXED-PROTOCOL.md",
        "fixed-plan.json",
        "fixed-tests.log",
        "fixed-test-receipt.json",
    ):
        p = HERE / name
        bindings[str(p.relative_to(ROOT))] = digest(p)
    save(HERE / "fixed-input-seal.json", {"sha256": bindings})
    print("Frozen 18 fixed-position comparisons", flush=True)


def launch():
    plan = read(HERE / "fixed-plan.json")
    bindings = read(HERE / "fixed-input-seal.json")["sha256"]
    bindings[str((HERE / "fixed-input-seal.json").relative_to(ROOT))] = digest(
        HERE / "fixed-input-seal.json"
    )
    verify(bindings)
    for unit in plan["units"]:
        memory = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        available = int(memory["MemAvailable"].split()[0]) * 1024
        assert available >= 5 * 1024**3
        folder = HERE / "fixed-runs" / unit["unit_id"]
        folder.mkdir(parents=True, exist_ok=False)
        command = [
            "sudo",
            "-n",
            "/usr/bin/time",
            "-v",
            "-o",
            str(folder / "resources.txt"),
            "timeout",
            "--kill-after=5s",
            "90s",
            "prlimit",
            "--as=4294967296",
            "nice",
            "-n",
            "19",
            "env",
            "OPENBLAS_NUM_THREADS=1",
            "OMP_NUM_THREADS=1",
            "MKL_NUM_THREADS=1",
            PYTHON,
            str(HERE / "fixed_score.py"),
            unit["unit_id"],
        ]
        save(folder / "launch.json", {"command": command, "available_bytes": available})
        with (folder / "terminal.log").open("x") as f:
            result = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
        save(folder / "exit.json", {"exit_code": result.returncode})
        verify(bindings)
        seal = dict(bindings)
        for p in folder.iterdir():
            if p.is_file():
                seal[str(p.relative_to(ROOT))] = digest(p)
        save(folder / "seal.json", {"sha256": seal})
        print(unit["unit_id"], "exit", result.returncode, flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    {"prepare": prepare, "launch": launch}[sys.argv[1]]()
