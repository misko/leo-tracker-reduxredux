"""Run original wide anchors and causal bounded pilot searches on saved IQ."""

import argparse
import json
import subprocess
from collections import Counter
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch
from uuid import uuid4

import numpy as np

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json
from ..variants import seeded_acquisition as seeded
from ..variants.original_kernel import PersistentGrid
from ..variants.selective_capture import visit_pairs
from . import field_exact_waveform as field
from .capture_detector_replay import scan_capture_window
from .full_v5_check import _from_native, _probe, _sha, factor_candidate

DEVELOPMENT, HELD = "DS26-0237", "DS29-0082"
SPANS = 128
CADENCE = 6
DEVRATES = (220, 550)
REPORT = field.REPORT.parents[1] / "coarse-and-navigation/seeded-acquisition"
WORK = Path("/var/tmp/leo-seeded-acquisition-20261120-A")
MODULE = "tools.pipeline_eval.qualification.seeded_acquisition_trial"
CPUS = {DEVELOPMENT: 12, HELD: 13}
base = field.base


def choose_span(ident, chunks, invalid):
    """Freeze adjacent complete chunks from one segment using capture validity only."""
    available = []
    ordered = sorted(chunks)
    for (i, a, b, offset), (j, c, d, other) in zip(ordered, ordered[1:], strict=False):
        if (i, b, offset) != (j, c, other) or b - a != 64 or d - c != 64:
            continue
        if sum(v not in invalid for v in range(offset + a, offset + d)) >= 80:
            available.append((i, a, d, offset))
    return min(
        available, key=lambda x: sha256(encoded([ident, "seeded-acquisition-span-v1", x])).digest()
    )


def freeze(work):
    from . import paired_epoch_build, retry_cadence_trial, wide_regional_build
    from .fresh_replay_results import sealed

    if work.exists() or (REPORT / "source-lock.json").exists():
        raise FileExistsError("choose a fresh frozen experiment scope")
    fine = sealed(field.PANEL, "qualification-lock.json", field.PANEL_SHA)
    qualified = whole_iq.read(
        whole_iq.checked(field.PANEL / "input-lock.json", fine["files"]["input-lock.json"])
    )
    fast = whole_iq.checked(
        wide_regional_build.ROOT / "wide" / wide_regional_build.LIBRARY,
        paired_epoch_build.BASE_SHA256,
    )
    work.mkdir(mode=0o755)
    files = {}
    for ident in (DEVELOPMENT, HELD):
        full, _, lock, _ = retry_cadence_trial.sources(ident)
        audit = qualified["cases"][ident]
        if (
            audit["root"] != lock["producer"]
            or audit["archive_sha256"] != lock["original"]["native"]["sha256"]
            or audit["input_manifest"] != lock["capture"]["input_manifest_sha256"]
            or any(qualified["libs"][k] != v for k, v in lock["libraries"].items())
        ):
            raise ValueError(
                "the chosen FFT and fine kernels were qualified on a different capture"
            )
        probes = dict(visit_pairs(full["source"]["probes"]))
        invalid = {r["visit"]: r for r in full["provenance"]["excluded_windows"]}
        span = choose_span(ident, [s for _, _, chunks in lock["workers"] for s in chunks], invalid)
        _, a, b, offset = span
        clocks = full["delivery_clocks"]
        ref = {
            str(v): dict(probes=probes.get(v), exclusion=invalid.get(v), clock=clocks[v])
            for v in range(offset + a, offset + b)
        }
        sources = lock["sources"] | audit["sources"] | qualified["sources"]
        sources.update(
            {
                str(p): _sha(p)
                for p in (Path(__file__), Path(seeded.__file__), REPORT / "PROTOCOL.md")
            }
        )
        for path, digest in sources.items():
            whole_iq.checked(Path(path), digest)
        lock.update(
            sources={n: d for n, d in sources.items() if Path(n).stat().st_mode & 0o004},
            libraries=qualified["libs"] | {"native": dict(path=str(fast), sha256=_sha(fast))},
            span=span,
            reference=ref,
            cpu=CPUS[ident],
            prior_receipts=retry_cadence_trial.PARENTS[ident],
        )
        path = work / f"{ident}.json"
        save_json(path, lock)
        path.chmod(0o644)
        files[path.name] = _sha(path)
        print(
            ident,
            "slots",
            offset + a,
            offset + b - 1,
            "valid",
            len(set(range(offset + a, offset + b)) & probes.keys()),
            flush=True,
        )
    plan = dict(
        cases=[DEVELOPMENT, HELD], slots=SPANS, cadence=CADENCE, devrates=DEVRATES, files=files
    )
    for p in (work / "source-lock.json", REPORT / "source-lock.json"):
        save_json(p, plan)
        p.chmod(0o644)


def configure(work, ident):
    source = work / "source-lock.json"
    plan = whole_iq.read(whole_iq.checked(source, _sha(REPORT / source.name)))
    name = f"{ident}.json"
    lock = whole_iq.read(whole_iq.checked(work / name, plan["files"][name]))
    for n, d in lock["sources"].items():
        whole_iq.checked(Path(n), d)
    whole_iq.checked(Path(lock["python"]), lock["python_sha256"])
    return (
        plan,
        lock,
        {k: whole_iq.checked(Path(v["path"]), v["sha256"]) for k, v in lock["libraries"].items()},
    )


def native_selected(fraction, ordinal):
    """Spread native comparator calls prospectively over nonanchor visits to each RF."""
    return int((ordinal + 1) * fraction) != int(ordinal * fraction)


def local_rows(window, antenna, sample, key, tracker, ranker, scores):
    prediction = tracker.forecast(key, sample)
    if prediction is None:
        return _probe(window, antenna, ()), dict(status="no_seed")
    start = process_time_ns()
    lane = window.samples[:, antenna]
    values = np.empty(len(lane), dtype=np.complex64)
    values.real, values.imag = lane[:, 0], lane[:, 1]
    epochs = ranker.rank(values, prediction)
    coarse_ns = process_time_ns() - start
    refinements = scores.refine_glrt64_epochs(
        values,
        seeded.RATE,
        integer_epoch_samples=epochs,
        acquired_cfo_hz=(prediction.cfo,) * len(epochs),
        edge=window.target["edge"],
    )
    candidates = []
    for i, (epoch, result) in enumerate(zip(epochs, refinements, strict=True)):
        mark = factor_candidate(
            i,
            epoch,
            status=result.status.value,
            offset=result.fractional_epoch_offset_samples,
            cfo=result.fractional_tracking_cfo_hz,
            exact=result.fractional_exact_score,
            control=result.fractional_control_score,
            margin=result.fractional_margin,
        )
        if mark is not None:
            candidates.append(mark)
    updated = tracker.observe(key, sample, prediction, candidates)
    return _probe(window, antenna, candidates), dict(
        status="searched",
        epoch=prediction.epoch,
        cfo=prediction.cfo,
        radius=prediction.radius,
        age=prediction.age,
        ranked_epochs=epochs,
        coarse_cpu_ns=coarse_ns,
        updated=updated,
    )


def timed(call, *args):
    wall, cpu = perf_counter_ns(), process_time_ns()
    result = call(*args)
    return result, dict(cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall)


def worker(work, ident):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.scanner.fast_scan_analysis import analyze_window
    from leo.storage import short_window

    _, lock, libs = configure(work, ident)
    start = base.resources.memory()
    if start["cpus"] != [lock["cpu"]]:
        raise ValueError("worker left its frozen CPU")
    tune = None
    if ident == HELD:
        tune = whole_iq.read(
            whole_iq.checked(work / "tune-lock.json", _sha(REPORT / "tune-lock.json"))
        )
    names = [str(rate) for rate in DEVRATES] if tune is None else ["seeded", "shifted"]
    trackers = {
        name: seeded.Tracker(int(name) if tune is None else tune["rate"], shifted=name == "shifted")
        for name in names
    }
    modes = (*trackers, "native")
    fraction = 1.0 if tune is None else tune["native_follow_fraction"]
    rate, edge = seeded.RATE, lock["capture"]["edge"]
    exact = qin_edge_pilot_frame(rate, edge)
    control = qin_edge_pilot_frame(rate, edge, symbol_roll=CONTROL_SYMBOL_ROLL)
    ranker = seeded.LocalSearch(exact)
    grid = PersistentGrid(libs["prepared"])
    fine = field.fine_for(lock, libs["fine"])
    policy = base.policy_for(lock)
    segment, first, stop, offset = lock["span"]
    initialized, follow = Counter(), Counter()
    outputs, verified = [], []
    member = short_window.ShortWindowReader._member

    def stream(reader, name, size, digest):
        if any(chunk.payload_relative_path == name for chunk in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return base.resources.AuthenticatedMember(path, size, digest, verified)
        return member(reader, name, size, digest)

    def empty(_window, antennas):
        return tuple(FastScanReceiverV1(receiver_id=r, candidates=()) for r in antennas)

    with ExitStack() as scope:
        scope.callback(grid.clear_cache)
        scope.enter_context(base.exact.refiners(libs))
        scope.enter_context(field.selector_waveform.selector(lock))
        scope.enter_context(grid.route(acquisition, base.exact.starts.screen_module()))
        scope.enter_context(fine.route())
        scope.enter_context(patch.object(short_window.ShortWindowReader, "_member", stream))
        native = scope.enter_context(
            NativeShortWindow(
                str(libs["native"]),
                np.asarray(exact, dtype="<c16"),
                np.asarray(control, dtype="<c16"),
                sample_rate_hz=rate,
                receiver_count=2,
                fractional_epoch=True,
            )
        )

        def native_rows(w):
            result = native.analyze(w.samples)
            return [
                _probe(
                    w,
                    row["receiver_id"],
                    map(lambda x: _from_native(*x), enumerate(row["candidates"])),
                )
                for row in result["rows"]
            ]

        def track(w, tracker, sample, lane):
            prior = [
                local_rows(w, r, sample, (r, *lane), tracker, ranker, fast_scan_scores)
                for r in (0, 1)
            ]
            return [p for p, _ in prior], [d for _, d in prior]

        source = base.open_span(lock, segment, first, stop)
        for i, w in enumerate(source.windows(), first):
            visit = offset + i
            a = w.acquisition
            clock = json.loads(a["retune_receipt"])["host_delivery_clock"]
            ref = lock["reference"][str(visit)]
            if a["global_visit"] != visit or clock != ref["clock"] or w.target["edge"] != edge:
                raise ValueError("signed IQ clock or edge differs from the frozen capture")
            status, valid_cost = timed(
                lambda w=w: analyze_window(w, (0, 1), None, policy, detector=empty)
            )
            if status.status not in ("processed", "invalid_capture"):
                raise ValueError("unsupported original validation status")
            row = dict(
                visit=visit,
                iq_sha256=w.iq_sha256,
                status=status.status,
                clock=clock,
                validation=valid_cost,
            )
            if status.status == "invalid_capture":
                if ref["exclusion"] is None or w.iq_sha256 != ref["exclusion"]["iq_sha256"]:
                    raise ValueError("invalid visit differs from the original archive")
                outputs.append(row)
                continue
            if ref["exclusion"] is not None:
                raise ValueError("raw validation admitted an archived excluded visit")
            sample = a["sample_start"]
            rf = float(a["actual_if_center_hz"] + w.target["lnb_lo_hz"])
            lane = (a["generation"], rf, edge)
            ordinal = initialized[lane]
            initialized[lane] += 1
            row.update(rf=rf, sample=sample, generation=a["generation"], ordinal=ordinal)
            if ordinal % CADENCE == 0:
                grid.calls.clear()
                (_, probes), clocks = timed(scan_capture_window, w, (0, 1), policy)
                if (
                    probes != ref["probes"]
                    or len(grid.calls) < 2
                    or not all(r["applied"] for r in grid.calls)
                ):
                    raise ValueError(f"real 12/22 anchor did not match the original at {visit}")
                updates = 0
                started = process_time_ns()
                for tracker in trackers.values():
                    for p in probes:
                        key = (p["receiver_id"], *lane)
                        tracker.anchor(key, sample, p["candidates"])
                        updates += key in tracker.lanes
                row["anchor"] = dict(
                    probes=probes,
                    clocks=clocks,
                    grids=len(grid.calls),
                    state_cpu_ns=process_time_ns() - started,
                    seeded=updates,
                )
                grid.calls.clear()
            else:
                step = follow[lane]
                follow[lane] += 1
                turn = (i - first) % len(modes)
                row["follow"] = {}
                for mode in modes[turn:] + modes[:turn]:
                    if mode == "native":
                        if native_selected(fraction, step):
                            probes, timing = timed(native_rows, w)
                            row["follow"][mode] = dict(probes=probes, clocks=timing)
                    else:
                        (probes, diagnostics), timing = timed(
                            track, w, trackers[mode], sample, lane
                        )
                        row["follow"][mode] = dict(probes=probes, clocks=timing, lanes=diagnostics)
            outputs.append(row)
            if (i - first) % 8 == 7:
                print(f"{ident} through {visit}", flush=True)
    if len(outputs) != SPANS or len(verified) != 2 or any(n < 6 for n in initialized.values()):
        raise ValueError("the wave did not authenticate both chunks and revisit each recorded RF")
    print(
        "seeded-acquisition: "
        + encoded(
            dict(
                case=ident,
                rows=outputs,
                source_lock_sha256=_sha(work / "source-lock.json"),
                tune_sha256=_sha(work / "tune-lock.json") if tune is not None else None,
                start=start,
                end=base.resources.memory(),
                compressed_bytes=verified,
            )
        ).decode(),
        flush=True,
    )


def run(work, ident):
    _, lock, _ = configure(work, ident)
    env = dict(PYTHONPATH=f"{lock['producer']}:{base.ROOT}", **base.recording.SINGLE_THREAD)
    unit = f"leo-seeded-{ident.lower()}-{uuid4().hex[:8]}"
    cmd = base.service(
        unit,
        360,
        [
            "taskset",
            "-c",
            str(lock["cpu"]),
            "sudo",
            "-n",
            "-u",
            "leo",
            "--",
            "env",
            *(f"{k}={v}" for k, v in env.items()),
            lock["python"],
            "-Bu",
            "-m",
            MODULE,
            "worker",
            str(work),
            ident,
        ],
    )
    save_json(work / f"{ident}-launch.json", cmd)
    with (work / f"{ident}.log").open("xb") as log:
        task = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=375, check=False)
    save_json(work / f"{ident}-exit.json", dict(exit_code=task.returncode, unit=unit))
    if task.returncode:
        raise RuntimeError(f"{ident} saved-IQ worker failed, see its service log")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("case", choices=(DEVELOPMENT, HELD), nargs="?")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.case is None:
        parser.error("a recording is required")
    else:
        (run if args.action == "run" else worker)(args.work, args.case)
