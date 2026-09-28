"""Equal-record summaries of the frozen six-fold evaluations."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRASTS = {
    "D-reference": ("D", None),
    "E-reference": ("E", None),
    "B-reference": ("B", None),
    "B-E": ("B", "E"),
    "B-D": ("B", "D"),
    "B-swap": ("B", "B_swap"),
    "B-geometry_reverse": ("B", "B_geometry_reverse"),
    "B-geometry_permute": ("B", "B_geometry_permute"),
    "B-zero_motion": ("B", "B_zero_motion"),
    "B-reverse_motion": ("B", "B_reverse_motion"),
}


def main():
    folds = []
    for index in range(6):
        assert (HERE / f"corrected-fold-{index}-exit-code.txt").read_text().strip() == "0"
        fold = json.loads((HERE / f"fold-{index}.json").read_text())
        assert fold["fold"] == index and fold["status"] == "complete"
        folds.append(fold)
    summary = {"weighting": "equal record after within-record window normalization", "roles": {}}
    for role in ("reception", "held_frequency"):
        values = {}
        for name, (left, right) in CONTRASTS.items():
            scores = []
            for fold in folds:

                def score(arm, fold=fold, role=role):
                    return fold["evaluations"][arm]["roles"][role]["relative_log_score_per_window"]

                scores.append(score(left) - (score(right) if right else 0.0))
            values[name] = {
                "mean": sum(scores) / 6,
                "positive_records": sum(x > 0 for x in scores),
                "per_record": dict(zip([f["held_session"] for f in folds], scores, strict=True)),
            }
        summary["roles"][role] = values
    summary["folds"] = [
        {
            "session": f["held_session"],
            "beam_scale": f["beam_scale"],
            "training_windows": f["training_source_window_count"],
            "selected": {arm: fit["selected"] for arm, fit in f["fits"].items()},
        }
        for f in folds
    ]
    summary["optimizer_starts"] = sum(
        len(fit["candidates"]) for f in folds for fit in f["fits"].values()
    )
    summary["converged_starts"] = sum(
        c["success"] for f in folds for fit in f["fits"].values() for c in fit["candidates"]
    )
    (HERE / "results-summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps(summary["roles"], indent=2))


if __name__ == "__main__":
    main()
