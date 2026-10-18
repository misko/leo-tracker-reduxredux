"""Extract past-only TLE histories before any radio/position fitting."""

import hashlib
import json
from pathlib import Path

from dsx01_causal_forecast import INPUT


def causal_inventory(candidates, origin):
    fields = {"name", "lines", "epoch", "collected_utc_ns", "snapshot_digest"}
    return {
        number: [
            {k: v for k, v in row.items() if k in fields}
            for row in record["past_versions"]
            if row["collected_utc_ns"] <= origin and row["epoch"] <= origin
        ]
        for number, record in candidates.items()
    }


def run():
    values = {}
    root = Path(__file__).resolve().parents[1]
    for k in range(1, 6):
        case = f"DSX01-S0{k}"
        source = root / "reports/2026_10_18_dsx01_clean_region" / case / "causal_history.json"
        data = json.loads(source.read_text())
        stem = (
            "2026_10_17_dsx01_polynomial_satellite_dive"
            if case.endswith("S01")
            else "2026_10_17_robust_curve_reassociation"
        )
        receipt = json.loads(
            (root / "reports" / stem / "frozen_inputs" / case / "receipt.json").read_text()
        )
        origin = receipt["origin_utc_ns"]
        values[case] = dict(
            origin_utc_ns=origin,
            past_versions=data["past_versions"],
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            future_fields_excluded=True,
            association_subset_used=False,
        )
    payload = json.dumps(values, indent=2) + "\n"
    if INPUT.exists() and INPUT.read_text() != payload:
        raise ValueError("Existing causal forecast input differs; preserve launched input")
    INPUT.write_text(payload)


if __name__ == "__main__":
    run()
