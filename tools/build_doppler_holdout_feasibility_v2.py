#!/usr/bin/env python3
"""Build the frozen response-blind Doppler holdout feasibility revision."""

from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import time
from collections import Counter
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.research.doppler_dataset_policy import (  # noqa: E402
    load_doppler_dataset_policy,
)
from leo.analysis.research.doppler_holdout_manifest import (  # noqa: E402
    load_derived_holdout_manifest,
)
from leo.analysis.research.doppler_holdout_selector_v2 import (  # noqa: E402
    MANIFEST_SCHEMA,
    DopplerHoldoutDerivedManifestV2,
    disposition_from_v1,
    load_holdout_protocol_v2,
    sha256_bytes,
    validate_derived_manifest_v2,
    validate_protocol_authority_v2,
)
from leo.contracts.digests import canonical_digest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config/analysis/doppler-experiment-dataset-policy-v1.json"
DEFAULT_PROTOCOL = ROOT / "config/analysis/doppler-holdout-feasibility-protocol-v2.json"
DEFAULT_OUTPUT = ROOT / "reports/figures/2026_08_26_doppler_holdout_selector_v2"
SELECTOR_PATHS = (
    "config/analysis/doppler-holdout-feasibility-protocol-v2.json",
    "src/leo/analysis/research/doppler_holdout_selector_v2.py",
    "tools/build_doppler_holdout_feasibility_v2.py",
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"
    ).encode()


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _protocol_commit() -> str:
    result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if len(commit) != 40 or any(value not in "0123456789abcdef" for value in commit):
        raise ValueError("repository HEAD is not one exact Git commit")
    for relative in SELECTOR_PATHS:
        path = ROOT / relative
        frozen = subprocess.run(
            ("git", "show", f"HEAD:{relative}"),
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        if path.read_bytes() != frozen:
            raise ValueError(f"protocol implementation differs from HEAD: {relative}")
    return commit


def _failure_ledger(manifest: DopplerHoldoutDerivedManifestV2) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=(
            "session_id",
            "status",
            "eligible_target_count",
            "eligible_target_span_ms",
            "failed_capture_gates",
            "ineligible_target_reason_counts",
            "recording_manifest_sha256",
            "analysis_run_id",
            "analysis_manifest_sha256",
            "inherited_v1_disposition_digest",
            "target_mask_digest",
        ),
        lineterminator="\n",
    )
    writer.writeheader()
    for capture in manifest.captures:
        reasons = Counter(
            reason for target in capture.target_mask for reason in target.rejection_reasons
        )
        writer.writerow(
            {
                "session_id": capture.session_id,
                "status": capture.status,
                "eligible_target_count": capture.eligible_target_count,
                "eligible_target_span_ms": f"{capture.eligible_target_span_ms:.9f}",
                "failed_capture_gates": ";".join(capture.failed_capture_gates),
                "ineligible_target_reason_counts": ";".join(
                    f"{key}={value}" for key, value in sorted(reasons.items())
                ),
                "recording_manifest_sha256": capture.recording_manifest_sha256,
                "analysis_run_id": capture.analysis_run_id,
                "analysis_manifest_sha256": capture.analysis_manifest_sha256,
                "inherited_v1_disposition_digest": capture.inherited_v1_disposition_digest,
                "target_mask_digest": capture.target_mask_digest,
            }
        )
    return buffer.getvalue().encode()


def _render_accounting(manifest: DopplerHoldoutDerivedManifestV2) -> bytes:
    labels = [item.session_id[-12:] for item in manifest.captures]
    eligible = np.asarray([item.eligible_target_count for item in manifest.captures])
    spans = np.asarray([item.eligible_target_span_ms for item in manifest.captures])
    colors = ["#16835d" if item.status == "evaluable" else "#c2413b" for item in manifest.captures]
    positions = np.arange(len(labels))
    figure = Figure(figsize=(14.0, 8.0), constrained_layout=True)
    axes = figure.subplots(2, 1, sharex=True)
    axes[0].bar(positions, eligible, color=colors)
    axes[0].axhline(75, color="#374151", linestyle="--", label="frozen minimum: 75")
    axes[0].set_ylabel("Eligible identical-mask targets")
    axes[0].set_title(
        f"Response-blind target-history feasibility: {manifest.evaluable_capture_count}/15 captures"
    )
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend(loc="upper right")
    axes[1].bar(positions, spans, color=colors)
    axes[1].axhline(250, color="#374151", linestyle="--", label="frozen minimum: 250 ms")
    axes[1].set_ylabel("Eligible-target span (ms)")
    axes[1].set_xticks(positions, labels, rotation=45, ha="right")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend(loc="upper right")
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=170)
    return buffer.getvalue()


def _render_reasons(manifest: DopplerHoldoutDerivedManifestV2) -> bytes:
    labels = [item.session_id[-12:] for item in manifest.captures]
    reason_labels = (
        "target_even_qin_unsupported",
        "history_20ms_count",
        "history_20ms_span",
        "history_125ms_count",
        "history_125ms_span",
        "history_500ms_count",
        "history_500ms_span",
    )
    values = np.asarray(
        [
            [
                sum(reason in target.rejection_reasons for target in capture.target_mask)
                for reason in reason_labels
            ]
            for capture in manifest.captures
        ],
        dtype=float,
    )
    figure = Figure(figsize=(14.0, 6.8), constrained_layout=True)
    axis = figure.subplots()
    image = axis.imshow(values.T, aspect="auto", cmap="Blues")
    axis.set_xticks(np.arange(len(labels)), labels, rotation=45, ha="right")
    axis.set_yticks(
        np.arange(len(reason_labels)),
        [item.replace("_", " ") for item in reason_labels],
    )
    axis.set_title("Retained response-blind target rejections (reasons overlap)")
    for row in range(values.shape[1]):
        for column in range(values.shape[0]):
            value = int(values[column, row])
            axis.text(
                column,
                row,
                str(value),
                ha="center",
                va="center",
                fontsize=7.5,
                color="white" if value > values.max() * 0.55 else "#111827",
            )
    figure.colorbar(image, ax=axis, label="Target opportunities")
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=170)
    return buffer.getvalue()


def main() -> int:
    args = _arguments()
    started = time.monotonic()
    commit = _protocol_commit()
    policy_payload = args.policy.read_bytes()
    protocol_payload = args.protocol.read_bytes()
    policy = load_doppler_dataset_policy(args.policy)
    protocol = load_holdout_protocol_v2(protocol_payload)
    frozen_path = ROOT / protocol.frozen_v1_input.path
    frozen_payload = frozen_path.read_bytes()
    frozen_v1 = load_derived_holdout_manifest(frozen_payload)
    validate_protocol_authority_v2(
        protocol,
        policy,
        policy_sha256=sha256_bytes(policy_payload),
        frozen_v1_payload=frozen_payload,
        frozen_v1=frozen_v1,
    )
    dispositions = tuple(
        disposition_from_v1(item, protocol=protocol) for item in frozen_v1.captures
    )
    evaluable = sum(item.status == "evaluable" for item in dispositions)
    values = {
        "schema": MANIFEST_SCHEMA,
        "phase": "feasibility_revision_only",
        "protocol_repository_commit": commit,
        "protocol_configuration_sha256": sha256_bytes(protocol_payload),
        "selector_implementation_sha256": _sha256(Path(__file__)),
        "manifest_contract_implementation_sha256": _sha256(
            ROOT / "src/leo/analysis/research/doppler_holdout_selector_v2.py"
        ),
        "dataset_policy_repository_commit": protocol.dataset_policy_repository_commit,
        "dataset_policy_sha256": protocol.dataset_policy_sha256,
        "inventory_sha256": policy.inventory_sha256,
        "frozen_v1_file_sha256": protocol.frozen_v1_input.file_sha256,
        "frozen_v1_semantic_manifest_digest": (protocol.frozen_v1_input.semantic_manifest_digest),
        "experiment_role": "holdout_foundation",
        "future_odd_qin_outcomes_opened": False,
        "odd_qin_symbols_demodulated_or_scored": False,
        "candidate_estimators_run": False,
        "bulk_storage_accessed": False,
        "raw_iq_accessed": False,
        "capture_count": 15,
        "evaluable_capture_count": evaluable,
        "minimum_evaluable_capture_count": 10,
        "launch_gate": "pass" if evaluable >= 10 else "fail",
        "runtime_seconds": time.monotonic() - started,
        "captures": [item.model_dump(mode="json") for item in dispositions],
    }
    manifest = DopplerHoldoutDerivedManifestV2.model_validate(
        {**values, "manifest_digest": canonical_digest(values)}
    )
    validate_derived_manifest_v2(manifest, protocol, frozen_v1)

    output = args.output_root.resolve()
    qnap = Path("/mnt/qnap01").resolve()
    if output == qnap or qnap in output.parents:
        raise ValueError("v2 output cannot be written beneath read-only QNAP")
    manifest_bytes = _json_bytes(manifest.model_dump(mode="json"))
    ledger_bytes = _failure_ledger(manifest)
    accounting_bytes = _render_accounting(manifest)
    reasons_bytes = _render_reasons(manifest)
    generated = {
        "derived_manifest": ("derived-manifest-v2.json", manifest_bytes),
        "failure_ledger": ("failure-ledger.csv", ledger_bytes),
        "accounting_figure": ("target-accounting.png", accounting_bytes),
        "rejection_figure": ("target-rejections.png", reasons_bytes),
    }
    for _, (name, payload) in generated.items():
        _write(output / name, payload)
    receipt = {
        "schema": "org.leo.research.doppler-holdout-selector-v2-audit/v1",
        "protocol_repository_commit": commit,
        "protocol_configuration_sha256": sha256_bytes(protocol_payload),
        "selector_implementation_sha256": _sha256(Path(__file__)),
        "manifest_contract_implementation_sha256": _sha256(
            ROOT / "src/leo/analysis/research/doppler_holdout_selector_v2.py"
        ),
        "frozen_v1_file_sha256": protocol.frozen_v1_input.file_sha256,
        "frozen_v1_semantic_manifest_digest": protocol.frozen_v1_input.semantic_manifest_digest,
        "bulk_storage_accessed": False,
        "raw_iq_accessed": False,
        "future_odd_qin_outcomes_opened": False,
        "odd_qin_symbols_demodulated_or_scored": False,
        "candidate_estimators_run": False,
        "capture_count": 15,
        "evaluable_capture_count": evaluable,
        "launch_gate": manifest.launch_gate,
        "derived_manifest_digest": manifest.manifest_digest,
        "artifacts": {
            key: {"path": name, "bytes": len(payload), "sha256": sha256_bytes(payload)}
            for key, (name, payload) in generated.items()
        },
    }
    _write(output / "audit-receipt.json", _json_bytes(receipt))
    print(
        json.dumps(
            {
                "protocol_commit": commit,
                "capture_count": 15,
                "evaluable_capture_count": evaluable,
                "launch_gate": manifest.launch_gate,
                "runtime_seconds": manifest.runtime_seconds,
                "output_root": str(output),
            },
            sort_keys=True,
        )
    )
    return 0 if manifest.launch_gate == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
