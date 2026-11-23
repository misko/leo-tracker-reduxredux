"""Price a shared restart decision from archived signed aperture factors."""

import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
from math import remainder
from pathlib import Path

from .eight_ms_primary_trial import encoded
from .progressive_primary import agrees, needs_restart


HERE = Path(__file__).resolve().parent
PINS = {
    "eight-ms-primary.json.gz": "a6b67123abe0a740b2843f08cc1cde7f603e6f18dd890ad15cc3b3243fc317b3",
    "progressive-primary.json": "42e7e3b8ae22c0e959639188bdf84ec9cb1abeb123d52849c0269d953a993609",
}


def read_ledger(name):
    data = (HERE / "measurements" / name).read_bytes()
    if sha256(data).hexdigest() != PINS[name]:
        raise ValueError(f"Unexpected archived receipt {name}")
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)


def dense_pairs(panel):
    schedule = {(row["visit"], row["rx"]): row["slot"] for row in panel["lanes"].values()}
    first, longer = (panel["probes"][arm] for arm in ("8ms", "12ms"))
    if len(schedule) != len(first):
        raise ValueError("Dense schedule does not cover the original probes")
    ordered = []
    for short, long in zip(first, longer, strict=True):
        if ({k: v for k, v in short.items() if k != "candidates"}
                != {k: v for k, v in long.items() if k != "candidates"}):
            raise ValueError("Dense 8 and 12 ms probe identities differ")
        visit, rx = short["visit_index"], short["receiver_id"]
        if schedule[visit, rx] == "short_primary":
            ordered.append((visit, rx, encoded(short), encoded(long)))
        elif short != long:
            raise ValueError("The full anchor was changed")
    for a, b in zip(ordered[::2], ordered[1::2], strict=True):
        if a[0] != b[0] or (a[1], b[1]) != (0, 1):
            raise ValueError("Expected simultaneous dense stereo pairs")
        yield a[0], (a[2], b[2]), (a[3], b[3])


def weak_pairs(panel):
    rows = panel["records"]
    for a, b in zip(rows[::2], rows[1::2], strict=True):
        fields = ("id", "sample_sha256", "edge")
        if tuple(a[k] for k in fields) != tuple(b[k] for k in fields) or (a["rx"], b["rx"]) != (0, 1):
            raise ValueError("Expected simultaneous weak stereo pairs")

        def at(aperture):
            factors = (row["factors"][aperture] for row in (a, b))
            return tuple(encoded({"candidates": [f] if f else []}) for f in factors)

        yield a["id"], at("8ms"), at("12ms")


def stereo_rules(short):
    independent = tuple(map(needs_restart, short))
    pending = any(independent)
    bilateral = pending or not agrees(*short)
    return {"frozen_independent": independent, "paired_margin": (pending, pending),
            "bilateral": (bilateral, bilateral)}


def tally(pairs):
    decisions, joint = defaultdict(Counter), Counter()
    evidence = []
    for visit, short, long in pairs:
        mismatch = tuple(not agrees(a, b) for a, b in zip(short, long, strict=True))
        rules = stereo_rules(short)
        rules.update(oracle_independent=mismatch, oracle_stereo=(any(mismatch),) * 2)
        joint[f"mismatches_{sum(mismatch)}"] += 1
        if not any(rules["frozen_independent"]):
            (a,), (b,) = short
            joint["both_confident"] += 1
            joint["timing_within_tolerance"] += abs(remainder((a[1]+a[2])-(b[1]+b[2]), 13333)) <= 2
            joint["cfo_within_tolerance"] += abs(a[3]-b[3]) <= 250
        for key, retry in rules.items():
            missed = sum(bad and not paid for bad, paid in zip(mismatch, retry, strict=True))
            decisions[key].update(retry_lanes=sum(retry), retry_visits=any(retry), missed_lanes=missed)
        evidence.append(dict(visit=visit, mismatches=list(mismatch), retries=rules))
    return dict(pairs=len(evidence), counts=dict(decisions), pair_statistics=dict(joint), rows=evidence)


def rate_bounds(counts, timing):
    lanes = timing["lanes"]
    base = counts["frozen_independent"]
    independent, stereo = counts["oracle_independent"]["retry_lanes"], counts["oracle_stereo"]["retry_lanes"]
    if (base["retry_lanes"] != timing["effects"]["restarts"]
            or base["missed_lanes"] != timing["effects"]["missed_restarts"]
            or independent != timing["effects"]["necessary_restarts"]):
        raise ValueError("Archived confidence and answer-key counts differ")
    added = stereo - independent
    result = []
    for row in timing["repeats_ns"]:
        eight, direct, old_oracle = (row[key] for key in ("eight_native_ns", "direct_native_ns", "ideal_native_ns"))
        mean = direct / lanes
        result.append(dict(direct_native_ns=direct, eight_native_ns=eight,
                           frozen_measured_cpu_ns=row["candidate_ns"], direct_measured_cpu_ns=row["direct_ns"],
                           oracle_independent_cpu_ns=old_oracle, oracle_stereo_bounds_ns=[old_oracle, eight+direct],
                           oracle_stereo_equal_mean_ns=old_oracle+added*mean,
                           oracle_partner_break_even_average_ns=(direct-old_oracle)/added if added else None,
                           paired_margin_equal_mean_ns=eight+counts["paired_margin"]["retry_lanes"]*mean,
                           bilateral_equal_mean_ns=eight+counts["bilateral"]["retry_lanes"]*mean))
    return result


def audit(out):
    ledger = read_ledger("eight-ms-primary.json.gz")
    clocks = read_ledger("progressive-primary.json")
    if clocks["input_sha256"] != PINS["eight-ms-primary.json.gz"]:
        raise ValueError("Timing receipt used a different aperture ledger")
    panels = {}
    for name, pairs in (("dense", dense_pairs), ("weak", weak_pairs)):
        panel = tally(pairs(ledger[name]))
        timing = clocks["panels"][name]
        if 2*panel["pairs"] != timing["lanes"]:
            raise ValueError("Pair ledger does not cover the measured lanes")
        panel["cost"] = rate_bounds(panel["counts"], timing)
        panels[name] = panel
    with out.open("x") as f:
        json.dump(dict(pins=PINS, panels=panels), f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    audit(parser.parse_args().output)
