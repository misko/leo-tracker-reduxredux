#!/usr/bin/env python3
"""Render the sealed post-seal DS2-22 comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--evaluation", type=Path, default=Path(__file__).with_name("evaluation.json"))
    p.add_argument(
        "--output", type=Path, default=Path(__file__).with_name("postseal-comparison.png")
    )
    a = p.parse_args()
    rows = json.loads(a.evaluation.read_text())["ds2_20_comparison"]
    x = range(len(rows))
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(x, [r["ds2_20_error_km"] for r in rows], "o-", label="DS2-20 fine")
    ax.plot(x, [r["ds2_22_error_km"] for r in rows], "o-", label="DS2-22 fine")
    ax.set_xticks(list(x), [r["method"] for r in rows], rotation=25, ha="right")
    ax.set_ylabel("post-seal haversine error (km)")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(a.output, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
