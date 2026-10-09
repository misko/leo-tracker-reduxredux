"""Synthetic scoring-only cost; excludes orbit propagation and optimization."""

import json
import time
import tracemalloc
from pathlib import Path

import numpy as np
from fixed_bank import streamed_score

from leo.contracts.regional_position import POSITION_SCORES


def main():
    rows = []
    for n, k in ((3000, 150), (10000, 500)):
        y = np.linspace(-200, 200, n)

        def batches(k=k, y=y):
            for start in range(0, k, 64):
                ids = np.arange(start, min(k, start + 64))
                prediction = y[:, None] + (ids[None, :] % 13 - 6) * 100
                visible = np.broadcast_to(ids[None, :] % 4 != 0, prediction.shape).copy()
                yield prediction, visible

        timings = []
        for _ in range(3):
            begun = time.perf_counter()
            streamed_score(y, batches(), candidate_count=k, score=POSITION_SCORES["V16"], penalty=0)
            timings.append(time.perf_counter() - begun)
        tracemalloc.start()
        streamed_score(y, batches(), candidate_count=k, score=POSITION_SCORES["V16"], penalty=0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows.append(
            {
                "observations": n,
                "candidates": k,
                "batch_size": 64,
                "seconds": timings,
                "median_seconds": float(np.median(timings)),
                "tracemalloc_peak_bytes": peak,
            }
        )
    receipt = {
        "scope": (
            "synthetic scoring and generated batches only; "
            "no orbit propagation, recording, or fitting"
        ),
        "numpy": np.__version__,
        "rows": rows,
    }
    Path(__file__).with_name("synthetic-cost.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
