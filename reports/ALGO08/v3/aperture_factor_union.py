"""Read sealed aperture factors and count within-lane complementarity."""

import argparse
import gzip
from hashlib import sha256
import json
from math import remainder
from pathlib import Path


DISTRIBUTED = "6849fc6150d1479e48439744ad906f5c537b00c840ad108bbc317f015d0a8cc7"
CENTERED = "a3a033f86d3e52b3217beb5972cac9f43068b631e9389d457c8f6a61a71f290b"


def read(path, expected):
    data = path.read_bytes()
    if data.startswith(b"\x1f\x8b") and expected == CENTERED:
        data = gzip.decompress(data)
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Unexpected sealed aperture receipt at {path}")
    return json.loads(gzip.decompress(data) if data.startswith(b"\x1f\x8b") else data)


def lane_key(metadata, iq):
    return tuple(sorted(metadata.items())), iq


def rank_zero(factors):
    return next((factor for factor in factors if factor[0] == 0), None)


def highest_margin(factors):
    return max((f for f in factors if f is not None),
               key=lambda f: (f[4] - f[5], -f[0]), default=None)


def matches(candidate, stock):
    return (candidate is not None and stock is not None
            and abs(remainder(sum(candidate[1:3]) - sum(stock[1:3]), 13_333)) <= 2.
            and abs(candidate[3] - stock[3]) <= 250.)


def distributed_rows(receipt, panel):
    info = receipt["final"][panel]
    names = ("full-20ms", "12ms", "selected-fir")
    factors = (info["factors"][a] for a in names)
    all_metadata = (info["probes"][a] for a in names)
    digests = ([value for _, value in info["lane_input"]] if panel == "weak" else info["input_sha256"])
    if len(digests) * 2 != len(info["probes"][names[0]]):
        raise ValueError("Incomplete original stereo input")
    streams, rows = {}, {}
    for index, (probes, stock, prefix, distributed) in enumerate(zip(zip(*all_metadata, strict=True), *factors, strict=True)):
        metadata = {k: v for k, v in probes[0].items() if k != "candidates"}
        if any(metadata != {k: v for k, v in probe.items() if k != "candidates"} for probe in probes):
            raise ValueError("Aperture experiment changed acquisition metadata")
        if index % 2 == 0:
            stream = tuple(metadata[k] for k in ("actual_rf_hz", "edge", "channel"))
            count = streams.get(stream, 0)
            mode = "full" if panel == "dense" and count % 8 == 0 else "short_primary"
            streams[stream] = count + 1
        key = lane_key(metadata, digests[index // 2])
        if key in rows:
            raise ValueError("Duplicate native lane identity")
        rows[key] = dict(mode=mode, stock=stock, prefix=rank_zero(prefix), distributed=rank_zero(distributed))
    return rows


def joint_rows(original, centered):
    joined, seen = [], set()
    for row in centered:
        key = lane_key(row["metadata"], row["iq_sha256"])
        if key not in original or key in seen:
            raise ValueError("Centered receipt contains an unbound or duplicate I/Q lane")
        seen.add(key)
        other = original[key]
        if row["mode"] != other["mode"] or row["installed"] != other["stock"]:
            raise ValueError("Common installed factors or scheduling mode disagree")
        if row["mode"] == "short_primary":
            if rank_zero(row["prefix"]) != other["prefix"]:
                raise ValueError("Common released prefix bytes disagree")
            joined.append(dict(other, centered=rank_zero(row["centered"])))
    return joined


def counts(rows, arms):
    output = {}
    for name, reference in (("stock_rank_zero", rank_zero), ("stock_highest_margin", highest_margin)):
        stock = [reference(row["stock"]) for row in rows]
        subsets = {"prefix": ("prefix",), **{arm: (arm,) for arm in arms},
                   **{f"prefix_plus_{arm}": ("prefix", arm) for arm in arms},
                   "all_apertures": ("prefix", *arms)}
        oracle = {key: sum(any(matches(row[arm], full) for arm in subset)
                           for row, full in zip(rows, stock, strict=True)) for key, subset in subsets.items()}
        highest = {key: sum(matches(highest_margin(row[arm] for arm in subset), full)
                            for row, full in zip(rows, stock, strict=True)) for key, subset in subsets.items()}
        output[name] = dict(present=sum(full is not None for full in stock),
                            ranked_one=sum(full is not None and full[0] == 1 for full in stock),
                            match_counts=oracle, highest_observed_margin=highest)
    return dict(common_nonanchor_lanes=len(rows), results=output)


def census(distributed, centered):
    result = {}
    for panel in ("weak", "dense"):
        original = distributed_rows(distributed, panel)
        common = joint_rows(original, centered[panel]["details"])
        result[panel] = dict(prefix_distributed=counts([r for r in original.values() if r["mode"] == "short_primary"],
                                                      ("distributed",)),
                             common_three=counts(common, ("distributed", "centered")))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("distributed", "centered"):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    print(json.dumps(census(read(args.distributed, DISTRIBUTED), read(args.centered, CENTERED)), indent=2, sort_keys=True))
