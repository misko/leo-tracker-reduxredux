"""Read-only production snapshot. No capture, control mutation, or radio access."""

import gzip
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np

root = Path(__file__).parent
session = "scan-hop-b5521c5e306d0bd3"
with httpx.Client(base_url="http://127.0.0.1:8090", timeout=30) as client:
    responses = {}
    for name, url in {
        "control": "/api/v1/capture-control",
        "detail": f"/api/v2/scanner/persistent-sessions/{session}",
        "glrt": f"/api/v1/scanner/persistent-sessions/{session}/glrt",
    }.items():
        response = client.get(url)
        response.raise_for_status()
        responses[name] = dict(
            path=url,
            status=response.status_code,
            response_sha256=hashlib.sha256(response.content).hexdigest(),
            body=response.json(),
        )
publication = responses["glrt"]["body"]
evidence = publication["evidence"]
capture = responses["detail"]["body"]["capture"]
assert publication["session_id"] == capture["session_id"] == session
assert publication["error"] is evidence["error"] is None
assert evidence["delivery_complete"] and evidence["dropped_results"] == 0
rows = evidence["results"]
assert len(rows) == capture["visit_count"] == evidence["expected_results"]
assert [int(row["visit"]) for row in rows] == list(range(len(rows)))
assert all(row["rate_hz"] == 5000000 and row["rx"] == 1 for row in rows)
assert all(row["search_window_mask"] in (0, 63) for row in rows)
evaluated = [row for row in rows if row["search_window_mask"] == 63]
snapshot = dict(
    observed_utc=datetime.now(UTC).isoformat(),
    method="Read-only published API and service status; no new IQ read/hash verification.",
    responses=responses,
    acquisition=subprocess.check_output(
        [
            "systemctl",
            "show",
            "leo-acquisition.service",
            "-p",
            "MainPID",
            "-p",
            "NRestarts",
            "-p",
            "ActiveState",
            "-p",
            "ActiveEnterTimestamp",
        ],
        text=True,
    ),
    selected_releases={
        name: str(Path(f"/opt/leo-tracker/current-{name}").resolve())
        for name in ("api", "acquisition")
    },
)
with (root / "production-snapshot.json.gz").open("xb") as stream:
    stream.write(gzip.compress(json.dumps(snapshot, separators=(",", ":")).encode(), mtime=0))
summary = dict(
    session_id=session,
    captured_at=capture["captured_at"],
    observed_utc=snapshot["observed_utc"],
    input_manifest_sha256=publication["input_manifest_sha256"],
    algorithm_sha256=publication["algorithm_sha256"],
    configuration_sha256=publication["configuration_sha256"],
    capture_duty_percent=capture["valid_duty_ppm"] / 10000,
    complete_visits=len(rows),
    temporal_screened_visits=len(evaluated),
    temporal_screening_percent=100 * len(evaluated) / len(rows),
    zero_coverage_visits=len(rows) - len(evaluated),
    positive_results=sum(row["verdict"] == "starlink" for row in rows),
    unavailable_results=sum(row["verdict"] == "unavailable" for row in rows),
    confirmation_evaluations=sum(
        int(row["confirmation_end"]) > int(row["confirmation_start"]) for row in rows
    ),
    delivery_complete=evidence["delivery_complete"],
    dropped_results=evidence["dropped_results"],
    new_full_iq_verification=False,
    evaluated_cpu_ms={
        "mean": float(np.mean([row["cpu_ms"] for row in evaluated])),
        "p99": float(np.percentile([row["cpu_ms"] for row in evaluated], 99)),
        "maximum": max(row["cpu_ms"] for row in evaluated),
    },
    per_target=[
        dict(
            target=target,
            visits=sum(row["channel"] - 1 + 4 * (row["edge"] == "upper") == target for row in rows),
            screened=sum(
                row["channel"] - 1 + 4 * (row["edge"] == "upper") == target for row in evaluated
            ),
        )
        for target in range(8)
    ],
)
with (root / "production-summary.json").open("x") as stream:
    json.dump(summary, stream, indent=2)
print(json.dumps(summary, indent=2))
