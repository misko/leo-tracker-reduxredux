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
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def check_partition(scans):
    assert len(scans) == 24
    assert [s["window"] for s in scans] == ["early"] * 8 + ["middle"] * 8 + ["late"] * 8
    assert len({s["input"]["session_id"] for s in scans}) == 24
    assert max(s["start_utc_ns"] + 300_000_000_000 for s in scans[:16]) < min(
        s["start_utc_ns"] for s in scans[16:]
    )


def main(ds):
    started = time.monotonic()
    frozen = read(HERE / "manifest.json")
    for name, h in frozen["hashes"].items():
        assert sha(ROOT / name) == h, name
    budget = module("budget", REPORTS / "2026_09_29_scan_budget/run.py")
    held = module("held", REPORTS / "2026_09_29_curvature_scan_holdout/run.py")
    helper = budget.helper
    manifest = read(REPORTS / "2026_09_29_scan_budget/manifest.json")
    pool = next(s for s in manifest["sets"] if s["dataset"] == ds and s["count"] == 24)
    check_partition(pool["scans"])
    config = manifest["config"]
    docs = helper.baseline.load_documents(
        dict(config=config, inputs=[s["input"] for s in pool["scans"]])
    )

    def model(documents):
        return helper.TrendMixturePosition(documents, config, helper.baseline.Stationary, 0.2)

    arms = {}
    for window, part in (("early", docs[:8]), ("middle", docs[8:16])):
        old = read(REPORTS / f"2026_09_29_time_balanced_scans/grid_{ds}_contiguous_{window}.json")
        assert old["sessions"] == [d["session_id"] for d in part]
        assert old["selected"]["qualified"]
        assert (
            abs(
                model(part).evaluate(old["selected"]["x"], gradient=False)["score"]
                - old["selected"]["score"]
            )
            < 1e-7
        )
        arms[window] = old["selected"]
    train = model(docs[:16])
    singles = [model([d]) for d in docs[:16]]
    grid = np.array(config["timing_grid_s"])
    starts = []
    for family in ("cold", "timing_grid"):
        for east in (-2.0, 0.0, 2.0):
            x = np.zeros(18)
            x[0] = east
            if family == "timing_grid":
                for i, one in enumerate(singles):
                    scores, _ = budget.training_scores(one, x[:2], grid)
                    k = int(np.argmax(scores))
                    x[i + 2] = grid[k]
                    assert (
                        abs(one.evaluate([east, 0.0, grid[k]], gradient=False)["score"] - scores[k])
                        < 1e-7
                    )
            starts.append(dict(helper.fit_model(train, x), family=family))
    valid = [s for s in starts if s["qualified"]]
    selected = max(valid, key=lambda s: s["score"]) if valid else None
    if selected:
        selected["estimate_deg"] = list(train.models[0].coordinates(selected["x"][:3]))
    with (HERE / f"{ds}.source.json").open("x") as out:
        json.dump(
            dict(starts=starts, selected=selected, manifest_sha256=sha(HERE / "manifest.json")),
            out,
            indent=2,
            allow_nan=False,
        )
    assert selected is not None, "No qualified cumulative endpoint"
    arms["cumulative"] = selected
    targets = []
    for doc in docs[16:]:
        test = model([doc])
        targets.append(
            dict(
                session_id=doc["session_id"],
                scores={name: held.marginal(test, arm["x"][:2]) for name, arm in arms.items()},
            )
        )
    with (HERE / f"{ds}.json").open("x") as out:
        json.dump(
            dict(
                dataset=ds,
                arms=arms,
                targets=targets,
                source_sessions=[d["session_id"] for d in docs[:16]],
                elapsed_seconds=time.monotonic() - started,
                manifest_sha256=sha(HERE / "manifest.json"),
            ),
            out,
            indent=2,
            allow_nan=False,
        )
    print(ds, time.monotonic() - started, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
