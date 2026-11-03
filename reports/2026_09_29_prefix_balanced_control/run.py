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
INDICES = [0, 2, 3, 5, 6, 8, 9, 11]


def read(p):
    return json.loads(p.read_text())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def main(ds):
    started = time.monotonic()
    frozen = read(HERE / "manifest.json")
    for name, expected in frozen["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    prefix = read(REPORTS / "2026_09_29_prefix_score_selection/manifest.json")
    unit = next(u for u in prefix["units"] if u["dataset"] == ds)
    config = prefix["config"]
    budget = module("budget", REPORTS / "2026_09_29_scan_budget/run.py")
    held = module("held", REPORTS / "2026_09_29_curvature_scan_holdout/run.py")
    helper = budget.helper
    inputs = [unit["scans"][i]["input"] for i in INDICES]
    docs = helper.baseline.load_documents(dict(config=config, inputs=inputs))

    def model(documents):
        return helper.TrendMixturePosition(documents, config, helper.baseline.Stationary, 0.2)

    train = model(docs)
    singles = [model([d]) for d in docs]
    grid = np.array(config["timing_grid_s"])
    starts = []
    for family in ("cold", "timing_grid"):
        for east in (-2.0, 0.0, 2.0):
            x = np.zeros(10)
            x[0] = east
            if family == "timing_grid":
                for i, single in enumerate(singles):
                    scores, _ = budget.training_scores(single, x[:2], grid)
                    k = int(np.argmax(scores))
                    x[i + 2] = grid[k]
                    assert abs(scores[k] - single.evaluate([east, 0, grid[k]], gradient=False)["score"]) < 1e-7
            starts.append(dict(helper.fit_model(train, x), family=family))
    valid = [s for s in starts if s["qualified"]]
    selected = max(valid, key=lambda s: s["score"]) if valid else None
    if selected:
        selected["estimate_deg"] = list(train.models[0].coordinates(selected["x"][:3]))
    result = dict(dataset=ds, indices=INDICES, sessions=[d["session_id"] for d in docs], starts=starts, selected=selected)
    with (HERE / f"{ds}.source.json").open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
    assert selected is not None, "No qualified source fit"
    prior = read(REPORTS / f"2026_09_29_prefix_score_selection/{ds}.json")
    targets = []
    for target, old in zip(unit["targets"], prior["targets"], strict=True):
        assert target["unit"] == old["unit"]
        assert target["start_utc_ns"] > unit["source_end_utc_ns"]
        assert target["input"]["session_id"] not in result["sessions"]
        test = model(helper.baseline.load_documents(dict(config=config, inputs=[target["input"]])))
        score = held.marginal(test, selected["x"][:2])
        assert all(s["qualified"] for s in old["scores"].values())
        targets.append(dict(unit=target["unit"], score=score, prior_scores=old["scores"]))
    result.update(targets=targets, elapsed_seconds=time.monotonic() - started)
    with (HERE / f"{ds}.json").open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
    print(ds, result["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
