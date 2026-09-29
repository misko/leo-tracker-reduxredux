"""Freeze and run the bounded, read-only cone-domain diagnostic."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / "2026_09_29_rx_cone_consistency"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
SOURCES = [
    HERE / n
    for n in ("PROTOCOL.md", "bounds.py", "test_bounds.py", "run.py", "study.py", "summarize.py")
]
EXTERNAL = [PRIOR / "cones.py", PRIOR / "plan.json"] + [
    ROOT / "tools" / n for n in ("ds7_baseline_adapter.py", "ds7_fast_baseline_adapter.py")
]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as f:
        json.dump(value, f, indent=2, allow_nan=False)


def bind(paths):
    return {str(p.relative_to(ROOT)): digest(p) for p in paths}


def verify(bindings):
    for name, value in bindings.items():
        assert digest(ROOT / name) == value, name


def unit_paths(unit):
    return [PRIOR / "runs" / unit["unit_id"] / "result.json"] + [
        Path(a["path"]) for i in unit["group"]["inputs"] for a in i["artifacts"]
    ]


def prepare():
    assert read(HERE / "test-receipt.json")["exit_code"] == 0
    plan = read(PRIOR / "plan.json")
    assert len(plan["units"]) == 18
    plan = {"config": plan["config"], "units": plan["units"], "half_angles_deg": [20, 30, 40, 50]}
    external = EXTERNAL + [p for u in plan["units"] for p in unit_paths(u)]
    old = read(PRIOR / "evidence-sha256.json")
    for name, value in bind(external).items():
        assert old[name] == value, name
    for u in plan["units"]:
        for i in u["group"]["inputs"]:
            for a in i["artifacts"]:
                assert "sha256:" + digest(Path(a["path"])) == a["sha256"]
    save(HERE / "plan.json", plan)
    paths = SOURCES + external + [HERE / n for n in ("plan.json", "tests.log", "test-receipt.json")]
    bindings = bind(paths)
    save(HERE / "input-seal.json", {"sha256": bindings})
    print("Frozen", len(plan["units"]), "panels;", len(bindings), "bindings", flush=True)


def launch():
    plan, frozen = read(HERE / "plan.json"), read(HERE / "input-seal.json")["sha256"]
    verify(frozen)
    for unit in plan["units"]:
        available = (
            int(
                next(
                    line.split()[1]
                    for line in Path("/proc/meminfo").read_text().splitlines()
                    if line.startswith("MemAvailable:")
                )
            )
            * 1024
        )
        assert available >= 5 * 1024**3, "Memory admission failed; no scientific retry"
        folder = HERE / "runs" / unit["unit_id"]
        folder.mkdir(parents=True, exist_ok=False)
        paths = (
            SOURCES + EXTERNAL + unit_paths(unit) + [HERE / "plan.json", HERE / "input-seal.json"]
        )
        bindings = bind(paths)
        for name, value in bindings.items():
            if name != str((HERE / "input-seal.json").relative_to(ROOT)):
                assert frozen[name] == value, name
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
            str(HERE / "run.py"),
            unit["unit_id"],
        ]
        save(
            folder / "launch.json",
            {"command": command, "available_bytes": available, "sha256": bindings},
        )
        with (folder / "terminal.log").open("x") as f:
            result = subprocess.run(command, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
        (folder / "exit-code.txt").write_text(str(result.returncode) + "\n")
        verify(bindings)
        bindings.update(bind(p for p in folder.iterdir() if p.is_file()))
        save(folder / "seal.json", {"sha256": bindings})
        print(unit["unit_id"], "exit", result.returncode, flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    {"prepare": prepare, "launch": launch}[sys.argv[1]]()
