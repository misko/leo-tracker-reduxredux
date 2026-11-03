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


def choose(current_time, current_score, grid, scores):
    k = int(np.argmax(scores))
    return (
        (float(grid[k]), float(scores[k] - current_score))
        if scores[k] > current_score + 1e-7
        else (float(current_time), 0.0)
    )


def main(ds):
    started = time.monotonic()
    for name, h in read(HERE / "manifest.json")["hashes"].items():
        assert sha(ROOT / name) == h, name
    budget = module("budget", REPORTS / "2026_09_29_scan_budget/run.py")
    held = module("held", REPORTS / "2026_09_29_curvature_scan_holdout/run.py")
    helper = budget.helper
    manifest = read(REPORTS / "2026_09_29_scan_budget/manifest.json")
    prior = read(REPORTS / f"2026_09_29_scan_budget/{ds}_n24_0.json")
    wide = read(REPORTS / f"2026_09_29_wide_start_audit/{ds}.json")
    pool = next(s for s in manifest["sets"] if s["dataset"] == ds and s["count"] == 24)
    docs = helper.baseline.load_documents(
        dict(config=manifest["config"], inputs=[s["input"] for s in pool["scans"]])
    )
    assert [d["session_id"] for d in docs] == prior["sessions"]

    def model(documents):
        return helper.TrendMixturePosition(
            documents, manifest["config"], helper.baseline.Stationary, 0.2
        )

    train = model(docs)
    singles = [model([d]) for d in docs]
    grid = np.array(manifest["config"]["timing_grid_s"])
    old = prior["selected"]
    bestwide = max(
        (c["fit"] for c in wide["cases"] if c.get("fit", {}).get("qualified")),
        key=lambda r: r["score"],
    )
    arms = []
    for name, endpoint in (("original", old), ("wide", bestwide)):
        x = np.array(endpoint["x"])
        initial = train.evaluate(x, gradient=False)["score"]
        assert endpoint["qualified"] and abs(initial - endpoint["score"]) < 1e-7
        selected = x.copy()
        changes = []
        for i, one in enumerate(singles):
            current = one.evaluate([*x[:2], x[i + 2]], gradient=False)["score"]
            scores, _ = budget.training_scores(one, x[:2], grid)
            k = int(np.argmax(scores))
            assert abs(one.evaluate([*x[:2], grid[k]], gradient=False)["score"] - scores[k]) < 1e-7
            selected[i + 2], gain = choose(x[i + 2], current, grid, scores)
            if gain:
                changes.append(
                    dict(
                        session_id=docs[i]["session_id"],
                        before=float(x[i + 2]),
                        after=float(selected[i + 2]),
                        gain=gain,
                    )
                )
        reseed = train.evaluate(selected, gradient=False)["score"]
        assert abs(reseed - initial - sum(c["gain"] for c in changes)) < 1e-7
        fitted = helper.fit_model(train, selected) if changes else dict(endpoint)
        fitted["estimate_deg"] = list(train.models[0].coordinates(fitted["x"][:3]))
        arms.append(
            dict(
                name=name,
                initial=endpoint,
                changes=changes,
                initial_score=initial,
                reseed_score=reseed,
                fit=fitted,
            )
        )
    candidates = [dict(old, name="baseline")] + [
        dict(a["fit"], name=a["name"]) for a in arms if a["fit"]["qualified"]
    ]
    best = max(candidates, key=lambda r: r["score"])
    improved = best["score"] > old["score"] + 1e-6
    targets = []
    with (HERE / f"{ds}.source.json").open("x") as out:
        json.dump(dict(arms=arms, best=best, improved=improved), out, indent=2, allow_nan=False)
    if improved:
        outside = read(REPORTS / "2026_09_29_out_of_pool/manifest.json")
        for target in (r for r in outside["sets"] if r["dataset"] == ds):
            assert target["input"]["session_id"] not in prior["sessions"]
            previous = read(REPORTS / f"2026_09_29_out_of_pool/{target['unit']}.json")
            assert previous["manifest_sha256"] == sha(
                REPORTS / "2026_09_29_out_of_pool/manifest.json"
            )
            assert previous["values"][1]["qualified"]
            test = model(
                helper.baseline.load_documents(
                    dict(config=manifest["config"], inputs=[target["input"]])
                )
            )
            score = held.marginal(test, best["x"][:2])
            targets.append(
                dict(
                    unit=target["unit"],
                    score=score,
                    delta=score["log_score"] - previous["values"][1]["log_score"],
                )
            )
    with (HERE / f"{ds}.json").open("x") as out:
        json.dump(
            dict(
                dataset=ds,
                arms=arms,
                best=best,
                improved=improved,
                targets=targets,
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
            (a["name"], len(a["changes"]), a["fit"]["score"] - old["score"], a["fit"]["qualified"])
            for a in arms
        ],
        flush=True,
    )


if __name__ == "__main__":
    main(sys.argv[1])
