"""Render geodesic differences from sealed embedded fit predictions."""

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt

from ..scoring import ARMS, ROLES, distance_km
from . import screening_figures
from .embedded_solve import METHOD, REPORT

ROLE_LABELS = ("No repair", "Selective gap", "One omitted track", "Two omitted tracks")


def generate(source, output):
    (chart,) = screening_figures.charts([METHOD], evidence=source)
    locks = json.loads((source / "prediction-lock.json").read_bytes())
    measurements = json.loads(screening_figures._sealed_bytes(source, locks, "measurements.json"))[
        "recordings"
    ]
    rows, positions = [], []
    for ident in chart.cases:
        ref = chart.references[ident]
        for arm in ARMS:
            label = f"{ident} · {'c = 0' if arm == 'c0' else 'fitted c'}"
            new = chart.predictions["one"][ident]["result"]["arms"][arm]["forced_latlon"]
            stock = chart.predictions["stock"][ident]["result"]["arms"][arm]["forced_latlon"]
            arm_run = measurements[ident]["arms"][arm]
            coords = {"Native-joint SciPy control": stock, "Compiled host Schur fit": new}
            if "aarch64" in arm_run["platforms"]:
                coords["AArch64 Schur replay"] = arm_run["platforms"]["aarch64"]["latlon"]
            points = {
                title: (ref["reference"][role].get(arm) or ref["reference"][role]["shape"])[
                    "latlon"
                ]
                for role, title in zip(ROLES, ROLE_LABELS, strict=True)
            }
            for method, point in coords.items():
                rows.append(
                    dict(
                        recording=ident,
                        arm=arm,
                        method=method,
                        latitude_deg=point[0],
                        longitude_deg=point[1],
                        error_km=distance_km(point, ref["truth"]),
                        shift_from_scipy_m=1000 * distance_km(point, stock),
                        **{
                            f"shift_from_{role.replace('-', '_')}_v5_km": distance_km(
                                point, points[title]
                            )
                            for role, title in zip(ROLES, ROLE_LABELS, strict=True)
                        },
                    )
                )
            positions.append((label, [distance_km(new, p) for p in points.values()]))
    output.mkdir(parents=True, exist_ok=True)
    with (output / "geographic-comparison.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fig, ax = plt.subplots(figsize=(9, 4.2), layout="constrained")
    for i, role in enumerate(ROLE_LABELS):
        ax.scatter(
            [row[1][i] for row in positions],
            [y + (i - 1.5) * 0.13 for y in range(len(positions))],
            label=role,
            s=37,
        )
    ax.set_yticks(range(len(positions)), [row[0] for row in positions])
    ax.invert_yaxis()
    ax.set(
        xlabel="Geodesic separation from the corresponding v5 fix (km)",
        title="Fixed-owner Schur fit compared with four original v5 options",
    )
    ax.set_xlim(left=0)
    ax.grid(axis="x", alpha=0.25)
    ax.legend(title="Original v5", ncols=2, loc="upper right")
    fig.savefig(output / "geographic-comparison.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=REPORT)
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    generate(args.evidence, args.out)


if __name__ == "__main__":
    main()
