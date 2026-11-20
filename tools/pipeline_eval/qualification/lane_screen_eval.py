"""Lock and measure an independent native two-antenna activity screen."""

import argparse
import gzip
import os
import resource
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import iq_stream, lane_screen
from . import differential_pilot_eval, partner_local_eval
from . import lane_screen_build as build
from .full_v5_check import _from_native, _load_case, _sha
from .pilot_kernel_eval import _windows
from .wide_regional_eval import templates

REPORT = build.REPORT
SCHEDULE = {
    "calibration": (
        ("DS26-0197", "DS29-0316"),
        (2, 6, 10),
        40,
        9,
    ),
    "held": (
        ("DS26-0273", "DS29-0604"),
        (1, 4, 8, 11),
        48,
        8,
    ),
}
CONTROLS = ("zero", "noise", "strong", "weak", "one-frame", "partner-only")
ROLES = ("stock", "screen")
REPEATS = 3


def frozen_threshold(scores, min_positives=80):
    """Retain one-fifth of the measured gap as slack above the coarse floor."""
    enough = {v["edge"] for v in scores} == {"lower", "upper"} and len(scores) >= min_positives
    if not enough:
        return lane_screen.FLOOR
    minimum = min(r["coarse_max"] for r in scores)
    if minimum < lane_screen.FLOOR:
        raise ValueError("an authenticated stock positive failed the stock coarse floor")
    return lane_screen.FLOOR + 0.8 * (minimum - lane_screen.FLOOR)


def source_files():
    import leo.analysis.starlink.native_short_window as decoder
    import leo.analysis.starlink.templates as qin

    files = (
        Path(__file__),
        Path(build.__file__),
        Path(lane_screen.__file__),
        build.HEADER,
        Path(partner_local_eval.__file__),
        Path(differential_pilot_eval.__file__),
        Path(qin.__file__),
        Path(decoder.__file__),
        Path(iq_stream.__file__),
        Path(_windows.__code__.co_filename),
        REPORT / "PROTOCOL.md",
    )
    return {str(p.relative_to(ROOT)): _sha(p) for p in files}


def staged(work, cohort):
    directory = work / cohort
    directory.mkdir(exist_ok=False)
    iq_stream.MAX_CHUNK_PREFIX = 96 * iq_stream.MIB
    iq_stream.MAX_DECODE_BYTES = 160 * iq_stream.MIB
    cases, segments, count, pin = SCHEDULE[cohort]
    save_json(
        REPORT / f"{cohort}-schedule.json",
        dict(cases=cases, segments=segments, attempted_sequences=list(range(count)), cpu=pin),
    )
    scheduled = []
    for ident in cases:
        case = _load_case(ident)
        for segment in segments:
            try:
                rows = list(partner_local_eval.block(directory, ident, case, segment, count))
            except (OSError, iq_stream.IQReadError) as exc:
                rows = [
                    dict(sequence=seq, status="unavailable", reason=str(exc))
                    for seq in range(count)
                ]
            if {row["sequence"] for row in rows} != set(range(count)) or len(rows) != count:
                raise ValueError("raw input omitted a scheduled opportunity")
            scheduled.extend(
                dict(row, recording=ident, segment=segment, cohort=cohort)
                for row in sorted(rows, key=lambda r: r["sequence"])
            )
            print(cohort, ident, segment, len(scheduled), flush=True)
    if cohort == "held":
        for edge in ("lower", "upper"):
            for kind in CONTROLS:
                original = "strong" if kind == "partner-only" else kind
                samples, known = differential_pilot_eval.synthetic(edge, original)
                if kind == "partner-only":
                    samples[:, 0] = 0
                name = f"{edge}-{kind}"
                path = directory / f"{name}.ci16"
                write(path, samples.tobytes())
                scheduled.append(
                    dict(
                        name=name,
                        edge=edge,
                        kind=kind,
                        target=known,
                        status="valid",
                        cohort="control",
                        file=path.name,
                        iq_sha256=_sha(path),
                    )
                )
    bound = work / "build/build.json"
    compiled = whole_iq.read(bound)
    lock = dict(
        roster=scheduled,
        sources=source_files(),
        selection_sha256=_sha(REPORT / f"{cohort}-schedule.json"),
        build_sha256=_sha(bound),
        binaries={role: compiled[role] for role in ("stock", "candidate")},
    )
    save_json(REPORT / f"{cohort}-source-lock.json", lock)


def positive_count(row):
    candidates = [_from_native(i, c) for i, c in enumerate(row["candidates"], 1)]
    return sum(c["passed_fractional_margin_gate"] for c in candidates if c is not None)


def clean(rows):
    return [{k: v for k, v in row.items() if k != "timings_ms"} for row in rows]


def timed(stock, port, samples, threshold, role):
    wall, cpu = perf_counter_ns(), process_time_ns()
    if role == "stock":
        document = stock.analyze(samples, include_timings=True)
        scores = None
    else:
        document, scores = port.analyze(samples, threshold, trace=True)
    wall, cpu = perf_counter_ns() - wall, process_time_ns() - cpu
    return (
        clean(document["rows"]),
        dict(
            wall_ns=wall,
            cpu_ns=cpu,
            stages_ms=[r["timings_ms"] for r in document["rows"]],
            scores=scores,
        ),
    )


def check_lane_pair(stock, screen, scores, threshold):
    """Require exact surviving rows and factual per-lane rejects."""
    if [row["receiver_id"] for row in stock] != [0, 1]:
        raise ValueError("unexpected release lane order")
    outcome = []
    for idx, (a, b, s) in enumerate(zip(stock, screen, scores, strict=True)):
        if b["receiver_id"] != idx or s["rejected"] != (s["coarse_max"] < threshold):
            raise ValueError("independent activity decision or physical lane changed")
        if s["rejected"]:
            if b["candidates"] or b["candidate_count"] or b["fine_precision_calls"]:
                raise ValueError("screened lane ran refinement")
        elif a != b:
            raise ValueError("lane admitted by the screen changed scientific output")
        outcome.append(
            dict(
                receiver=idx,
                stock_positive=positive_count(a),
                screen_positive=positive_count(b),
                stock_slots=a["candidate_count"],
                screen_slots=b["candidate_count"],
                **s,
            )
        )
    return outcome


def measure(work, cohort):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    schedule = SCHEDULE[cohort]
    if os.sched_getaffinity(0) != {schedule[-1]}:
        raise ValueError(f"pin {cohort} on CPU{schedule[-1]}")
    lock = REPORT / f"{cohort}-source-lock.json"
    plan = whole_iq.read(lock)
    if plan["sources"] != source_files():
        raise ValueError("numerical sources changed after freeze")
    paths = {k: whole_iq.checked(Path(v["path"]), v["sha256"]) for k, v in plan["binaries"].items()}
    threshold = 0.0
    training_lock = None
    if cohort == "held":
        training_lock = REPORT / "threshold-lock.json"
        training = whole_iq.read(training_lock)
        whole_iq.checked(
            REPORT / "calibration-paired.json.gz", training["calibration_results_sha256"]
        )
        if training["build_sha256"] != plan["build_sha256"]:
            raise ValueError("training and held must use the identical native source build")
        threshold = training["threshold"]
    measurements = []
    for edge in ("lower", "upper"):
        with (
            NativeShortWindow(
                str(paths["stock"]),
                *templates(lane_screen.RATE, edge),
                sample_rate_hz=lane_screen.RATE,
                fractional_epoch=True,
            ) as stock,
            lane_screen.LaneScreen(paths["candidate"], edge) as port,
        ):
            warm = differential_pilot_eval.synthetic(edge, "strong")[0]
            for role in ROLES:
                timed(stock, port, warm, threshold, role)
            for index, entry in enumerate(plan["roster"]):
                if entry.get("edge") != edge or entry["status"] != "valid":
                    continue
                path = whole_iq.checked(work / cohort / entry["file"], entry["iq_sha256"])
                iq = np.fromfile(path, dtype="<i2").reshape(200000, 2, 2)
                repeats = REPEATS if cohort == "held" else 1
                rows, times = {}, {role: [] for role in ROLES}
                for repeat in range(repeats):
                    first, second = ROLES if (index + repeat) % 2 == 0 else ROLES[::-1]
                    for role in (first, second):
                        y, t = timed(stock, port, iq, threshold, role)
                        if role in rows and rows[role] != y:
                            raise ValueError("same detector generated different rows on repeat")
                        rows[role] = y
                        times[role].append(t)
                activity = times["screen"][0]["scores"]
                if any(t["scores"] != activity for t in times["screen"]):
                    raise ValueError("same detector generated different activity on repeat")
                measurements.append(
                    dict(
                        entry=entry,
                        rows=rows,
                        times=times,
                        lanes=check_lane_pair(rows["stock"], rows["screen"], activity, threshold),
                    )
                )
                if len(measurements) % 48 == 0:
                    print(cohort, len(measurements), flush=True)
    result = REPORT / f"{cohort}-paired.json.gz"
    write(
        result,
        gzip.compress(
            encoded(
                dict(
                    source_lock_sha256=_sha(lock),
                    threshold=threshold,
                    threshold_lock_sha256=_sha(training_lock) if training_lock else None,
                    scheduled=len(plan["roster"]),
                    measurements=measurements,
                    peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                )
            ),
            mtime=0,
        ),
    )
    if cohort == "calibration":
        scores = [
            dict(
                coarse_max=lane["coarse_max"],
                edge=m["entry"]["edge"],
                visit=m["entry"]["visit"],
                receiver=lane["receiver"],
                recording=m["entry"]["recording"],
            )
            for m in measurements
            for lane in m["lanes"]
            if lane["stock_positive"]
        ]
        save_json(
            REPORT / "threshold-lock.json",
            dict(
                threshold=frozen_threshold(scores),
                positive_scores=scores,
                calibration_results_sha256=_sha(result),
                calibration_inputs_sha256=_sha(lock),
                build_sha256=plan["build_sha256"],
            ),
        )
        print(
            "locked threshold", frozen_threshold(scores), "positive lanes", len(scores), flush=True
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("materialize", "measure"))
    parser.add_argument("cohort", choices=SCHEDULE)
    parser.add_argument("work", type=local_output)
    ns = parser.parse_args()
    (staged if ns.action == "materialize" else measure)(ns.work, ns.cohort)
