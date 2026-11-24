"""Remove contiguous held observations while keeping the sealed forecasts fixed."""

import gzip
import json
from math import fsum, isclose, isfinite
from pathlib import Path


HERE = Path(__file__).resolve().parent


def interval_sensitivity(scores, widths=(1, 2, 3)):
    by_block = {int(index): weight for index, weight in scores["blocks"].items()}
    total = scores["first_minus_second_nats"]
    if (not by_block or min(by_block) < 0 or not all(map(isfinite, by_block.values()))
            or not isclose(fsum(by_block.values()), total, rel_tol=1e-10, abs_tol=1e-9)):
        raise ValueError("The held time blocks must partition the sealed score")
    radio = scores["by_radio"]
    if set(radio) != {"1", "2"} or not isclose(fsum(radio.values()), total, rel_tol=1e-10, abs_tol=1e-9):
        raise ValueError("Expected a matching two-radio decomposition")
    first, last = min(by_block), max(by_block)
    result = {}
    for width in widths:
        if width < 1 or width >= last - first + 1:
            raise ValueError("Erase a proper, nonempty interval")
        retained = [
            (total - fsum(by_block.get(i, 0.0) for i in range(start, start + width)), start)
            for start in range(first, last - width + 2)
        ]
        weakest, start = min(retained)
        result[str(10 * width)] = dict(minimum=weakest, maximum=max(score for score, _ in retained),
                                       weakest_start_s=10 * start, first_loses=sum(score < 0 for score, _ in retained),
                                       starts=len(retained))
    return result


def main():
    with gzip.open(HERE / "measurements/dense-family-holdout-offline.json.gz", "rt") as stream:
        packet = json.load(stream)
    print(json.dumps({case: {arm: interval_sensitivity(scores) for arm, scores in packet[case]["held-score"]["scores"].items()}
                      for case in ("DS30-0008", "DS30-0057")}, indent=2))


if __name__ == "__main__":
    main()
