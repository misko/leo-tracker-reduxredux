"""ABBA serialization comparison on a completed native v3 scientific result.

The reference codec is an explicitly bound external oracle. It is never an
inference dependency. Every restored field and PNG is checked, outside timing.
"""

import argparse
import gc
import hashlib
import importlib.util
import json
import time
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint

from leo.storage import localization_v3_codec as candidate
from leo.storage.localization_v3 import LocalizationV3Store


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def value_sha(value):
    h = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, allow_nan=False, separators=(",", ":"))
    for part in encoder.iterencode(fingerprint(value)):
        h.update(part.encode())
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Fresh output required")
    source_receipt = json.loads((args.native_run / "result.receipt.json").read_text())
    name = "leo.storage.localization_v3_codec"
    reference_path = args.native_run / "source" / (name + ".py")
    assert file_sha(reference_path) == source_receipt["modules"][name]["sha256"]
    spec = importlib.util.spec_from_file_location("external_v3_codec_oracle", reference_path)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    saved = LocalizationV3Store(args.native_run / "publication").load(
        source_receipt["publication"]["run_id"]
    )
    evidence, pngs = saved["evidence"], saved["pngs"]
    expected = value_sha(evidence)
    rows = []
    for label in ("reference", "candidate", "candidate", "reference"):
        codec = reference if label == "reference" else candidate
        gc.collect()
        began = time.perf_counter()
        raw = codec.pack(evidence, pngs)
        packed = time.perf_counter()
        restored, figures = codec.unpack(raw)
        finished = time.perf_counter()
        row = dict(
            side=label,
            pack_seconds=packed - began,
            unpack_seconds=finished - packed,
            total_seconds=finished - began,
            bytes=len(raw),
            raw_sha256=hashlib.sha256(raw).hexdigest(),
        )
        assert value_sha(restored) == expected
        assert figures == pngs
        row["all_fields_exact"] = row["all_pngs_exact"] = True
        rows.append(row)
        print(json.dumps(row), flush=True)
        del raw, restored, figures
    for label in ("reference", "candidate"):
        assert len({r["raw_sha256"] for r in rows if r["side"] == label}) == 1
    summary = dict(
        scope="evidence pack + unpack only; excludes inference and filesystem publication",
        order="ABBA",
        rows=rows,
        scientific_value_sha256=expected,
        reference_codec=dict(path=str(reference_path), sha256=file_sha(reference_path)),
        candidate_codec=dict(path=candidate.__file__, sha256=file_sha(candidate.__file__)),
        source_receipt=dict(
            path=str(args.native_run / "result.receipt.json"),
            sha256=file_sha(args.native_run / "result.receipt.json"),
        ),
        tool_sha256=file_sha(__file__),
        complete_path_speedup=None,
    )
    args.output.write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
