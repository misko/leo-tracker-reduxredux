"""Three generic starts on one target-disjoint donor group."""

import sys
import traceback

import numpy as np
from study import HERE, ROOT, read, save

sys.path.insert(0, str(HERE.parent / "2026_09_29_profile_refinement"))
sys.path.insert(0, str(HERE.parent / "2026_09_29_unassociated_trend"))
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from core import refine  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402


def main(key):
    plan = read(HERE / "plan.json")
    u = next(u for u in plan["units"] if u["unit_id"] == key)
    docs = baseline.load_documents(dict(config=plan["config"], inputs=u["group"]["inputs"]))
    assert [d["session_id"] for d in docs] == u["group"]["session_ids"]
    assert not set(u["group"]["session_ids"]) & set(plan["target_session_ids"])
    model = TrendMixturePosition(docs, plan["config"], baseline.Stationary, 0.2)
    results = []
    for name, position in (
        ("origin", [0.0, 0.0]),
        ("southeast", [3.0, -3.0]),
        ("northwest", [-3.0, 3.0]),
    ):
        initial = position + [0.0] * len(docs)
        try:
            r = refine(model.evaluate, initial)
        except (ValueError, AssertionError, FloatingPointError, IndexError) as error:
            r = dict(
                initial=initial,
                qualified=False,
                error=repr(error),
                traceback=traceback.format_exc(),
            )
        r["name"] = name
        results.append(r)
    eligible = [r for r in results if r["qualified"]]
    selected = max(eligible, key=lambda r: r["score"]) if eligible else None
    output = dict(
        unit_id=key,
        session_ids=u["group"]["session_ids"],
        available_utc_ns=u["available_utc_ns"],
        starts=results,
        selected=selected,
        rows=[],
    )
    if selected:
        ev = model.evaluate(np.asarray(selected["x"]), held=True)
        assert abs(ev["score"] - selected["score"]) < 1e-7
        assert abs(sum(t["training_log_score"] for t in ev["rows"]) - selected["score"]) < 1e-7
        output["rows"] = ev["rows"]
        output["held_score_diagnostic_only"] = sum(t["held_log_score"] for t in ev["rows"])
    save(HERE / "runs" / key / "result.json", output)
    print(
        key, len(eligible), "qualified starts;", len(output["rows"]), "exported tracks", flush=True
    )


if __name__ == "__main__":
    main(sys.argv[1])
