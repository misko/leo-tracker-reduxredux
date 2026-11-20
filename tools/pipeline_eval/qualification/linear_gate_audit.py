"""Measure how often the original zero-calibration check rules out a predictive fit."""

import argparse
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import cache
from pathlib import Path
from zipfile import ZipFile

from ..__main__ import encoded, local_output, read_predictions, save_json
from ..scoring import ARMS
from ..variants import v5_lean
from . import initial_branch_audit, search_budget
from .prefix_figures import csv_file
from .search_budget import digest
from .v5_postfit import ARCHIVE, _map
from .v5_prefix_audit import DS29, value

REPORT = Path(__file__).resolve().parents[3] / "reports/2026_11_19_receiver_screening/lazy-pair"
GATE_SHA = "429c230cb01438a4889f6e77256b7f00df4435b3522632bbef8cc2a83d223ca1"


@cache
def original_gate():
    sys.path.insert(0, str(v5_lean.SOURCE))
    try:
        from leo.analysis.localization_v3 import history_policy
    finally:
        sys.path.pop(0)
    source = Path(history_policy.__file__).resolve()
    if not source.is_relative_to(v5_lean.SOURCE) or digest(source) != GATE_SHA:
        raise ValueError("original predictive policy source changed")
    return history_policy.pair_passes


def field(raw, name, following):
    start, stop = (b'["' + n.encode() + b'",' for n in (name, following))
    if raw.count(start) != 1:
        raise ValueError(f"ambiguous original {name} archive field")
    a = raw.index(start) + len(start)
    b = raw.find(stop, a)
    if b < a + 2 or raw[b - 2 : b] != b"],":
        raise ValueError(f"malformed archive slice for {name}")
    return json.loads(raw[a : b - 2])


def portable_record(node, archive):
    record = _map(node)

    def gates(data):
        if data[0] != "list":
            raise ValueError("expected an ordered list of compatibility gates")
        result = [{"compatible": _map(r)["compatible"]} for r in data[1]]
        if any(type(r["compatible"]) is not bool for r in result):
            raise ValueError("compatibility must be an archived boolean")
        return result

    return dict(
        gates={"tracks": gates(_map(record["gates"])["tracks"])},
        linear_gates=gates(record["linear_gates"]),
        endpoint_east_north_km=value(record["endpoint_east_north_km"], archive),
        final_phase_change_s=value(record["final_phase_change_s"], archive),
    )


def half_width(raw, archive):
    header = b'["history_policy",["map",['
    end = b'["start_east_north_km",'
    if raw.count(header) != 1:
        raise ValueError("expected one archived history policy")
    a = raw.index(header) + len(header)
    b = raw.index(end, a) + len(end)
    width = value(field(raw[a:b], "box_width_km", "start_east_north_km"), archive)
    if not math.isfinite(width) or width <= 0:
        raise ValueError("invalid recorded history-policy tile width")
    return width / 2


def eligibility(pair, half_width, gate):
    if set(pair) != set(ARMS):
        raise ValueError("the predictive check requires both calibration settings")

    # The frozen gate is a conjunction of identical per-arm predicates, evaluated c0 first.
    def passes(data):
        return gate(data, include_linear=True, half_width_km=half_width)

    first, second = [passes(dict.fromkeys(ARMS, pair[arm])) for arm in ARMS]
    both = passes(pair)
    if both != (first and second):
        raise ValueError("paired acceptance depends on more than per-arm predicates")
    return first, second, both


def inspect(record):
    ident = record["id"]
    root = ARCHIVE if ident.startswith("DS26-") else DS29
    path = root / (ident + "-r0") / "baseline/experimental-evidence.zip"
    if digest(path) != record["source_archive_sha256"]:
        raise ValueError(f"original v5 archive differs for {ident}")
    with ZipFile(path) as archive:
        raw = archive.read("values.json")
        if raw.count(encoded(["request_sha256", "sha256:" + record["input_sha256"]])) != 1:
            raise ValueError("original request and predictive decision differ")
        pair = {
            a: portable_record(n, archive)
            for a, n in _map(field(raw, "linear_arms", "linear_entries")).items()
        }
        reported = field(raw, "linear_paired_valid", "fallback")
        count = field(raw, "linear_offered_tracks", "linear_offered_points")
        radius = half_width(raw, archive)
    first, second, both = eligibility(pair, radius, original_gate())
    if type(reported) is not bool or both != reported:
        raise ValueError(f"predictive decision disagrees with original v5 on {ident}")
    return dict(
        recording=ident,
        dataset=ident[:4],
        offered_linear_tracks=count,
        c0_passes=first,
        fitted_c_passes=second,
        original_paired_accepts=reported,
        fitted_c_probe_can_be_skipped=not first,
        archive_sha256=record["source_archive_sha256"],
    )


def audit(output, jobs):
    source = search_budget.REPORT / "initial-checkpoints"
    path = source / f"{initial_branch_audit.STOCK}.jsonl.gz"
    receipt = json.loads((source / "receipt.json").read_bytes())
    if (
        digest(path) != receipt["files"][path.name]
        or receipt["scientific_source"] != v5_lean.SOURCE_SHA256
    ):
        raise ValueError("original numerical archive index differs")
    records = read_predictions(path)
    if sorted(records) != receipt["cases"]:
        raise ValueError("original v5 roster differs")
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        rows = list(executor.map(inspect, records.values()))
    csv_file(output / "archived-gates.csv", rows)
    groups = {}
    for ds in ("DS26", "DS29", "all"):
        group = [r for r in rows if ds in ("all", r["dataset"])]
        groups[ds] = dict(
            cases=len(group),
            paired_accepts=sum(r["original_paired_accepts"] for r in group),
            c0_rejects=sum(not r["c0_passes"] for r in group),
            fitted_only_rejects=sum(r["c0_passes"] and not r["fitted_c_passes"] for r in group),
            empty_offers=sum(r["offered_linear_tracks"] == 0 for r in group),
        )
    save_json(
        output / "archived-gates.json",
        dict(
            gate_sha256=GATE_SHA,
            original_sources_sha256=digest(source / "receipt.json"),
            csv_sha256=digest(output / "archived-gates.csv"),
            groups=groups,
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--out", type=Path, default=REPORT)
    cli.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
    args = cli.parse_args()
    audit(local_output(args.out), args.jobs)
