"""Measure what the two original primary antenna proposals cover before peer retry."""

import argparse
import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from ..__main__ import ROOT, save_json
from ..variants.selective_capture import visit_pairs
from .full_v5_check import ALIAS_HZ, _sha
from .prefix_figures import csv_file
from .single_pass_trial import REPORT as SINGLE_PASS

REPORT = ROOT / "reports/2026_11_19_receiver_screening/retry-and-transfer/peer-retry"
ORIGINAL = SINGLE_PASS.parents[1] / "receiver-deadline/selector-waveform"
PRIMARY = SINGLE_PASS / "position"
FRAME = 13_333
RADIUS = ((2, 1000), (8, 40_000), (32, 80_000))
PORTS = ("failed_top", "peer_top", "failed_all", "peer_all", "both_all")
SHUFFLES = 32


def cyclic(a, b, period):
    return abs((a - b + period / 2) % period - period / 2)


def position(row):
    return (
        row["integer_epoch_sample"] + row["fractional_epoch_offset_samples"],
        row["fractional_tracking_cfo_hz"],
    )


def active(probe):
    return [c for c in probe["candidates"] if c["passed_fractional_margin_gate"]]


def compare(target, proposals):
    """Require one proposal to share both components of support."""
    e, f = position(target)
    distances = []
    for proposal in proposals:
        pe, pf = position(proposal)
        distances.append((cyclic(e, pe, FRAME), cyclic(f, pf, ALIAS_HZ), abs(f - pf)))
    result = {}
    for ep, hz in RADIUS:
        result[f"epoch_{ep}"] = any(x <= ep for x, _, _ in distances)
        result[f"alias_{ep}_{hz}"] = any(x <= ep and y <= hz for x, y, _ in distances)
        result[f"literal_{ep}_{hz}"] = any(x <= ep and y <= hz for x, _, y in distances)
    return result


def ports(pair, failed):
    a, b = (pair[rx]["candidates"] for rx in (failed, 1 - failed))
    return dict(zip(PORTS, (a[:1], b[:1], a, b, a + b), strict=True))


def cohorts(full, primary):
    if full.keys() != primary.keys():
        raise ValueError("full and primary captures differ in scheduled physical support")
    groups = defaultdict(list)
    for visit, pair in full.items():
        mains = primary[visit]
        original, first = (list(map(active, r)) for r in (pair, mains))
        if any(
            {k: v for k, v in a.items() if k != "candidates"}
            != {k: v for k, v in b.items() if k != "candidates"}
            for a, b in zip(pair, mains, strict=True)
        ):
            raise ValueError("same-visit physical support changed")
        if not (all(original) and sum(map(bool, first)) == 1):
            continue
        failed = 0 if not first[0] else 1
        if pair[1 - failed] != mains[1 - failed]:
            raise ValueError("conditional retry changed the passing physical lane")
        group = (failed, pair[failed]["channel"])
        groups[group].append((visit, original[failed]))
    return groups


def measure(full, primary):
    groups = cohorts(full, primary)
    rng = np.random.default_rng(39821)
    rows = []
    for (failed, channel), visits in sorted(groups.items()):
        if len(visits) < 2:
            raise ValueError("a matched shuffle group has fewer than two rescue visits")
        orders = []
        for _ in range(SHUFFLES):
            order = rng.permutation(len(visits))
            orders.append(dict(zip(order, np.roll(order, 1), strict=True)))
        proposals = [ports(primary[v], failed) for v, _ in visits]
        for j, (visit, targets) in enumerate(visits):
            for target in targets:
                for port in PORTS:
                    truth = compare(target, proposals[j][port])
                    shuffled = [compare(target, proposals[order[j]][port]) for order in orders]
                    rows.append(
                        dict(
                            visit=visit,
                            receiver=failed,
                            channel=channel,
                            target_rank=target["candidate_rank"],
                            port=port,
                            **{key: int(value) for key, value in truth.items()},
                            **{
                                key + "_shuffled": sum(item[key] for item in shuffled)
                                for key in truth
                            },
                        )
                    )
    return rows


def verified(folder, seal, name):
    expected = json.loads((folder / seal).read_bytes())["files"][name]
    path = folder / name
    if _sha(path) != expected:
        raise ValueError(f"sealed source differs: {path}")
    return path


def factor_rows(path):
    return json.loads(gzip.decompress(path.read_bytes()))["source"]["probes"]


def run(report):
    full_path = verified(ORIGINAL, "prediction-lock.json", "native.json.gz")
    primary_path = verified(PRIMARY, "prediction-lock.json", "native.json.gz")
    changed = verified(PRIMARY, "prediction-lock.json", "changed-visits.csv")
    original, primary = (dict(visit_pairs(factor_rows(p))) for p in (full_path, primary_path))
    samples = measure(original, primary)
    with changed.open(newline="") as f:
        expected = {
            (int(r["visit"]), int(r["receiver"]))
            for r in csv.DictReader(f)
            if r["conditional_positive"] == "True" and r["primary_positive"] == "False"
        }
    actual = {(r["visit"], r["receiver"]) for r in samples}
    if actual != expected or len(actual) != 448:
        raise ValueError("full-factor rescue roster does not match the independent replay")
    report.mkdir(exist_ok=True, parents=True)
    csv_file(report / "primary-support.csv", samples)
    summary = {}
    count_fields = [
        k
        for k in samples[0]
        if k.startswith(("alias", "literal", "epoch")) and not k.endswith("_shuffled")
    ]
    for port in PORTS:
        subset = [r for r in samples if r["port"] == port]
        summary[port] = {
            k: dict(
                observed=sum(r[k] for r in subset),
                observed_probes=len({(r["visit"], r["receiver"]) for r in subset if r[k]}),
                shuffled_fraction=sum(r[k + "_shuffled"] for r in subset)
                / (len(subset) * SHUFFLES),
            )
            for k in count_fields
        }
    save_json(
        report / "primary-support.json",
        dict(
            case="DS26-0237",
            probes=len(expected),
            winners=len(samples) // len(PORTS),
            calls_per_shuffle=SHUFFLES,
            physical_group_count=len(cohorts(original, primary)),
            files={str(p): _sha(p) for p in (full_path, primary_path, changed, Path(__file__))},
            support=summary,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPORT)
    run(parser.parse_args().out)
