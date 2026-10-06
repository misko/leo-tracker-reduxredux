"""Read sealed per-visit metrics and audit actual edge tuning; never read/write IQ."""

import argparse
import collections
import json
from pathlib import Path

import numpy as np

from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    selection = json.loads((args.input / "selection.json").read_text())
    captures = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    analyses = AdaptiveHopAnalysisStore(args.bulk_root, read_only=True)
    output = []
    for scan in selection:
        sid = scan["session_id"]
        cached = args.output / f"{sid}.json"
        if cached.exists():
            previous = json.loads(cached.read_text())
            if "conditional" in previous["lanes"]["1:0"]:
                output.append(previous)
                continue
        capture = captures.inspect(sid)
        binding = bind_actual_visit_analysis(
            capture.manifest.receipt,
            input_manifest_sha256=capture.manifest_sha256,
            probe_stride_ms=120,
        )
        status = json.loads((args.input / f"{sid}-analysis.json").read_text())
        assert binding.sha256 == status["binding_sha256"]
        cfg = capture.manifest.receipt.plan.geometry
        lanes = collections.defaultdict(list)
        counts = collections.defaultdict(collections.Counter)
        geometry = set()
        examples = {}
        with analyses.job(binding) as job:
            for visit in job.published_visits():
                nominal = (
                    starlink_edge_rf_center_frequency_hz(visit.target.channel, visit.target.edge)
                    - cfg.lnb_lo_hz
                    - visit.actual_if_center_hz
                )
                half = min(cfg.sample_rate_hz, cfg.bandwidth_hz) / 2
                headroom = min(800000.0, half - 820312.5 - abs(nominal))
                geometry.add((visit.target.channel, visit.actual_if_center_hz, nominal, headroom))
                for probe in visit.probes:
                    key = f"{visit.target.channel}:{probe.receiver_id}"
                    c = counts[key]
                    c["probes"] += 1
                    c["unavailable_candidates"] += len(probe.unavailable_candidates)
                    c["candidate_inventory"] += probe.candidate_count
                    c["empty_probes"] += not bool(probe.candidates)
                    c["at_candidate_limit"] += probe.candidate_count == 8
                    if not probe.candidates:
                        continue
                    w = max(probe.candidates, key=lambda x: x.fractional_margin)
                    acq_residual = w.acquired_cfo_hz - nominal
                    c["passing"] += w.passed_fractional_margin_gate
                    c["integer_passing"] += w.integer_margin >= 0.025
                    c["fractional_rescued"] += w.integer_margin < 0.025 <= w.fractional_margin
                    c["refinement_boundary"] += abs(w.fractional_epoch_offset_samples) >= 1.9
                    c["near_search_boundary"] += abs(acq_residual) >= headroom - 20000
                    c["winner_acq_outside_search"] += abs(acq_residual) > headroom + 1
                    c["passed_outside_narrow"] += bool(
                        w.passed_fractional_margin_gate and abs(acq_residual) > 429687.5
                    )
                    c["strong"] += w.fractional_margin > 0.4
                    c["strong_outside_narrow"] += bool(
                        w.fractional_margin > 0.4 and abs(acq_residual) > 429687.5
                    )
                    lanes[key].append(
                        [
                            w.fractional_margin,
                            w.fractional_exact_score,
                            w.fractional_control_score,
                            acq_residual,
                            w.fractional_tracking_cfo_hz - nominal,
                            w.fractional_epoch_offset_samples,
                            w.integer_margin,
                        ]
                    )
                    # Deterministic bounded replay candidates: first strong and first
                    # marginal winner in each lane after one minute of device time.
                    elapsed = (
                        visit.valid_start_counter - capture.manifest.receipt.terminal.first_counter
                    ) / cfg.sample_rate_hz
                    bucket = (
                        "strong"
                        if w.fractional_margin > 0.4
                        else "marginal"
                        if -0.01 < w.fractional_margin < 0.06
                        else None
                    )
                    if elapsed >= 60 and bucket and f"{key}:{bucket}" not in examples:
                        examples[f"{key}:{bucket}"] = dict(
                            visit_index=visit.visit_index,
                            receiver_id=probe.receiver_id,
                            probe_index=probe.probe_index,
                            probe_start_ms=probe.probe_start_ms,
                            channel=visit.target.channel,
                            candidate=w.model_dump(mode="json"),
                            nominal_baseband_hz=nominal,
                        )
        stats = {}
        labels = [
            "margin",
            "exact",
            "control",
            "acquired_residual_hz",
            "tracking_pilot_relative_hz",
            "epoch_offset_samples",
            "integer_margin",
        ]
        for key, values in lanes.items():
            a = np.asarray(values)
            conditional = {}
            for name, mask in [
                ("passed", a[:, 0] >= 0.025),
                ("strong", a[:, 0] > 0.4),
                ("failed", a[:, 0] < 0.025),
            ]:
                b = a[mask]
                conditional[name] = dict(
                    count=len(b),
                    quantiles={
                        label: np.quantile(b[:, i], [0.05, 0.5, 0.95]).tolist() if len(b) else None
                        for i, label in enumerate(labels)
                    },
                    cfo_histogram=np.histogram(b[:, 3], bins=np.linspace(-800000, 800000, 33))[
                        0
                    ].tolist(),
                )
            stats[key] = dict(
                counts=counts[key],
                quantiles={
                    name: np.quantile(a[:, i], [0.05, 0.5, 0.95]).tolist()
                    for i, name in enumerate(labels)
                },
                conditional=conditional,
                cfo_histogram=np.histogram(a[:, 3], bins=np.linspace(-800000, 800000, 33))[
                    0
                ].tolist(),
            )
        result = dict(
            session_id=sid,
            rate=scan["sample_rate_hz"],
            edge=scan["selected_edge"],
            captured_at=scan["captured_at"],
            geometry=sorted(geometry),
            lanes=stats,
            examples=examples,
        )
        cached.write_text(json.dumps(result))
        output.append(result)
        print(sid, len(output), flush=True)
    (args.output / "edge-audit.json").write_text(json.dumps(output, indent=2))
    analyses.close()
    captures.close()


if __name__ == "__main__":
    main()
