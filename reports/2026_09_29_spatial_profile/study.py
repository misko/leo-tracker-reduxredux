"""Freeze and run bounded spatial-curvature and timing-profile diagnostics."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / "2026_09_29_drift_position"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"


def read(p):
    return json.loads(p.read_text())


def save(p, data):
    with p.open("x") as f:
        json.dump(data, f, indent=2, allow_nan=False)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify(bindings):
    for n, h in bindings.items():
        assert digest(ROOT / n) == h, n


def unit_paths(u):
    return [ROOT / u[k] for k in ("selection", "baseline_held")] + [
        Path(a["path"]) for i in u["group"]["inputs"] for a in i["artifacts"]
    ]


def prepare():
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
        "test_geometry.py",
        "-v",
    ]
    with (HERE / "tests.log").open("x") as f:
        result = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    save(HERE / "test-receipt.json", dict(command=command, exit_code=result.returncode))
    assert result.returncode == 0
    prior = read(PRIOR / "fixed-plan.json")
    save(
        HERE / "plan.json",
        dict(
            config=prior["config"],
            units=prior["units"],
        ),
    )
    evidence = read(PRIOR / "evidence-sha256.json")["sha256"]
    external = [
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
        HERE.parent / "2026_09_29_unassociated_trend/trend_mixture.py",
        HERE.parent / "2026_09_29_frequency_contrast/contrast_position.py",
        PRIOR / "fixed-plan.json",
    ]
    paths = external + [p for u in prior["units"] for p in unit_paths(u)]
    bindings = {}
    for p in paths:
        n = str(p.relative_to(ROOT))
        assert digest(p) == evidence[n], n
        bindings[n] = evidence[n]
    sources = external + [
        HERE / n
        for n in (
            "study.py",
            "run.py",
            "geometry.py",
            "test_geometry.py",
            "PROTOCOL.md",
            "plan.json",
        )
    ]
    for p in sources + [HERE / "tests.log", HERE / "test-receipt.json"]:
        bindings[str(p.relative_to(ROOT))] = digest(p)
    save(
        HERE / "input-seal.json",
        dict(sha256=bindings, execution_sources=[str(p.relative_to(ROOT)) for p in sources]),
    )
    print("Frozen 18 panels; five tests passed", flush=True)


def launch():
    frozen = read(HERE / "input-seal.json")
    verify(frozen["sha256"])
    for u in read(HERE / "plan.json")["units"]:
        names = frozen["execution_sources"] + [str(p.relative_to(ROOT)) for p in unit_paths(u)]
        bindings = {n: frozen["sha256"][n] for n in names}
        verify(bindings)
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
        assert available >= 5 * 1024**3
        folder = HERE / "runs" / u["unit_id"]
        folder.mkdir(parents=True, exist_ok=False)
        bindings[str((HERE / "input-seal.json").relative_to(ROOT))] = digest(
            HERE / "input-seal.json"
        )
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
            u["unit_id"],
        ]
        save(
            folder / "launch.json",
            dict(command=command, sha256=bindings, available_bytes=available),
        )
        with (folder / "terminal.log").open("x") as f:
            result = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
        save(folder / "exit.json", dict(exit_code=result.returncode))
        verify(bindings)
        for p in folder.iterdir():
            if p.is_file():
                bindings[str(p.relative_to(ROOT))] = digest(p)
        save(folder / "seal.json", dict(sha256=bindings))
        print(u["unit_id"], "exit", result.returncode, flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    {"prepare": prepare, "launch": launch}[sys.argv[1]]()
