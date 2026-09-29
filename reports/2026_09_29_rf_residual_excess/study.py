"""Freeze and execute a cross-band residual-excess diagnostic."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / "2026_09_29_donor_residual_transfer"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"


def read(p):
    return json.loads(p.read_text())


def save(p, d):
    with p.open("x") as f:
        json.dump(d, f, indent=2, allow_nan=False)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify(bindings):
    for n, h in bindings.items():
        assert digest(ROOT / n) == h, n


def prepare():
    command = [
        str(ROOT / ".venv/bin/python"),
        "-m",
        "unittest",
        "discover",
        "-s",
        str(HERE),
        "-p",
        "test_model.py",
        "-v",
    ]
    with (HERE / "tests.log").open("x") as f:
        r = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    assert r.returncode == 0
    sourcecommand = ["sudo", "-n", "timeout", "90s", PYTHON, str(HERE / "source_audit.py")]
    with (HERE / "source-audit.log").open("x") as f:
        s = subprocess.run(sourcecommand, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    assert s.returncode == 0
    save(
        HERE / "test-receipt.json",
        dict(
            command=command,
            exit_code=r.returncode,
            source_command=sourcecommand,
            source_exit_code=s.returncode,
        ),
    )
    units = read(PRIOR / "plan.json")["units"]
    save(HERE / "plan.json", dict(units=units))
    evidence = read(PRIOR / "evidence-sha256.json")["sha256"]
    bindings = {}
    paths = [PRIOR / "plan.json", PRIOR / "residual.py"] + [
        PRIOR / "runs" / u["unit_id"] / "result.json" for u in units
    ]
    for p in paths:
        n = str(p.relative_to(ROOT))
        h = digest(p)
        assert h == evidence[n], n
        bindings[n] = h
    exporter = ROOT / "tools/ds7_export_baseline.py"
    bindings[str(exporter.relative_to(ROOT))] = digest(exporter)
    for p in HERE.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            bindings[str(p.relative_to(ROOT))] = digest(p)
    save(HERE / "input-seal.json", dict(sha256=bindings))
    print("Frozen residual-excess model, inputs and source audit", flush=True)


def child():
    from model import Evidence

    sys.path.insert(0, str(PRIOR))
    from residual import errors

    donors = []
    targets = []
    for u in read(HERE / "plan.json")["units"]:
        cases = read(PRIOR / "runs" / u["unit_id"] / "result.json")["cases"]
        (donors if u["role"] == "donor" else targets).extend(cases)
    real = Evidence(donors)
    shuffled = Evidence(donors, True)
    rows = []
    for t in targets:
        p = real.predict(t)
        s = shuffled.predict(t)
        assert (p is None) == (s is None)
        r = {k: t[k] for k in ("unit_id", "session_id", "track_id", "number")}
        r["matched"] = p is not None
        if p:
            slopes = dict(
                zero=0.0,
                rf=p["rf_slope"],
                candidate=p["total_slope"],
                shuffled=p["rf_slope"] + s["excess_slope"],
            )
            r.update(
                real=p,
                shuffle=s,
                slopes=slopes,
                errors={arm: errors(t, v) for arm, v in slopes.items()},
            )
        rows.append(r)
    save(
        HERE / "result.json",
        dict(
            rows=rows,
            donor_cases=len(donors),
            target_cases=len(targets),
            rotated_cases=shuffled.rotated_cases,
            unchanged_label_cases=shuffled.unchanged_labels,
        ),
    )
    print("Matched", sum(r["matched"] for r in rows), "of", len(rows), "eligible cases", flush=True)


def launch():
    bindings = read(HERE / "input-seal.json")["sha256"]
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
        str(ROOT / ".venv/bin/python"),
        str(HERE / "study.py"),
        "child",
    ]
    save(HERE / "launch.json", dict(command=command, available_bytes=available))
    with (HERE / "terminal.log").open("x") as f:
        r = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    save(HERE / "exit.json", dict(exit_code=r.returncode))
    verify(bindings)
    for p in HERE.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            bindings[str(p.relative_to(ROOT))] = digest(p)
    save(HERE / "seal.json", dict(sha256=bindings))
    assert r.returncode == 0
    print("Residual-excess child completed", flush=True)


if __name__ == "__main__":
    {"prepare": prepare, "launch": launch, "child": child}[sys.argv[1]]()
