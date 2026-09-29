"""Freeze and run independent donor-only q020 fits."""

import importlib.util
import math
import subprocess
import sys
from pathlib import Path

from grouping import groups

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RECURRENCE = HERE.parent / "2026_09_29_catalogue_recurrence"
PROFILE = HERE.parent / "2026_09_29_spatial_profile"
spec = importlib.util.spec_from_file_location("sealed_launcher", PROFILE / "study.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
read, save, digest, verify = launcher.read, launcher.save, launcher.digest, launcher.verify


def unit_paths(u):
    return [Path(a["path"]) for item in u["group"]["inputs"] for a in item["artifacts"]]


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
        "test_grouping.py",
        "-v",
    ]
    with (HERE / "tests.log").open("x") as f:
        r = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    assert r.returncode == 0
    corecommand = [
        "sudo",
        "-n",
        "env",
        "OPENBLAS_NUM_THREADS=1",
        launcher.PYTHON,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(HERE.parent / "2026_09_29_profile_refinement"),
        "-p",
        "test_core.py",
        "-v",
    ]
    with (HERE / "optimizer-tests.log").open("x") as f:
        c = subprocess.run(corecommand, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    assert c.returncode == 0
    save(
        HERE / "test-receipt.json",
        dict(
            grouping_command=command,
            grouping_exit=r.returncode,
            optimizer_command=corecommand,
            optimizer_exit=c.returncode,
        ),
    )
    full = read(RECURRENCE / "result.json")["scans"]
    targets = read(HERE.parent / "2026_09_29_candidate_transfer_support/result.json")["scans"]
    excluded = {s["session_id"] for s in targets}
    assert len(excluded) == 72
    source = read(RECURRENCE / "plan.json")["groups"]
    inputs = {item["session_id"]: item for g in source for item in g["inputs"]}
    units = []
    for index, members in enumerate(groups(full, excluded)):
        end = 0
        unitinputs = [inputs[s["session_id"]] for s in members]
        for item in unitinputs:
            obs = read(
                Path(next(a["path"] for a in item["artifacts"] if a["kind"] == "observations"))
            )
            end = max(
                end, obs["start_utc_ns"] + math.ceil(max(max(t["times_s"]) for t in obs["tracks"]) * 1e9)
            )
        units.append(
            dict(
                unit_id=f"{members[0]['dataset']}_donor_{index:02d}",
                available_utc_ns=end,
                group=dict(
                    inputs=unitinputs,
                    session_ids=[s["session_id"] for s in members],
                    size=len(members),
                ),
            )
        )
    assert len(units) == 25 and sum(u["group"]["size"] for u in units) == 186
    assert not excluded & {sid for u in units for sid in u["group"]["session_ids"]}
    config = read(PROFILE / "plan.json")["config"]
    save(HERE / "plan.json", dict(config=config, units=units, target_session_ids=sorted(excluded)))
    inherited = read(RECURRENCE / "evidence-sha256.json")["sha256"]
    paths = [p for u in units for p in unit_paths(u)]
    paths += [
        RECURRENCE / "result.json",
        RECURRENCE / "rosters.json",
        RECURRENCE / "plan.json",
        HERE.parent / "2026_09_29_candidate_transfer_support/result.json",
    ]
    bindings = {}
    for p in paths:
        n = str(p.relative_to(ROOT))
        h = digest(p)
        assert h == inherited[n], n
        bindings[n] = h
    prior = read(HERE.parent / "2026_09_29_profile_refinement/evidence-sha256.json")["sha256"]
    external = [
        PROFILE / "study.py",
        PROFILE / "plan.json",
        HERE.parent / "2026_09_29_profile_refinement/core.py",
        HERE.parent / "2026_09_29_profile_refinement/test_core.py",
        ROOT / "tools/ds7_baseline_adapter.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        HERE.parent / "2026_09_29_frequency_contrast/contrast_position.py",
        HERE.parent / "2026_09_29_unassociated_trend/trend_mixture.py",
    ]
    for p in external:
        n = str(p.relative_to(ROOT))
        h = digest(p)
        assert h == prior[n], n
        bindings[n] = h
    sources = external + [p for p in HERE.iterdir() if p.is_file()]
    for p in sources:
        bindings[str(p.relative_to(ROOT))] = digest(p)
    save(
        HERE / "input-seal.json",
        dict(sha256=bindings, execution_sources=[str(p.relative_to(ROOT)) for p in sources]),
    )
    print("Frozen 25 groups, 186 donor scans, 72 excluded target scans", flush=True)


def launch():
    launcher.HERE = HERE
    launcher.unit_paths = unit_paths
    launcher.launch()


if __name__ == "__main__":
    {"prepare": prepare, "launch": launch}[sys.argv[1]]()
