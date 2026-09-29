"""Freeze a metadata-only candidate support census over 72 distinct scans."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / "2026_09_29_spatial_profile"


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
        sys.executable,
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
    plan = read(PRIOR / "plan.json")
    units = [u for u in plan["units"] if u["group"]["size"] == 8]
    assert len(units) == 9
    save(HERE / "plan.json", dict(units=units))
    old = read(PRIOR / "evidence-sha256.json")["sha256"]
    bindings = {}
    paths = [PRIOR / "plan.json", ROOT / "tools/ds7_export_baseline.py"]
    for u in units:
        paths.append(ROOT / u["baseline_held"])
        paths.extend(Path(a["path"]) for i in u["group"]["inputs"] for a in i["artifacts"])
    for p in paths:
        n = str(p.relative_to(ROOT))
        h = digest(p)
        if n in old:
            assert h == old[n], n
        else:
            assert n == "tools/ds7_export_baseline.py"
        bindings[n] = h
    for p in HERE.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = digest(p)
    save(HERE / "input-seal.json", dict(sha256=bindings))
    print("Frozen nine panels, 72 distinct scans", flush=True)


def child():
    import numpy as np
    from support import census

    scans = []
    for u in read(HERE / "plan.json")["units"]:
        posterior = {
            (r["session_id"], r["track_id"]): r for r in read(ROOT / u["baseline_held"])["rows"]
        }
        for item in u["group"]["inputs"]:
            obs = read(
                Path(next(a["path"] for a in item["artifacts"] if a["kind"] == "observations"))
            )
            mpath = Path(
                next(
                    a["path"]
                    for a in item["artifacts"]
                    if a["kind"] == "candidates" and a["path"].endswith(".json")
                )
            )
            m = read(mpath)
            assert m["session_id"] == obs["session_id"] == item["session_id"]
            assert m["tracks_sha256"] == "sha256:" + digest(
                Path(next(a["path"] for a in item["artifacts"] if a["kind"] == "observations"))
            )
            tracks = {t["track_id"]: t for t in obs["tracks"]}
            rows = []
            bankpath = Path(
                next(a["path"] for a in item["artifacts"] if a["path"].endswith(".npz"))
            )
            with np.load(bankpath, allow_pickle=False) as bank:
                for t in m["tracks"]:
                    o = tracks[t["track_id"]]
                    p = posterior[item["session_id"], t["track_id"]]
                    ids = bank[f"candidate_ids_{t['index']}"].tolist()
                    weights = p["weights_given_signal"]
                    assert len(ids) == len(weights) == t["candidate_count"] and len(
                        set(ids)
                    ) == len(ids)
                    assert all(isinstance(i, int) and 0 <= i < m["catalogue_size"] for i in ids)
                    assert min(weights) >= 0 and abs(sum(weights) - 1) < 1e-8
                    assert 0 <= p["signal_responsibility"] <= 1
                    rows.append(
                        dict(
                            track_id=t["track_id"],
                            ids=ids,
                            weights=weights,
                            signal_responsibility=p["signal_responsibility"],
                            receiver_id=o["receiver_id"],
                            rf_hz=o["rf_hz"],
                        )
                    )
            scans.append(
                dict(
                    session_id=item["session_id"],
                    panel=u["unit_id"],
                    start_utc_ns=obs["start_utc_ns"],
                    snapshot=m["baseline_snapshot_sha256"],
                    catalogue_size=m["catalogue_size"],
                    provider_sources=m["provider_sources"],
                    tracks=rows,
                )
            )
    assert len(scans) == 72 and sum(len(s["tracks"]) for s in scans) == 4328
    save(HERE / "result.json", dict(scans=scans, rows=census(scans)))
    print("Censused 4328 tracks across 72 scans", flush=True)


def launch():
    bindings = read(HERE / "input-seal.json")["sha256"]
    verify(bindings)
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
    save(HERE / "launch.json", dict(command=command, available_bytes=available))
    with (HERE / "terminal.log").open("x") as f:
        r = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    save(HERE / "exit.json", dict(exit_code=r.returncode))
    verify(bindings)
    for p in HERE.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = digest(p)
    save(HERE / "seal.json", dict(sha256=bindings))
    assert r.returncode == 0
    print("Census child exited zero", flush=True)


if __name__ == "__main__":
    {"prepare": prepare, "child": child, "launch": launch}[sys.argv[1]]()
