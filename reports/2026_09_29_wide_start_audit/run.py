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
CORNERS = ((-8.0, -8.0), (-8.0, 8.0), (8.0, -8.0), (8.0, 8.0))


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
    helper = budget.helper
    manifest = read(REPORTS / "2026_09_29_scan_budget/manifest.json")
    prior = read(REPORTS / f"2026_09_29_scan_budget/{ds}_n24_0.json")
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
    old = prior["selected"]
    assert (
        old["qualified"]
        and abs(train.evaluate(old["x"], gradient=False)["score"] - old["score"]) < 1e-7
    )
    grid = np.array(manifest["config"]["timing_grid_s"])
    cases = []
    for index, corner in enumerate(CORNERS):
        began = time.monotonic()
        try:
            x = np.zeros(26)
            x[:2] = corner
            replay = 0.0
            for i, one in enumerate(singles):
                scores, _ = budget.training_scores(one, x[:2], grid)
                k = int(np.argmax(scores))
                x[i + 2] = grid[k]
                replay = max(
                    replay,
                    abs(one.evaluate([*corner, grid[k]], gradient=False)["score"] - scores[k]),
                )
            assert replay < 1e-7
            fit = helper.fit_model(train, x)
            case = dict(
                corner=corner,
                initial=x.tolist(),
                fit=fit,
                grid_replay=replay,
                score_delta=fit["score"] - old["score"],
                position_difference_m=float(
                    np.linalg.norm(np.array(fit["x"][:2]) - old["x"][:2]) * 1000
                ),
                elapsed_seconds=time.monotonic() - began,
            )
        except Exception as exc:
            case = dict(
                corner=corner,
                error_type=type(exc).__name__,
                error=str(exc),
                elapsed_seconds=time.monotonic() - began,
            )
        with (HERE / f"{ds}_corner{index}.json").open("x") as out:
            json.dump(case, out, indent=2, allow_nan=False)
        cases.append(case)
    with (HERE / f"{ds}.json").open("x") as out:
        json.dump(
            dict(
                dataset=ds,
                baseline=old,
                cases=cases,
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
            (c.get("fit", {}).get("qualified"), c.get("score_delta"), c.get("error_type"))
            for c in cases
        ],
        flush=True,
    )


if __name__ == "__main__":
    main(sys.argv[1])
