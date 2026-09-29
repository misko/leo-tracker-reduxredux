"""Reuse the sealed sequential launcher; freeze this experiment separately."""

import importlib.util
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / "2026_09_29_spatial_profile"
spec = importlib.util.spec_from_file_location("profile_launcher", PRIOR / "study.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
read, save, digest, verify = launcher.read, launcher.save, launcher.digest, launcher.verify


def prepare():
    prior = read(PRIOR / "evidence-sha256.json")["sha256"]
    verify(prior)
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
        "test_core.py",
        "-v",
    ]
    with (HERE / "tests.log").open("x") as f:
        test = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    save(HERE / "test-receipt.json", dict(command=command, exit_code=test.returncode))
    assert test.returncode == 0
    plan = read(PRIOR / "plan.json")
    save(HERE / "plan.json", plan)
    sources = read(PRIOR / "input-seal.json")["execution_sources"] + [
        str(p.relative_to(ROOT)) for p in sorted(HERE.iterdir()) if p.suffix in (".py", ".md")
    ]
    sources += [str((HERE / "plan.json").relative_to(ROOT))]
    sources += [
        str((PRIOR / "runs" / u["unit_id"] / "result.json").relative_to(ROOT))
        for u in plan["units"]
    ]
    bindings = dict(prior)
    for p in HERE.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = digest(p)
    save(HERE / "input-seal.json", dict(sha256=bindings, execution_sources=sources))
    print("Frozen 18 panels and 36 training-only starts; tests passed", flush=True)


def launch():
    launcher.HERE = HERE
    launcher.launch()


if __name__ == "__main__":
    {"prepare": prepare, "launch": launch}[sys.argv[1]]()
