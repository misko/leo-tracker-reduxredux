"""Bounded saved-IQ numerical parity, not an adaptive RF or sensitivity trial.

The first archived dwell per rate/edge is selected without consulting scores.
Only RX1 was archived: RX0 is explicitly zero-filled and all adaptive receipt
metadata is synthetic. Neither fixture is published as a real recording.
Run manually with an explicit source and new output directory; no radio access.
"""

from __future__ import annotations

import argparse
import gzip
import json
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    AdaptiveHopAnalysisSource,
    analyze_adaptive_hop_visit,
    validate_adaptive_analysis_binding,
)
from leo.scanner.adaptive_hop_ports import AdaptiveHopVisitBlock
from leo.scanner.adaptive_hop_products import AdaptiveHopAnalysisBindingV1
from leo.scanner.detector import analyze_glrt64_dwell
from leo.scanner.persistent_hop_analysis import PersistentHopGlrt64Configuration
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from tests.scanner.adaptive_hop_fixtures import receipt_fixture, timing_fixture
from tools.evaluate_presence_window_rank import load_dwells

_INPUT_SHA = "572f502a0209c0171bcd7527b7f205f29f6669cecda4bca261c353adb184e3cd"
_RESULT_SHA = "0e473850bc02da46a5d1ee6c92de2d6dd1d9d42b2f31b5ea124b7ad54a063c02"


class ReplayReader:
    def __init__(self, metadata: dict, iq: np.ndarray):
        target = metadata["channel"] - 1 + (4 if metadata["edge"] == "upper" else 0)
        self.index = target
        self.receipt = receipt_fixture(
            rate=metadata["rate_hz"],
            mode="shadow",
            count=target + 2,
            session_id=f"synthetic-parity-{metadata['rate_hz']}-{metadata['edge']}",
        )
        self.session_id = self.receipt.session_id
        # A binding of the synthetic input, never the original recording digest.
        self.input_manifest_sha256 = sha256_digest(
            canonical_json_bytes(
                {
                    "receipt": self.receipt.model_dump(mode="json"),
                    "saved_rx1_ci16_sha256": sha256_digest(iq.tobytes()),
                    "rx0": "synthetic-zero",
                }
            )
        )
        self.values = np.zeros((len(iq), 2, 2), dtype="<i2")
        self.values[:, 1, :] = iq

    def read_visit_ci16(self, index):
        if index != self.index:
            raise ValueError("replay contains only the explicitly selected saved dwell")
        return self.receipt.visits[index], self.values


def compare_candidates(product, reference):
    """Check every numerical field, including integer audit and abstentions."""
    if len(product.probes) != len(reference.probes):
        raise AssertionError("probe inventory changed")
    total = complete = unavailable = changed_winners = 0
    for actual, expected in zip(product.probes, reference.probes, strict=True):
        if (actual.receiver_id, actual.probe_index, actual.probe_start_ms) != (
            expected.receiver_id,
            expected.probe_index,
            expected.probe_start_ms,
        ) or actual.candidate_count != len(expected.candidates):
            raise AssertionError("probe identity/candidate inventory changed")
        by_rank = {c.candidate_rank: c for c in expected.candidates}
        for candidate in actual.candidates:
            old = by_rank[candidate.candidate_rank]
            checks = {
                "integer_epoch_sample": "epoch_sample",
                "acquired_cfo_hz": "acquired_cfo_hz",
                "integer_residual_cfo_hz": "residual_cfo_hz",
                "integer_tracking_cfo_hz": "tracking_cfo_hz",
                "integer_exact_score": "exact_score",
                "integer_control_score": "control_score",
                "integer_margin": "margin",
            }
            checks.update(
                {
                    key: key
                    for key in (
                        "fractional_epoch_offset_samples",
                        "fractional_residual_cfo_hz",
                        "fractional_tracking_cfo_hz",
                        "fractional_exact_score",
                        "fractional_control_score",
                        "fractional_margin",
                    )
                }
            )
            if old.fractional_epoch_status != "complete" or any(
                getattr(candidate, new) != getattr(old, source) for new, source in checks.items()
            ):
                raise AssertionError("fractional/diagnostic numerical parity changed")
            complete += 1
        for candidate in actual.unavailable_candidates:
            old = by_rank[candidate.candidate_rank]
            fields = (
                old.fractional_epoch_offset_samples,
                old.fractional_residual_cfo_hz,
                old.fractional_tracking_cfo_hz,
                old.fractional_exact_score,
                old.fractional_control_score,
                old.fractional_margin,
            )
            incomplete = old.fractional_epoch_status != "complete" or None in fields
            if candidate.fractional_epoch_status != old.fractional_epoch_status:
                raise AssertionError("unavailable source status changed")
            if candidate.reason == "fractional_incomplete" and not incomplete:
                raise AssertionError("complete candidate silently discarded")
            if candidate.reason == "outside_retained_interval":
                local = actual.probe_start_ms * product.configuration.sample_rate_hz // 1000
                if incomplete or 0 <= local + old.epoch_sample + fields[0] < (
                    product.configuration.dwell_samples
                ):
                    raise AssertionError("retained candidate silently discarded")
            unavailable += 1
        old_best = max(
            expected.candidates, key=lambda c: (c.margin, -c.candidate_rank), default=None
        )
        changed_winners += actual.winning_candidate_rank != (
            old_best.candidate_rank if old_best else None
        )
        total += len(expected.candidates)
    return {
        "candidates": total,
        "fractional_complete": complete,
        "unavailable": unavailable,
        "integer_vs_fractional_winner_changes": changed_winners,
    }


def exercise_storage_and_cli(reader: ReplayReader, product, output: Path) -> dict:
    """Actual saved RX1 through the public codec, CLI, resume and sealed metrics.

    Nonselected fixture visits are zero-filled on both RX, and receipt/UTC
    metadata is modelled. Only this new temporary root is written.
    """
    output.mkdir()
    captures = AdaptiveHopIqStore(output)
    writer = captures.begin(reader.session_id, reader.receipt.plan)
    try:
        for visit in reader.receipt.visits:
            values = np.zeros((visit.valid_sample_count, 2), dtype=np.complex64)
            if visit.event.visit_index == reader.index:
                values.real, values.imag = reader.values[:, :, 0], reader.values[:, :, 1]
            writer.append(AdaptiveHopVisitBlock(values, (0, 1), visit))
        published = writer.finish(reader.receipt, timing=timing_fixture(reader.receipt))
        captures.verify(reader.session_id)
    except BaseException:
        writer.abort()
        raise
    finally:
        captures.close()
    executions = []
    for run, budget in enumerate((1, 2500, 2500)):
        command = [
            sys.executable,
            "-m",
            "leo.cli.adaptive_hop_analysis",
            "--bulk-root",
            str(output),
            "--session-id",
            reader.session_id,
            "--maximum-visits",
            str(budget),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        receipt = {
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        with (output.parent / f"{output.name}-cli-{run}.json").open("xb") as stream:
            stream.write(canonical_json_bytes(receipt))
        if result.returncode:
            raise AssertionError(f"saved-IQ CLI failed: {result.stderr}")
        executions.append(json.loads(result.stdout))
    total = reader.receipt.complete_visit_count
    if (
        executions[0]["newly_analyzed_visits"] != 1
        or executions[1]["newly_analyzed_visits"] != total - 1
        or executions[1]["state"] != "metrics_complete"
        or executions[2]["newly_analyzed_visits"] != 0
        or executions[2]["state"] != "metrics_complete"
    ):
        raise AssertionError("saved-IQ CLI did not resume exact missing visits")
    binding = AdaptiveHopAnalysisBindingV1(
        receipt=published.manifest.receipt,
        input_manifest_sha256=published.manifest_sha256,
        configuration=product.configuration,
    )
    store = AdaptiveHopAnalysisStore(output, read_only=True)
    try:
        with store.job(binding) as job:
            manifest = job.verify()
            restored = job.read_visit(reader.index)
            if manifest is None or restored.model_dump(exclude={"input_manifest_sha256"}) != (
                product.model_dump(exclude={"input_manifest_sha256"})
            ):
                raise AssertionError("saved RX1 changed through storage/CLI metrics publication")
    finally:
        store.close()
    return {
        "temporary_synthetic_capture_root": str(output),
        "synthetic_capture_manifest_sha256": published.manifest_sha256,
        "metrics_binding_sha256": binding.sha256,
        "cli_runs": executions,
        "complete_fixture_visits": total,
        "real_rx1_visit_index": reader.index,
        "other_visits": "synthetic-zero, not observations of those channels",
    }


def qualify(source: Path, output: Path):
    source = source.resolve(strict=True)
    output = output.resolve(strict=False)
    if any(output.is_relative_to(p) for p in (source, Path("/mnt/qnap01"), Path("/srv/bulk/leo"))):
        raise ValueError("output must be separate from source/archive")
    expected = {"inputs.json": "sha256:" + _INPUT_SHA, "results.json": "sha256:" + _RESULT_SHA}
    for name, digest in expected.items():
        if sha256_digest((source / name).read_bytes()) != digest:
            raise ValueError("saved development inventory differs from frozen input")
    provenance = {
        r["file"]: r["provenance"] for r in json.loads((source / "inputs.json").read_text())
    }
    output.mkdir(parents=True, exist_ok=False)
    rows, selected = [], set()
    for metadata, iq in load_dwells(source):
        key = (metadata["rate_hz"], metadata["edge"])
        if key in selected:
            continue
        selected.add(key)
        reader = ReplayReader(metadata, iq)
        bound = AdaptiveHopAnalysisSource(reader)
        cfg = AdaptiveHopAnalysisConfigurationV1(sample_rate_hz=metadata["rate_hz"])
        print(f"starting {key}: {metadata['session']} visit {metadata['visit']}", flush=True)
        started = time.monotonic()
        product = analyze_adaptive_hop_visit(bound, reader.index, configuration=cfg)
        adaptive_seconds = time.monotonic() - started
        started = time.monotonic()
        reference = analyze_glrt64_dwell(
            bound.read_visit(reader.index),
            PersistentHopGlrt64Configuration(plan=reader.receipt.plan.geometry),
            edge=metadata["edge"],
        )
        reference_seconds = time.monotonic() - started
        counts = compare_candidates(product, reference)
        validate_adaptive_analysis_binding(
            product,
            reader.receipt,
            input_manifest_sha256=reader.input_manifest_sha256,
        )
        artifacts = {}
        for suffix, payload in (
            ("adaptive", product.model_dump(mode="json")),
            ("reference", asdict(reference)),
        ):
            name = f"{key[0]}-{key[1]}-{suffix}.json.gz"
            data = gzip.compress(canonical_json_bytes(payload), mtime=0)
            with (output / name).open("xb") as stream:
                stream.write(data)
            artifacts[name] = sha256_digest(data)
        row = {
            **metadata,
            "original_provenance": provenance[metadata["source_files"][0]],
            **counts,
            "adaptive_seconds": adaptive_seconds,
            "reference_seconds": reference_seconds,
            "artifacts": artifacts,
        }
        row["storage_cli"] = exercise_storage_and_cli(
            reader, product, output / f"fixture-{key[0]}-{key[1]}"
        )
        rows.append(row)
        print(
            json.dumps(
                {"rate": key[0], "edge": key[1], **counts, "adaptive_seconds": adaptive_seconds}
            ),
            flush=True,
        )
        if len(selected) == 4:
            break
    if len(selected) != 4:
        raise ValueError("saved source did not cover both rates and both edges")
    for name, digest in expected.items():
        if sha256_digest((source / name).read_bytes()) != digest:
            raise ValueError("source inventory changed during qualification")
    summary = {
        "kind": "saved-rx1-synthetic-adaptive-receipt-numerical-parity-v1",
        "qualification": "development numerical parity only; no sensitivity, ARM or RF claim",
        "source": str(source),
        "input_hashes": expected,
        "rx0": "synthetic-zero",
        "receipt": "synthetic-shadow-with-exact-counters-above-2**53",
        "selection": "first dwell per rate/edge in source order, independent of scores",
        "rows": rows,
    }
    with (output / "summary.json").open("xb") as stream:
        stream.write(canonical_json_bytes(summary))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    qualify(args.source, args.output)


if __name__ == "__main__":
    main()
