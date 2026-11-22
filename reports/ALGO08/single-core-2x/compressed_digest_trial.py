"""Compare verified member and full sealed reader times on two small chunks."""
import argparse
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from time import perf_counter, process_time

from leo.contracts.digests import canonical_digest
from leo.storage.short_window import ShortWindowReader
from tools.pipeline_eval.variants.experimental.compressed_member_digest import tiled_member_digest
from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256, paired_decoded_hashes
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer


def run(manifest, expected_sha, library):
    reader = ShortWindowReader(manifest.parent)
    if reader.manifest_sha256 != "sha256:" + expected_sha:
        raise ValueError("Recording manifest differs from the assigned input")
    chunk = reader.manifest.chunks[0]
    if chunk.first_sequence != 0 or chunk.window_count != 64:
        raise ValueError("Expected a full first chunk")
    rows, evidence = [], None
    for kind in ("member", "windows"):
        def measure():
            if kind == "member":
                return len(reader._member(chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256))
            return [window.index for window in reader.windows(start_sequence=0, stop_sequence=40)]

        with compressed_input_buffer(), paired_decoded_hashes(library):
            measure()  # Untimed warmup, identical page residency at the first measured read.
            for iteration in range(4):
                arms = ("control", "tiled") if iteration % 2 == 0 else ("tiled", "control")
                for arm in arms:
                    with tiled_member_digest() if arm == "tiled" else nullcontext():
                        wall, cpu = perf_counter(), process_time()
                        result = measure()
                        elapsed_cpu, elapsed_wall = process_time() - cpu, perf_counter() - wall
                    rows.append(dict(kind=kind, iteration=iteration, arm=arm, cpu_s=elapsed_cpu, wall_s=elapsed_wall))
                    if kind == "windows":
                        digest = canonical_digest([item.model_dump(mode="json") for item in result])
                        if len(result) != 40 or (evidence is not None and evidence != digest):
                            raise ValueError("Verified window receipt changed")
                        evidence = digest
    summary = {}
    for kind in ("member", "windows"):
        groups = {arm: [r for r in rows if (r["kind"], r["arm"]) == (kind, arm)] for arm in ("control", "tiled")}
        summary[kind] = {metric: {
            "control": median(r[metric] for r in groups["control"]),
            "tiled": median(r[metric] for r in groups["tiled"]),
            "median_paired_ratio": median(b[metric] / a[metric] for a, b in zip(groups["control"], groups["tiled"], strict=True))
        } for metric in ("cpu_s", "wall_s")}
    return dict(manifest=str(manifest), manifest_sha256=reader.manifest_sha256,
                compressed_bytes=chunk.compressed_bytes, decoded_bytes=chunk.uncompressed_bytes,
                windows_sha256=evidence, verified_windows=64, returned_windows=40, summary=summary, rows=rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    parser.add_argument("--manifest", nargs=2, metavar=("PATH", "SHA256"), action="append", required=True)
    args = parser.parse_args()
    if not PairedSha256(args.library).hardware:
        raise RuntimeError("Expected the frozen paired SHA-256 implementation")
    print(json.dumps(dict(library_sha256=sha256(args.library.read_bytes()).hexdigest(),
                          cases=[run(Path(p), h, args.library) for p, h in args.manifest]), indent=2))
