"""Summarize paired-state leave-one-record-out predictive contrasts."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPARISONS = {
    "P-reference": ("P", None),
    "U-reference": ("U", None),
    "O-reference": ("O", None),
    "U-P": ("U", "P"),
    "O-U": ("O", "U"),
    "O-P": ("O", "P"),
    "O-swap": ("O", "O_swap"),
    "O-reverse": ("O", "O_reverse"),
    "O-permute": ("O", "O_permute"),
}


def main():
    folds = []
    for index in range(6):
        assert (HERE / f"fold-{index}-exit-code.txt").read_text().strip() == "0"
        fold = json.loads((HERE / f"fold-{index}.json").read_text())
        assert fold["fold"] == index
        folds.append(fold)
    summary = {"weighting": "equal recording after window normalization", "roles": {}}
    for role in ("reception", "held_frequency"):
        result = {}
        for label, (left, right) in COMPARISONS.items():
            scores = []
            for fold in folds:

                def score(arm, fold=fold, role=role):
                    return fold["evaluations"][arm]["roles"][role]["relative_log_score_per_window"]

                scores.append(score(left) - (score(right) if right else 0.0))
            result[label] = {
                "mean": sum(scores) / 6,
                "positive_records": sum(value > 0 for value in scores),
                "per_record": scores,
            }
        summary["roles"][role] = result
    summary["sessions"] = [fold["held_session"] for fold in folds]
    summary["selected"] = [
        {arm: fit["selected"] for arm, fit in fold["fits"].items()} for fold in folds
    ]
    with (HERE / "results-summary.json").open("x") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
    print(json.dumps(summary["roles"], indent=2))


if __name__ == "__main__":
    main()
