"""Measure the two decoded SHA-256 digests used by a full sealed I/Q chunk."""

import argparse
import json
from contextlib import nullcontext
from hashlib import sha256
from pathlib import Path
from random import Random
from time import perf_counter, process_time


def control(windows):
    chunk = sha256()
    digests = []
    for window in windows:
        digests.append(sha256(window).digest())
        chunk.update(window)
    return digests, chunk.digest()


def measure(windows, candidate=None, repeats=3):
    expected = control(windows)

    def windows_only(raw):
        return [sha256(window).digest() for window in raw]

    def chunk_only(raw):
        chunk = sha256()
        for window in raw:
            chunk.update(window)
        return chunk.digest()

    arms = {"two-hashes": control, "windows-only": windows_only, "chunk-only": chunk_only}
    if candidate is not None:
        arms["sha-ni-pair"] = candidate
    wanted = {"windows-only": expected[0], "chunk-only": expected[1]}
    rows = []
    for index in range(repeats):
        order = list(arms) if index % 2 == 0 else list(reversed(arms))
        for arm in order:
            cpu, wall = process_time(), perf_counter()
            got = arms[arm](windows)
            cpu, wall = process_time() - cpu, perf_counter() - wall
            if got != wanted.get(arm, expected):
                raise ValueError(f"{arm} did not reproduce independent SHA-256 verification")
            rows.append(dict(arm=arm, iteration=index, cpu_s=cpu, elapsed_s=wall))
    return dict(window_count=len(windows), window_bytes=len(windows[0]),
                bytes=sum(map(len, windows)), chunk_sha256=expected[1].hex(), timings=rows)


def saved_segments(bindings, bulk):
    segments = []
    for binding in bindings:
        case = json.loads(binding.read_bytes())["case"]
        segment = case["recording"]["segments"][0]
        segments.append((case["id"], bulk / segment["path"], segment["sha256"]))
    return segments


def verified_chunks(segments, library, repeats=3):
    from leo.contracts.digests import canonical_digest
    from leo.storage.short_window import ShortWindowReader
    from tools.pipeline_eval.variants.experimental.paired_sha256 import (
        PairedSha256,
        paired_decoded_hashes,
    )
    from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer

    if not PairedSha256(library).hardware:
        raise ValueError("SHA-NI path unavailable on this machine")
    cases = []
    for index, (label, manifest, expected_sha256) in enumerate(segments):
        manifest = manifest.resolve(strict=True)
        reader = ShortWindowReader(manifest.parent)
        if reader.manifest_sha256 != "sha256:" + expected_sha256:
            raise ValueError("Sealed manifest differs from saved binding")
        chunk = reader.manifest.chunks[0]
        if chunk.window_count != 64:
            raise ValueError("Expected one complete 64-window chunk")
        timings, expected = [], None
        for repeat in range(repeats):
            arms = ("compressed", "paired")
            if (index + repeat) % 2:
                arms = arms[::-1]
            for arm in arms:
                hashing = paired_decoded_hashes(library) if arm == "paired" else nullcontext()
                with compressed_input_buffer(), hashing:
                    cpu, wall = process_time(), perf_counter()
                    windows = [w.index for w in reader.windows(start_sequence=0, stop_sequence=40)]
                    cpu, wall = process_time() - cpu, perf_counter() - wall
                receipt = canonical_digest([w.model_dump(mode="json") for w in windows])
                if expected is None:
                    expected = receipt
                if receipt != expected or len(windows) != 40:
                    raise ValueError("Reader did not reproduce its verified window evidence")
                timings.append(dict(arm=arm, iteration=repeat, cpu_s=cpu, elapsed_s=wall))
        cases.append(dict(case=label, manifest=reader.manifest_sha256,
                          verified_windows=chunk.window_count, returned_windows=40,
                          decoded_bytes=chunk.uncompressed_bytes,
                          chunk_sha256=chunk.uncompressed_sha256, windows_sha256=expected,
                          timings=timings))
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path)
    parser.add_argument("--binding", type=Path, action="append", default=[])
    parser.add_argument("--bulk", type=Path)
    parser.add_argument(
        "--manifest", nargs=2, action="append", metavar=("PATH", "SHA256"), default=[],
    )
    args = parser.parse_args()
    if args.binding or args.manifest:
        count = len(args.binding) + len(args.manifest)
        if args.native is None or count > 2 or (args.binding and args.bulk is None):
            parser.error("verify at most two sealed chunks with their native binary and bulk root")
        segments = saved_segments(args.binding, args.bulk)
        segments.extend(
            (Path(path).parent.name, Path(path), digest) for path, digest in args.manifest
        )
        print(json.dumps(verified_chunks(segments, args.native), indent=2))
        return
    rng = Random(0)
    windows = tuple(rng.randbytes(1_600_000) for _ in range(64))
    candidate = None
    if args.native is not None:
        from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256

        def candidate(raw):
            chunk = PairedSha256(args.native)
            if not chunk.hardware:
                raise ValueError("SHA-NI path unavailable on this machine")
            return [chunk.window(window) for window in raw], chunk.digest()
    print(json.dumps(measure(windows, candidate), indent=2))


if __name__ == "__main__":
    main()
