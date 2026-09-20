"""Evaluate sealed cohort fits using an explicit antenna coordinate, after inference."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km


def separation(lat, lon, reference):
    p, q = np.deg2rad([lat, reference["latitude_deg"]])
    d = np.deg2rad(lon - reference["longitude_deg"])
    return float(
        12742017.6
        * np.arcsin(np.sqrt(np.sin((p - q) / 2) ** 2 + np.cos(p) * np.cos(q) * np.sin(d / 2) ** 2))
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["run", "reference", "historical", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    inference_bytes = (a.run / "results.json").read_bytes()
    inference_digest = hashlib.sha256(inference_bytes).hexdigest()
    results = json.loads(inference_bytes)
    reference = json.loads(a.reference.read_text())
    out = dict(inference_sha256=inference_digest, reference=reference, models=[])
    for cohort, values in results["cohorts"].items():
        for model in values["models"]:
            out["models"].append(
                dict(
                    cohort=cohort,
                    **{k: v for k, v in model.items() if k != "segment_training_rms"},
                    horizontal_error_m=separation(
                        model["latitude_deg"], model["longitude_deg"], reference
                    ),
                )
            )
    history = json.loads(a.historical.read_text())["pooled_positioning"][-1]
    base = geodetic_to_ecef_km(37.858988, -122.478103, -29.0)
    enu = ecef_to_enu_matrix(37.858988, -122.478103)
    reference_ecef = geodetic_to_ecef_km(reference["latitude_deg"], reference["longitude_deg"], 0)
    reference_enu = ecef_to_enu_matrix(reference["latitude_deg"], reference["longitude_deg"])
    out["historical_published_fits"] = []
    for row in history["modes"]:
        fitted = base + np.array(row["enu_km"]) @ enu[:2]
        horizontal = (fitted - reference_ecef) @ reference_enu[:2].T
        out["historical_published_fits"].append(
            dict(
                mode=row["mode"],
                reported_configured_site_error_m=row["horizontal_error_m"],
                actual_antenna_horizontal_error_m=float(np.linalg.norm(horizontal) * 1000),
            )
        )
    out["configured_reference_separation_m"] = separation(37.858988, -122.478103, reference)
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output / "evaluation.json").write_text(json.dumps(out, indent=2) + "\n")
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
    for ax, cohort in zip(axes, results["cohorts"], strict=True):
        rows = [r for r in out["models"] if r["cohort"] == cohort]
        names = [
            r["weighting"]
            + (" robust" if r["robust"] else " LS")
            + (" +UTC" if r.get("clock_fitted") else "")
            for r in rows
        ]
        ax.bar(names, [r["horizontal_error_m"] for r in rows])
        ax.axhline(1000, color="red", linestyle="--", label="1 km target")
        ax.set_title(cohort.replace("_", " "), fontsize=10)
        ax.tick_params(axis="x", labelrotation=35)
        ax.set_ylabel("Error to user-confirmed antenna (m)")
        ax.legend(fontsize=8)
    fig.suptitle("Matched randomized local fits: selection provenance differs by cohort")
    fig.savefig(a.output / "01-matched-cohorts.png", dpi=160)
    print(
        json.dumps(
            {
                "configured_reference_separation_m": out["configured_reference_separation_m"],
                "historical_published_fits": out["historical_published_fits"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
