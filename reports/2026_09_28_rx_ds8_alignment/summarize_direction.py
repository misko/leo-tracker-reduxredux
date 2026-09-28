"""Summarize full-order support separately from partial-arc contrast slopes."""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    summaries = {}
    for panel in ("pilot", "ds8"):
        payload = (HERE / f"direction-{panel}.json").read_bytes()
        document = json.loads(payload)
        rows = []
        for lane in document["lanes"]:
            positive = math.fsum(n["prior"] for n in lane["nominees"]
                                 if n["q_overall_secant_per_s"] > 0)
            negative = math.fsum(n["prior"] for n in lane["nominees"]
                                 if n["q_overall_secant_per_s"] < 0)
            rows.append({"lane": lane["lane"], "recording_split": lane["recording_split"],
                         "full_order_disagreement_mass": lane["pair_disagreement_mass"],
                         "partial_positive_secant_mass": positive,
                         "partial_negative_secant_mass": negative,
                         "partial_secant_disagreement_mass": 2 * positive * negative})
        summaries[panel] = {
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "lanes": rows,
            "nominee_statuses": dict(Counter(
                n["unavailable_reason"] or n["order"]
                for lane in document["lanes"] for n in lane["nominees"])),
        }
    with (HERE / "direction-summary.json").open("x") as stream:
        json.dump(summaries, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
