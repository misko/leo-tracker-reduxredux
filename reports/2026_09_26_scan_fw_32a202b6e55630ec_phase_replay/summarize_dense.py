"""Summarize dense acquisition without inspecting any phase estimate."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRATCH = Path("/srv/bulk/leo/experiments/scan-fw-32a202-phase-replay/acquisition-dense-v1")


def main() -> None:
    selection = json.loads((HERE / "selection.json").read_text())
    rows = []
    for item in selection["visits"]:
        visit = item["visit_index"]
        path = SCRATCH / f"visit-{visit:06d}.corrected-dense.json"
        base = {key: item[key] for key in ("visit_index", "split", "channel", "time_bin")}
        if not path.exists():
            rows.append({**base, "status": "pending"})
            continue
        receipt = json.loads(path.read_text())
        product = receipt["product"]
        probes = product["probes"]
        support = {}
        for probe in probes:
            key = int(probe["probe_index"]), int(probe["receiver_id"])
            support[key] = sum(
                bool(candidate["passed_fractional_margin_gate"])
                for candidate in probe["candidates"]
            )
        if set(support) != {(probe, rx) for probe in range(6) for rx in (0, 1)}:
            raise ValueError(f"incomplete probe lattice for visit {visit}")
        common = [probe for probe in range(6) if support[probe, 0] and support[probe, 1]]
        rows.append(
            {
                **base,
                "status": "completed",
                "rx0_any_probe": any(support[probe, 0] for probe in range(6)),
                "rx1_any_probe": any(support[probe, 1] for probe in range(6)),
                "same_probe_dual_rx": bool(common),
                "same_probe_dual_rx_count": len(common),
                "passing_receiver_probes": sum(count > 0 for count in support.values()),
                "passing_candidate_records": sum(support.values()),
                "first_probe_dual_rx": bool(support[0, 0] and support[0, 1]),
            }
        )
    fields = sorted({key for row in rows for key in row})
    with (HERE / "dense-coverage.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    completed = [row for row in rows if row["status"] == "completed"]
    summary = {
        "schema": "scan-phase-dense-coverage/v1",
        "eligible_visits": len(rows),
        "completed_visits": len(completed),
        "pending_visits": len(rows) - len(completed),
        "completed_by_split": dict(Counter(row["split"] for row in completed)),
        "same_probe_dual_rx_by_split": dict(
            Counter(row["split"] for row in completed if row["same_probe_dual_rx"])
        ),
        "first_probe_dual_rx_by_split": dict(
            Counter(row["split"] for row in completed if row["first_probe_dual_rx"])
        ),
        "passing_receiver_probes": sum(row["passing_receiver_probes"] for row in completed),
        "same_probe_dual_rx_probes": sum(row["same_probe_dual_rx_count"] for row in completed),
        "interpretation": "Acquisition comparison only; neither phase lock nor same-emitter proof.",
    }
    (HERE / "dense-coverage-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
