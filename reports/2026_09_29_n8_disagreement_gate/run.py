import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def read(path):
    return json.loads(path.read_text())


def accept(qualified, scan_m, pair_m):
    return bool(qualified and np.isfinite([scan_m, pair_m]).all() and max(scan_m, pair_m) < 1000)


def main(ds):
    started = time.monotonic()
    for name, h in read(HERE / "manifest.json")["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h, name
    helper = module("receiver", REPORTS / "2026_09_29_receiver_holdout/run.py")
    diag = module("diag", REPORTS / "2026_09_29_scan_disagreement/study.py")
    uncertainty = module("uncertainty", REPORTS / "2026_09_29_scan_uncertainty/study.py")
    manifest = read(REPORTS / "2026_09_29_scan_budget/manifest.json")
    pool = next(s for s in manifest["sets"] if s["dataset"] == ds and s["count"] == 24)
    docs = helper.baseline.load_documents(dict(config=manifest["config"], inputs=[s["input"] for s in pool["scans"]]))
    by_id = {d["session_id"]: d for d in docs}

    def model(items):
        return helper.TrendMixturePosition(items, manifest["config"], helper.baseline.Stationary, 0.2)

    panels = []
    for family, suffixes in [("contiguous", ["early", "middle", "late"]), ("balanced", [0, 1, 2])]:
        for suffix in suffixes:
            name = f"grid_{ds}_{family}_{suffix}.json"
            prior = read(REPORTS / "2026_09_29_time_balanced_scans" / name)
            selected = prior["selected"]
            assert selected["qualified"] and len(prior["sessions"]) == 8
            subset = [by_id[s] for s in prior["sessions"]]
            assert [d["start_utc_ns"] for d in subset] == sorted(d["start_utc_ns"] for d in subset)
            x = np.array(selected["x"])
            original = model(subset).evaluate(x)
            replay = np.zeros_like(x)
            rows = []
            for i, doc in enumerate(subset):
                one = model([doc])
                local = np.array([*x[:2], x[i + 2]])
                out = one.evaluate(local)
                h, asym = diag.curvature(one, local, 1.0)
                ha, aa = diag.curvature(one, local, 0.5)
                discrepancy = float(np.linalg.norm(h - ha) / max(np.linalg.norm(h), 1e-12))
                profiled = diag.profile(h, out["gradient"])
                qualified = profiled is not None and max(asym, aa, discrepancy) < 0.01
                replay[:2] += out["gradient"][:2]
                replay[i + 2] = out["gradient"][2]
                rows.append(dict(session_id=doc["session_id"], score=out["score"], qualified=bool(qualified), discrepancy=discrepancy, asymmetry=max(asym, aa), hessian=None if profiled is None else profiled[0].tolist(), gradient=None if profiled is None else profiled[1].tolist()))
            score_replay = abs(sum(r["score"] for r in rows) - original["score"])
            gradient_replay = float(np.max(np.abs(replay - original["gradient"])))
            saved_replay = abs(original["score"] - selected["score"])
            qualified = all(r["qualified"] for r in rows) and max(score_replay, gradient_replay, saved_replay) < 1e-7
            result = dict(dataset=ds, family=family, panel=str(suffix), source=name, rows=rows, score_replay=score_replay, gradient_replay=gradient_replay, saved_replay=saved_replay, estimate_deg=selected["estimate_deg"], accepted=False)
            if qualified:
                h = sum(np.array(r["hessian"]) for r in rows)
                g = np.array([r["gradient"] for r in rows])
                qualified = bool(np.linalg.eigvalsh(h).min() > 0)
                if qualified:
                    scan = uncertainty.covariance(h, g)
                    pair = uncertainty.covariance(h, g.reshape(4, 2, 2).sum(axis=1))
                    scan_m = float(1000 * np.sqrt(np.trace(scan)))
                    pair_m = float(1000 * np.sqrt(np.trace(pair)))
                    result.update(scan_covariance_km2=scan.tolist(), pair_covariance_km2=pair.tolist(), scan_scale_m=scan_m, pair_scale_m=pair_m, accepted=accept(True, scan_m, pair_m))
            result["qualified"] = qualified
            panels.append(result)
    with (HERE / f"{ds}.json").open("x") as out:
        json.dump(dict(panels=panels, elapsed_seconds=time.monotonic() - started), out, indent=2, allow_nan=False)
    print(ds, [(p["family"], p["panel"], p["qualified"], p["accepted"]) for p in panels], flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
