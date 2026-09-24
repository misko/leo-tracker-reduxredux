#!/usr/bin/env python3
"""Evaluate and plot sealed bounded DS2 objective outputs after inference."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REFERENCE = (37.84903264307456, -122.4856541910174)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path: Path) -> dict[str, Any]:
    seals = (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    if not any(seal.is_file() and seal.read_text().strip() == expected for seal in seals):
        raise ValueError(f"unsealed inference input: {path}")
    return json.loads(path.read_text())


def distance_km(point: dict[str, Any]) -> float:
    radius = 6371.0088
    lat1, lon1 = map(math.radians, REFERENCE)
    lat2, lon2 = map(math.radians, (point["latitude_deg"], point["longitude_deg"]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def save(path: Path, document: dict[str, Any]) -> None:
    content = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.write_text(content)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


def main() -> None:
    cap_path = HERE / "cap800-inference.json"
    rate_path = HERE / "rate-screen.json"
    cap = sealed(cap_path)
    rate = sealed(rate_path)
    rate_winner = rate["winners"]["rate_aware"]
    control_winner = rate["winners"]["nominal_control"]
    cap_winner = cap["winner"]
    rows = [
        {
            "method": "consistent cap-800 proposal/exact",
            "latitude_deg": cap_winner["latitude_deg"],
            "longitude_deg": cap_winner["longitude_deg"],
            "postseal_error_km": distance_km(cap_winner),
            "selection_score": cap_winner["balanced_exact_capped_loss"],
            "exact_gates_passed": all(
                value["exact_comparison"]["exact_sgp4_gate"]["passed"]
                for value in cap_winner["best_exact_by_group"].values()
            ),
        },
        {
            "method": "rate-aware cache screen",
            "latitude_deg": rate_winner["latitude_deg"],
            "longitude_deg": rate_winner["longitude_deg"],
            "postseal_error_km": distance_km(rate_winner),
            "selection_score": rate_winner["rate_aware"]["fit"]["selection_objective"],
            "exact_gates_passed": rate["exact_replay"]["rate_aware"]["exact_sgp4_gate"]["passed"],
        },
        {
            "method": "nominal matched control",
            "latitude_deg": control_winner["latitude_deg"],
            "longitude_deg": control_winner["longitude_deg"],
            "postseal_error_km": distance_km(control_winner),
            "selection_score": control_winner["nominal_control"]["selection_objective"],
            "exact_gates_passed": rate["exact_replay"]["nominal_control"][
                "exact_sgp4_gate"
            ]["passed"],
        },
    ]
    output = {
        "schema": "ds2-consistent-rate-screen-postseal-evaluation/v1",
        "development_evaluation": True,
        "reference_coordinate": {
            "latitude_deg": REFERENCE[0],
            "longitude_deg": REFERENCE[1],
            "role": "introduced only after rate-screen and cap-800 inferences sealed",
        },
        "rows": rows,
        "bindings": {"cap800_inference": digest(cap_path), "rate_screen": digest(rate_path)},
    }
    save(HERE / "postseal-evaluation.json", output)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharex=True, sharey=True)
    for axis, arm, title in (
        (axes[0], "nominal_control", "Nominal matched control"),
        (axes[1], "rate_aware", "Rate-aware screen"),
    ):
        values = [
            row[arm]["selection_objective"]
            if arm == "nominal_control"
            else row[arm]["fit"]["selection_objective"]
            for row in rate["rows"]
        ]
        xs = [row["east_from_sealed_winner_km"] for row in rate["rows"]]
        ys = [row["north_from_sealed_winner_km"] for row in rate["rows"]]
        scatter = axis.scatter(xs, ys, c=values, cmap="viridis_r", s=90)
        winner = rate["winners"][arm]
        axis.plot(
            winner["east_from_sealed_winner_km"],
            winner["north_from_sealed_winner_km"],
            marker="*",
            color="red",
            markersize=15,
            label="selected RF-only cell",
        )
        axis.plot(0, 0, marker="x", color="black", markersize=9, label="sealed parent centre")
        axis.set_title(title)
        axis.set_xlabel("East from sealed parent (km)")
        axis.grid(alpha=0.25)
        fig.colorbar(scatter, ax=axis, label="selection objective")
    axes[0].set_ylabel("North from sealed parent (km)")
    axes[1].legend(loc="upper right")
    fig.suptitle("DS2 bounded local screen; reference is excluded from these panels")
    fig.tight_layout()
    fig.savefig(HERE / "rate-screen-objective.png", dpi=170)
    plt.close(fig)
    print(json.dumps({"rows": len(rows), "output": str(HERE / "postseal-evaluation.json")}))


if __name__ == "__main__":
    main()
