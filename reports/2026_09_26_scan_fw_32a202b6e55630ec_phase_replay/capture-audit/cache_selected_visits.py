#!/usr/bin/env python3
"""Materialize the sealed 128-visit cohort once for all replay workers."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import zstandard as zstd


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(8 << 20), b""):
            h.update(part)
    return "sha256:" + h.hexdigest()


def main(source: Path, selection_path: Path, mask_path: Path, output: Path) -> None:
    envelope = json.loads((source / "manifest.json").read_bytes())
    manifest = envelope["manifest"]
    selection = json.loads(selection_path.read_text())
    masks = json.loads(mask_path.read_text())
    if selection["input_manifest_sha256"] != envelope["sha256"] or masks["source_manifest_sha256"] != envelope["sha256"]:
        raise ValueError("selection/mask/source manifest bindings disagree")
    mask_by_visit = {row["visit_index"]: row for row in masks["visits"]}
    chunks = manifest["chunks"]
    output.mkdir(parents=True, exist_ok=True)
    inventory = []
    for selected in sorted(selection["visits"], key=lambda row: row["visit_index"]):
        visit = selected["visit_index"]
        chunk = chunks[visit]
        compressed = (source / chunk["relative_path"]).read_bytes()
        raw = zstd.ZstdDecompressor(max_window_size=32 << 20).decompress(compressed, max_output_size=chunk["uncompressed_bytes"], allow_extra_data=False)
        if "sha256:" + hashlib.sha256(raw).hexdigest() != chunk["uncompressed_sha256"]:
            raise ValueError(f"visit {visit} source digest failed")
        iq = np.frombuffer(raw, dtype="<i2").reshape(chunk["sample_count"], 2, 2)
        valid = np.ones((len(iq), 2), dtype=np.bool_)
        source_mask = np.ones((len(iq), 2), dtype=np.uint8)
        for start, stop in mask_by_visit[visit]["invalid_intervals_half_open"]:
            valid[start:stop] = False
            source_mask[start:stop] = 2
        device = np.arange(len(iq), dtype=np.int64) + np.int64(selected["valid_start_counter"])
        stored = np.arange(len(iq), dtype=np.int64) + np.int64(selected["stored_sample_start"])
        directory = output / f"visit-{visit:04d}"
        directory.mkdir(exist_ok=True)
        arrays = {"iq_ci16": iq, "valid_mask": valid, "source_mask": source_mask, "device_counter": device, "stored_sample_index": stored}
        files = {}
        for name, array in arrays.items():
            path = directory / f"{name}.npy"
            np.save(path, array, allow_pickle=False)
            files[name] = {"relative_path": str(path.relative_to(output)), "sha256": digest(path), "dtype": array.dtype.str, "shape": list(array.shape)}
        inventory.append({"visit_index": visit, "split": selected["split"], "target_index": selected["target_index"], "valid_start_counter": selected["valid_start_counter"], "stored_sample_start": selected["stored_sample_start"], "files": files})
    body = {"schema_version": 1, "input_manifest_sha256": envelope["sha256"], "selection_sha256": digest(selection_path), "validity_mask_sha256": digest(mask_path), "source_mask_values": {"RF_VALID": 1, "KNOWN_NON_IQ": 2, "UNEXPLAINED_INVALID": 4, "FILTER_TRANSIENT": 8, "STORAGE_GAP": 16, "SETTLING": 32}, "visits": inventory}
    (output / "cache-index.json").write_text(json.dumps(body, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path)
    p.add_argument("selection", type=Path)
    p.add_argument("mask", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    main(a.source, a.selection, a.mask, a.output)
