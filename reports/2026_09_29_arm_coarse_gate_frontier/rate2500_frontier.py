#!/usr/bin/env python3
"""Small, 2.5 MHz-only extension of the coarse-score frontier."""
import json
from pathlib import Path

from analyze import BASELINE, COHORT, candidate_rate, evaluate, frozen

HERE = Path(__file__).resolve().parent


def main() -> None:
    manifest = json.loads((COHORT / "manifest.json").read_text())
    selected = manifest["selected"]
    native = frozen.load_native(COHORT / "rows.jsonl")
    baseline = frozen.load_baseline(BASELINE)
    rates = candidate_rate(selected)
    # The prior 0.150--0.175 grid removed nothing at 2.5 MHz. These thirteen
    # points only extend that one rate, sufficient to bracket 5/10/20 losses.
    values = [0.18, 0.19, 0.20, 0.21, 0.22, 0.23, 0.24, 0.25, 0.26, 0.28,
              0.30, 0.305, 0.31, 0.311, 0.312, 0.313, 0.314, 0.315, 0.32, 0.325, 0.33, 0.335, 0.34,
              0.345, 0.35, 0.40]
    results = []
    for threshold in values:
        result = evaluate("rate2500_absolute", native, rates, selected, baseline,
            lambda row, index, rate, t=threshold:
                rate != 2500000 or row[index]["coarse_score"] >= t,
            {"rate_hz": 2500000, "coarse_score_gte": threshold})
        quality = result["quality"]["by_rate"]["2500000"]
        result["rate2500_removed"] = 26752 - result["emitted_by_rate"]["2500000"]
        result["rate2500_recovered_loss"] = 4515 - quality["recovered_positive_hits"]
        results.append(result)
    (HERE / "rate2500-results.json").write_text(json.dumps({
        "scope": "offline 2.5 MHz-only exploratory extension; same frozen matcher and rows",
        "results": results,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
