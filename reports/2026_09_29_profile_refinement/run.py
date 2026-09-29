"""Refine two training-selected profile probes on one unchanged q020 panel."""

import sys

import numpy as np
from core import refine, starts
from study import HERE, PRIOR, ROOT, read, save

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE.parent / "2026_09_29_unassociated_trend"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402


def main(key):
    plan = read(HERE / "plan.json")
    u = next(u for u in plan["units"] if u["unit_id"] == key)
    docs = baseline.load_documents(dict(config=plan["config"], inputs=u["group"]["inputs"]))
    assert [d["session_id"] for d in docs] == u["group"]["session_ids"]
    model = TrendMixturePosition(docs, plan["config"], baseline.Stationary, 0.2)
    old = read(PRIOR / "runs" / key / "result.json")
    center = model.evaluate(np.asarray(u["x"]), held=True)
    assert abs(center["score"] - old["center_score"]) < 1e-7
    assert abs(sum(r["held_log_score"] for r in center["rows"]) - old["center_held_score"]) < 1e-7
    rows = []
    for start in starts(old["profiles"]):
        ev = model.evaluate(np.asarray(start["x"]))
        assert abs(ev["score"] - start["score"]) < 1e-7
        row = refine(model.evaluate, start["x"])
        row["probe"] = start
        held = model.evaluate(np.asarray(row["x"]), held=True)
        assert abs(held["score"] - row["score"]) < 1e-7
        row["held_score"] = sum(r["held_log_score"] for r in held["rows"])
        row["held_rows"] = held["rows"]
        row["coordinates"] = list(model.coordinates(row["x"]))
        row["center_distance_m"] = float(
            1000 * np.linalg.norm(np.asarray(row["x"][:2]) - u["x"][:2])
        )
        row["training_delta"] = row["score"] - old["center_score"]
        row["held_delta"] = row["held_score"] - old["center_held_score"]
        rows.append(row)
    save(
        HERE / "runs" / key / "result.json",
        dict(
            unit_id=key,
            center=u["x"],
            center_score=old["center_score"],
            center_held_score=old["center_held_score"],
            results=rows,
        ),
    )
    print(
        key,
        [(r["qualified"], r["training_delta"], r["center_distance_m"]) for r in rows],
        flush=True,
    )


if __name__ == "__main__":
    main(sys.argv[1])
