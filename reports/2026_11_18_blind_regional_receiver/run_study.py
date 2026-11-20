"""Freeze inputs and run a stateless Linux namespace per query. Run with the repo venv."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
LOCKS = ROOT / "locks"
PREDS = ROOT / "predictions"
PANELS = {"synthetic": "holdout_private", "recorded": "recorded_private",
          "field": "field_private", "field2": "field2_private"}
ENGINE = ["__init__.py", "grid.py", "receiver.py"]
SCIENCE = ["leo/sky/frames.py", "leo/sky/propagation.py", "leo/sky/sampling.py",
           "leo/contracts/base.py", "leo/contracts/digests.py", "leo/contracts/sky.py"]
ARMS = ["plus", "minus", "reverse"]
HEX = re.compile(r"[0-9a-f]{64}")
ID = re.compile(r"[A-Za-z0-9_-]{1,128}")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def packed(value):
    serialized = json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))
    return (serialized + "\n").encode()


def read(path):
    return json.loads(path.read_bytes())


def save(path, value, *, replace=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = packed(value)
    with NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        tmp = Path(handle.name)
        handle.write(data)
    try:
        if replace:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def timestamp():
    return datetime.now(UTC).isoformat()


def sources():
    files = {f"engine/{name}": ROOT / "engine" / name for name in ENGINE}
    files.update({f"science/{name}": REPO / "src" / name for name in SCIENCE})
    for name in ["blind_worker.py", "run_study.py", "study-protocol.json"]:
        files[name] = ROOT / name
    return files


def runtime():
    return {
        "python": sys.version,
        "interpreter_sha256": sha(Path(sys.executable).resolve().read_bytes()),
        "packages": {name: {"version": dist.version,
                            "record_sha256": sha(dist.read_text("RECORD").encode())}
                     for name in ("numpy", "sgp4", "pydantic", "pydantic-core")
                     for dist in [metadata.distribution(name)]},
        "files": {name: sha(path.read_bytes()) for name, path in sources().items()},
    }


def freeze():
    path = LOCKS / "engine.json"
    current = runtime()
    if not path.exists():
        save(path, {"timestamp": timestamp(), "sha256": sha(packed(current)), "contents": current})
    locked = read(path)
    if locked["sha256"] != sha(packed(current)):
        raise RuntimeError("engine/runtime changed since freeze")
    return locked["sha256"]


def one_query(public, qid):
    if not isinstance(qid, str) or not ID.fullmatch(qid):
        raise ValueError("unsafe or invalid query ID")
    qpath = public / "queries" / f"{qid}.json"
    q = read(qpath)
    if q["id"] != qid or not all(HEX.fullmatch(q[k]) for k in ("observation", "catalog")):
        raise ValueError("invalid content reference")
    paths = {"query.json": qpath,
             "observation.json": public / "observations" / (q["observation"] + ".json"),
             "orbits.tle": public / "orbits" / (q["catalog"] + ".tle")}
    if any(p.resolve() != p for p in paths.values()):
        raise ValueError("unexpected link in input tree")
    return paths


def panel_snapshot(panel):
    public = ROOT / f"public_{panel}"
    manifest = public / "manifest.json"
    ids = read(manifest)["queries"]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("manifest requires unique query IDs")
    files = {manifest: sha(manifest.read_bytes())}
    for qid in ids:
        for name, path in one_query(public, qid).items():
            if path not in files:
                files[path] = sha(path.read_bytes())
            if name != "query.json" and files[path] != path.stem:
                raise ValueError("content address mismatch")
    fingerprint = {str(p.relative_to(public)): digest for p, digest in files.items()}
    return {"public_sha256": sha(packed(fingerprint)), "truth_sha256": sha(
                (ROOT / PANELS[panel] / "truth.json").read_bytes()),
            "query_count": len(ids), "files": fingerprint}, ids


def seal(panel):
    state, ids = panel_snapshot(panel)
    path = LOCKS / f"{panel}.json"
    if not path.exists():
        save(path, {"timestamp": timestamp(), **state})
    locked = read(path)
    if any(locked[key] != value for key, value in state.items()):
        raise RuntimeError(f"{panel} changed since sealing")
    return state, ids


def bindings():
    interp = Path(sys.executable).resolve()
    base = interp.parents[1]
    libs = Path(sysconfig.get_paths()["purelib"]).resolve()
    cmd = [shutil.which("bwrap") or "/usr/bin/bwrap", "--die-with-parent", "--unshare-all",
           "--new-session", "--clearenv", "--ro-bind", "/usr", "/usr",
           "--symlink", "usr/bin", "/bin",
           "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
           "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
           "--ro-bind", str(base), "/runtime", "--ro-bind", str(libs), "/packages"]
    for directory in ["/input", "/code", "/code/engine", "/science", "/science/leo",
                      "/science/leo/contracts", "/science/leo/sky"]:
        cmd += ["--dir", directory]
    for name in ENGINE:
        cmd += ["--ro-bind", str(ROOT / "engine" / name), f"/code/engine/{name}"]
    for name in SCIENCE:
        cmd += ["--ro-bind", str(REPO / "src" / name), f"/science/{name}"]
    cmd += ["--ro-bind", str(ROOT / "blind_worker.py"), "/code/worker.py"]
    threads = ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]
    for name in threads:
        cmd += ["--setenv", name, "1"]
    return cmd, "/runtime/" + str(interp.relative_to(base))


def dispatch(paths, arm):
    cmd, exe = bindings()
    for name, path in paths.items():
        cmd += ["--ro-bind", str(path), "/input/" + name]
    started = perf_counter()
    args = [*cmd, "--chdir", "/tmp", "--", exe, "-I", "-S", "-B", "/code/worker.py", arm]
    completed = subprocess.run(args, capture_output=True, text=True, timeout=600)
    wall = perf_counter() - started
    if completed.returncode != 0:
        msg = f"inference process exited {completed.returncode}: {completed.stderr[-3000:]}"
        raise RuntimeError(msg)
    output = json.loads(completed.stdout)
    output["process_wall_s"] = wall
    return output


def jobs_for(ids, controls):
    if not controls:
        return [(qid, "primary") for qid in ids]
    chosen = sorted(ids, key=lambda q: sha(("invariance-v1/" + q).encode()))[:3]
    return [(qid, arm) for qid in chosen for arm in ARMS]


@contextmanager
def panel_mutex(name):
    PREDS.mkdir(exist_ok=True)
    with (PREDS / f"{name}.runlock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def predict(panel, jobs, controls):
    engine = freeze()
    state, ids = seal(panel)
    schedule = jobs_for(ids, controls)
    stem = panel + ("-checks" if controls else "")
    dest = PREDS / (stem + ".json")
    header = {"engine_sha256": engine, "public_sha256": state["public_sha256"]}
    partial = PREDS / (stem + ".checkpoint.json")
    with panel_mutex(stem):
        if dest.exists():
            doc = read(dest)
            if any(doc[k] != v for k, v in header.items()) or len(doc["cases"]) != len(schedule):
                raise ValueError("finalized prediction document does not match request")
            return
        old = read(partial) if partial.exists() else {**header, "cases": []}
        if any(old[k] != v for k, v in header.items()):
            raise RuntimeError("checkpoint has different inputs")
        done = {(row["id"], row["arm"]): row for row in old["cases"]}
        public = ROOT / f"public_{panel}"
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            todo = {pool.submit(dispatch, one_query(public, q), a): (q, a)
                    for q, a in schedule if (q, a) not in done}
            for future in as_completed(todo):
                qid, arm = todo[future]
                result = future.result()
                if result["id"] != qid:
                    raise ValueError("wrong query result")
                done[qid, arm] = dict(result, arm=arm)
                save(partial, {**header, "cases": list(done.values())}, replace=True)
                if len(done) % 10 == 0:
                    print(f"{stem}: {len(done)}/{len(schedule)} completed", flush=True)
        if freeze() != engine or seal(panel)[0] != state:
            raise RuntimeError("inputs changed during processing")
        save(dest, {**header, "cases": [done[key] for key in schedule]})
        partial.unlink(missing_ok=True)
        print(f"{stem}: {len(schedule)} frozen outputs", flush=True)


def commit(panels):
    engine = freeze()
    results = {}
    for panel in sorted(panels):
        state, ids = seal(panel)
        for controls in [False, True]:
            path = PREDS / (panel + ("-checks" if controls else "") + ".json")
            doc = read(path)
            if (doc["engine_sha256"] != engine or doc["public_sha256"] != state["public_sha256"]
                    or [(r["id"], r["arm"]) for r in doc["cases"]] != jobs_for(ids, controls)):
                raise ValueError("incomplete or mismatched predictions")
            results[path.name] = sha(path.read_bytes())
        results[f"locks/{panel}.json"] = sha((LOCKS / f"{panel}.json").read_bytes())
    results["locks/engine.json"] = sha((LOCKS / "engine.json").read_bytes())
    for name in ["score.py", "METRICS.md"]:
        results[f"evaluation/{name}"] = sha((ROOT / "evaluation" / name).read_bytes())
    path = LOCKS / "prediction-lock.json"
    if not path.exists():
        save(path, {"timestamp": timestamp(), "panels": sorted(panels), "sha256": results})
    previous = read(path)
    if previous["sha256"] != results or previous["panels"] != sorted(panels):
        raise RuntimeError("predictions or scoring specification changed since commitment")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("probe")
    sub.add_parser("freeze")
    for name in ["seal", "predict", "checks"]:
        cmd = sub.add_parser(name)
        cmd.add_argument("panel", choices=PANELS)
        if name != "seal":
            cmd.add_argument("--jobs", type=int, default=2)
    sub.add_parser("commit").add_argument("panels", choices=PANELS, nargs="+")
    args = parser.parse_args()
    if args.operation == "probe":
        print(dispatch({}, "probe"))
    elif args.operation == "freeze":
        print(freeze())
    elif args.operation == "seal":
        state, _ = seal(args.panel)
        print(f"{args.panel}: {state['query_count']} sealed queries")
    elif args.operation == "commit":
        commit(args.panels)
        print("All predictions and scoring code committed.")
    else:
        if args.jobs < 1:
            parser.error("jobs must be positive")
        predict(args.panel, args.jobs, args.operation == "checks")


if __name__ == "__main__":
    main()
