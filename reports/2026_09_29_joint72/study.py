import concurrent.futures
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent
REUSED = REPORTS / "2026_09_29_curvature_scan_holdout/run.py"
spec = importlib.util.spec_from_file_location("holdout_runner", REUSED)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def read(p):
    return json.loads(p.read_text())


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(name, data):
    with (HERE / name).open("x") as f:
        json.dump(data, f, indent=2, allow_nan=False)


def prepare():
    poolpath = REPORTS / "2026_09_29_scan_budget/manifest.json"
    targetpath = REPORTS / "2026_09_29_out_of_pool/manifest.json"
    pool, targets = read(poolpath), read(targetpath)
    assert pool["config"] == targets["config"]
    inputs = []
    fits = []
    paths = [
        poolpath,
        targetpath,
        HERE / "study.py",
        HERE / "PROTOCOL.md",
        REUSED,
        REPORTS / "2026_09_29_receiver_holdout/run.py",
        REPORTS / "2026_09_29_scan_holdout/timing.py",
        REPORTS / "2026_09_29_unassociated_trend/trend_mixture.py",
        REPORTS / "2026_09_29_frequency_contrast/contrast_position.py",
        ROOT / "tools/ds7_baseline_adapter.py",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
    ]
    for ds in ("DS7", "DS8", "DS9"):
        p = REPORTS / f"2026_09_29_scan_budget/{ds}_n24_0.json"
        d = read(p)
        paths.append(p)
        assert d["selected"]["qualified"]
        for name, h in d["hashes"].items():
            assert digest(ROOT / name) == h, name
        group = next(s for s in pool["sets"] if s["dataset"] == ds and s["count"] == 24)
        assert [r["session_id"] for r in group["scans"]] == d["sessions"]
        inputs.extend(s["input"] for s in group["scans"])
        fits.append(d["selected"])
    assert len({r["session_id"] for r in inputs}) == 72
    assert not {r["session_id"] for r in inputs} & {
        s["input"]["session_id"] for s in targets["sets"]
    }
    for entry in inputs + [s["input"] for s in targets["sets"]]:
        for artifact in entry["artifacts"]:
            p = Path(artifact["path"])
            assert "sha256:" + digest(p) == artifact["sha256"]
            paths.append(p)
    for s in targets["sets"]:
        paths.append(REPORTS / f"2026_09_29_out_of_pool/{s['unit']}.json")
    mean = np.mean([f["x"][:2] for f in fits], axis=0).tolist()
    times = [t for f in fits for t in f["x"][2:]]
    save(
        "manifest.json",
        dict(
            config=pool["config"],
            inputs=inputs,
            targets=targets["sets"],
            mean_position=mean,
            starts=[[0.0, 0.0] + times, mean + times],
            source_fits=fits,
            hashes={str(p.relative_to(ROOT)): digest(p) for p in paths},
        ),
    )


def verify(m):
    for name, h in m["hashes"].items():
        assert digest(ROOT / name) == h, name


def fit(index):
    started = time.monotonic()
    m = read(HERE / "manifest.json")
    verify(m)
    receiver = helper.receiver
    docs = receiver.baseline.load_documents(dict(config=m["config"], inputs=m["inputs"]))
    model = receiver.TrendMixturePosition(docs, m["config"], receiver.baseline.Stationary, 0.2)
    result = receiver.fit_model(model, np.array(m["starts"][index]))
    result.update(
        estimate_deg=list(model.models[0].coordinates(result["x"][:3])),
        elapsed_seconds=time.monotonic() - started,
        manifest_sha256=digest(HERE / "manifest.json"),
    )
    save(f"fit_{index}.json", result)
    print(index, result["qualified"], result["message"], result["elapsed_seconds"], flush=True)


def select():
    fits = [read(HERE / f"fit_{i}.json") for i in (0, 1) if (HERE / f"fit_{i}.json").exists()]
    valid = [r for r in fits if r["qualified"]]
    if not valid:
        raise RuntimeError("No qualified source fit; do not evaluate targets")
    selected = max(valid, key=lambda r: r["score"])
    save(
        "selected.json",
        dict(
            selected,
            fit_hashes={
                f"fit_{i}.json": digest(HERE / f"fit_{i}.json")
                for i in (0, 1)
                if (HERE / f"fit_{i}.json").exists()
            },
        ),
    )


def target(key):
    started = time.monotonic()
    m = read(HERE / "manifest.json")
    selected = read(HERE / "selected.json")
    row = next(r for r in m["targets"] if r["unit"] == key)
    receiver = helper.receiver
    docs = receiver.baseline.load_documents(dict(config=m["config"], inputs=[row["input"]]))
    model = receiver.TrendMixturePosition(docs, m["config"], receiver.baseline.Stationary, 0.2)
    arms = [helper.marginal(model, p) for p in (selected["x"][:2], m["mean_position"])]
    save(
        f"{key}.json",
        dict(
            unit=key,
            session_id=row["input"]["session_id"],
            arms=arms,
            mean_estimate_deg=list(model.models[0].coordinates([*m["mean_position"], 0])),
            selected_sha256=digest(HERE / "selected.json"),
            manifest_sha256=digest(HERE / "manifest.json"),
            elapsed_seconds=time.monotonic() - started,
        ),
    )
    print(key, [a["qualified"] for a in arms], flush=True)


def batch(mode):
    verify(read(HERE / "manifest.json"))
    jobs = (
        [str(i) for i in (0, 1)]
        if mode == "fit"
        else [r["unit"] for r in read(HERE / "manifest.json")["targets"]]
    )

    def worker(key):
        try:
            p = subprocess.run(
                [sys.executable, str(HERE / "study.py"), mode, key],
                capture_output=True,
                text=True,
                timeout=180 if mode == "fit" else 120,
            )
            r = dict(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
        except subprocess.TimeoutExpired:
            r = dict(exit_code=None, timed_out=True)
        save(f"{mode}_{key}.receipt.json", r)
        print(mode, key, r, flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2 if mode == "fit" else 3) as executor:
        list(executor.map(worker, jobs))


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "fit":
        fit(int(sys.argv[2]))
    elif sys.argv[1] == "select":
        select()
    elif sys.argv[1] == "target":
        target(sys.argv[2])
    elif sys.argv[1] == "batch":
        batch(sys.argv[2])
    else:
        raise ValueError("Unknown command")
