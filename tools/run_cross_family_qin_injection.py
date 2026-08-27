#!/usr/bin/env python3
"""Run the frozen paired orbit/radio Qin injection on three hard-null spans."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import zstandard as zstd

from leo.analysis.research.cross_family_injection_experiment import (
    CrossFamilyInjectedArmEvidence,
    CrossFamilyInjectedPairEvidence,
    CrossFamilyObservationRow,
    generate_cross_family_injected_evidence,
)
from leo.analysis.research.cross_family_injection_protocol import (
    CrossFamilyInjectionProtocol,
    load_cross_family_injection_protocol,
)
from leo.analysis.research.cross_family_orbit_truth import (
    VerifiedCrossFamilyTruthPair,
    build_verified_cross_family_truth,
)
from leo.analysis.research.doppler_dataset_policy import (
    CaptureDisposition,
    authorize_manifest_files,
    finalize_capture_dispositions,
    load_doppler_dataset_policy,
    verify_policy_inventory,
)
from leo.analysis.research.polynomial_injection_protocol import BackgroundSpan
from leo.analysis.starlink.local_doppler import stable_measurement_floats

DEFAULT_POLICY = Path("config/analysis/doppler-experiment-dataset-policy-v1.json")
DEFAULT_PROTOCOL = Path("config/analysis/satellite-pnt-cross-family-injection-protocol-v1.json")
DEFAULT_AMENDMENT = Path("config/analysis/satellite-pnt-cross-family-injection-execution-v1.json")
DEFAULT_OUTPUT = Path("reports/figures/2026_08_27_satellite_pnt_cross_family_injection_v1")
DEFAULT_REPORT = Path("reports/2026_08_27_satellite_pnt_cross_family_injection_results.md")
_AMENDMENT_SCHEMA = "org.leo.research.satellite-pnt-cross-family-injection-execution/v1"


@dataclass(frozen=True, slots=True)
class VerifiedBackground:
    binding: BackgroundSpan
    samples: np.ndarray
    span_sha256: str
    background_power: float
    compressed_bytes_read: int
    uncompressed_bytes_verified: int


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--execution-amendment", type=Path, default=DEFAULT_AMENDMENT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify frozen code, protocol, and response-free TLE truth without reading IQ",
    )
    return parser.parse_args()


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_complex_sha256(values: np.ndarray) -> str:
    return _sha256_bytes(np.asarray(values, dtype="<c8").tobytes(order="C"))


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            stable_measurement_floats(value),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _git_head(repository_root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_tree(repository_root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_is_ancestor(repository_root: Path, ancestor: str, descendant: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=repository_root,
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )


def _implementation_paths(repository_root: Path) -> tuple[Path, ...]:
    return (
        Path(__file__).resolve(),
        repository_root / "src/leo/analysis/research/trajectory_qin_injection.py",
        repository_root / "src/leo/analysis/research/cross_family_injection_protocol.py",
        repository_root / "src/leo/analysis/research/cross_family_orbit_truth.py",
        repository_root / "src/leo/analysis/research/cross_family_injection_experiment.py",
        repository_root / "src/leo/analysis/research/polynomial_injection.py",
        repository_root / "src/leo/analysis/qam/pilot.py",
        repository_root / "src/leo/analysis/starlink/templates.py",
        repository_root / "src/leo/analysis/research/doppler_dataset_policy.py",
    )


def _validate_execution_authority(
    repository_root: Path,
    amendment_path: Path,
    *,
    protocol_path: Path,
    output_root: Path,
    report_path: Path,
) -> dict[str, object]:
    if not amendment_path.is_file():
        raise ValueError("execution requires the frozen hash-bound amendment")
    value = json.loads(amendment_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != _AMENDMENT_SCHEMA:
        raise ValueError("execution amendment schema differs")
    head = _git_head(repository_root)
    implementation_commit = value.get("implementation_commit")
    if not isinstance(implementation_commit, str) or not _git_is_ancestor(
        repository_root, implementation_commit, head
    ):
        raise ValueError("execution implementation is not an ancestor of HEAD")
    if value.get("protocol_path") != str(protocol_path):
        raise ValueError("execution amendment names another protocol path")
    if value.get("protocol_sha256") != _sha256_file(repository_root / protocol_path):
        raise ValueError("execution amendment protocol hash differs")
    expected_outputs = value.get("exclusive_outputs")
    if expected_outputs != {
        "output_root": str(output_root),
        "report": str(report_path),
    }:
        raise ValueError("execution amendment output paths differ")
    hashes = value.get("implementation_sha256")
    if not isinstance(hashes, dict) or set(hashes) != {
        str(path.relative_to(repository_root)) for path in _implementation_paths(repository_root)
    }:
        raise ValueError("execution amendment implementation inventory differs")
    for relative, expected in hashes.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("execution amendment hash binding is malformed")
        if _sha256_file(repository_root / relative) != expected:
            raise ValueError(f"execution amendment hash differs: {relative}")
    if value.get("execution_authorized") is not True:
        raise ValueError("execution amendment does not authorize the frozen run")
    return {
        "path": str(amendment_path),
        "sha256": _sha256_file(amendment_path),
        "implementation_commit": implementation_commit,
        "repository_head": head,
    }


def _read_verified_background(background: BackgroundSpan, *, policy: Any) -> VerifiedBackground:
    authorize_manifest_files(
        policy,
        experiment_role="polynomial_injection",
        session_id=background.session_id,
        analysis_run_id=background.analysis_run_id,
        recording_manifest_path=background.recording_manifest_path,
        analysis_manifest_path=background.analysis_manifest_path,
    )
    if _sha256_file(background.recording_manifest_path) != background.recording_manifest_sha256:
        raise ValueError(f"recording manifest digest differs: {background.session_id}")
    if _sha256_file(background.analysis_manifest_path) != background.analysis_manifest_sha256:
        raise ValueError(f"analysis manifest digest differs: {background.session_id}")
    manifest = json.loads(background.recording_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("session_id") != background.session_id:
        raise ValueError(f"recording manifest identity differs: {background.session_id}")
    streams = manifest.get("streams")
    if not isinstance(streams, list):
        raise ValueError(f"recording manifest has no streams: {background.session_id}")
    matches = [
        item
        for item in streams
        if isinstance(item, dict) and item.get("stream_id") == background.stream_id
    ]
    if len(matches) != 1:
        raise ValueError(f"recording stream binding is ambiguous: {background.session_id}")
    stream = matches[0]
    radio = stream.get("radio")
    applied = stream.get("applied_settings")
    continuity = stream.get("continuity")
    chunks = stream.get("chunks")
    if not all(isinstance(item, dict) for item in (radio, applied, continuity)):
        raise ValueError(f"recording stream metadata is incomplete: {background.session_id}")
    assert isinstance(radio, dict) and isinstance(applied, dict) and isinstance(continuity, dict)
    receiver_ids = applied.get("receiver_ids")
    if (
        radio.get("radio_id") != background.radio_id
        or radio.get("serial") != background.radio_serial
        or applied.get("sample_rate_hz") != background.sample_rate_hz
        or not isinstance(receiver_ids, list)
        or background.receiver_id not in receiver_ids
    ):
        raise ValueError(f"recording hardware binding differs: {background.session_id}")
    lossless = (
        continuity.get("sample_loss_observable") is True
        and continuity.get("gap_count") == 0
        and continuity.get("missing_sample_count") == 0
        and continuity.get("overflow_count") == 0
        and continuity.get("enqueue_failure_count") == 0
        and continuity.get("clipped_sample_count") == 0
        and continuity.get("constant_iq_refill_count") == 0
        and continuity.get("terminal_rejected_gap_count") == 0
        and continuity.get("terminal_rejected_missing_sample_count") == 0
        and continuity.get("terminal_rejected_overflow_count") == 0
        and continuity.get("segment_count") == 1
        and continuity.get("observed_sample_count") == stream.get("captured_sample_count")
        and continuity.get("device_span_sample_count") == stream.get("captured_sample_count")
        and stream.get("state") == "complete"
    )
    if not lossless or not isinstance(chunks, list):
        raise ValueError(f"recording is not lossless and complete: {background.session_id}")
    chunk_matches = [
        item
        for item in chunks
        if isinstance(item, dict) and item.get("chunk_index") == background.chunk.chunk_index
    ]
    if len(chunk_matches) != 1:
        raise ValueError(f"recording chunk binding is ambiguous: {background.session_id}")
    chunk = chunk_matches[0]
    expected = (
        background.chunk.sample_start,
        background.chunk.sample_count,
        background.chunk.relative_path,
        background.chunk.compressed_sha256,
        background.chunk.uncompressed_sha256,
        "ci16_le",
        "sample_receiver_iq",
    )
    actual = (
        chunk.get("sample_start"),
        chunk.get("sample_count"),
        chunk.get("relative_path"),
        chunk.get("compressed_sha256"),
        chunk.get("uncompressed_sha256"),
        chunk.get("sample_format"),
        chunk.get("sample_layout"),
    )
    if actual != expected:
        raise ValueError(f"recording chunk fields differ: {background.session_id}")
    capture_root = background.recording_manifest_path.parent.resolve()
    chunk_path = (capture_root / background.chunk.relative_path).resolve()
    if not chunk_path.is_relative_to(capture_root):
        raise ValueError("chunk path escapes the exact recording root")
    compressed = chunk_path.read_bytes()
    if _sha256_bytes(compressed) != background.chunk.compressed_sha256:
        raise ValueError(f"compressed chunk digest differs: {background.session_id}")
    uncompressed_bytes = chunk.get("uncompressed_bytes")
    if not isinstance(uncompressed_bytes, int) or uncompressed_bytes <= 0:
        raise ValueError(f"uncompressed chunk size is invalid: {background.session_id}")
    payload = zstd.ZstdDecompressor().decompress(compressed, max_output_size=uncompressed_bytes)
    if (
        len(payload) != uncompressed_bytes
        or _sha256_bytes(payload) != background.chunk.uncompressed_sha256
    ):
        raise ValueError(f"uncompressed chunk differs: {background.session_id}")
    raw = np.frombuffer(payload, dtype="<i2")
    receiver_count = len(receiver_ids)
    if raw.size != background.chunk.sample_count * receiver_count * 2:
        raise ValueError(f"CI16 chunk geometry differs: {background.session_id}")
    cube = raw.reshape(background.chunk.sample_count, receiver_count, 2)
    receiver_column = receiver_ids.index(background.receiver_id)
    offset = background.sample_start - background.chunk.sample_start
    selected = cube[offset : offset + background.sample_count, receiver_column]
    if selected.shape != (background.sample_count, 2):
        raise ValueError(f"frozen background span is incomplete: {background.session_id}")
    samples = np.asarray(
        (selected[:, 0].astype(np.float32) + 1j * selected[:, 1].astype(np.float32)) / 32_768.0,
        dtype=np.complex64,
    )
    power = float(np.mean(np.abs(samples.astype(np.complex128)) ** 2))
    if not math.isfinite(power) or power <= np.finfo(float).tiny:
        raise ValueError(f"frozen background has no finite power: {background.session_id}")
    return VerifiedBackground(
        binding=background,
        samples=samples,
        span_sha256=_canonical_complex_sha256(samples),
        background_power=power,
        compressed_bytes_read=len(compressed),
        uncompressed_bytes_verified=len(payload),
    )


def _arm_payload(value: CrossFamilyInjectedArmEvidence) -> dict[str, Any]:
    payload = asdict(value)
    payload.pop("frame_evidence", None)
    return payload


def _pair_payload(value: CrossFamilyInjectedPairEvidence) -> dict[str, object]:
    return {
        "pair_id": value.pair_id,
        "background_session_id": value.background_session_id,
        "orbit": _arm_payload(value.orbit),
        "radio": _arm_payload(value.radio),
        "occupancy_identical": value.occupancy_identical,
        "pair_evidence_digest": value.pair_evidence_digest,
        "independent_unit": value.independent_unit,
        "independent_unit_count": value.independent_unit_count,
        "identity_claimed": value.identity_claimed,
        "threshold_fitted": value.threshold_fitted,
    }


def _arm_summary(arm: CrossFamilyInjectedArmEvidence) -> dict[str, object]:
    rows = arm.observation_rows
    training = [item for item in rows if item.split == "training-even-qin" and item.usable]
    future = [item for item in rows if item.split == "future-odd-qin" and item.usable]

    def rms(items: list[CrossFamilyObservationRow]) -> float | None:
        residuals = [item.residual_hz for item in items if item.residual_hz is not None]
        return None if not residuals else float(np.sqrt(np.mean(np.square(residuals))))

    return {
        "truth_family": arm.truth_family,
        "scenario_id": arm.scenario_id,
        "training_usable_count": len(training),
        "future_usable_count": len(future),
        "training_residual_rms_hz": rms(training),
        "future_residual_rms_hz": rms(future),
    }


def _report_bytes(result: dict[str, Any]) -> bytes:
    lines = [
        "# Satellite PNT paired cross-family Qin injection results",
        "",
        (
            "Status: opened-development known-truth measurement evidence; no model-selection "
            "gate, posterior odds, satellite identity, or positioning claim."
        ),
        "",
        (
            "The three rows below are the independent units. Each row contains a "
            "catalogue-orbit truth arm and a center-matched radio-linear truth arm on the "
            "same frozen hard-null background. The six arms are not six independent "
            "experiments."
        ),
        "",
        (
            "| Background pair | Orbit train/future usable | Orbit future RMS (Hz) | "
            "Radio train/future usable | Radio future RMS (Hz) |"
        ),
        "|---|---:|---:|---:|---:|",
    ]
    for pair in result["pair_summaries"]:
        orbit = pair["orbit"]
        radio = pair["radio"]
        orbit_counts = f"{orbit['training_usable_count']}/{orbit['future_usable_count']}"
        radio_counts = f"{radio['training_usable_count']}/{radio['future_usable_count']}"
        lines.append(
            f"| `{pair['pair_id']}` | {orbit_counts} | "
            f"{_display(orbit['future_residual_rms_hz'])} | "
            f"{radio_counts} | "
            f"{_display(radio['future_residual_rms_hz'])} |"
        )
    lines.extend(
        (
            "",
            (
                "The orbit truth objects were selected using TLE geometry only, before "
                "background IQ was read. Even Qin supplies training rows; odd Qin supplies "
                "future rows. Every opportunity and no-result is retained in the "
                "machine-readable evidence."
            ),
            "",
            (
                "This artifact measures the front-end response to paired known truth. "
                "Catalogue-versus-radio predictive discrimination and covariance scaling "
                "remain separate downstream analyses."
            ),
            "",
        )
    )
    return "\n".join(lines).encode("utf-8")


def _display(value: float | int | None) -> str:
    return "no-result" if value is None else f"{float(value):.6f}"


def _write_outputs(
    *,
    output_root: Path,
    report_path: Path,
    evidence: dict[str, Any],
    execution: dict[str, object],
) -> None:
    if output_root.exists() or report_path.exists():
        raise ValueError("canonical output paths must be absent before execution")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.with_name(output_root.name + f".staging-{os.getpid()}")
    if staging.exists():
        raise ValueError("staging output path already exists")
    staging.mkdir()
    evidence_bytes = _json_bytes(evidence)
    report_bytes = _report_bytes(evidence)
    execution = {
        **execution,
        "evidence_sha256": _sha256_bytes(evidence_bytes),
        "report_sha256": _sha256_bytes(report_bytes),
    }
    execution_bytes = _json_bytes(execution)
    manifest = {
        "schema": "org.leo.research.satellite-pnt-cross-family-injection-output/v1",
        "files": {
            "evidence.json": _sha256_bytes(evidence_bytes),
            "execution.json": _sha256_bytes(execution_bytes),
            str(report_path): _sha256_bytes(report_bytes),
        },
    }
    (staging / "evidence.json").write_bytes(evidence_bytes)
    (staging / "execution.json").write_bytes(execution_bytes)
    (staging / "manifest.json").write_bytes(_json_bytes(manifest))
    temporary_report = report_path.with_name(report_path.name + f".staging-{os.getpid()}")
    temporary_report.write_bytes(report_bytes)
    staging.rename(output_root)
    temporary_report.replace(report_path)


def main() -> None:
    args = _arguments()
    repository_root = Path.cwd().resolve()
    policy_path = args.policy.resolve()
    protocol_path = args.protocol.resolve()
    amendment_path = args.execution_amendment.resolve()
    output_root = args.output_root.resolve()
    report_path = args.report.resolve()
    relative_protocol = protocol_path.relative_to(repository_root)
    relative_output = output_root.relative_to(repository_root)
    relative_report = report_path.relative_to(repository_root)
    authority = _validate_execution_authority(
        repository_root,
        amendment_path,
        protocol_path=relative_protocol,
        output_root=relative_output,
        report_path=relative_report,
    )
    policy = load_doppler_dataset_policy(policy_path)
    verify_policy_inventory(policy, repository_root)
    protocol: CrossFamilyInjectionProtocol = load_cross_family_injection_protocol(
        protocol_path,
        dataset_policy=policy,
        repository_root=repository_root,
    )
    truth_pairs: list[VerifiedCrossFamilyTruthPair] = []
    for pair in protocol.pairs:
        truth_pairs.append(
            build_verified_cross_family_truth(
                pair,
                pair.tle_snapshot_path.read_bytes(),
                observer_site=protocol.observer_site,
                nominal_rf_hz=protocol.nominal_rf_hz,
                interpolation_spacing_s=protocol.interpolation_spacing_s,
                interpolation_maximum_error_hz=protocol.interpolation_maximum_error_hz,
            )
        )
    if args.verify_only:
        print(
            _json_bytes(
                {
                    "authority": authority,
                    "protocol_digest": protocol.protocol_digest,
                    "truth_digests": [item.truth_digest for item in truth_pairs],
                    "iq_read": False,
                }
            ).decode(),
            end="",
        )
        return
    if output_root.exists() or report_path.exists():
        raise ValueError("canonical output paths must be absent before IQ access")
    started_monotonic = time.monotonic()
    started_utc = datetime.now(UTC).isoformat()
    backgrounds: dict[str, VerifiedBackground] = {}
    dispositions: list[CaptureDisposition] = []
    for binding in protocol.base_protocol.backgrounds:
        verified = _read_verified_background(binding, policy=policy)
        backgrounds[binding.session_id] = verified
        dispositions.append(
            CaptureDisposition(
                capture=policy.capture(binding.session_id),
                status="evaluable",
                reason="exact manifest/chunk/span digest verified",
            )
        )
        print(f"verified {binding.session_id} {verified.span_sha256}", flush=True)
    finalize_capture_dispositions(
        policy,
        experiment_role="polynomial_injection",
        dispositions=dispositions,
    )
    paired: list[CrossFamilyInjectedPairEvidence] = []
    for pair, truth in zip(protocol.pairs, truth_pairs, strict=True):
        paired.append(
            generate_cross_family_injected_evidence(
                backgrounds[pair.background_session_id].samples,
                pair,
                truth,
                protocol,
            )
        )
        print(f"measured {pair.pair_id}", flush=True)
    completed_utc = datetime.now(UTC).isoformat()
    summaries = [
        {
            "pair_id": item.pair_id,
            "orbit": _arm_summary(item.orbit),
            "radio": _arm_summary(item.radio),
        }
        for item in paired
    ]
    evidence = {
        "schema": "org.leo.research.satellite-pnt-cross-family-injection-evidence/v1",
        "protocol_digest": protocol.protocol_digest,
        "protocol_sha256": _sha256_file(protocol_path),
        "independent_background_count": 3,
        "truth_arm_count": 6,
        "truth_receipts": [
            {
                "pair_id": item.pair_id,
                "catalog_number": item.true_catalog_number,
                "object_name": item.true_object_name,
                "visible_starlink_count": item.visible_starlink_count,
                "selected_centre_elevation_deg": item.selected_centre_elevation_deg,
                "orbit_interpolation_maximum_error_hz": item.orbit_interpolation_maximum_error_hz,
                "truth_digest": item.truth_digest,
            }
            for item in truth_pairs
        ],
        "backgrounds": [
            {
                "session_id": item.binding.session_id,
                "span_sha256": item.span_sha256,
                "background_power": item.background_power,
                "compressed_bytes_read": item.compressed_bytes_read,
                "uncompressed_bytes_verified": item.uncompressed_bytes_verified,
            }
            for item in backgrounds.values()
        ],
        "pair_summaries": summaries,
        "paired_evidence": [_pair_payload(item) for item in paired],
        "claim_boundary": {
            "mechanistic_descriptive_only": True,
            "formal_coverage_claimed": False,
            "threshold_fitted": False,
            "posterior_odds_produced": False,
            "identity_claimed": False,
            "positioning_validated": False,
        },
    }
    execution = {
        "schema": "org.leo.research.satellite-pnt-cross-family-injection-execution/v1",
        "authority": authority,
        "repository_head": _git_head(repository_root),
        "repository_tree": _git_tree(repository_root),
        "started_utc": started_utc,
        "completed_utc": completed_utc,
        "elapsed_s": time.monotonic() - started_monotonic,
        "exit_status": 0,
        "iq_read": True,
        "new_rf_collection": False,
    }
    _write_outputs(
        output_root=output_root,
        report_path=report_path,
        evidence=evidence,
        execution=execution,
    )


if __name__ == "__main__":
    main()
