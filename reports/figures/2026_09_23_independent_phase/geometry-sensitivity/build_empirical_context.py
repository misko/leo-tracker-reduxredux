"""Summarize published multirate phase context without reading IQ or refitting."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[4]
MULTIRATE = ROOT / "reports/figures/2026_09_23_phase_multirate"
SUMMARY = MULTIRATE / "summary.json"
PER_DWELL = MULTIRATE / "per-dwell.csv"
OUTPUT = Path(__file__).with_name("empirical-context.json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    summary = json.loads(SUMMARY.read_text())
    with PER_DWELL.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    rates = []
    for rate_hz in (2_500_000, 10_000_000, 15_000_000):
        rate_msps = rate_hz / 1e6
        selected = [row for row in rows if float(row["sample_rate_msps"]) == rate_msps]
        supported = [row for row in selected if row["native_supported"] == "True"]
        later_b = [math.radians(float(row["native_spline_rms_deg"])) for row in supported]
        pilot = [
            math.radians(float(row["native_pilot_rms_deg"]))
            for row in supported
            if row["native_pilot_rms_deg"]
        ]
        canonical = next(
            row
            for row in summary
            if row["sample_rate_hz"] == rate_hz and row["selected_visits"]
        )
        result = {
            "sample_rate_hz": rate_hz,
            "selected_dwell_count": len(selected),
            "native_supported_count": len(supported),
            "native_later_b_discrepancy_median_rad": median(later_b),
            "refined_pilot_discrepancy_median_rad": median(pilot),
            "refined_pilot_comparable_count": len(pilot),
            "native_fft_block_duration_s": 4096 / rate_hz,
        }
        if len(supported) != canonical["native_supported"]:
            raise ValueError("per-dwell support count disagrees with canonical summary")
        if not math.isclose(
            result["native_later_b_discrepancy_median_rad"],
            math.radians(canonical["native_supported_spline_rms_median_deg"]),
            abs_tol=1e-15,
        ):
            raise ValueError("later-B median disagrees with canonical summary")
        if not math.isclose(
            result["refined_pilot_discrepancy_median_rad"],
            math.radians(canonical["native_supported_pilot_rms_median_deg"]),
            abs_tol=1e-15,
        ):
            raise ValueError("pilot median disagrees with canonical summary")
        rates.append(result)
    return {
        "schema": "phase-geometry-empirical-context/v1",
        "purpose": "descriptive empirical context for an affine-surviving geometric phase bound",
        "comparison_bound_rad": 2.04e-6,
        "comparison_bound_description": (
            "parent-computed maximum predicted phase remaining after a per-dwell phase "
            "intercept and rate are removed"
        ),
        "rates": rates,
        "historical_protocol": (
            "first 60 ms fit the spectral response; the later time half supplies the B-band "
            "check; the A-band curve uses the documented historical fitting and selection"
        ),
        "interpretation": (
            "The phase values are conditional internal estimator discrepancies. They share "
            "fitted nuisances and are neither independent measurement errors nor noise floors. "
            "The comparison is descriptive and does not define a phase detection limit."
        ),
        "no_iq_read": True,
        "no_refit": True,
        "inputs": {
            str(SUMMARY.relative_to(ROOT)): digest(SUMMARY),
            str(PER_DWELL.relative_to(ROOT)): digest(PER_DWELL),
        },
        "source_sha256": digest(Path(__file__)),
    }


if __name__ == "__main__":
    if OUTPUT.exists():
        raise ValueError("fresh output path required")
    OUTPUT.write_text(json.dumps(build(), indent=2, allow_nan=False) + "\n")
