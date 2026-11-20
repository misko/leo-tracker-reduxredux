"""Replay both original DS29-0082 primary rows on all conditional retry visits."""

import argparse
import csv
import json
import subprocess
from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json
from ..variants.original_kernel import PersistentGrid
from ..variants.selective_capture import visit_pairs
from . import field_exact_waveform as field
from . import single_pass_position as lower
from .full_v5_check import _sha

IDENT = field.IDENT
REPORT = field.REPORT.parents[1] / "retry-and-transfer/upper-primary"
WORK = Path("/srv/bulk/leo-dev/upper-primary-20261119-A")
METHOD = "upper_original_primary12_complete_factors"
MODULE = "tools.pipeline_eval.qualification.upper_primary"
CPUS = lower.CPUS
base = lower.base
assay = lower.assay


@contextmanager
def configured():
    with patch.multiple(base, IDENT=IDENT, REPORT=REPORT, METHOD=METHOD, MODULE=MODULE):
        yield


def parent_path(lock, name):
    return whole_iq.checked(field.REPORT / name, lock["parent_files"][name])


def archive(lock):
    document = assay.read_gzip(parent_path(lock, "native.json.gz"))
    original = whole_iq.read(
        whole_iq.checked(
            base.BULK / lock["original"]["native"]["path"], lock["original"]["native"]["sha256"]
        )
    )
    if (
        document["source"]["probes"] != original["source"]["probes"]
        or document["provenance"]["excluded_windows"] != original["provenance"]["excluded_windows"]
        or any(
            document[k] != original[k]
            for k in ("clock_anchor", "delivery_clocks", "last_sample_counter", "schema_version")
        )
        or document["source"]["input_manifest_sha256"] != lock["capture"]["input_manifest_sha256"]
        or document["source"]["raw_recording_authority_digest"]
        != original["source"]["raw_recording_authority_digest"]
    ):
        raise ValueError("the whole field-exact capture changed its original rows or clocks")
    return document


def verify_traces(lock, ledger, grid):
    by_cpu = {cpu: {} for cpu, _, _ in lock["workers"]}
    for row in ledger:
        cpu, ordinal = int(row["cpu"]), int(row["ordinal"])
        if ordinal in by_cpu[cpu]:
            raise ValueError("repeated field-exact telemetry ordinal")
        by_cpu[cpu][ordinal] = row
    for cpu, _, spans in lock["workers"]:
        saw = [
            json.loads(line.removeprefix(lower.TRACE))
            for line in parent_path(lock, f"receipts/cpu-{cpu}.log").read_text().splitlines()
            if line.startswith(lower.TRACE)
        ]
        roster = [offset + i for _, a, b, offset in spans for i in range(a, b)]
        if len(saw) != len(roster) or set(by_cpu[cpu]) != set(range(len(roster))):
            raise ValueError("historical trace did not cover every assigned ordinal")
        for i, (record, visit) in enumerate(zip(saw, roster, strict=True)):
            row = by_cpu[cpu][i]
            p, w = grid[visit]
            if (
                int(row["visit"]) != visit
                or record["ordinal"] != i
                or any(
                    record[key] != int(row[key])
                    for key in ("calls", "inverse_ffts", "input_ffts", "spans", "coarse_cpu_ns")
                )
                or (record["calls"], record["inverse_ffts"]) != (p + w, p * 104_286 + w * 191_037)
            ):
                raise ValueError("coarse census and measured trace differ")


def choose_controls(probes, selected):
    buckets = (
        ((False, False), False, 7),
        ((True, True), False, 4),
        ((True, False), True, 2),
        ((False, True), True, 2),
    )

    def order(v):
        return sha256(encoded([IDENT, "upper-primary-control-v1", v])).digest()

    controls = []
    for signature, retry, n in buckets:
        candidates = [
            v
            for v, pair in probes.items()
            if tuple(map(assay.positive, pair)) == signature and (v in selected) == retry
        ]
        if len(candidates) < n:
            raise ValueError("incomplete physical preflight strata")
        controls.extend(sorted(candidates, key=order)[:n])
    return sorted(controls)


def freeze(work):
    from .fresh_replay_results import sealed

    published = REPORT / "source-lock.json"
    if published.exists() or work.exists():
        raise FileExistsError("choose an unused physical replay attempt")
    receipt = sealed(field.REPORT, "prediction-lock.json")
    lock = whole_iq.read(
        whole_iq.checked(field.REPORT / "source-lock.json", receipt["files"]["source-lock.json"])
    )
    names = (
        "native.json.gz",
        "source-lock.json",
        "coarse.csv",
        "audit.json",
        "timing.csv",
        "positions.jsonl.gz",
        *(f"receipts/cpu-{cpu}.log" for cpu, _, _ in lock["workers"]),
    )
    lock["parent_files"] = {name: receipt["files"][name] for name in names}
    document = archive(lock)
    probes = dict(visit_pairs(document["source"]["probes"]))
    excluded = {r["visit"] for r in document["provenance"]["excluded_windows"]}
    with parent_path(lock, "coarse.csv").open(newline="") as stream:
        ledger = list(csv.DictReader(stream))
    grid = lower.census(ledger, probes, excluded)
    verify_traces(lock, ledger, grid)
    selected = {v for v, (_, wide) in grid.items() if wide}
    rescued = sum(all(map(assay.positive, probes[v])) for v in selected)
    total_positive = sum(map(assay.positive, document["source"]["probes"]))
    historical = whole_iq.read(parent_path(lock, "audit.json"))["raw"]
    if (
        (len(ledger), len(probes), len(excluded), len(selected), rescued, total_positive)
        != (6772, 4868, 1904, 1010, 228, 1868)
        or sum(sum(row) for row in grid.values()) != historical["measured_folded_calls"]
        or lock["capture"]["edge"] != "upper"
    ):
        raise ValueError("the measured upper-edge retry census changed")
    spans = sorted(span for _, _, chunks in lock["workers"] for span in chunks)
    controls = choose_controls(probes, selected)
    smoke = []
    for visit in controls:
        segment, _, _, offset = next(s for s in spans if s[3] + s[1] <= visit < s[3] + s[2])
        smoke.append((segment, visit - offset, visit))
    shapes = Counter(grid.values())
    lock.update(
        workers=lower.partition(spans, selected),
        smoke=smoke,
        selected=sorted(selected),
        census=[dict(primary=p, wide=w, visits=n) for (p, w), n in sorted(shapes.items())],
        rescued=rescued,
        historical_cpus=[c for c, _, _ in lock["workers"]],
        parent_prediction_lock_sha256=_sha(field.REPORT / "prediction-lock.json"),
        raw_limit_s=720,
    )
    sources = (
        Path(__file__),
        Path(lower.__file__),
        Path(assay.__file__),
        Path(assay.single_pass.__file__),
        Path(assay.prepared_hotpath_trial.__file__),
        REPORT / "PROTOCOL.md",
    )
    lock["sources"].update({str(p): _sha(p) for p in sources})
    work.mkdir(mode=0o755)
    smoke_input = work / "smoke-input.json"
    save_json(smoke_input, {str(v): probes[v] for v in controls})
    smoke_input.chmod(0o644)
    lock["smoke_input_sha256"] = _sha(smoke_input)
    for path in (published, work / published.name):
        save_json(path, lock)
        path.chmod(0o644)
    base.configure(work)
    print("Raw assignments", [(cpu, n, len(s)) for cpu, n, s in lock["workers"]], flush=True)


@contextmanager
def detector(lock, libs):
    from leo.analysis.starlink import acquisition
    from leo.scanner import fast_scan_analysis, fast_scan_detector

    policy, kernel = base.policy_for(lock), PersistentGrid(libs["prepared"])
    fine = field.fine_for(lock, libs["fine"])
    try:
        with (
            base.exact.refiners(libs),
            field.selector_waveform.selector(lock),
            kernel.route(acquisition, base.exact.starts.screen_module()),
            fine.route(),
        ):

            def evaluate(window, mode):
                observed = SimpleNamespace(**vars(window), receiver_ids=(0, 1))
                before = tuple(getattr(fine, k) for k in field.FINE_COUNTERS)
                result, timing = assay.trial(
                    observed, mode, policy, fast_scan_analysis, fast_scan_detector, kernel
                )
                timing["fine"] = {
                    k: getattr(fine, k) - old
                    for k, old in zip(field.FINE_COUNTERS, before, strict=True)
                }
                return result, timing

            yield evaluate
    finally:
        kernel.clear_cache()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "preflight", "smoke", "run", "raw"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("cpu", type=int, nargs="?", default=CPUS[0])
    args = parser.parse_args()
    with configured(), patch.object(lower, "detector", detector):
        if args.action == "freeze":
            freeze(args.work)
        elif args.action == "preflight":
            result = subprocess.run(
                base.service(
                    f"leo-upper-primary-preflight-{uuid4().hex[:8]}",
                    100,
                    base.command(args.work, args.cpu, "smoke"),
                ),
                check=True,
                stdout=subprocess.PIPE,
                timeout=115,
            )
            save_json(args.work / "smoke.json", json.loads(result.stdout))
        elif args.action == "smoke":
            lower.smoke(args.work)
        elif args.action == "run":
            field.check_evidence(args.work)
            base.run(args.work)
        else:
            lower.raw(args.work, args.cpu)


if __name__ == "__main__":
    main()
