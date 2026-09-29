"""Freeze and execute candidate-ID-only support census."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / "2026_09_29_drift_position"
PYTHON = ROOT / ".venv/bin/python"


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


def prepare():
    command = [
        str(PYTHON),
        "-m",
        "unittest",
        "discover",
        "-s",
        str(HERE),
        "-p",
        "test_support.py",
        "-v",
    ]
    with (HERE / "tests.log").open("x") as f:
        result = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    save(HERE / "test-receipt.json", dict(command=command, exit_code=result.returncode))
    assert result.returncode == 0
    old = read(PRIOR / "fixed-plan.json")
    units = [u for u in old["units"] if u["unit_id"].endswith("_8")]
    assert len(units) == 9
    evidence = read(PRIOR / "evidence-sha256.json")["sha256"]
    paths = [ROOT / old["coherence"], PRIOR / "fixed-plan.json"]
    for u in units:
        paths += [ROOT / u["baseline_held"]]
        paths += [Path(a["path"]) for i in u["group"]["inputs"] for a in i["artifacts"]]
    bindings = {}
    for p in paths:
        n = str(p.relative_to(ROOT))
        assert digest(p) == evidence[n], n
        bindings[n] = evidence[n]
    save(HERE / "plan.json", dict(units=units, coherence=old["coherence"], scans=72, pairs=913))
    for p in [PRIOR / "evidence-sha256.json"] + [
        HERE / n
        for n in (
            "study.py",
            "support.py",
            "test_support.py",
            "PROTOCOL.md",
            "plan.json",
            "tests.log",
            "test-receipt.json",
        )
    ]:
        bindings[str(p.relative_to(ROOT))] = digest(p)
    save(HERE / "input-seal.json", {"sha256": bindings})
    print("Frozen", len(bindings), "bindings", flush=True)


def child():
    import numpy as np
    from support import compare

    plan = read(HERE / "plan.json")
    scans = {s["session_id"]: s for s in read(ROOT / plan["coherence"])["scans"]}
    results = []
    for unit in plan["units"]:
        posterior = {
            (r["session_id"], r["track_id"]): r for r in read(ROOT / unit["baseline_held"])["rows"]
        }
        for entry in unit["group"]["inputs"]:
            sid = entry["session_id"]
            source = scans[sid]
            files = entry["artifacts"]
            manifest_path = Path(
                next(
                    a["path"]
                    for a in files
                    if a["kind"] == "candidates" and a["path"].endswith(".json")
                )
            )
            bank_path = Path(next(a["path"] for a in files if a["path"].endswith(".npz")))
            manifest = read(manifest_path)
            assert manifest["session_id"] == sid
            obs_path = Path(next(a["path"] for a in files if a["kind"] == "observations"))
            assert manifest["tracks_sha256"] == "sha256:" + digest(obs_path)
            assert obs_path == ROOT / source["observations"]
            tracks = {}
            with np.load(bank_path, allow_pickle=False) as bank:
                for t in manifest["tracks"]:
                    tid = t["track_id"]
                    r = posterior[sid, tid]
                    ids = bank[f"candidate_ids_{t['index']}"]
                    assert len(ids) == t["candidate_count"]
                    tracks[tid] = {
                        "snapshot": manifest["baseline_snapshot_sha256"],
                        "catalogue_size": manifest["catalogue_size"],
                        "ids": ids.tolist(),
                        "weights": r["weights_given_signal"],
                        "signal_responsibility": r["signal_responsibility"],
                    }
                    compare(tracks[tid], tracks[tid])
            selected = sorted(
                (p for p in source["pairs"] if p["selected"]), key=lambda p: (p["rx0"], p["rx1"])
            )
            assert len({p["rx0"] for p in selected}) == len(selected)
            assert len({p["rx1"] for p in selected}) == len(selected)
            pairs = []
            for p in selected:
                row = {k: p[k] for k in ("rx0", "rx1", "channel", "rf_hz")}
                row["actual"] = (
                    compare(tracks[p["rx0"]], tracks[p["rx1"]])
                    if p["rx0"] in tracks and p["rx1"] in tracks
                    else None
                )
                row["missing_tracks"] = [p[k] for k in ("rx0", "rx1") if p[k] not in tracks]
                group = [
                    q for q in selected if q["channel"] == p["channel"] and q["rf_hz"] == p["rf_hz"]
                ]
                other = group[(group.index(p) + 1) % len(group)]["rx1"] if len(group) > 1 else None
                row["control_rx1"] = other
                row["control"] = (
                    compare(tracks[p["rx0"]], tracks[other])
                    if other in tracks and p["rx0"] in tracks
                    else None
                )
                row["control_reason"] = (
                    "singleton"
                    if other is None
                    else "missing_bank"
                    if row["control"] is None
                    else "available"
                )
                pairs.append(row)
            results.append(
                dict(dataset=source["dataset"], session_id=sid, tracks=tracks, pairs=pairs)
            )
    assert len(results) == plan["scans"] and len({s["session_id"] for s in results}) == 72
    assert sum(len(s["pairs"]) for s in results) == plan["pairs"]
    save(HERE / "result.json", {"scans": results})
    print("Completed 72 scans and 913 pairs", flush=True)


def launch():
    bindings = read(HERE / "input-seal.json")["sha256"]
    bindings[str((HERE / "input-seal.json").relative_to(ROOT))] = digest(HERE / "input-seal.json")
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
        "OMP_NUM_THREADS=1",
        str(PYTHON),
        str(HERE / "study.py"),
        "child",
    ]
    save(HERE / "launch.json", dict(command=command, available_bytes=available))
    with (HERE / "terminal.log").open("x") as f:
        result = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    save(HERE / "exit.json", {"exit_code": result.returncode})
    verify(bindings)
    for n in ("result.json", "resources.txt", "launch.json", "terminal.log", "exit.json"):
        p = HERE / n
        if p.exists():
            bindings[str(p.relative_to(ROOT))] = digest(p)
    save(HERE / "seal.json", {"sha256": bindings})
    print("Exit", result.returncode, flush=True)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    {"prepare": prepare, "launch": launch, "child": child}[sys.argv[1]]()
