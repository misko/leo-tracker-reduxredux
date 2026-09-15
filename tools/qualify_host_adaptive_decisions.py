"""Seal then evaluate the reserved saved-IQ holdout. Never opens a radio."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from leo.analysis.host_decision import NativeHostDecision
from leo.storage.persistent_hop import PersistentHopIqStore
from tools.investigate_adaptive_decision_budget import decimate
from tools.prepare_decimated_dwell_replay import (
    build,
    coefficients,
    multirate_coefficients,
    reference,
)
from tools.presence_dwell import NativeDwell, unpack

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "reports/2026_09_12_adaptive_decimated_dwell/qualification-protocol.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: object) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def seal(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    library = build(output / "decision.so", shared=True)
    protocol = json.loads(PROTOCOL.read_text())
    sources = json.loads(library.with_suffix(".so.build.json").read_text())["sources_sha256"]
    sources[str(ROOT / "src/leo/analysis/host_decision.py")] = digest(
        ROOT / "src/leo/analysis/host_decision.py"
    )
    sources[str(Path(__file__).resolve())] = digest(Path(__file__).resolve())
    write_new(
        output / "sealed.json",
        {
            "schema": "leo-host-adaptive-decision-qualification-v1",
            "sealed_at": datetime.now(UTC).isoformat(),
            "protocol_sha256": digest(PROTOCOL),
            "protocol": protocol,
            "library_sha256": digest(library),
            "sources_sha256": sources,
            "filters": [
                {
                    "id": "direct161-q15-phase0-reset-mask40-v1",
                    "coefficients_q15": coefficients("direct")[1].tolist(),
                    "source_rate_hz": 10000000,
                    "decision_rate_hz": 2500000,
                    "group_delay_source_samples": 80,
                    "phase": 0,
                    "supported_output_interval": [40, 300000],
                },
                {
                    "id": "direct201-q15-phase0-reset-mask34-v1",
                    "coefficients_q15": multirate_coefficients(15000000).tolist(),
                    "source_rate_hz": 15000000,
                    "decision_rate_hz": 2500000,
                    "group_delay_source_samples": 100,
                    "phase": 0,
                    "supported_output_interval": [34, 300000],
                },
                {
                    "id": "direct257-q15-phase0-reset-mask32-v1",
                    "coefficients_q15": multirate_coefficients(20000000).tolist(),
                    "source_rate_hz": 20000000,
                    "decision_rate_hz": 2500000,
                    "group_delay_source_samples": 128,
                    "phase": 0,
                    "supported_output_interval": [32, 300000],
                },
            ],
            "candidate_support": "window>0 or integer epoch>=42; +/-2 fractional support",
            "decision": {
                "screen_mask": 63,
                "maximum_confirmations": 1,
                "seeded": False,
                "minimum_exact_score": 0.175,
                "minimum_margin": 0.025,
            },
            "limits": "Holdout is not RF truth. Compare reference decisions, not calibrated recall.",
        },
    )


def verdict(result: object, support_start: int) -> str:
    window = int(result.rank.order[0])
    outcome = "not_detected"
    evidence = result.confirmations[0]
    for c in evidence.candidates[: evidence.candidate_count]:
        supported = window > 0 or c.epoch >= support_start + 2
        if not c.fractional_complete or not supported:
            outcome = "unknown"
        if supported and c.fractional_complete and c.exact_score >= 0.175 and c.margin >= 0.025:
            return "detected"
    return outcome


def holdout(output: Path, bulk_root: Path) -> None:
    sealed = json.loads((output / "sealed.json").read_text())
    library = output / "decision.so"
    if digest(library) != sealed["library_sha256"] or digest(PROTOCOL) != sealed["protocol_sha256"]:
        raise ValueError("sealed binary/protocol changed")
    for path, expected in sealed["sources_sha256"].items():
        if digest(Path(path)) != expected:
            raise ValueError(f"sealed source changed: {path}")
    protocol = sealed["protocol"]
    store = PersistentHopIqStore.open_read_only(bulk_root)
    rows = []
    with (output / "holdout.jsonl").open("x") as stream, NativeHostDecision(library) as host:
        for sid in protocol["sessions"]:
            session = store.inspect(sid)
            m = session.manifest
            assert m.plan.sample_rate_hz == 10000000 and len(m.receiver_ids) == 1
            rx = m.receiver_ids[0]
            for sweep in protocol["holdout_sweeps"]:
                visits, values = store.read_sweep_ci16(session, sweep)
                assert len(visits) == 8
                for index, visit in enumerate(visits):
                    iq = np.ascontiguousarray(values[index * 1200000 : (index + 1) * 1200000, 0, :])
                    edge = m.plan.profiles[visit.target_index].target.edge
                    result = host.run(iq, edge=edge)
                    scalar = reference(iq, *coefficients("direct"))
                    scalar[:40] = 0
                    high, _ = decimate(iq, 2500000)
                    high[:64] = 0
                    with NativeDwell(library, 2500000, edge, 512) as ref:
                        expected = ref.run(scalar, maximum=1, seeded=False)
                        same = verdict(expected, 40)
                        ec = expected.confirmations[0].candidates[0]
                        assert result.outcome == same
                        assert result.confirmation_mask == expected.confirmation_window_mask
                        assert (result.epoch, result.exact_score, result.margin) == (
                            ec.epoch,
                            ec.exact_score,
                            ec.margin,
                        )
                        high_result = ref.run(high, maximum=1, seeded=False)
                        high_verdict = verdict(high_result, 64)
                    row = {
                        "session_id": sid,
                        "input_manifest_sha256": session.manifest_sha256,
                        "rx": rx,
                        "sweep": sweep,
                        "visit": sweep * 8 + index,
                        "target": visit.target_index,
                        "edge": edge,
                        "iq_sha256": hashlib.sha256(iq.tobytes()).hexdigest(),
                        "result": asdict(result),
                        "same_coefficient_outcome": same,
                        "high_quality_outcome": high_verdict,
                        "high_quality_result": unpack(high_result),
                    }
                    rows.append(row)
                    stream.write(json.dumps(row, allow_nan=False) + "\n")
                    stream.flush()
                print(f"validated {len(rows)}/64 held-out dwells", flush=True)
    assert len(rows) == 64
    times = [row["result"]["wall_ms"] for row in rows]
    summary = {
        "cases": len(rows),
        "same_coefficient_mismatches": 0,
        "mean_wall_ms": float(np.mean(times)),
        "p99_wall_ms": float(np.percentile(times, 99)),
        "by_rx": {},
        "rows_sha256": digest(output / "holdout.jsonl"),
    }
    for rx in (0, 1):
        subset = [r for r in rows if r["rx"] == rx]
        summary["by_rx"][str(rx)] = {
            "cases": len(subset),
            "candidate_positive": sum(r["result"]["outcome"] == "detected" for r in subset),
            "reference_positive": sum(r["high_quality_outcome"] == "detected" for r in subset),
            "different_outcomes": [
                r["visit"] for r in subset if r["result"]["outcome"] != r["high_quality_outcome"]
            ],
        }
    write_new(output / "holdout-summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "holdout"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    if args.action == "seal":
        seal(args.output)
    else:
        holdout(args.output, args.bulk_root)
