"""Freeze fixed-point residual exports; reuse the bounded sequential launcher."""

import importlib.util
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DONOR = HERE.parent / "2026_09_29_donor_weights"
PROFILE = HERE.parent / "2026_09_29_spatial_profile"
RECURRENCE = HERE.parent / "2026_09_29_catalogue_recurrence"
spec = importlib.util.spec_from_file_location("sealed_launcher", PROFILE / "study.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
read, save, digest, verify = launcher.read, launcher.save, launcher.digest, launcher.verify


def unit_paths(u):
    return [ROOT / u["posterior"]] + [
        Path(a["path"]) for item in u["group"]["inputs"] for a in item["artifacts"]
    ]


def prepare():
    command = [
        "sudo",
        "-n",
        "env",
        "OPENBLAS_NUM_THREADS=1",
        launcher.PYTHON,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(HERE),
        "-p",
        "test_residual.py",
        "-v",
    ]
    with (HERE / "tests.log").open("x") as f:
        r = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    assert r.returncode == 0
    save(HERE / "test-receipt.json", dict(command=command, exit_code=r.returncode))
    donor = read(DONOR / "plan.json")
    units = []
    for u in donor["units"]:
        p = DONOR / "runs" / u["unit_id"] / "result.json"
        fit = read(p)
        assert fit["selected"] is not None
        units.append(
            dict(
                **u,
                role="donor",
                x=fit["selected"]["x"],
                posterior=str(p.relative_to(ROOT)),
                training_score=fit["selected"]["score"],
            )
        )
    for u in read(PROFILE / "plan.json")["units"]:
        if u["group"]["size"] != 8:
            continue
        p = ROOT / u["baseline_held"]
        units.append(
            dict(
                unit_id=u["unit_id"],
                group=u["group"],
                role="target",
                x=u["x"],
                posterior=u["baseline_held"],
                training_score=read(p)["training_log_score"],
                available_utc_ns=None,
            )
        )
    assert len(units) == 34
    save(HERE / "plan.json", dict(config=donor["config"], units=units))
    inherited = {}
    for parent in (DONOR, PROFILE, RECURRENCE):
        for n, h in read(parent / "evidence-sha256.json")["sha256"].items():
            assert n not in inherited or inherited[n] == h
            inherited[n] = h
    paths = [p for u in units for p in unit_paths(u)]
    external = [
        PROFILE / "study.py",
        DONOR / "plan.json",
        PROFILE / "plan.json",
        RECURRENCE / "result.json",
        ROOT / "tools/ds7_baseline_adapter.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        HERE.parent / "2026_09_29_frequency_contrast/contrast_position.py",
        HERE.parent / "2026_09_29_unassociated_trend/trend_mixture.py",
    ]
    bindings = {}
    for p in paths + external:
        n = str(p.relative_to(ROOT))
        h = digest(p)
        assert inherited[n] == h, n
        bindings[n] = h
    sources = external + [p for p in HERE.iterdir() if p.is_file()]
    for p in sources:
        bindings[str(p.relative_to(ROOT))] = digest(p)
    save(
        HERE / "input-seal.json",
        dict(sha256=bindings, execution_sources=[str(p.relative_to(ROOT)) for p in sources]),
    )
    print("Frozen 25 donor and 9 target fixed-point exports", flush=True)


def launch():
    launcher.HERE = HERE
    launcher.unit_paths = unit_paths
    launcher.launch()


if __name__ == "__main__":
    {"prepare": prepare, "launch": launch}[sys.argv[1]]()
