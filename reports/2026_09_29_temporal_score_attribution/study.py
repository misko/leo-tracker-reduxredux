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


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def profiled_contribution(gradient, hessian):
    gradient, hessian = np.asarray(gradient), np.asarray(hessian)
    assert hessian[2, 2] > 0
    return gradient[:2] - hessian[:2, 2] / hessian[2, 2] * gradient[2]


def prepare():
    previous = read(REPORTS / "2026_09_29_scan_disagreement/manifest.json")
    paths = [ROOT / p for p in previous["hashes"]]
    paths.extend(HERE.glob("*.py"))
    paths.append(HERE / "PROTOCOL.md")
    paths.extend(
        REPORTS / f"2026_09_29_scan_disagreement/{ds}.json" for ds in ("DS7", "DS8", "DS9")
    )
    with (HERE / "manifest.json").open("x") as f:
        json.dump(dict(hashes={str(p.relative_to(ROOT)): sha(p) for p in paths}), f, indent=2)


def run(ds):
    started = time.monotonic()
    for name, h in read(HERE / "manifest.json")["hashes"].items():
        assert sha(ROOT / name) == h, name
    spec = importlib.util.spec_from_file_location(
        "receiver", REPORTS / "2026_09_29_receiver_holdout/run.py"
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    manifest = read(REPORTS / "2026_09_29_scan_budget/manifest.json")
    prior = read(REPORTS / f"2026_09_29_scan_budget/{ds}_n24_0.json")
    diagnostic = read(REPORTS / f"2026_09_29_scan_disagreement/{ds}.json")
    pool = next(s for s in manifest["sets"] if s["dataset"] == ds and s["count"] == 24)
    docs = helper.baseline.load_documents(
        dict(config=manifest["config"], inputs=[s["input"] for s in pool["scans"]])
    )
    assert [d["session_id"] for d in docs] == prior["sessions"]
    x = np.array(prior["selected"]["x"])
    rows, audits = [], []
    for di, (doc, old) in enumerate(zip(docs, diagnostic["rows"], strict=True)):
        assert old["session_id"] == doc["session_id"] and old["qualified"]
        local = np.array([*x[:2], x[di + 2]])
        localrows = []
        for track in doc["tracks"]:
            one = helper.TrendMixturePosition(
                [dict(doc, tracks=[track])], manifest["config"], helper.baseline.Stationary, 0.2
            )
            out = one.evaluate(local)
            g = profiled_contribution(out["gradient"], old["hessian"])
            localrows.append(
                dict(
                    session_id=doc["session_id"],
                    track_id=track["track_id"],
                    window=old["window"],
                    receiver=int(track["receiver_id"]),
                    rf_hz=float(track["rf_hz"]),
                    score=out["score"],
                    gradient=out["gradient"].tolist(),
                    profiled_gradient=g.tolist(),
                )
            )
        errors = dict(
            score=abs(sum(r["score"] for r in localrows) - old["score"]),
            gradient=float(
                max(abs(sum(np.array(r["gradient"]) for r in localrows) - old["gradient"]))
            ),
            profiled=float(
                max(
                    abs(
                        sum(np.array(r["profiled_gradient"]) for r in localrows)
                        - old["profiled_gradient"]
                    )
                )
            ),
        )
        assert max(errors.values()) < 1e-7
        audits.append(dict(session_id=doc["session_id"], **errors))
        rows.extend(localrows)
    with (HERE / f"{ds}.json").open("x") as f:
        json.dump(
            dict(
                dataset=ds,
                rows=rows,
                audits=audits,
                elapsed_seconds=time.monotonic() - started,
                manifest_sha256=sha(HERE / "manifest.json"),
            ),
            f,
            indent=2,
            allow_nan=False,
        )
    print(ds, len(rows), time.monotonic() - started, flush=True)


def worker(ds):
    try:
        r = subprocess.run(
            [sys.executable, str(HERE / "study.py"), ds],
            capture_output=True,
            text=True,
            timeout=120,
        )
        receipt = dict(exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr)
    except subprocess.TimeoutExpired:
        receipt = dict(exit_code=None, timed_out=True)
    with (HERE / f"{ds}.receipt.json").open("x") as f:
        json.dump(receipt, f, indent=2)
    print(ds, receipt, flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "batch":
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(worker, ("DS7", "DS8", "DS9")))
    else:
        run(sys.argv[1])
