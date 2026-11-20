"""Run the complete capture detector with one or two anchor sets on authenticated IQ."""

import argparse
import csv
import gzip
import json
import os
import subprocess
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from ..__main__ import ROOT, encoded, save_json, write
from ..variants import iq_stream, prepared_hotpath_peaks, single_pass
from ..variants.original_kernel import PersistentGrid
from ..variants.selective_capture import visit_pairs
from . import capture_starts, oracle_start, prepared_hotpath_trial, selector_waveform
from .capture_runtime import checked, read
from .full_v5_check import BULK, _load_case, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/pilot-search-and-region/single-pass"
CASE_IDS = tuple(sorted(capture_starts.CASES))
KNOWN = "known-wide-miss"
HELD = "outcome-blind"
COUNT = 16
REPEATS = 5
MODULE = "tools.pipeline_eval.qualification.single_pass_trial"
original = prepared_hotpath_trial.original
exact = prepared_hotpath_trial.exact


def sealed(folder, lock_name, artifact):
    return checked(folder / artifact, read(folder / lock_name)["files"][artifact])


def choose(case_id, visits, excluded):
    """Sample by a fixed hash of recording/visit keys before reading candidate outcomes."""

    def rank(visit):
        return sha256(encoded(["capture-single-pass-v1", case_id, visit])).digest(), visit

    return sorted(sorted(set(visits) - set(excluded), key=rank)[:COUNT])


def positive(probe):
    return any(c["passed_fractional_margin_gate"] for c in probe["candidates"])


def archive_bounds(pairs, counts=None):
    """Identify retry count from final support and, where present, the grid ledger."""
    outcomes, retry = Counter(), Counter()
    for visit, probes in pairs:
        hit = tuple(map(positive, probes))
        outcomes[str(int(hit[0])) + str(int(hit[1]))] += 1
        minimum, maximum = int(sum(hit) == 1), int(any(hit))
        if counts is not None:
            observed = counts[visit]
            if not minimum <= observed <= maximum:
                raise ValueError("complete grid ledger and gate-derived retry bounds disagree")
            minimum = maximum = observed
        retry["visit_min"] += minimum
        retry["visit_max"] += maximum
        if sum(hit) == 1:
            retry[f"rx{int(hit[0])}_min"] += 1
            retry[f"rx{int(hit[0])}_max"] += 1
        if all(hit):
            for rx in (0, 1):
                retry[f"rx{rx}_max"] += maximum
    return dict(
        final_lanes=dict(outcomes), retry_bounds=dict(retry), grid_ledger=counts is not None
    )


def archive_counts():
    path = sealed(selector_waveform.REPORT, "prediction-lock.json", "cache.csv")
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    counts, total = {}, 0
    for row in rows:
        if row["status"] != "processed":
            continue
        calls, inverses, spans = (int(row[key]) for key in ("calls", "inverse_ffts", "spans"))
        # Every dense 21 x 13,333 grid uses the fixed work for its anchor set.
        # The conditioned-CFO tie guard may repeat that same acquisition.
        wide, remainder = divmod(inverses - calls * 104286, 191037 - 104286)
        if remainder or spans != calls * 21 * 13333 or not 0 <= wide <= 2:
            raise ValueError("the grid ledger does not identify the anchor mix")
        if not 2 <= calls - wide <= 4 or (wide and calls - wide > 3):
            raise ValueError("the grid ledger violates the dual single-retry geometry")
        counts[int(row["visit"])] = int(wide > 0)
        total += calls
    if len(counts) != 6766 or total != 15330:
        raise ValueError("complete selector grid ledger does not agree with its published totals")
    return path, counts


def freeze(work):
    prepared = sealed(
        prepared_hotpath_trial.REPORT, "qualification-lock.json", "selector-input-lock.json"
    )
    selection = sealed(capture_starts.REPORT, "result-lock.json", "input-lock.json")
    authority = sealed(oracle_start.REPORT, "result-lock.json", "input-lock.json")
    trace_plan, labels, base = (read(path) for path in (selection, authority, prepared))
    ledger, counts = archive_counts()
    cases = {}
    for name in CASE_IDS:
        case = _load_case(name)
        trace = trace_plan["cases"][name]
        archive = checked(BULK / case["native"]["path"], case["native"]["sha256"])
        document = read(archive)
        pairs = dict(visit_pairs(document["source"]["probes"]))
        selected_trace = labels["cases"][name]["selected"]
        exclusions = set(trace["visits"]) | {
            item["visit"] for item in base["cases"].get(name, {}).get("rows", ())
        }
        visits = choose(name, pairs, exclusions)
        if len(visits) != COUNT:
            raise ValueError("the outcome-blind sample is incomplete")
        targets = {item["visit"]: item for item in selected_trace if item["kind"] == "miss"}
        trace_file = sealed(capture_starts.REPORT, "result-lock.json", f"{name}-capture.json.gz")
        trace_rows = {item["visit"]: item for item in read_gzip(trace_file)["capture"]}
        selection_rows = []
        for visit in sorted(visits + list(targets)):
            segment, sequence, manifest, digest = original.locate(case, visit)
            probe_pair = pairs[visit]
            row = dict(
                visit=visit,
                segment=segment,
                sequence=sequence,
                manifest=str(manifest),
                manifest_sha256=digest,
                probes=probe_pair,
                cohort=HELD,
            )
            if visit in targets:
                target = targets[visit]
                traced = trace_rows[visit]
                if (target["segment"], target["sequence"], target["manifest_sha256"]) != (
                    segment,
                    sequence,
                    digest,
                ):
                    raise ValueError("known target lost signed raw support")
                if list(probe_pair) != traced["capture"]["probes"]:
                    raise ValueError("known target's trace disagrees with the capture archive")
                row.update(
                    cohort=KNOWN,
                    target=target["target"],
                    receiver=target["receiver"],
                    iq_sha256=target["iq_sha256"],
                )
            selection_rows.append(row)
        cases[name] = dict(
            producer=trace,
            rows=selection_rows,
            archive=case["native"],
            trace_sha256=_sha(trace_file),
            archive_structure=archive_bounds(
                pairs.items(), counts if name == "DS26-0237" else None
            ),
        )
        print(name, "held", visits, "known misses", sorted(targets), flush=True)
    sources = [
        Path(__file__),
        Path(single_pass.__file__),
        Path(prepared_hotpath_peaks.__file__),
        Path(iq_stream.__file__),
        Path(exact.__file__),
        Path(original.__file__),
        prepared,
        selection,
        authority,
        ledger,
    ]
    work.mkdir()
    save_json(
        work / "input-lock.json",
        dict(
            cases=cases,
            modes=single_pass.MODES,
            repeats=REPEATS,
            libs=base["libs"],
            python_sha256=base["python_sha256"],
            sources={str(path): _sha(path) for path in sources},
        ),
    )


def read_gzip(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def validate_attempts(attempts, mode, receivers, probes):
    if mode == "conditional":
        if [(rx, anchors) for rx, anchors, _ in attempts[:2]] != [(rx, 12) for rx in receivers]:
            raise ValueError("the conditional path skipped a primary evaluation")
        primary = {rx: passing for rx, _, passing in attempts[:2]}
        retry = [(rx, 22) for rx in receivers if not primary[rx] and any(primary.values())]
        if [(rx, anchors) for rx, anchors, _ in attempts[2:]] != retry:
            raise ValueError("observed retry differs from the producer rule")
    elif [(rx, anchors) for rx, anchors, _ in attempts] != [
        (rx, 12 if mode == "primary12" else 22) for rx in receivers
    ]:
        raise ValueError("one-pass mode did not run one complete acquisition on each lane")
    final = {rx: passing for rx, _, passing in attempts}
    if [final[rx] for rx in receivers] != list(map(positive, probes)):
        raise ValueError("observed retry gate differs from the projected gate")


def trial(window, mode, policy, analysis, detector, grid):
    grid.calls.clear()
    with single_pass.route(analysis, detector, mode) as attempts:
        result, timing = prepared_hotpath_trial.sample(window, policy)
    validate_attempts(attempts, mode, window.receiver_ids, result[1])
    primary_grids, wide_grids = (sum(c["anchors"] == n for c in grid.calls) for n in (12, 22))
    primary_attempts, wide_attempts = (sum(a[1] == n for a in attempts) for n in (12, 22))
    if not (
        primary_grids + wide_grids == len(grid.calls)
        and all(c["applied"] for c in grid.calls)
        and primary_attempts <= primary_grids <= 2 * primary_attempts
        and wide_attempts <= wide_grids <= 2 * wide_attempts
    ):
        raise ValueError("the prepared full grid was bypassed")
    coarse_ns = sum(c["config_cpu_ns"] + c["native_cpu_ns"] for c in grid.calls)
    return dict(public=result[0], probes=result[1], attempts=attempts), dict(
        **timing,
        coarse_cpu_ns=coarse_ns,
        primary_grids=primary_grids,
        wide_grids=wide_grids,
        fft_inverses=sum(c["inverse_ffts"] for c in grid.calls),
    )


def load_windows(rows):
    segments = defaultdict(list)
    for row in rows:
        segments[row["segment"]].append(row)
    for fixtures in segments.values():
        binding = fixtures[0]
        policy = dict(
            recording_path=binding["manifest"],
            recording_sha256="sha256:" + binding["manifest_sha256"],
        )
        with patch.multiple(
            iq_stream,
            MAX_CHUNK_PREFIX=original.MAX_PREFIX,
            MAX_DECODE_BYTES=original.MAX_PREFIX * len(fixtures),
        ):
            windows = iq_stream.load_windows(policy, [r["sequence"] for r in fixtures])
        for fixture, window in zip(fixtures, windows, strict=True):
            probe_pair = fixture["probes"]
            if (
                window.acquisition["global_visit"] != fixture["visit"]
                or window.samples.shape != (200_000, 2, 2)
                or window.acquisition["sample_start"] != probe_pair[0]["valid_start_counter"]
                or window.iq_sha256 != fixture.get("iq_sha256", window.iq_sha256)
            ):
                raise ValueError("saved IQ differs from the original raw authority")
            yield fixture, window


def worker(work, name, cpu):
    from leo.analysis.starlink import acquisition
    from leo.scanner import fast_scan_analysis, fast_scan_detector

    lock = read(work / "input-lock.json")
    case = lock["cases"][name]
    producer = case["producer"]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError("the trial must run on its assigned CPU")
    checked(original.PYTHON, lock["python_sha256"])
    for path, digest in (lock["sources"] | producer["sources"]).items():
        checked(Path(path), digest)
    capture, policy, observed = exact.lineage.source_lineage(_load_case(name))
    if (
        observed["capture"]["root"],
        capture["edge"],
        observed["capture"]["input_manifest_sha256"],
    ) != (producer["producer"], producer["edge"], producer["input_manifest_sha256"]):
        raise ValueError("worker ran against a different capture producer")
    libraries = {k: checked(Path(v["path"]), v["sha256"]) for k, v in lock["libs"].items()}
    grid = PersistentGrid(libraries["prepared"])
    modes, rows = single_pass.MODES, []
    try:
        with (
            exact.refiners(libraries),
            grid.route(acquisition, capture_starts.screen_module()),
            patch.object(
                acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
            ),
        ):
            for index, (fixture, window) in enumerate(load_windows(case["rows"])):

                def call(mode, window=window):
                    return trial(window, mode, policy, fast_scan_analysis, fast_scan_detector, grid)

                evidence = {mode: call(mode)[0] for mode in modes}
                if evidence["conditional"]["probes"] != fixture["probes"]:
                    raise ValueError(
                        "prepared conditional reference changed the archived probe factors"
                    )
                clocks = defaultdict(list)
                if fixture["cohort"] == HELD:
                    for repetition in range(REPEATS):
                        turn = (index + repetition) % len(modes)
                        for order, mode in enumerate(modes[turn:] + modes[:turn]):
                            result, timing = call(mode)
                            if result != evidence[mode]:
                                raise ValueError(
                                    "interleaved replay changed the complete ordered result"
                                )
                            clocks[mode].append(dict(**timing, repetition=repetition, order=order))
                rows.append(
                    dict(
                        visit=fixture["visit"],
                        iq_sha256=window.iq_sha256,
                        cohort=fixture["cohort"],
                        evidence=evidence,
                        clocks=dict(clocks),
                    )
                )
                print(name, fixture["visit"], fixture["cohort"], flush=True)
    finally:
        grid.clear_cache()
    write(
        work / f"{name}.json.gz",
        gzip.compress(
            encoded(
                dict(
                    case=name,
                    cpu=cpu,
                    rows=rows,
                    peak_rss_kib=exact.stages.resident()["hwm_kib"],
                    input_lock_sha256=_sha(work / "input-lock.json"),
                )
            ),
            mtime=0,
        ),
    )


def run(work, name, cpu):
    producer = read(work / "input-lock.json")["cases"][name]["producer"]
    env = os.environ | {"PYTHONPATH": f"{producer['producer']}:{ROOT}"}
    for prefix in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR", "BLIS"):
        env[prefix + "_NUM_THREADS"] = "1"
    subprocess.run(
        [
            "taskset",
            "-c",
            str(cpu),
            str(original.PYTHON),
            "-u",
            "-m",
            MODULE,
            "worker",
            str(work),
            name,
            str(cpu),
        ],
        cwd=ROOT,
        env=env,
        check=True,
        timeout=420,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("work", type=Path)
    parser.add_argument("case", choices=CASE_IDS, nargs="?")
    parser.add_argument("cpu", type=int, nargs="?")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    else:
        if args.case is None or args.cpu is None:
            parser.error("a recording and CPU are required")
        (worker if args.action == "worker" else run)(args.work, args.case, args.cpu)
