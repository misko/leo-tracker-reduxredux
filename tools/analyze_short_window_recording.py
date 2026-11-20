#!/usr/bin/env python3
"""Analyze sealed 20 ms recordings with one reusable native GLRT context.

Every complete window is considered, including QUIET power decisions. Retune
validity, RF authority and clock support are reported independently of native
candidate evidence. This tool does not publish tracking observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np

from leo.analysis.starlink import native_short_window
from leo.analysis.starlink.native_short_window import NativeShortWindow
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.short_window import ShortWindowRead, ShortWindowReader


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _line(document: dict[str, Any]) -> bytes:
    return canonical_json_bytes(document) + b"\n"


def _read_checkpoint(stream: BinaryIO) -> dict[str, Any] | None:
    start = stream.tell()
    line = stream.readline()
    if not line:
        return None
    if not line.endswith(b"\n"):
        # Only an interrupted last append may be discarded. Complete malformed
        # checkpoint lines are corruption and remain intact for diagnosis.
        stream.seek(start)
        stream.truncate()
        return None
    return json.loads(line)


def _identity(window: ShortWindowRead) -> dict[str, Any]:
    return {
        "sequence": window.index.sequence,
        "target_id": window.index.target_id,
        "iq_sha256": window.index.iq_sha256,
        "sample_count": window.index.sample_count,
    }


def _support(window: ShortWindowRead, targets: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    acquisition = window.index.acquisition
    count = window.index.sample_count
    if acquisition.get("sample_count", count) != count:
        raise ValueError("recorded acquisition count differs from verified payload")
    start = acquisition.get("sample_start")
    if start is not None and (type(start) is not int or start < 0):
        raise ValueError("recorded sample start is invalid")
    end = None if start is None else start + count
    if acquisition.get("sample_end", end) != end:
        raise ValueError("recorded sample end differs from verified payload support")
    support = {
        "sample_start": start,
        "sample_end_exclusive": end,
        "sample_count": count,
        "generation": acquisition.get("generation"),
        "counter_authority": acquisition.get("counter_authority", "unknown"),
        "validity_authority": acquisition.get("validity_authority", "unknown"),
        "sample_start_utc_ns": acquisition.get("sample_start_utc_ns"),
        "host_request_utc_ns": acquisition.get("host_request_utc_ns"),
        "requested_if_center_hz": acquisition.get("requested_if_center_hz"),
        "actual_if_center_hz": acquisition.get("actual_if_center_hz"),
        "rf_mapping": targets.get(window.index.target_id),
        "quality_flags": acquisition.get("quality_flags", []),
    }
    diagnostic = []
    if support["validity_authority"] != "provider_attested":
        diagnostic.append("post_retune_validity_not_attested")
    if support["counter_authority"] != "hardware" or start is None:
        diagnostic.append("hardware_sample_support_unavailable")
    if support["sample_start_utc_ns"] is None:
        diagnostic.append("sample_utc_support_unavailable")
    target = support["rf_mapping"] or {}
    if target.get("rf_mapping_authority") != "known":
        diagnostic.append("rf_mapping_not_authoritative")
    if support["actual_if_center_hz"] is None:
        diagnostic.append("actual_tuned_if_unavailable")
    return support, diagnostic


def analyze_recording(
    recording: Path,
    *,
    library: Path,
    exact_template: Path,
    control_template: Path,
    output: Path,
    fractional_epoch: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    """Hash-bind an atomic JSONL result; resume a verified prefix in constant memory.

    The operator supplies one declared template pair for this analysis. Its RF
    mapping is not independently qualified, so results always state that they
    are ineligible for qualified tracking. Partial/gapped/quality-invalid IQ
    is retained as skipped evidence. Complete diagnostic windows may produce
    explicitly diagnostic native candidates without promoting their authority.
    """
    output = output.resolve()
    qnap = Path("/mnt/qnap01")
    if output == qnap or qnap in output.parents:
        raise ValueError("analysis outputs cannot be written beneath QNAP")
    reader = ShortWindowReader(recording)
    manifest = reader.manifest
    template_count = (manifest.sample_rate_hz + 375) // 750
    template_arrays = []
    template_hashes = []
    for path in (exact_template, control_template):
        with path.open("rb") as template_stream:
            payload = template_stream.read(template_count * 16 + 1)
        if len(payload) != template_count * 16:
            raise ValueError("template file has the wrong baseline frame length")
        template_arrays.append(np.frombuffer(payload, dtype="<c16"))
        template_hashes.append(sha256_digest(payload))
    header = {
        "schema": "leo-short-window-recording-analysis/v1",
        "kind": "analysis_binding",
        "session_id": manifest.session_id,
        "manifest_sha256": reader.manifest_sha256,
        "native_library_sha256": _file_digest(library),
        "python_adapter_sha256": _file_digest(Path(native_short_window.__file__)),
        "analysis_tool_sha256": _file_digest(Path(__file__)),
        "exact_template_sha256": template_hashes[0],
        "control_template_sha256": template_hashes[1],
        "template_selection": "operator_supplied_common_pair",
        "sample_rate_hz": manifest.sample_rate_hz,
        "window_ms": 20,
        "receiver_ids": list(manifest.receiver_ids),
        "fractional_epoch": fractional_epoch,
        "algorithm_id": "wave8-gate314-source-v1",
        "qualified_tracking": False,
        "tracking_status": "not_projected_or_qualified",
    }
    targets = {
        target["target_id"]: target
        for target in manifest.configuration.get("targets", [])
        if isinstance(target, dict) and "target_id" in target
    }
    partial = output.with_name(output.name + ".partial")
    if partial.is_symlink():
        raise ValueError("analysis checkpoint must be a regular owned file")
    if output.exists() and not resume:
        raise FileExistsError(output)
    if partial.exists() and not resume:
        raise FileExistsError(partial)
    output.parent.mkdir(parents=True, exist_ok=True)
    published = output.exists()
    # Existing published results are verified in read-only mode. Interrupted
    # partial results are exclusively owned by this tool and may be appended.
    path = output if published else partial
    mode = "rb" if published else ("r+b" if partial.exists() else "x+b")
    analyzed = skipped = diagnostic_count = 0
    rows_digest = hashlib.sha256()
    context: NativeShortWindow | None = None
    try:
        with path.open(mode) as stream:
            if stream.seek(0, os.SEEK_END):
                stream.seek(0)
                existing_header = json.loads(stream.readline())
                if existing_header != header:
                    raise ValueError(
                        "analysis checkpoint binding differs from current inputs/configuration"
                    )
            else:
                stream.write(_line(header))
            rows_digest.update(_line(header))
            for window in reader.windows():
                identity = _identity(window)
                support, diagnostic = _support(window, targets)
                expected = None
                if published:
                    raw = stream.readline()
                    if not raw.endswith(b"\n"):
                        raise ValueError("published analysis has a missing or truncated row")
                    expected = json.loads(raw)
                else:
                    expected = _read_checkpoint(stream)
                if expected is not None:
                    if expected.get("kind") != "window" or any(
                        expected.get(key) != value for key, value in identity.items()
                    ):
                        raise ValueError(
                            "analysis checkpoint window differs from verified recording"
                        )
                    record = expected
                    checksum = record.get("row_sha256")
                    unsigned = {key: value for key, value in record.items() if key != "row_sha256"}
                    if checksum != sha256_digest(canonical_json_bytes(unsigned)):
                        raise ValueError("analysis checkpoint row digest changed")
                else:
                    record = {
                        "kind": "window",
                        **identity,
                        "window_support": support,
                        "powers": list(window.index.powers),
                        "qualified_tracking": False,
                        "diagnostic_reasons": diagnostic + ["template_mapping_not_qualified"],
                        "glrt": None,
                    }
                    invalid = (
                        window.index.sample_count != manifest.sample_rate_hz // 50
                        or window.index.acquisition.get("complete") is False
                        or bool(support["quality_flags"])
                    )
                    if invalid:
                        record["status"] = "skipped_invalid_support"
                    else:
                        if context is None:
                            context = NativeShortWindow(
                                str(library),
                                *template_arrays,
                                sample_rate_hz=manifest.sample_rate_hz,
                                receiver_count=len(manifest.receiver_ids),
                                fractional_epoch=fractional_epoch,
                            )
                        record["glrt"] = context.analyze(window.samples)
                        for row in record["glrt"]["rows"]:
                            row["physical_receiver_id"] = manifest.receiver_ids[row["receiver_id"]]
                        record["status"] = (
                            "diagnostic" if diagnostic else "native_candidate_evidence"
                        )
                    record["row_sha256"] = sha256_digest(canonical_json_bytes(record))
                    stream.write(_line(record))
                    stream.flush()
                rows_digest.update(_line(record))
                if record["glrt"] is None:
                    skipped += 1
                else:
                    analyzed += 1
                    diagnostic_count += record["status"] == "diagnostic"
            summary = {
                "kind": "summary",
                "windows": manifest.window_count,
                "analyzed_windows": analyzed,
                "skipped_windows": skipped,
                "diagnostic_windows": diagnostic_count,
                "source_recording_status": manifest.status,
                "analysis_rows_sha256": f"sha256:{rows_digest.hexdigest()}",
                "qualified_tracking": False,
            }
            if published:
                if json.loads(stream.readline()) != summary or stream.read(1):
                    raise ValueError("published analysis summary differs from verified results")
            else:
                existing_summary = _read_checkpoint(stream)
                if existing_summary is not None and (existing_summary != summary or stream.read(1)):
                    raise ValueError("analysis checkpoint has unexpected trailing records")
                if existing_summary is None:
                    stream.write(_line(summary))
                stream.flush()
                os.fsync(stream.fileno())
        if not published:
            if output.exists():
                raise FileExistsError(output)
            os.replace(partial, output)
            descriptor = os.open(output.parent, os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return summary
    finally:
        if context is not None:
            context.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--exact-template", type=Path, required=True)
    parser.add_argument("--control-template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fractional-epoch", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    summary = analyze_recording(**vars(args))
    print(canonical_json_bytes(summary).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
