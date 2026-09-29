"""Freeze 72 observation exports and execute one bounded, read-only census."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DONOR = HERE.parent / "2026_09_29_hard_cone_scoring_v2"
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
        "test_coherence.py",
        "-v",
    ]
    with (HERE / "tests.log").open("x") as f:
        result = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    save(HERE / "test-receipt.json", {"command": command, "exit_code": result.returncode})
    assert result.returncode == 0
    old = read(DONOR / "plan.json")
    inventory = read(DONOR / "evidence-sha256.json")["sha256"]
    units = []
    for unit in old["units"]:
        group = unit["group"]
        if group["size"] != 8:
            continue
        for item in group["inputs"]:
            obs = [a for a in item["artifacts"] if a["kind"] == "observations"]
            assert len(obs) == 1
            path = Path(obs[0]["path"])
            name = str(path.relative_to(ROOT))
            assert digest(path) == obs[0]["sha256"].removeprefix("sha256:") == inventory[name]
            units.append(
                {
                    "dataset": group["source_dataset"],
                    "panel": unit["unit_id"],
                    "session_id": item["session_id"],
                    "observations": name,
                }
            )
    assert len(units) == len({u["session_id"] for u in units}) == 72
    save(HERE / "plan.json", {"units": units})
    paths = [ROOT / u["observations"] for u in units] + [
        DONOR / "plan.json",
        DONOR / "evidence-sha256.json",
    ]
    paths += [
        HERE / n
        for n in (
            "coherence.py",
            "test_coherence.py",
            "study.py",
            "PROTOCOL.md",
            "plan.json",
            "tests.log",
            "test-receipt.json",
        )
    ]
    save(HERE / "input-seal.json", {"sha256": bind(paths)})
    print("Frozen", len(units), "scans", flush=True)


def child():
    from coherence import analyze

    outputs = []
    for unit in read(HERE / "plan.json")["units"]:
        document = read(ROOT / unit["observations"])
        assert document["session_id"] == unit["session_id"]
        outputs.append({**unit, **analyze(document)})
    save(HERE / "result.json", {"scans": outputs})
    print("Completed", len(outputs), "scans", flush=True)


def launch():
    bindings = read(HERE / "input-seal.json")["sha256"]
    verify(bindings)
    bindings.update(bind([HERE / "input-seal.json"]))
    memory = (
        int(
            next(
                s.split()[1]
                for s in Path("/proc/meminfo").read_text().splitlines()
                if s.startswith("MemAvailable:")
            )
        )
        * 1024
    )
    assert memory >= 5 * 1024**3
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
    save(HERE / "launch.json", {"command": command, "sha256": bindings, "available_bytes": memory})
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
