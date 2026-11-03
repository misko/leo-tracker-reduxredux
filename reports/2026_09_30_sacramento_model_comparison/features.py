"""Feature-availability gates for Sacramento comparison models M6, M7 and M10.

This module deliberately does not synthesize missing observables.  A track time
axis is an observation epoch, not a propagation delay or TOA measurement.
Likewise, an RX label is provenance, not a calibrated detection likelihood.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class FeatureAudit:
    scans: int
    tracks: int
    observations: int
    toa_observations: int
    joint_toa_doppler_covariances: int
    calibrated_rx_likelihoods: int
    relative_timing_observations: int
    timing_covariances: int
    declared_aliases: int
    declared_discontinuities: int

    def as_dict(self) -> dict[str, int]:
        return self.__dict__.copy()


def _present_number(row: dict[str, Any], names: Iterable[str]) -> bool:
    return any(isinstance(row.get(name), (int, float)) for name in names)


def audit_evidence_documents(documents: Iterable[dict[str, Any]]) -> FeatureAudit:
    counts = {field: 0 for field in FeatureAudit.__dataclass_fields__}
    for document in documents:
        counts["scans"] += 1
        for track in document.get("tracks", []):
            counts["tracks"] += 1
            samples = len(track.get("times_utc_ns", []))
            counts["observations"] += samples
            # Only explicit measurement fields count. Observation timestamps are
            # excluded because they do not measure signal travel time.
            if _present_number(track, ("toa_s", "delay_s", "pseudorange_s")):
                counts["toa_observations"] += samples
            covariance = track.get("toa_doppler_covariance")
            if isinstance(covariance, list) and covariance:
                counts["joint_toa_doppler_covariances"] += 1
            calibration = track.get("receiver_membership_calibration")
            if isinstance(calibration, dict) and calibration.get("status") == "calibrated":
                counts["calibrated_rx_likelihoods"] += 1
            if _present_number(track, ("relative_toa_s", "tdoa_s")):
                counts["relative_timing_observations"] += samples
            timing_covariance = track.get("timing_covariance_s2")
            if isinstance(timing_covariance, (int, float)) and timing_covariance > 0:
                counts["timing_covariances"] += 1
            counts["declared_aliases"] += len(track.get("aliases", []))
            counts["declared_discontinuities"] += len(track.get("discontinuities", []))
    return FeatureAudit(**counts)


def model_decisions(audit: FeatureAudit) -> dict[str, dict[str, Any]]:
    m6_ready = (
        audit.toa_observations > 0 and audit.joint_toa_doppler_covariances > 0
    )
    m7_ready = audit.calibrated_rx_likelihoods > 0
    m10_ready = (
        audit.relative_timing_observations > 0 and audit.timing_covariances > 0
    )
    return {
        "M6": {
            "method": "joint_waveform_toa_doppler",
            "status": "feasible" if m6_ready else "not_evaluated_missing_qualified_input",
            "required_fields": ["explicit waveform TOA/delay", "joint TOA-Doppler covariance"],
            "reason": None if m6_ready else "track exports contain Doppler samples and observation epochs, but no range-like TOA or joint covariance",
            "matched_control": "Doppler-only on identical observations",
        },
        "M7": {
            "method": "calibrated_receiver_membership",
            "status": "feasible" if m7_ready else "not_evaluated_failed_calibration_transfer",
            "required_fields": ["pre-scan held receiver-membership calibration", "pose/RX mapping continuity"],
            "reason": None if m7_ready else "receiver IDs are provenance only; existing nominal-geometry corrections failed their causal held gate",
            "weak_comparator": "uncalibrated RX-label indicator, diagnostic only; never interpret as detection probability or promote geographically",
        },
        "M10": {
            "method": "relative_timing_doppler",
            "status": "feasible" if m10_ready else "not_evaluated_missing_qualified_input",
            "required_fields": ["same-source relative TOA/TDOA", "relative timing covariance", "qualified shared-clock semantics"],
            "reason": None if m10_ready else "no relative propagation-delay measurement or covariance is exported; host timestamps cannot substitute",
            "matched_control": "Doppler-only on identical paired support",
        },
    }


def build_receipt(paths: list[Path]) -> dict[str, Any]:
    documents = [json.loads(path.read_text()) for path in paths]
    audit = audit_evidence_documents(documents)
    receipt = {
        "schema": "sacramento-feature-feasibility/v1",
        "scope": "derived evidence only; no IQ read and no RF collection",
        "reference_coordinate_accessed": False,
        "inputs": [str(path) for path in paths],
        "audit": audit.as_dict(),
        "models": model_decisions(audit),
        "supplemental_existing_data_audit": {
            "literature": {
                "paths": [
                    "docs/research/starlink-literature/review.md",
                    "docs/research/starlink-literature/broad-review-2026-09-28.md",
                    "docs/research/starlink-literature/identity-timing-orbit.md",
                    "docs/research/starlink-literature/datasets.md",
                ],
                "finding": "published methods establish that full-waveform synchronization can estimate TOA and Doppler, but precise receiver TOA is not broadcast time or absolute range",
                "role": "method support only; external exemplars are not observations from the selected Sacramento recordings",
            },
            "pilot_products": {
                "paths": [
                    "reports/2026_09_29_ds10_signal_extension/README.md",
                    "reports/2026_09_29_ds10_signal_extension/RECEIVER_COMBINING.md",
                    "reports/2026_09_29_ds10_signal_extension/local/qualified-tracks.json",
                    "reports/2026_09_29_ds10_signal_extension/local/paired-summary.json",
                ],
                "finding": "bounded excerpts contain pilot-selected frame timing, CFO and paired receiver waveform products, but no validated propagation-delay/TOA observable, joint TOA-Doppler covariance, decoded transmit epoch or full frozen-panel coverage",
                "consequence": "useful waveform evidence exists, but M6 and M10 cannot receive a matched 32-scan geographic evaluation without a new qualified extraction and calibration experiment",
            },
            "timing_metadata": {
                "paths": [
                    "reports/2026_09_29_timing_authority/README.md",
                    "reports/2026_09_29_timing_authority/results.json",
                    "reports/2026_09_29_weak_frame_timing/README.md",
                ],
                "finding": "host begin-session brackets anchor sample epochs coarsely but provide no capture-level GNSS/PPS UTC accuracy or propagation delay; weak-frame timing searches did not improve held pilot prediction",
                "consequence": "host timestamps must not be substituted for TOA/TDOA covariance",
            },
            "receiver_calibration": {
                "paths": [
                    "reports/2026_09_30_rx_causal_response/README.md",
                    "reports/2026_09_30_rx_causal_geometry/README.md",
                ],
                "finding": "causal occupancy prediction is real but is not a satellite detector; nominal geometry corrections lost to that baseline and failed their transfer gate",
                "consequence": "M7 remains a failed-calibration-transfer outcome; an RX-label diagnostic is not a geographic likelihood",
            },
        },
        "invariants": [
            "observation UTC is not TOA",
            "receiver_id is not a calibrated membership likelihood",
            "empty alias/discontinuity arrays do not prove absence when exports declare them unrecoverable",
            "unsupported models produce no position estimate",
        ],
    }
    selection_path = Path(__file__).with_name("selection.json")
    inventory_path = Path(__file__).with_name("inventory.json")
    if selection_path.exists() and inventory_path.exists():
        selection = json.loads(selection_path.read_text())
        selected_units = {
            row["unit_id"]
            for rows in selection["selected"].values()
            for row in rows
        }
        audited_units = {path.stem for path in paths}
        pending = sorted(selected_units - audited_units)
        receipt["panel_binding"] = {
            "selection_sha256": "sha256:" + hashlib.sha256(selection_path.read_bytes()).hexdigest(),
            "requested_scans": sum(selection["counts"].values()),
            "audited_ready_scans": len(selected_units & audited_units),
            "pending_source_exports": pending,
            "scope_note": "exact frozen panel; feature audit currently covers ready derived evidence only",
        }
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = build_receipt(args.evidence)
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
