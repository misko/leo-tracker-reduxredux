"""Query exact track neighbors without expanding a full all-pairs matrix."""

import argparse
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent


def distance_row(condensed, n, index):
    if len(condensed) != n * (n - 1) // 2 or not 0 <= index < n:
        raise ValueError("Invalid condensed matrix or track index")
    out = np.zeros(n)
    for j in range(n):
        if j == index:
            continue
        a, b = sorted((index, j))
        out[j] = condensed[n * a - a * (a + 1) // 2 + b - a - 1]
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--view", default="upper_early_profiles")
    parser.add_argument("--track", required=True)
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()
    folder = BASE / "local/clusters" / args.view
    names = json.loads((folder / "labels.json").read_text())
    if args.track not in names:
        parser.error("Track absent from this view; check quality/edge and its labels.json")
    if args.count < 1:
        parser.error("--count must be positive")
    distances = np.load(folder / "condensed_distances.npy", mmap_mode="r")
    i = names.index(args.track)
    row = distance_row(distances, len(names), i)
    row[i] = np.inf
    order = np.argsort(row, kind="stable")[: min(args.count, len(names) - 1)]
    metadata = {
        t["id"]: t for t in json.loads((BASE / "local/clustering.json").read_text())["tracks"]
    }
    print(
        json.dumps(
            dict(
                track=args.track,
                view=args.view,
                nearest_tie_count=int(np.isclose(row, row.min(), atol=1e-7, rtol=0).sum()),
                neighbors=[
                    dict(
                        distance=float(row[j]),
                        correlation=float(1 - row[j] ** 2 / 2)
                        if args.view.endswith("early_profiles")
                        else None,
                        **metadata[names[j]],
                    )
                    for j in order
                ],
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
