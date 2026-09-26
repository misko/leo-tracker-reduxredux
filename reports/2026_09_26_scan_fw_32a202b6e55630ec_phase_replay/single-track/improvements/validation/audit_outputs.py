"""Fail-closed consistency audit of tracker result artifacts."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRACKER = HERE.parent / "tracker"


def main():
    payload = json.loads((TRACKER / "tracker-results.json").read_text())
    rows = list(csv.DictReader((TRACKER / "tracker-predictions.csv").open()))
    failures = []
    if payload.get("cache", {}).get("npz_sha256") != json.loads((HERE / "cache-audit.json").read_text())["cache_sha256"]:
        failures.append("tracker and validation cache digests differ")
    for aggregate in payload["aggregates"]:
        if aggregate["held_frames"] != 371:
            failures.append(f'{aggregate["model"]}: held_frames != 371')
        for field in ("gate_conditional_wrapped_rmse_deg", "all_held_failure_inclusive_rmse_deg"):
            value = aggregate[field]
            if value is None or not math.isfinite(value):
                failures.append(f'{aggregate["model"]}: {field} is non-finite')
    crossing = [r for r in rows if r["training_early20ms"] == "False" and
                r["held_forward100ms"] == "False"]
    if len(crossing) != 4 * len(payload["aggregates"]):
        failures.append("CSV does not preserve four excluded crossing frames per model")
    early = [r for r in rows if r["training_early20ms"] == "True"]
    held = [r for r in rows if r["held_forward100ms"] == "True"]
    if any(float(r["support_end_s"]) > .020 for r in early):
        failures.append("training row support extends past 20 ms")
    if any(float(r["support_start_s"]) < .020 for r in held):
        failures.append("held row support starts before 20 ms")
    report = {"status": "pass" if not failures else "fail",
              "failures": failures, "csv_rows": len(rows),
              "aggregate_count": len(payload["aggregates"])}
    (HERE / "output-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
