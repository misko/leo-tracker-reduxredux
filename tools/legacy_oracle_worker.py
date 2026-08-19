#!/usr/bin/env python3
"""Historical-process worker for the sealed CH4-lower pilot oracle.

This file is deliberately outside the ``leo`` package.  It is launched with a
clean pinned legacy checkout on ``PYTHONPATH`` and may only emit an unsealed
worker result; the current qualification process validates and seals it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

acquire_exact_receiver = None
demodulate_edge_window = None
np = None
scipy = None


def _canonical_digest(value: dict) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _iq_digest(samples: np.ndarray) -> str:
    assert np is not None
    canonical = np.ascontiguousarray(samples, dtype="<c8")
    return f"sha256:{hashlib.sha256(canonical.tobytes(order='C')).hexdigest()}"


def _decision(config: dict, raw: np.ndarray, index: int) -> dict:
    assert acquire_exact_receiver is not None
    assert demodulate_edge_window is not None
    assert np is not None
    sample_start = index * config["interval_sample_count"]
    iq = np.asarray(
        raw[sample_start : sample_start + config["window_sample_count"], 0].astype(np.float32)
        + 1j
        * raw[sample_start : sample_start + config["window_sample_count"], 1].astype(np.float32),
        dtype=np.complex64,
    ) / np.float32(32_768)
    digest = _iq_digest(iq)
    result = acquire_exact_receiver(
        iq,
        config["sample_rate_hz"],
        edge=config["edge"],
        acquisition_span_hz=config["acquisition_span_hz"],
        acquisition_step_hz=config["acquisition_step_hz"],
        subband_rate_hz=config["exact_subband_rate_hz"],
        frequency_center_hz=config["receiver_center_hz"],
        method=config["acquisition_method"],
    )
    candidate = bool(
        result["acquisition"]["match_score_margin"] >= config["single_match_margin"]
        and result["pilot"]["score_margin"] >= config["single_symbol_margin"]
    )
    epoch = int(result["acquisition"]["selected_epoch_sample"]) if candidate else None
    cfo = _absolute_cfo(result) if candidate else None
    accuracy = evm = None
    qam_reason = ""
    if candidate:
        try:
            decoded, _arrays = demodulate_edge_window(
                iq,
                config["sample_rate_hz"],
                epoch_sample=epoch,
                carrier_offset_hz=cfo,
                edge=config["edge"],
            )
            accuracy = float(decoded["pilot"]["hard_symbol_accuracy"])
            evm = float(decoded["pilot"]["rms_evm"])
            qam_reason = "; historical pilot QAM evaluated"
        except ValueError as exc:
            qam_reason = f"; historical QAM unavailable: {exc}"
    values = {
        "schema_version": 1,
        "source": "legacy_reference",
        "algorithm_id": "leo-tracker-pilot-symbolwise-v3-single-rx",
        "algorithm_version": config["source_revision"],
        "window_iq_digest": digest,
        "window_index": index,
        "sample_start": sample_start,
        "status": "evaluated",
        "candidate": candidate,
        "epoch_sample": epoch,
        "cfo_hz": cfo,
        "qam_accuracy": accuracy,
        "qam_evm": evm,
        "reason": (
            "historical single-RX candidate gates passed"
            if candidate
            else "historical single-RX candidate gates did not pass"
        )
        + qam_reason,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return {**values, "evidence_digest": _canonical_digest(values)}


def _absolute_cfo(result: dict) -> float:
    """Return old acquire_exact_receiver's absolute digital CFO, not QAM residual CFO."""

    pilot = result["pilot"]
    acquisition = result["acquisition"]
    absolute = float(pilot["frequency_offset_hz"])
    local = float(pilot["local_frequency_offset_hz"])
    subband_center = float(acquisition["selected_center_offset_hz"])
    if abs(absolute - (local + subband_center)) > 1e-6:
        raise ValueError("historical acquisition returned inconsistent absolute CFO semantics")
    return absolute


def main() -> int:
    global acquire_exact_receiver, demodulate_edge_window, np, scipy
    parser = argparse.ArgumentParser()
    parser.add_argument("--iq-fd", type=int, required=True)
    parser.add_argument("--iq-sha256", required=True)
    parser.add_argument("--config-json", required=True)
    args = parser.parse_args()
    config = json.loads(args.config_json)
    config_content = {key: value for key, value in config.items() if key != "config_digest"}
    if _canonical_digest(config_content) != config["config_digest"]:
        raise ValueError("configuration digest mismatch")
    sys.path.insert(0, config["legacy_root"] + "/src")
    import numpy as legacy_numpy
    import scipy as legacy_scipy
    from leo_tracker.radio.beacon.acquisition import acquire_exact_receiver as acquire
    from leo_tracker.radio.beacon.decode import demodulate_edge_window as demodulate

    acquire_exact_receiver = acquire
    demodulate_edge_window = demodulate
    np = legacy_numpy
    scipy = legacy_scipy
    info = os.fstat(args.iq_fd)
    expected_bytes = config["dwell_sample_count"] * 4
    if not os.path.samestat(info, os.fstat(args.iq_fd)) or info.st_size != expected_bytes:
        raise ValueError("IQ snapshot descriptor has the wrong identity or geometry")
    if _fd_digest(args.iq_fd) != args.iq_sha256:
        raise ValueError("IQ digest mismatch before evaluation")
    source = os.fdopen(os.dup(args.iq_fd), "rb", closefd=True)
    raw = np.memmap(source, mode="r", dtype="<i2")
    if raw.size != config["dwell_sample_count"] * 2:
        raise ValueError("IQ geometry mismatch")
    raw = raw.reshape((-1, 2))
    decisions = [_decision(config, raw, index) for index in range(config["scheduled_window_count"])]
    if not os.path.samestat(info, os.fstat(args.iq_fd)) or _fd_digest(args.iq_fd) != args.iq_sha256:
        raise ValueError("IQ snapshot changed during evaluation")
    payload = {
        "config_digest": config["config_digest"],
        "iq_sha256": args.iq_sha256,
        "environment": {
            "schema_version": 1,
            "manifest_digest": config["environment_manifest_digest"],
            "python_executable": sys.executable,
            "external_executable_files": _mapped_external_executables(
                Path(config["legacy_root"]) / ".venv"
            ),
        },
        "decisions": decisions,
    }
    encoded = json.dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write(encoded + "\n")
    return 0


def _fd_digest(descriptor: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while block := os.pread(descriptor, 1024 * 1024, offset):
        offset += len(block)
        if block:
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _mapped_external_executables(venv: Path) -> list[dict[str, object]]:
    paths: set[Path] = {Path(sys.executable).resolve()}
    with Path("/proc/self/maps").open(encoding="utf-8") as maps:
        for line in maps:
            fields = line.split()
            if len(fields) < 6 or "x" not in fields[1] or not fields[-1].startswith("/"):
                continue
            path = Path(fields[-1].removesuffix(" (deleted)"))
            if venv == path or venv in path.parents:
                continue
            paths.add(path)
    entries = []
    for path in sorted(paths):
        if path == Path("/mnt/qnap01") or Path("/mnt/qnap01") in path.parents:
            raise ValueError("mapped executable unexpectedly points beneath /mnt/qnap01")
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"mapped executable is not a regular file: {path}")
        entries.append(
            {
                "path": str(path),
                "kind": "file",
                "mode": stat.S_IMODE(info.st_mode),
                "size": info.st_size,
                "sha256": _file_digest(path),
            }
        )
    return entries


if __name__ == "__main__":
    raise SystemExit(main())
