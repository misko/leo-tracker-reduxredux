"""Freeze and launch a small fixed-position scoring comparison."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent
TREND = REPORTS / "2026_09_29_unassociated_trend"
FEAS = REPORTS / "2026_09_29_cone_feasibility"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
SOURCES = [
    HERE / n
    for n in (
        "hard_gate.py",
        "run.py",
        "study.py",
        "summarize.py",
        "test_hard_gate.py",
        "PROTOCOL.md",
    )
]
EXTERNAL = [
    REPORTS / p
    for p in (
        "2026_09_29_cone_trend/cone_trend.py",
        "2026_09_29_rx_cone_position/cones.py",
        "2026_09_29_unassociated_trend/trend_mixture.py",
        "2026_09_29_frequency_contrast/contrast_position.py",
    )
]
EXTERNAL += [
    ROOT / "tools" / n for n in ("ds7_baseline_adapter.py", "ds7_fast_baseline_adapter.py")
]
EXTERNAL += [
    REPORTS / p
    for p in (
        "2026_09_29_unassociated_trend/test_trend_mixture.py",
        "2026_09_29_frequency_contrast/test_contrast_position.py",
    )
]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(paths):
    return {str(p.relative_to(ROOT)): digest(p) for p in paths}


def verify(bindings):
    for name, value in bindings.items():
        assert digest(ROOT / name) == value, name


def save(path, data):
    with path.open("x") as f:
        json.dump(data, f, indent=2, allow_nan=False)


def unit_paths(unit):
    return [ROOT / unit[k] for k in ("selection", "baseline_held")] + [
        Path(a["path"]) for i in unit["group"]["inputs"] for a in i["artifacts"]
    ]


def prepare():
    assert read(HERE / "test-v2-receipt.json")["exit_code"] == 0
    prior = read(FEAS / "plan.json")
    units = []
    for old in prior["units"]:
        folder = TREND / "runs" / (old["unit_id"] + "_q020")
        selection, held = folder / "selection.json", folder / "held/result.json"
        selected = read(selection)["selected"]
        assert selected["qualified"] and read(held)["audit_passed"]
        assert selected["session_ids"] == old["group"]["session_ids"]
        units.append(
            {
                "unit_id": old["unit_id"],
                "group": old["group"],
                "x": selected["x"],
                "selection": str(selection.relative_to(ROOT)),
                "baseline_held": str(held.relative_to(ROOT)),
            }
        )
    assert len(units) == 18
    expected = read(REPORTS / "2026_09_29_cone_trend/evidence-sha256.json")["sha256"]
    external = EXTERNAL + [FEAS / "plan.json"] + [p for u in units for p in unit_paths(u)]
    # The no-cone donor files and banks were already bound by the soft-cone study.
    feasibility = read(FEAS / "evidence-sha256.json")["sha256"]
    trend = read(TREND / "evidence-sha256.json")["sha256"]
    for name, value in bind(external).items():
        assert expected.get(name, feasibility.get(name, trend.get(name))) == value, name
    plan = {
        "config": prior["config"],
        "units": units,
        "arms": ["soft40", "hard40", "soft50", "hard50"],
    }
    original = REPORTS / "2026_09_29_hard_cone_scoring"
    verify(read(original / "evidence-sha256.json")["sha256"])
    assert plan == read(original / "plan.json"), "Scientific plan changed"
    external += [
        original / n for n in ("plan.json", "input-seal.json", "README.md", "evidence-sha256.json")
    ]
    save(HERE / "plan.json", plan)
    paths = (
        SOURCES
        + external
        + [
            HERE / n
            for n in (
                "plan.json",
                "tests-v2.log",
                "test-v2-receipt.json",
            )
        ]
    )
    save(HERE / "input-seal.json", {"sha256": bind(paths)})
    print("Frozen 18 panels, four fixed-position arms", flush=True)


def launch():
    plan, frozen = read(HERE / "plan.json"), read(HERE / "input-seal.json")["sha256"]
    verify(frozen)
    for unit in plan["units"]:
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
        folder = HERE / "runs" / unit["unit_id"]
        folder.mkdir(parents=True, exist_ok=False)
        bindings = bind(
            SOURCES + EXTERNAL + unit_paths(unit) + [HERE / "plan.json", HERE / "input-seal.json"]
        )
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
