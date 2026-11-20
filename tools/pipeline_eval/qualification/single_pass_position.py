"""Replay the two primary anchor rows on every DS26-0237 conditional retry."""

import argparse
import csv
import json
import subprocess
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json
from ..variants.original_kernel import PersistentGrid
from ..variants.selective_capture import visit_pairs
from . import capture_whole as base
from . import selector_waveform as prior
from . import single_pass_trial as assay
from .full_v5_check import _sha

IDENT = "DS26-0237"
REPORT = assay.REPORT / "position"
WORK = Path("/srv/bulk/leo-dev/single-pass-position-20261119-B")
ASSAY = WORK.with_name("single-pass-20261119-B") / "input-lock.json"
HISTORICAL = REPORT.parents[2] / "latency-and-support/complete-roster"
METHOD = "original_capture_primary12_complete_factors"
MODULE = "tools.pipeline_eval.qualification.single_pass_position"
CPUS = (12, 13, 14, 15)
TRACE = "prepared-grid-v1: "


@contextmanager
def configured():
    with patch.multiple(base, IDENT=IDENT, REPORT=REPORT, METHOD=METHOD, MODULE=MODULE):
        yield


def parent_path(lock, name):
    return whole_iq.checked(prior.REPORT / name, lock["parent_files"][name])


def census(rows, probes, excluded):
    """Validate all physical visits, with tie repeats counted as acquisition calls."""
    grid = {}
    for row in rows:
        visit = int(row["visit"])
        if visit in grid:
            raise ValueError("duplicate visit in historical grid ledger")
        status = "invalid_capture" if visit in excluded else "processed"
        if row["status"] != status:
            raise ValueError("grid ledger disagrees with physical validity")
        calls, inverse, inputs, spans = (
            int(row[key]) for key in ("calls", "inverse_ffts", "input_ffts", "spans")
        )
        # One complete CFO grid uses 427 input transforms on this producer.
        # Each resolution has the same 21 lanes and 13,333 epochs. The
        # per-anchor inverse work differs, even when the tie guard repeats it.
        if inputs != 427 * calls or spans != 21 * 13_333 * calls:
            raise ValueError("grid dimensions differ from the historical prepared detector")
        if status == "invalid_capture":
            if calls or inverse:
                raise ValueError("excluded visit entered the detector")
            grid[visit] = (0, 0)
            continue
        mixes = [
            (p, w)
            for p in (2, 3, 4)
            for w in (0, 1, 2)
            if p + w == calls and p * 104_286 + w * 191_037 == inverse
        ]
        if len(mixes) != 1:
            raise ValueError("prepared trace did not uniquely identify the anchor counts")
        primary, wide = mixes[0]
        positive = sum(assay.positive(lane) for lane in probes[visit])
        if (wide and (not positive or primary > 3)) or (positive == 1 and not wide):
            raise ValueError("conditional branch lacks its required physical gate support")
        grid[visit] = primary, wide
    if set(grid) != set(probes) | excluded or set(probes) & excluded:
        raise ValueError("grid ledger and complete physical support differ")
    return grid


def verify_history(lock, chunks):
    """Match the published census against per-call traces and measured terminal receipts."""
    _, expected = assay.archive_counts()
    document = assay.read_gzip(parent_path(lock, "native.json.gz"))
    archive = whole_iq.read(
        whole_iq.checked(
            base.BULK / lock["original"]["native"]["path"], lock["original"]["native"]["sha256"]
        )
    )
    probes = dict(visit_pairs(document["source"]["probes"]))
    if probes != dict(visit_pairs(archive["source"]["probes"])) or any(
        document[field] != archive[field]
        for field in ("clock_anchor", "delivery_clocks", "last_sample_counter")
    ):
        raise ValueError("historical measured probes or physical clocks differ from the archive")
    excluded = {r["visit"] for r in document["provenance"]["excluded_windows"]}
    if document["provenance"]["excluded_windows"] != archive["provenance"]["excluded_windows"]:
        raise ValueError("historical replay changed original physical exclusions")
    with parent_path(lock, "cache.csv").open(newline="") as stream:
        cached = list(csv.DictReader(stream))
    grid = census(cached, probes, excluded)
    if expected != {v: int(w > 0) for v, (_, w) in grid.items() if v not in excluded}:
        raise ValueError("independent grid and assay retry rosters differ")
    for cpu, _, spans in lock["workers"]:
        saw = [
            json.loads(line.removeprefix(TRACE))
            for line in parent_path(lock, f"receipts/cpu-{cpu}.log").read_text().splitlines()
            if line.startswith(TRACE)
        ]
        roster = [int(r["visit"]) for r in cached if int(r["cpu"]) == cpu]
        observed = [base + i for _, a, b, base in spans for i in range(a, b)]
        if roster != observed or len(saw) != len(roster):
            raise ValueError("published trace no longer matches the measured worker roster")
        for record, visit in zip(saw, roster, strict=True):
            p, w = grid[visit]
            if (record["calls"], record["inverse_ffts"]) != (p + w, p * 104_286 + w * 191_037):
                raise ValueError("published census and measured call trace differ")
    ledger = whole_iq.read(parent_path(lock, "audit.json"))["raw"]
    shape = Counter(grid.values())
    if (
        len(grid) != 6_768
        or len(excluded) != 2
        or len(probes) != 6_766
        or sum(expected.values()) != 1_592
        or sum(sum(x) for x in grid.values()) != 15_330
        or sum(b - a for _, a, b, _ in chunks) != ledger["completed"]
        or ledger["measured_folded_calls"] != 15_330
    ):
        raise ValueError("historical recording does not match the complete retry census")
    return document, probes, expected, shape


def partition(chunks, selected):
    """Balance detector visits across single-core workers and read each chunk once."""
    work = {cpu: [] for cpu in CPUS}
    costs = dict.fromkeys(CPUS, 0)
    weighted = [
        (sum(v in selected for v in range(a + base, b + base)), (seg, a, b, base))
        for seg, a, b, base in chunks
    ]
    for n, span in sorted(weighted, key=lambda x: (-x[0], x[1])):
        if n:
            cpu = min(CPUS, key=lambda c: (costs[c], len(work[c]), c))
            work[cpu].append(span)
            costs[cpu] += n
    return [(cpu, costs[cpu], sorted(work[cpu])) for cpu in CPUS]


def freeze(work, receipt):
    from .fresh_replay_results import sealed

    if (REPORT / "source-lock.json").exists() or work.exists():
        raise FileExistsError("use a new scope for an independent freeze")
    parent = sealed(prior.REPORT, "prediction-lock.json")
    lock = whole_iq.read(
        whole_iq.checked(prior.REPORT / "source-lock.json", parent["files"]["source-lock.json"])
    )
    history = sealed(HISTORICAL, "all-figure-lock.json")
    hold = whole_iq.read(receipt)["cases"][IDENT]
    names = (
        "native.json.gz",
        "source-lock.json",
        "cache.csv",
        "audit.json",
        "timing.csv",
        "positions.jsonl.gz",
        *(f"receipts/cpu-{cpu}.log" for cpu, _, _ in lock["workers"]),
    )
    lock["parent_files"] = {name: parent["files"][name] for name in names}
    lock["historical_positions_sha256"] = history["files"]["all-positions.jsonl.gz"]
    lock["input_locks"] = {
        str(prior.REPORT / "prediction-lock.json"): _sha(prior.REPORT / "prediction-lock.json"),
        str(HISTORICAL / "all-figure-lock.json"): _sha(HISTORICAL / "all-figure-lock.json"),
        str(receipt): _sha(receipt),
    }
    chunks = sorted(t for _, _, spans in lock["workers"] for t in spans)
    document, probes, expected, shape = verify_history(lock, chunks)
    if (
        hold["archive"] != lock["original"]["native"]
        or document["source"]["input_manifest_sha256"] != lock["capture"]["input_manifest_sha256"]
        or hold["producer"]["producer"] != lock["producer"]
    ):
        raise ValueError("held and complete waveform producers do not match")
    selected = sorted(v for v, retry in expected.items() if retry)
    held = [r["visit"] for r in hold["rows"] if r["cohort"] == assay.HELD]
    controls = [v for v in held if not expected[v]]
    if len(controls) < 4:
        raise ValueError("independent held controls require at least four no-retry visits")
    # Exactly one final positive identifies the opposite physical retry lane.
    for receiver in (0, 1):
        controls.append(
            min(
                v
                for v in selected
                if tuple(map(assay.positive, probes[v])) == (receiver == 1, receiver == 0)
            )
        )
    smoke = []
    for visit in sorted(controls):
        segment, _, _, offset = next(c for c in chunks if c[3] + c[1] <= visit < c[3] + c[2])
        smoke.append((segment, visit - offset, visit))
    lock.update(
        workers=partition(chunks, set(selected)),
        smoke=smoke,
        selected=selected,
        census=[dict(primary=p, wide=w, visits=n) for (p, w), n in sorted(shape.items())],
        raw_limit_s=720,
    )
    paths = (
        Path(__file__),
        Path(assay.__file__),
        Path(assay.single_pass.__file__),
        Path(assay.prepared_hotpath_trial.__file__),
        REPORT / "PROTOCOL.md",
    )
    lock["sources"].update({str(p): _sha(p) for p in paths})
    # Only readable code/recipe files go into worker verification. Prior
    # predictions and the held selection remain with the replay coordinator.
    protected = [name for name in lock["sources"] if not Path(name).stat().st_mode & 0o004]
    lock["evidence_sources"] = {name: lock["sources"].pop(name) for name in protected}
    work.mkdir(mode=0o755)
    smoke_archive = {str(v): probes[v] for _, _, v in smoke}
    save_json(work / "smoke-input.json", smoke_archive)
    (work / "smoke-input.json").chmod(0o644)
    lock["smoke_input_sha256"] = _sha(work / "smoke-input.json")
    for path in (work / "source-lock.json", REPORT / "source-lock.json"):
        save_json(path, lock)
        path.chmod(0o644)
    base.configure(work)
    print("Selected detector visits by CPU", [(c, n) for c, n, _ in lock["workers"]], flush=True)


@contextmanager
def detector(lock, libs):
    from leo.analysis.starlink import acquisition
    from leo.scanner import fast_scan_analysis, fast_scan_detector

    policy = base.policy_for(lock)
    kernel = PersistentGrid(libs["prepared"])
    try:
        with (
            base.exact.refiners(libs),
            prior.selector(lock),
            kernel.route(acquisition, base.exact.starts.screen_module()),
        ):

            def evaluate(window, mode):
                observed = SimpleNamespace(**vars(window), receiver_ids=(0, 1))
                return assay.trial(
                    observed, mode, policy, fast_scan_analysis, fast_scan_detector, kernel
                )

            yield evaluate
    finally:
        kernel.clear_cache()


def smoke(work):
    lock, libs = base.configure(work)
    baseline = whole_iq.read(
        whole_iq.checked(work / "smoke-input.json", lock["smoke_input_sha256"])
    )
    selected = set(lock["selected"])
    results, retry_lanes = [], set()
    with detector(lock, libs) as evaluate:
        for segment, first, visit in lock["smoke"]:
            (window,) = base.open_span(lock, segment, first, first + 1).windows()
            conditional, ct = evaluate(window, "conditional")
            primary, pt = evaluate(window, "primary12")
            retry = conditional["attempts"][2:]
            if (
                window.acquisition["global_visit"] != visit
                or encoded(conditional["probes"]) != encoded(baseline[str(visit)])
                or bool(retry) != (visit in selected)
                or conditional["attempts"][:2] != primary["attempts"]
                or (not retry and conditional != primary)
                or (retry and conditional["probes"] == primary["probes"])
            ):
                raise ValueError(
                    f"prepared primary or conditional counterfactual differs at {visit}"
                )
            if retry:
                lane, _, _ = retry[0]
                retry_lanes.add(lane)
                if conditional["probes"][1 - lane] != primary["probes"][1 - lane]:
                    raise ValueError("retry changed the other physical receiver")
            results.append(
                dict(
                    visit=visit,
                    iq_sha256=window.iq_sha256,
                    attempts=conditional["attempts"],
                    conditional_probe_sha256=base.recording.digest(conditional["probes"]),
                    primary_probe_sha256=base.recording.digest(primary["probes"]),
                    conditional_timing=ct,
                    primary_timing=pt,
                )
            )
    if retry_lanes != {0, 1}:
        raise ValueError("preflight needs both physical retry directions")
    print(encoded(dict(source_lock_sha256=_sha(work / "source-lock.json"), rows=results)).decode())


def raw(work, cpu):
    from leo.storage import short_window

    lock, libs = base.configure(work)
    _, total, chunks = next(x for x in lock["workers"] if x[0] == cpu)
    selected = set(lock["selected"])
    start, measured, verified = base.resources.memory(), 0, []
    if start["cpus"] != [cpu]:
        raise ValueError("worker outside its planned CPU")
    member = short_window.ShortWindowReader._member

    def stream(reader, name, size, digest):
        if any(chunk.payload_relative_path == name for chunk in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return base.resources.AuthenticatedMember(path, size, digest, verified)
        return member(reader, name, size, digest)

    def emit(record):
        print(encoded(record).decode(), flush=True)

    with (
        detector(lock, libs) as evaluate,
        patch.object(short_window.ShortWindowReader, "_member", stream),
    ):
        for segment, first, stop, offset in chunks:
            source = base.open_span(lock, segment, first, stop)
            count, before, previous = 0, perf_counter(), len(verified)
            for sequence, window in enumerate(source.windows(), first):
                visit = offset + sequence
                if (
                    visit != window.acquisition["global_visit"]
                    or sequence != window.sequence
                    or window.target["edge"] != lock["capture"]["edge"]
                ):
                    raise ValueError("signed visit order or physical edge changed")
                if visit in selected:
                    result, timing = evaluate(window, "primary12")
                    if sum(passed for _, _, passed in result["attempts"]) != 1:
                        raise ValueError(
                            "historical retry visit has the wrong primary gate pattern"
                        )
                    emit(
                        dict(
                            kind="visit",
                            segment=segment,
                            sequence=sequence,
                            visit=visit,
                            iq_sha256=window.iq_sha256,
                            probes=result["probes"],
                            attempts=result["attempts"],
                            **timing,
                        )
                    )
                    measured += 1
                count += 1
            if count != stop - first or len(verified) != previous + 1:
                raise ValueError("capture chunk was incomplete or failed authentication")
            emit(
                dict(
                    kind="chunk",
                    segment=segment,
                    first=first,
                    stop=stop,
                    manifest_digest=source.manifest_digest,
                    compressed_bytes=verified[-1],
                    wall_s=perf_counter() - before,
                )
            )
    if measured != total:
        raise ValueError("measured visits differ from the frozen retry roster")
    emit(
        dict(
            kind="worker",
            cpu=cpu,
            count=measured,
            start=start,
            end=base.resources.memory(),
            source_lock_sha256=_sha(work / "source-lock.json"),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "preflight", "smoke", "run", "raw"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("cpu", type=int, nargs="?", default=CPUS[0])
    parser.add_argument("--assay-lock", type=Path, default=ASSAY)
    args = parser.parse_args()
    with configured():
        if args.action == "freeze":
            freeze(args.work, args.assay_lock)
        elif args.action == "preflight":
            result = subprocess.run(
                base.service(
                    f"leo-primary-preflight-{uuid4().hex[:8]}",
                    100,
                    base.command(args.work, args.cpu, "smoke"),
                ),
                check=True,
                stdout=subprocess.PIPE,
                timeout=115,
            )
            save_json(args.work / "smoke.json", json.loads(result.stdout))
        elif args.action in ("run", "smoke"):
            if args.action == "run":
                lock, _ = base.configure(args.work)
                for name, digest in (lock["input_locks"] | lock["evidence_sources"]).items():
                    whole_iq.checked(Path(name), digest)
            (base.run if args.action == "run" else smoke)(args.work)
        else:
            raw(args.work, args.cpu)


if __name__ == "__main__":
    main()
