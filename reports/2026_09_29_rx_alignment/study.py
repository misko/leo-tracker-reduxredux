"""Freeze and execute a bounded alignment diagnostic on published selected pairs."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DONOR = HERE.parent / "2026_09_29_rx_track_coherence"
PYTHON = ROOT / ".venv/bin/python"


def read(p):
    return json.loads(p.read_text())


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, d):
    with p.open("x") as f:
        json.dump(d, f, indent=2, allow_nan=False)


def bind(paths):
    return {str(p.relative_to(ROOT)): digest(p) for p in paths}


def verify(bindings):
    for name, value in bindings.items():
        assert digest(ROOT / name) == value, name


def prepare():
    command = [
        str(PYTHON),
        "-m",
        "unittest",
        "discover",
        "-s",
        str(HERE),
        "-p",
        "test_align.py",
        "-v",
    ]
    with (HERE / "tests.log").open("x") as f:
        result = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    save(HERE / "test-receipt.json", {"command": command, "exit_code": result.returncode})
    assert result.returncode == 0
    external = [DONOR / n for n in ("result.json", "summary.json", "PROTOCOL.md")]
    inventory = read(DONOR / "evidence-sha256.json")["sha256"]
    for p in external:
        assert digest(p) == inventory[str(p.relative_to(ROOT))]
    save(
        HERE / "plan.json",
        {
            "source": str((DONOR / "result.json").relative_to(ROOT)),
            "scans": 72,
            "selected_pairs": 913,
            "models": [
                "median",
                "constant",
                "drift",
                "slope",
                "both",
                "drift_permuted",
                "slope_permuted",
            ],
        },
    )
    paths = (
        external
        + [DONOR / "evidence-sha256.json"]
        + [
            HERE / n
            for n in (
                "align.py",
                "test_align.py",
                "study.py",
                "PROTOCOL.md",
                "plan.json",
                "tests.log",
                "test-receipt.json",
            )
        ]
    )
    save(HERE / "input-seal.json", {"sha256": bind(paths)})
    print("Frozen 913 targets, seven arms", flush=True)


def child():
    from align import analyze

    plan = read(HERE / "plan.json")
    source = read(ROOT / plan["source"])["scans"]
    assert len(source) == plan["scans"]
    results = [analyze(scan) for scan in source]
    assert sum(len(r["rows"]) for r in results) == plan["selected_pairs"]
    save(HERE / "result.json", {"scans": results})
    print("Completed", len(results), "scans", flush=True)


def launch():
    bindings = read(HERE / "input-seal.json")["sha256"]
    verify(bindings)
    bindings.update(bind([HERE / "input-seal.json"]))
    available = (
        int(
            next(
                s.split()[1]
                for s in Path("/proc/meminfo").read_text().splitlines()
                if s.startswith("MemAvailable:")
            )
        )
        * 1024
    )
    assert available >= 5 * 1024**3
    command = [
        "/usr/bin/time",
        "-v",
        "-o",
        str(HERE / "resources.txt"),
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
        str(PYTHON),
        str(HERE / "study.py"),
        "child",
    ]
    save(
        HERE / "launch.json", {"command": command, "sha256": bindings, "available_bytes": available}
    )
    with (HERE / "terminal.log").open("x") as f:
        result = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    (HERE / "exit-code.txt").write_text(str(result.returncode) + "\n")
    verify(bindings)
    bindings.update(bind(p for p in HERE.iterdir() if p.is_file() and p.name != "seal.json"))
    save(HERE / "seal.json", {"sha256": bindings})
    print("Exit", result.returncode, flush=True)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    {"prepare": prepare, "child": child, "launch": launch}[sys.argv[1]]()
