"""Post-seal presentation only: no optimizer or model objective calls."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior

HERE = Path(__file__).resolve().parent
ATTEMPT = HERE.parent / "blocked_cold/S03-block20-parity0"
STATION = HERE.parents[2] / "deploy/station/gauss-r20-lt3d-004b-20261001-v1.json"


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def distance_km(a, b):
    a, b = np.radians(a), np.radians(b)
    d = b - a
    h = np.sin(d[0] / 2) ** 2 + np.cos(a[0]) * np.cos(b[0]) * np.sin(d[1] / 2) ** 2
    return float(2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(h, 0, 1))))


def main():
    evaluation = json.loads((HERE / "blocked_evaluation.json").read_text())
    terminal = json.loads((ATTEMPT / "output/terminal.json").read_text())
    derived = json.loads((ATTEMPT / "derivation.json").read_text())
    source = json.loads((ATTEMPT / "training-input.json").read_text())["source"]
    station = json.loads(STATION.read_text())
    if not (
        source["radio_id"] == station["radio_serial"]
        and station["valid_from_utc_ns"] <= derived["origin_utc_ns"] < station["valid_until_utc_ns"]
    ):
        raise ValueError("Configured station metadata must match source radio and time")
    prior = RegionalPrior(**terminal["provenance"]["prior"])
    options = json.loads((ATTEMPT / "output/stages/shared-all-A-5.json").read_text())["result"][
        "options"
    ]
    rows = []
    for result in evaluation["rows"]:
        name = f"{result['family']}_{result['arm']}"
        fit_path = HERE / f"blocked_fit_{name}.json"
        fit = json.loads(fit_path.read_text())
        v = np.array(fit["vector"])
        lat, lon = coordinates(prior, v[:2])
        local_distance = float(np.linalg.norm(v[:2] - options["local_center"]))
        requested = {
            role: dict(
                observations=sum(w[role]["observations"] for w in result["windows"].values()),
                associated=sum(w[role]["associated"] for w in result["windows"].values()),
                frequency_nll=sum(w[role]["frequency_nll"] for w in result["windows"].values()),
            )
            for role in ("train", "held", "boundary")
        }
        rows.append(
            dict(
                result,
                requested=requested,
                fit_sha256=digest(fit_path),
                latitude_deg=float(lat),
                longitude_deg=float(lon),
                configured_reference_distance_km=distance_km(
                    [lat, lon], [station["latitude_deg"], station["longitude_deg"]]
                ),
                regional_feasible=bool(result["audit"]["feasible"]),
                original_production_local_disk_feasible=local_distance
                <= options["local_radius_km"] + 1e-9,
                original_production_local_center_distance_km=local_distance,
            )
        )
    summary = dict(
        rows=rows,
        scope="Matched broad regional research domain, not original production 25 km domain",
        evaluation_sha256=digest(HERE / "blocked_evaluation.json"),
        erratum_sha256=digest(HERE / "blocked_domain_erratum.json"),
        configured_reference=dict(
            path=str(STATION),
            sha256=digest(STATION),
            binding=(
                "matching radio serial and configured validity interval; post-seal diagnostic only"
            ),
            qualification=station["position_evidence"],
        ),
        additional_objective_calls=0,
        additional_fits=0,
        promotion=False,
        all_source_denominator=20084,
        all_requested_denominator=693,
        tested_source="S03 only: 2073 train + 1909 held + 6 boundary; requested 58 train + 80 held",
        original_blocked_anchor=(
            "795/1909 and 66/80 descriptive only: extra optimization/domain differ"
        ),
    )
    (HERE / "blocked_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.5))
    colors = {"scalar2": "#4268a8", "age": "#ce7d30"}
    for arm_i, arm in enumerate(("fitted-c", "zero-c")):
        baseline = next(r for r in rows if r["arm"] == arm and r["family"] == "scalar2")
        for family_i, family in enumerate(("scalar2", "age")):
            row = next(r for r in rows if r["arm"] == arm and r["family"] == family)
            x = arm_i + (family_i - 0.5) * 0.32
            axes[0].bar(
                x,
                row["held"]["associated"],
                width=0.30,
                color=colors[family],
                label=family if arm_i == 0 else None,
            )
            axes[0].text(
                x,
                row["held"]["associated"] + 8,
                str(row["held"]["associated"]),
                ha="center",
                fontsize=9,
            )
            delta = row["held"]["frequency_nll"] - baseline["held"]["frequency_nll"]
            axes[1].bar(x, delta, width=0.30, color=colors[family])
            axes[1].text(x, delta - 3, f"{delta:.2f}", ha="center", va="top", fontsize=9)
            axes[2].bar(
                x,
                row["configured_reference_distance_km"],
                width=0.30,
                color=colors[family],
                hatch="///" if not row["original_production_local_disk_feasible"] else "",
            )
            axes[2].text(
                x,
                row["configured_reference_distance_km"] + 0.05,
                f"{row['configured_reference_distance_km']:.3f}",
                ha="center",
                fontsize=9,
            )
    axes[0].set(title="Held associations /1909", ylim=(0, 950))
    axes[0].legend(frameon=False)
    axes[1].set(title="Held NLL minus scalar2", ylim=(-100, 15))
    axes[1].axhline(0, color=".4", linewidth=0.7)
    axes[2].set(title="Configured-reference distance (km)")
    for ax in axes:
        ax.set_xticks([0, 1], ["Fitted c", "c = 0"])
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(
        "S03 train-only age-prior sensitivity: all four endpoints strict in regional domain"
    )
    fig.text(
        0.5,
        0.015,
        (
            "Hatched position bars: outside original production 25 km disk. "
            "No promotion; other four sources untested."
        ),
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    for suffix in ("png", "pdf"):
        fig.savefig(HERE / f"blocked_comparison.{suffix}", dpi=160)
    plt.close(fig)
    for r in rows:
        print(
            r["family"],
            r["arm"],
            "km",
            r["configured_reference_distance_km"],
            "local25",
            r["original_production_local_disk_feasible"],
            "requestedheld",
            r["requested"]["held"]["associated"],
        )


if __name__ == "__main__":
    main()
