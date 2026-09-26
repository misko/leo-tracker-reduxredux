#!/usr/bin/env python3
"""One-pass integrity and RF-row audit for scan-fw-32a202b6e55630ec."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path

import numpy as np
import zstandard as zstd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def counter_word_matches(values: np.ndarray, start_counter: int) -> tuple[np.ndarray, np.ndarray]:
    """Return rows that decode near their authoritative counter and signed offsets."""
    if values.dtype != np.dtype("<i2") or values.ndim != 3 or values.shape[1:] != (2, 2):
        raise ValueError("expected little-endian (sample, 2, 2) CI16")
    decoded = values.reshape(-1, 4).view("<u8").reshape(-1)
    expected = np.arange(values.shape[0], dtype=np.uint64) + np.uint64(start_counter)
    near = (decoded >= expected - np.uint64(16)) & (decoded <= expected + np.uint64(16))
    rows = np.flatnonzero(near)
    offsets = decoded[rows].astype(object) - expected[rows].astype(object)
    return rows, np.asarray(offsets, dtype=np.int64)


def intervals(rows: list[int]) -> list[list[int]]:
    if not rows:
        return []
    out: list[list[int]] = []
    first = previous = rows[0]
    for row in rows[1:]:
        if row != previous + 1:
            out.append([first, previous + 1])
            first = row
        previous = row
    out.append([first, previous + 1])
    return out


def run(source: Path, output: Path) -> None:
    started = time.monotonic()
    manifest_path = source / "manifest.json"
    document_bytes = manifest_path.read_bytes()
    envelope_file_sha = "sha256:" + hashlib.sha256(document_bytes).hexdigest()
    envelope = json.loads(document_bytes)
    manifest = envelope["manifest"]
    canonical_manifest_bytes = json.dumps(manifest, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    document_sha = "sha256:" + hashlib.sha256(canonical_manifest_bytes).hexdigest()
    if envelope.get("sha256") != document_sha:
        raise ValueError("manifest envelope does not bind the canonical manifest document")
    receipt = manifest["receipt"]
    events = receipt["events"]
    chunks = manifest["chunks"]
    if len(chunks) != 2214 or len(events) != len(chunks):
        raise ValueError("capture does not contain the expected 2,214 one-visit chunks")
    compact_expected = 0
    previous_event_end = None
    for ordinal, (chunk, event) in enumerate(zip(chunks, events, strict=True)):
        if (chunk["chunk_index"], chunk["first_visit_index"], chunk["visit_count"], event["visit_index"], event["event_sequence"]) != (ordinal, ordinal, 1, ordinal, ordinal):
            raise ValueError(f"chunk/event ordinal mapping fails at {ordinal}")
        if chunk["sample_start"] != compact_expected or event["valid_end_counter_exclusive"] - event["valid_start_counter"] != chunk["sample_count"]:
            raise ValueError(f"compact/device interval mapping fails at {ordinal}")
        if previous_event_end is not None and event["valid_start_counter"] < previous_event_end:
            raise ValueError(f"device intervals overlap or reverse at {ordinal}")
        compact_expected += chunk["sample_count"]
        previous_event_end = event["valid_end_counter_exclusive"]
    if compact_expected != manifest["total_sample_count"] or sum(c["uncompressed_bytes"] for c in chunks) != manifest["uncompressed_bytes"] or sum(c["compressed_bytes"] for c in chunks) != manifest["compressed_bytes"]:
        raise ValueError("manifest global byte/sample sums disagree with chunk inventory")
    output.mkdir(parents=True, exist_ok=True)
    masks = output / "validity-masks"
    masks.mkdir(exist_ok=True)

    inventory_path = output / "visit-inventory.csv"
    invalid_path = masks / "timestamp-rows.csv"
    integrity_rows = []
    mask_index = []
    offset_counts: Counter[int] = Counter()
    global_uncompressed = hashlib.sha256()
    duplicate_blocks: dict[str, tuple[int, int]] = {}
    duplicate_hits = []
    all_elapsed = []
    all_targets = []
    all_invalid = []
    all_gaps = []

    with inventory_path.open("w", newline="") as inv_stream, invalid_path.open("w", newline="") as bad_stream:
        inv = csv.writer(inv_stream)
        bad = csv.writer(bad_stream)
        inv.writerow(["visit_index", "chunk_index", "target_index", "channel", "edge", "sample_start", "valid_start_counter", "valid_end_counter_exclusive", "gap_before_samples", "counter_word_rows", "counter_word_offset", "clipped_rows", "rx_equal_rows", "max_abs_ci16"])
        bad.writerow(["visit_index", "local_sample_index", "compact_sample_index", "device_counter", "decoded_counter", "decoded_minus_device_counter", "reason"])
        previous_end = None
        compact = 0
        for chunk, event in zip(chunks, events, strict=True):
            path = source / chunk["relative_path"]
            compressed = path.read_bytes()
            compressed_sha = "sha256:" + hashlib.sha256(compressed).hexdigest()
            raw = zstd.ZstdDecompressor(max_window_size=32 << 20).decompress(compressed, max_output_size=chunk["uncompressed_bytes"], allow_extra_data=False)
            raw_sha = "sha256:" + hashlib.sha256(raw).hexdigest()
            global_uncompressed.update(raw)
            integrity_rows.append({"chunk_index": chunk["chunk_index"], "relative_path": chunk["relative_path"], "compressed_bytes": len(compressed), "compressed_sha256": compressed_sha, "compressed_ok": compressed_sha == chunk["compressed_sha256"] and len(compressed) == chunk["compressed_bytes"], "uncompressed_bytes": len(raw), "uncompressed_sha256": raw_sha, "uncompressed_ok": raw_sha == chunk["uncompressed_sha256"] and len(raw) == chunk["uncompressed_bytes"]})
            values = np.frombuffer(raw, dtype="<i2").reshape(chunk["sample_count"], 2, 2)
            rows, offsets = counter_word_matches(values, event["valid_start_counter"])
            for local, offset in zip(rows.tolist(), offsets.tolist(), strict=True):
                decoded = event["valid_start_counter"] + local + offset
                bad.writerow([event["visit_index"], local, compact + local, event["valid_start_counter"] + local, decoded, offset, "embedded_counter_word"])
                offset_counts[offset] += 1
            invalid_intervals = intervals(rows.tolist())
            mask_index.append({"visit_index": event["visit_index"], "valid_sample_count": chunk["sample_count"], "invalid_intervals_half_open": invalid_intervals, "policy": "exclude any estimator support intersecting an invalid interval; expand by the complete impulse response when filtering"})
            flat = values.reshape(-1, 4)
            clipped = np.any((flat == -32768) | (flat == 32767), axis=1)
            rx_equal = np.all(values[:, 0, :] == values[:, 1, :], axis=1)
            for block_start in range(0, len(raw), 800_000):
                block = raw[block_start:block_start + 800_000]
                digest = hashlib.blake2b(block, digest_size=16).hexdigest()
                key = duplicate_blocks.get(digest)
                if key is not None:
                    duplicate_hits.append({"first_visit": key[0], "first_local_sample": key[1], "duplicate_visit": event["visit_index"], "duplicate_local_sample": block_start // 8})
                else:
                    duplicate_blocks[digest] = (event["visit_index"], block_start // 8)
            gap = None if previous_end is None else event["valid_start_counter"] - previous_end
            inv.writerow([event["visit_index"], chunk["chunk_index"], event["target_index"], event["target"]["channel"], event["target"]["edge"], chunk["sample_start"], event["valid_start_counter"], event["valid_end_counter_exclusive"], gap, ";".join(map(str, rows.tolist())), ";".join(map(str, offsets.tolist())), int(clipped.sum()), int(rx_equal.sum()), int(np.max(np.abs(flat.astype(np.int32))))])
            origin = receipt["terminal"]["first_counter"]
            all_elapsed.append((event["valid_start_counter"] - origin) / 10_000_000)
            all_targets.append(event["target_index"])
            all_invalid.append(len(rows))
            all_gaps.append(0 if gap is None else gap)
            previous_end = event["valid_end_counter_exclusive"]
            compact += chunk["sample_count"]

    session_uncompressed_sha = "sha256:" + global_uncompressed.hexdigest()
    integrity_ok = all(row["compressed_ok"] and row["uncompressed_ok"] for row in integrity_rows) and session_uncompressed_sha == manifest["uncompressed_sha256"]
    if not integrity_ok:
        raise ValueError("chunk or session integrity verification failed")
    (output / "chunk-integrity.json").write_text(json.dumps({"schema_version": 1, "all_chunks_ok": integrity_ok, "chunk_count": len(integrity_rows), "session_uncompressed_sha256": session_uncompressed_sha, "chunks": integrity_rows}, indent=2) + "\n")
    mask_document = {"schema_version": 1, "source_manifest_sha256": document_sha, "reason": "Eight-byte stored sample rows decode as the authoritative per-row device counter within +/-16 samples.", "invalid_row_count": sum(sum(stop - start for start, stop in x["invalid_intervals_half_open"]) for x in mask_index), "visits": mask_index}
    mask_text = json.dumps(mask_document, indent=2) + "\n"
    (masks / "validity-mask-index.json").write_text(mask_text)
    mask_sha = "sha256:" + hashlib.sha256(mask_text.encode()).hexdigest()

    target_counts = Counter(all_targets)
    audit = {"schema_version": 1, "session_id": manifest["session_id"], "source_manifest_sha256": document_sha, "manifest_schema_version": manifest["schema_version"], "receipt_schema_version": receipt["schema_version"], "chunk_count": len(chunks), "visit_count": len(events), "integrity_all_chunks_ok": integrity_ok, "sample_format": manifest["sample_format"], "sample_layout": manifest["sample_layout"], "samples_per_visit": chunks[0]["sample_count"], "receiver_ids": receipt["plan"]["geometry"]["receiver_ids"], "sample_rate_hz": receipt["plan"]["geometry"]["sample_rate_hz"], "compact_samples": manifest["total_sample_count"], "device_counter_origin": receipt["terminal"]["first_counter"], "device_counter_end_exclusive": receipt["terminal"]["final_counter"], "timestamp_word_rows": sum(all_invalid), "timestamp_offsets": {str(k): v for k, v in sorted(offset_counts.items())}, "visits_with_timestamp_words": sum(x > 0 for x in all_invalid), "validity_mask_sha256": mask_sha, "duplicate_100k_sample_blocks": duplicate_hits, "target_counts": {str(k): v for k, v in sorted(target_counts.items())}, "transport_missing_samples": receipt["transport_missing_sample_count"], "unclassified_samples": receipt["unclassified_sample_count"], "unreceived_tail_samples": receipt["unreceived_tail_sample_count"], "transition_invalid_samples": receipt["transition_invalid_sample_count"], "valid_duty_ppm": receipt["valid_duty_ppm"], "runtime_seconds": time.monotonic() - started}
    (output / "capture-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    provenance = {"schema_version": 1, "session_id": manifest["session_id"], "manifest_path": str(manifest_path), "manifest_document_sha256": document_sha, "envelope_file_sha256": envelope_file_sha, "manifest_envelope_claimed_sha256": envelope["sha256"], "manifest_declared_uncompressed_sha256": manifest["uncompressed_sha256"], "verified_session_uncompressed_sha256": session_uncompressed_sha, "git_revision": os.popen("git rev-parse HEAD").read().strip(), "reader_contract": "ci16_le, shape (sample, receiver, iq), receiver_ids (0,1); compact rows map to device counter valid_start_counter + local index", "utc_policy": "UTC is derived only from the host-bracketed device-counter binding and retains the manifest uncertainty; device counter is authoritative for elapsed time.", "rf_validity_policy": "Counter-word rows are metadata contamination, not RF. Preserve coordinates, exclude estimator/transform windows that touch them, and expand invalidity by filter support. Zero fill is sensitivity analysis only.", "source_semantics_limit": "The repository reader preserves all stored rows and supplies no row classification. Capture code copies upstream.samples unchanged. Exact firmware/kernel insertion versus overwrite semantics are not attested by the saved manifest; the words occupy one stored IQ row and therefore the original RF values at that coordinate are unavailable."}
    (output / "source-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(14, 6), sharex=True, constrained_layout=True)
    sc = ax0.scatter(all_elapsed, all_targets, c=all_targets, s=5, cmap="tab10", rasterized=True)
    ax0.set_ylabel("target index")
    ax0.set_title("scan-fw-32a202b6e55630ec capture coverage and embedded counter words")
    contaminated = np.asarray(all_invalid) > 0
    ax1.scatter(np.asarray(all_elapsed)[contaminated], np.asarray(all_invalid)[contaminated], s=7, color="crimson", label="counter-word rows")
    gap_ms = np.asarray(all_gaps) / 10_000
    ax1.scatter(all_elapsed, gap_ms, s=4, alpha=.35, color="black", label="gap before visit (ms)")
    ax1.set_xlabel("seconds from terminal.first_counter")
    ax1.set_ylabel("count / ms")
    ax1.legend(loc="upper right")
    fig.savefig(output / "capture-coverage-contamination.png", dpi=160)
    fig.savefig(output / "capture-coverage-contamination.svg")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.source, args.output)
