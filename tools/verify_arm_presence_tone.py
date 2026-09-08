#!/usr/bin/env python3
"""Bounded synthetic specificity check of the eight-basin fractional reference."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from leo.analysis.research.arm_presence import fresh_glrt, noise_control, reference_label


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    args = parser.parse_args()
    rows = []
    for rate in (2_500_000, 5_000_000):
        for edge in ("lower", "upper"):
            for kind in ("gaussian", "tone_noise"):
                values = noise_control(round(rate * 0.120), rate, seed=712341, kind=kind)
                windows = [
                    fresh_glrt(
                        values[i * rate // 50 : (i + 1) * rate // 50],
                        rate,
                        edge=edge,
                        candidate_count=8,
                    )
                    for i in range(6)
                ]
                result = {
                    "rate_hz": rate,
                    "edge": edge,
                    "kind": kind,
                    "label": reference_label(windows),
                    "windows": [[asdict(c) for c in window] for window in windows],
                }
                rows.append(result)
                print(rate, edge, kind, result["label"], flush=True)
    with open(args.output, "x") as stream:
        json.dump(
            {
                "seed": 712341,
                "tone_hz": 173123.0,
                "tone_amplitude": 6.0,
                "noise_sigma_per_quadrature": 1.0,
                "rows": rows,
            },
            stream,
            indent=2,
        )
        stream.write("\n")


if __name__ == "__main__":
    main()
