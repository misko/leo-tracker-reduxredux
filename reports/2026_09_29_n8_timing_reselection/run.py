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


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main(ds):
    started = time.monotonic()
    for name, h in read(HERE / "manifest.json")["hashes"].items():
        assert sha(ROOT / name) == h, name
    budget = module("budget", REPORTS / "2026_09_29_scan_budget/run.py")
    reselection = module("reselection", REPORTS / "2026_09_29_timing_reselection/run.py")
    held = module("held", REPORTS / "2026_09_29_curvature_scan_holdout/run.py")
    helper = budget.helper
    manifest = read(REPORTS / "2026_09_29_scan_budget/manifest.json")
    outside = read(REPORTS / "2026_09_29_out_of_pool/manifest.json")
    pool = next(s for s in manifest["sets"] if s["dataset"] == ds and s["count"] == 24)
    grid = np.array(manifest["config"]["timing_grid_s"])

    def model(documents):
        return helper.TrendMixturePosition(
            documents, manifest["config"], helper.baseline.Stationary, 0.2
        )

    results = []
    for window in ("early", "middle", "late"):
        old = read(REPORTS / f"2026_09_29_time_balanced_scans/grid_{ds}_contiguous_{window}.json")
        docs = helper.baseline.load_documents(
            dict(
                config=manifest["config"],
                inputs=[s["input"] for s in pool["scans"] if s["window"] == window],
            )
        )
        assert [d["session_id"] for d in docs] == old["sessions"] and len(docs) == 8
        initial = old["selected"]
        assert initial["qualified"]
        train = model(docs)
        x = np.array(initial["x"])
        z = x.copy()
        assert abs(train.evaluate(x, gradient=False)["score"] - initial["score"]) < 1e-7
        changes = []
        for i, doc in enumerate(docs):
            one = model([doc])
            current = one.evaluate([*x[:2], x[i + 2]], gradient=False)["score"]
            scores, _ = budget.training_scores(one, x[:2], grid)
            k = int(np.argmax(scores))
            assert abs(one.evaluate([*x[:2], grid[k]], gradient=False)["score"] - scores[k]) < 1e-7
            z[i + 2], gain = reselection.choose(x[i + 2], current, grid, scores)
            if gain:
                changes.append(
                    dict(
                        session_id=doc["session_id"],
                        before=float(x[i + 2]),
                        after=float(z[i + 2]),
                        gain=gain,
                    )
                )
        seeded = train.evaluate(z, gradient=False)["score"]
        assert abs(seeded - initial["score"] - sum(c["gain"] for c in changes)) < 1e-7
        fit = helper.fit_model(train, z) if changes else dict(initial)
        fit["estimate_deg"] = list(train.models[0].coordinates(fit["x"][:3]))
        improved = fit["qualified"] and fit["score"] > initial["score"] + 1e-6
        result = dict(
            dataset=ds,
            window=window,
            initial=initial,
            changes=changes,
            reseed_score=seeded,
            fit=fit,
            improved=bool(improved),
            targets=[],
        )
        with (HERE / f"{ds}_{window}.source.json").open("x") as out:
            json.dump(result, out, indent=2, allow_nan=False)
        if improved:
            for target in (r for r in outside["sets"] if r["dataset"] == ds):
                assert target["input"]["session_id"] not in {
                    s["input"]["session_id"] for s in pool["scans"]
                }
                test = model(
                    helper.baseline.load_documents(
                        dict(config=manifest["config"], inputs=[target["input"]])
                    )
                )
                before = held.marginal(test, x[:2])
                after = held.marginal(test, fit["x"][:2])
                result["targets"].append(
                    dict(
                        unit=target["unit"],
                        before=before,
                        after=after,
                        delta=after["log_score"] - before["log_score"],
                    )
                )
        with (HERE / f"{ds}_{window}.json").open("x") as out:
            json.dump(result, out, indent=2, allow_nan=False)
        results.append(result)
    with (HERE / f"{ds}.json").open("x") as out:
        json.dump(
            dict(
                dataset=ds,
                results=results,
                elapsed_seconds=time.monotonic() - started,
                manifest_sha256=sha(HERE / "manifest.json"),
            ),
            out,
            indent=2,
            allow_nan=False,
        )
    print(
        ds,
        [
            (
                r["window"],
                len(r["changes"]),
                r["fit"]["score"] - r["initial"]["score"],
                r["improved"],
            )
            for r in results
        ],
        flush=True,
    )


if __name__ == "__main__":
    main(sys.argv[1])
