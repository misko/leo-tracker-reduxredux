"""Convert ordinary native files or verify the producer from recorded IQ lane messages."""

import argparse
import gzip
import hashlib
import heapq
import json
from pathlib import Path
from time import perf_counter, process_time

from ..__main__ import local_output, save_json
from ..variants import winner_stream

EXCLUSION = ("visit", "reason", "iq_sha256", "sample_start", "sample_end")


def visits(path, digest):
    with path.open("rb") as handle:
        last = -1
        for encoded in handle:
            digest.update(encoded)
            row = json.loads(encoded)
            if row["kind"] in {"segment", "worker"}:
                continue
            if row["kind"] != "visit" or row["visit"] <= last:
                raise ValueError("recorded lane is outside the chronological visit contract")
            last = row["visit"]
            yield row


def recorded_lanes(paths, footer, native_sha, output):
    """Pass each recorded detector reply through the same incremental Writer ABI."""
    hashes = tuple(hashlib.sha256() for _ in paths)
    merged = heapq.merge(
        *(visits(p, h) for p, h in zip(paths, hashes, strict=True)), key=lambda row: row["visit"]
    )
    writer = winner_stream.Writer(output)
    clocks, excluded, anchors = [], [], []
    generation = None
    end = None
    for index, visit in enumerate(merged):
        if index == 0:
            generation = visit["generation"]
            end = visit["sample_start"]
        if (
            visit["visit"] != index
            or visit["generation"] != generation
            or not end <= visit["sample_start"] <= visit["sample_end"]
        ):
            raise ValueError("lost or nonmonotonic recorded visit")
        end = visit["sample_end"]
        clocks.append(visit["delivery_clock"])
        if visit["clock_anchor"] is not None:
            anchors.append(visit["clock_anchor"])
        probes = visit["probes"]
        if visit["status"] == "invalid_capture" and not probes:
            excluded.append({key: visit[key] for key in EXCLUSION})
            continue
        if visit["status"] != "processed" or [p["receiver_id"] for p in probes] != [0, 1]:
            raise ValueError("recorded visit lacks its original receiver pair")
        for probe in probes:
            if (
                probe["visit_index"] != index
                or probe["valid_start_counter"] != visit["sample_start"]
            ):
                raise ValueError("detector probe is outside its visit authority")
            writer.probe(probe)
    if (
        clocks != footer["delivery_clocks"]
        or anchors != [footer["clock_anchor"]]
        or end != footer["last_sample_counter"]
        or excluded != footer["provenance"]["excluded_windows"]
    ):
        raise ValueError(
            "recorded producer clock or exclusion audit differs from the native source"
        )
    sha, size = writer.finish(footer, native_sha)
    return dict(
        sha256=sha,
        bytes=size,
        visits=len(clocks),
        probes=writer.count,
        exclusions=len(excluded),
        lane_sha256=[digest.hexdigest() for digest in hashes],
    )


def reproduce(paths, reference, expected, output):
    raw = reference.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("recorded producer reference differs from the declared private digest")
    footer = json.loads(raw.rsplit(b"\n", 2)[1])
    with output.open("xb") as handle:
        result = recorded_lanes(paths, footer["document"], footer["native_sha256"], handle)
    if result["sha256"] != expected:
        raise ValueError("recorded detector messages did not reproduce the private stream")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("sha256")
    parser.add_argument("output", type=local_output)
    parser.add_argument("--recorded-lanes", type=Path, nargs=2)
    parser.add_argument("--receipt", type=local_output)
    args = parser.parse_args()
    start, cpu = perf_counter(), process_time()
    if args.recorded_lanes:
        result = reproduce(args.recorded_lanes, args.source, args.sha256, args.output)
    else:
        reader = gzip.open if args.source.suffix == ".gz" else open
        pending = args.output.with_suffix(args.output.suffix + ".pending")
        with reader(args.source, "rb") as source, pending.open("xb") as output:
            digest, size = winner_stream.convert(source, output, args.sha256)
        args.output.hardlink_to(pending)
        pending.unlink()
        result = dict(sha256=digest, bytes=size)
    result.update(wall_s=perf_counter() - start, cpu_s=process_time() - cpu)
    if args.receipt:
        save_json(args.receipt, result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
