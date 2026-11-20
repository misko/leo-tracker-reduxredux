"""Reconstruct finite FCFS detector queues from authenticated host-delivery clocks."""

import argparse
import gzip
import heapq
import json
from collections import Counter, deque
from pathlib import Path

from ..__main__ import encoded, local_output, read_predictions, save_json, write
from ..scoring import distribution
from . import arrival_pace, iq_schedule, whole_cavity, whole_pair
from .full_receiver_comparison import read, require_fields, seal, sha
from .full_v5_check import _load_case
from .prefix_figures import csv_file
from .recording_to_v5 import capture_release

REPORT = whole_pair.REPORT.with_name("arrival-clock")
RUNS = whole_pair.RUNS.with_name("arrival-clock")
ORDINARY = {"DS26-0036": whole_cavity.RUNS, "DS29-0082": whole_pair.RUNS}
NS = 1_000_000_000
DELIVERY_SOURCE = "07a6a522dfabbb3df9080aac9c7ebbbf3a8c172aa1da7a1780f3c6ff140e55cc"
CAPACITIES = (0, 1, 2, 3, 4, 8, 16, 32, 64)
TRACE = "delivery-events.json.gz"


def gzip_json(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def source_trial(folder, name, lock):
    receipt = seal(folder, lock, (name, "positions.jsonl.gz"))
    require_fields(receipt, dict(source_lock_sha256=sha(folder / "source-lock.json")))
    return gzip_json(folder / name), read(folder / "source-lock.json"), receipt


def route_lanes(directory, raw, recording, native, *, scheduled=False):
    clocks = native["delivery_clocks"]
    excluded = {row["visit"]: row for row in native["provenance"]["excluded_windows"]}
    segments = recording["segments"]
    source_rows, timed, seen_skipped = {}, {}, set()
    for lane, stats in enumerate(raw["raw_lanes"]):
        active, seen_segments = [], []
        skipped = set(stats.get("skipped_valid_visits", ()))
        log = directory / f"replayed-{lane}.jsonl"
        lane_count, previous_visit = 0, -1
        with log.open() as stream:
            for row in map(json.loads, stream):
                if row["kind"] == "segment":
                    ident = row["segment"]
                    if (
                        ident % 2 != lane
                        or row["count"] != lane_count
                        or row["manifest_digest"] != "sha256:" + segments[ident]["sha256"]
                    ):
                        raise ValueError("lane segment differs from the capture input authority")
                    seen_segments.append(ident)
                    lane_count = 0
                if row["kind"] != "visit":
                    continue
                lane_count += 1
                i = row["visit"]
                if (
                    i in source_rows
                    or not previous_visit < i < len(clocks)
                    or row["segment"] != lane + 2 * len(seen_segments)
                    or row["sequence"] != lane_count - 1
                ):
                    raise ValueError("duplicate or misrouted saved-IQ visit")
                previous_visit = i
                if row["delivery_clock"] != clocks[i]:
                    raise ValueError("lane and ordinary-factor clocks differ")
                if i in excluded:
                    require_fields(
                        row,
                        dict(
                            status="invalid_capture", probes=[], iq_sha256=excluded[i]["iq_sha256"]
                        ),
                    )
                    status = "invalid_capture"
                elif row["status"] == "processed" and len(row["probes"]) == 2:
                    status = "schedule_skipped" if i in skipped else "detector"
                    if status == "detector":
                        active.append(i)
                    else:
                        seen_skipped.add(i)
                else:
                    raise ValueError("unrecognized raw envelope")
                source_rows[i] = status
        if seen_segments != list(range(lane, len(segments), 2)) or lane_count:
            raise ValueError("the lane lacks its full immutable segment inventory")
        if scheduled and (
            len(active) + len(skipped) != stats["original_valid_visit_count"]
            or not skipped <= seen_skipped
        ):
            raise ValueError("recorded scheduled calls do not match the physical visit inventory")
        for visit, (wall, cpu) in zip(active, stats["native_timings_s"], strict=True):
            if not 0 < cpu <= 1 or not 0 < wall <= 1:
                raise ValueError("invalid measured detector duration")
            timed[visit] = round(cpu * NS), round(wall * NS)
    if len(clocks) != recording["window_count"] or set(source_rows) != set(range(len(clocks))):
        raise ValueError("missing physical arrival slot")
    if (
        len(excluded) != raw["raw_counts"]["invalid_capture"]
        or len(timed) + len(seen_skipped) != (raw["raw_counts"]["processed_windows"])
    ):
        raise ValueError("detector durations do not account for every originally valid visit")
    if scheduled and len(timed) != raw["schedule_coverage"]["retained_visits"]:
        raise ValueError("timed calls differ from the fresh pre-detector schedule")
    first = clocks[0]["monotonic_ns"]
    return [
        [i, c["monotonic_ns"] - first, source_rows[i], *timed.get(i, (0, 0))]
        for i, c in enumerate(clocks)
    ]


def stages_for(ident, directory, measured, recording, native_sha, *, scheduled=False):
    raw, position = measured["raw"], measured["position"]
    native_file = directory / "native.json"
    if sha(native_file) != native_sha or raw["native_sha256"] != native_sha:
        raise ValueError(f"{ident} factor archive differs from the recorded measurement")
    native = read(native_file)
    record = dict(id=ident, policy="recorded_schedule" if scheduled else "every_valid_visit")
    rows = route_lanes(directory, raw, recording, native, scheduled=scheduled)
    require_fields(raw, dict(id=ident))
    return dict(
        record,
        native_sha256=native_sha,
        acquisition_clock_origin_ns=native["delivery_clocks"][0]["monotonic_ns"],
        handoff_s=position["start"]["monotonic_s"] - raw["raw_complete"]["monotonic_s"],
        cavity_s=position["end"]["monotonic_s"] - position["start"]["monotonic_s"],
        complete_position="end" in position,
        events=rows,
        raw_replay_sha256={f"lane{i}": sha(directory / f"replayed-{i}.jsonl") for i in range(2)},
    )


def extract(report, *, include_schedule=False):
    ordinary, source, receipt = source_trial(
        whole_pair.REPORT, "stages.json.gz", "prediction-lock.json"
    )
    positions = read_predictions(whole_pair.REPORT / "positions.jsonl.gz")
    if (
        set(positions) != set(ordinary)
        or set(ordinary) != set(ORDINARY)
        or receipt["cases"] != list(ORDINARY)
    ):
        raise ValueError("the whole-IQ measured roster changed")
    cases = []
    for ident, root in ORDINARY.items():
        item = source["inputs"][ident]
        require_fields(positions[ident], dict(native_sha256=item["native_sha256"]))
        require_fields(positions[ident]["result"], dict(status="ok"))
        directory = root / ident
        config = read(directory / "capture.json")
        runtime = capture_release.producer(_load_case(ident), config).root
        ppu = runtime / "leo/acquisition/continuous_window_ppu.py"
        if sha(ppu) != DELIVERY_SOURCE:
            raise ValueError("recorded delivery clock producer does not match the audited source")
        cases.append(
            stages_for(ident, directory, ordinary[ident], item["recording"], item["native_sha256"])
        )
    provenance = {"whole_pair_prediction_sha256": sha(whole_pair.REPORT / "prediction-lock.json")}
    if include_schedule:
        append_schedule(cases, source, provenance)
    pace = RUNS / "paced.json"
    if pace.is_file() and pace.stat().st_size:
        pace_result = read(pace)
        archive = seal(
            whole_pair.REPORT, "archive-authority-lock.json", ("archive-authority.json.gz",)
        )
        archive_doc = gzip_json(whole_pair.REPORT / "archive-authority.json.gz")
        require_fields(
            pace_result,
            dict(
                id=arrival_pace.CASE,
                native_sha256=source["inputs"][arrival_pace.CASE]["native_sha256"],
                library_sha256=archive_doc["native_detector_sha256"],
                manifest_sha256=source["inputs"][arrival_pace.CASE]["recording"]["segments"][0][
                    "sha256"
                ],
            ),
        )
        save_json(report / "paced.json", pace_result)
        provenance["paced_file_sha256"] = sha(report / "paced.json")
        provenance["paced_source_sha256"] = sha(Path(arrival_pace.__file__))
        provenance["native_iq_authority_sha256"] = archive["files"]["archive-authority.json.gz"]
    path = report / TRACE
    write(path, gzip.compress(encoded(cases), mtime=0))
    save_json(
        report / "source-lock.json",
        dict(
            **provenance,
            cases=[(r["id"], r["policy"]) for r in cases],
            producer_source_sha256=DELIVERY_SOURCE,
            event_file_sha256=sha(path),
            event_columns=[
                "visit",
                "arrival_offset_ns",
                "status",
                "native_cpu_ns",
                "native_wall_ns",
            ],
        ),
    )


def append_schedule(cases, source, provenance):
    traces, plan, receipt = source_trial(
        iq_schedule.REPORT, "stages.json.gz", "prediction-lock.json"
    )
    predictions = read_predictions(iq_schedule.REPORT / "positions.jsonl.gz")
    if set(traces) != set(receipt["cases"]) or set(traces) != set(predictions):
        raise ValueError("scheduled replay has a mismatched sealed roster")
    provenance["schedule_prediction_sha256"] = sha(iq_schedule.REPORT / "prediction-lock.json")
    default = {row["id"]: row for row in cases}
    for ident in ORDINARY:
        if ident not in traces:
            continue
        trace, position = traces[ident], predictions[ident]
        if trace["raw"] is None or trace["position"] is None:
            continue
        reference_sha = default[ident]["native_sha256"]
        require_fields(plan["inputs"][ident], dict(native_sha256=reference_sha))
        require_fields(trace["raw"], dict(full_native_sha256=reference_sha))
        require_fields(position, dict(origin_native_sha256=reference_sha))
        measured = stages_for(
            ident,
            iq_schedule.RUNS / ident,
            trace,
            source["inputs"][ident]["recording"],
            position["native_sha256"],
            scheduled=True,
        )
        for full, scheduled in zip(default[ident]["events"], measured["events"], strict=True):
            if full[:2] != scheduled[:2] or (full[2] == "invalid_capture") != (
                scheduled[2] == "invalid_capture"
            ):
                raise ValueError("schedule changed the physical delivery or exclusion authority")
        measured["complete_position"] = position["result"]["status"] == "ok"
        cases.append(measured)


def simulate(events, workers, capacity=None, *, wall=False):
    """Arrival ties retain physical visit order. A completion frees a slot before an arrival."""
    if workers not in (1, 2) or capacity is not None and capacity < 0:
        raise ValueError("use one or two workers and a nonnegative waiting capacity")
    if not events:
        raise ValueError("missing delivery events")
    free, waiting = [(0, k) for k in range(workers)], deque()
    counts, completed, waiting_trace = Counter(), [], []
    previous, maximum = -1, 0
    for expected, (visit, arrival, status, cpu_ns, wall_ns) in enumerate(events):
        if (
            visit != expected
            or arrival < previous
            or status not in ("detector", "invalid_capture", "schedule_skipped")
        ):
            raise ValueError("malformed physical arrival sequence")
        previous = arrival
        while waiting and waiting[0] <= arrival:
            waiting.popleft()
        counts[status] += 1
        if status != "detector":
            if cpu_ns != 0 or wall_ns != 0:
                raise ValueError("an excluded visit cannot claim detector service")
            waiting_trace.append(len(waiting))
            continue
        if min(cpu_ns, wall_ns) <= 0:
            raise ValueError("a detector call requires measured service")
        idle, worker = free[0]
        if idle > arrival and capacity is not None and len(waiting) >= capacity:
            counts["dropped"] += 1
        else:
            start = max(idle, arrival)
            finish = start + (wall_ns if wall else cpu_ns)
            heapq.heapreplace(free, (finish, worker))
            if start > arrival:
                waiting.append(start)
            completed.append((visit, arrival, start, finish))
        maximum = max(maximum, len(waiting))
        waiting_trace.append(len(waiting))
    drain = max(0, max(value for value, _ in free) - previous)
    return dict(
        counts=dict(counts),
        completed=completed,
        max_waiting=maximum,
        drain_ns=drain,
        waiting_trace=waiting_trace,
    )


def quantiles(samples):
    d = distribution(samples)
    return {p: d[p] for p in ("p50", "p95", "p99", "max")}


def queue_rows(record):
    visits = record["events"]
    span = visits[-1][1] / NS
    service_cpu = sum(row[3] for row in visits) / NS
    time_after = record["handoff_s"] + record["cavity_s"]
    for wall in (False, True):
        for workers in (1, 2):
            sufficient = simulate(visits, workers, wall=wall)["max_waiting"]
            for capacity in (*sorted(set(CAPACITIES) | {sufficient}), None):
                result = simulate(visits, workers, capacity, wall=wall)
                counts = result["counts"]
                dropped = counts.get("dropped", 0)
                completed = result["completed"]
                delay, latency = (
                    quantiles((row[index] - row[1]) / 1e6 for row in completed) for index in (2, 3)
                )
                drain_s = result["drain_ns"] / NS
                compared = [(i, end) for i, _a, _s, end in completed if i + 1 < len(visits)]
                through_next = sum(end <= visits[i + 1][1] for i, end in compared)
                yield dict(
                    id=record["id"],
                    policy=record["policy"],
                    workers=workers,
                    duration="measured_native_wall" if wall else "measured_native_cpu",
                    waiting_slots=capacity if capacity is not None else "unbounded",
                    physical_slots=len(visits),
                    offered_detector_calls=counts["detector"],
                    invalid_capture=counts.get("invalid_capture", 0),
                    schedule_skipped=counts.get("schedule_skipped", 0),
                    completed=len(completed),
                    dropped=dropped,
                    max_waiting=result["max_waiting"],
                    minimum_lossless_waiting=sufficient,
                    span_s=span,
                    native_cpu_total_s=service_cpu,
                    demand_over_span_pct=service_cpu / span * 100,
                    drain_s=drain_s,
                    with_next_physical_delivery=len(compared),
                    completed_by_next_physical_delivery=through_next,
                    native_calls_at_most_20ms=sum(
                        0 < visit[4 if wall else 3] <= 20_000_000 for visit in visits
                    ),
                    **{f"waiting_{p}_ms": value for p, value in delay.items()},
                    **{f"latency_{p}_ms": value for p, value in latency.items()},
                    recorded_handoff_s=record["handoff_s"],
                    recorded_cavity_s=record["cavity_s"],
                    earliest_complete_position_after_last_delivery_s=(
                        drain_s + time_after
                        if not dropped and record["complete_position"]
                        else None
                    ),
                )


def score(report, output):
    lock = read(report / "source-lock.json")
    path = report / TRACE
    require_fields(lock, dict(event_file_sha256=sha(path)))
    cases = gzip_json(path)
    if [[r["id"], r["policy"]] for r in cases] != lock["cases"]:
        raise ValueError("event evidence roster changed")
    all_rows = [row for record in cases for row in queue_rows(record)]
    csv_file(output / "queue.csv", all_rows)
    save_json(
        output / "summary.json",
        [
            row
            for row in all_rows
            if row["waiting_slots"] in (0, row["minimum_lossless_waiting"])
            and row["waiting_slots"] != "unbounded"
        ],
    )
    if "paced_file_sha256" in lock:
        pace_path = report / "paced.json"
        require_fields(lock, dict(paced_file_sha256=sha(pace_path)))
        first = next(r for r in cases if r["id"] == arrival_pace.CASE)
        pace_rows, phase = score_pace(read(pace_path), first)
        csv_file(output / "paced-visits.csv", pace_rows)
        save_json(output / "paced-summary.json", phase)
    plots(cases, all_rows, output)


def score_pace(pace, record):
    n = len(pace["requested_offsets_ns"])
    prefix = record["events"][:n]
    if n != arrival_pace.PREFIX or len(pace["observations"]) != n:
        raise ValueError("wall-clock replay did not traverse the declared prefix")
    require_fields(
        pace,
        dict(
            id=record["id"],
            native_sha256=record["native_sha256"],
            requested_offsets_ns=[row[1] for row in prefix],
            predecoded=True,
            cpu=arrival_pace.CPU,
        ),
    )
    rows, finished = [], -1
    starts = [row["started_ns"] for row in pace["observations"]]
    for entry, (visit, wanted, status, _, _) in zip(pace["observations"], prefix, strict=True):
        release, start, end = (entry[k] for k in ("released_ns", "started_ns", "finished_ns"))
        require_fields(
            entry, dict(visit=visit, status="processed" if status == "detector" else status)
        )
        if not wanted <= release <= start <= end or start < finished:
            raise ValueError("paced worker violated causal release or single-worker order")
        finished = end
        rows.append(
            dict(
                visit=visit,
                released_ns=release,
                started_ns=start,
                finished_ns=end,
                requested_ns=wanted,
                status=status,
                worker_cpu_ms=entry["worker_cpu_ns"] / 1e6,
                release_lateness_ms=(release - wanted) / 1e6,
                worker_wait_ms=(start - release) / 1e6,
                latency_ms=(end - release) / 1e6,
                from_original_deadline_ms=(end - wanted) / 1e6,
                waiting_after_release=sum(t > release for t in starts[: visit + 1]),
            )
        )
    waiting = max(row["waiting_after_release"] for row in rows)
    if waiting >= pace["waiting_slots"]:
        raise ValueError("pace producer may have blocked on its finite queue")
    model = simulate(prefix, 1)
    actual = {
        key: quantiles(r[key] for r in rows)
        for key in (
            "release_lateness_ms",
            "worker_wait_ms",
            "latency_ms",
            "from_original_deadline_ms",
            "worker_cpu_ms",
        )
    }
    return rows, dict(
        physical_slots=n,
        cpu=pace["cpu"],
        nice=pace["nice"],
        all_factor_rows_exact=True,
        predecoded=pace["predecoded"],
        input_span_s=prefix[-1][1] / NS,
        actual_drained_after_final_release_s=(finished - rows[-1]["released_ns"]) / NS,
        max_waiting=waiting,
        model_cpu_latency_ms=quantiles((end - a) / 1e6 for _i, a, _s, end in model["completed"]),
        model_cpu_max_waiting=model["max_waiting"],
        observed=actual,
    )


def plots(cases, rows, out):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        2, len(ORDINARY), figsize=(12.5, 7), sharey="row", layout="constrained"
    )
    modes = (("measured_native_cpu", "Native CPU"), ("measured_native_wall", "Native wall"))
    for (mode, title), panels in zip(modes, axes, strict=True):
        for ident, ax in zip(ORDINARY, panels, strict=True):
            for record in cases:
                if ident != record["id"]:
                    continue
                for workers, color in ((1, "#176177"), (2, "#c07536")):
                    group = [
                        row
                        for row in rows
                        if row["id"] == ident
                        and row["workers"] == workers
                        and row["policy"] == record["policy"]
                        and row["duration"] == mode
                        and row["waiting_slots"] != "unbounded"
                    ]
                    maximum = max(4, max(row["minimum_lossless_waiting"] for row in group))
                    group = [row for row in group if row["waiting_slots"] <= maximum]
                    style = "-" if record["policy"] == "every_valid_visit" else "--"
                    label = f"{workers} worker{'s' if workers > 1 else ''} · " + (
                        "all valid" if style == "-" else "recorded schedule"
                    )
                    ax.plot(
                        [r["waiting_slots"] for r in group],
                        [r["dropped"] for r in group],
                        style,
                        marker="o",
                        color=color,
                        label=label,
                    )
            ax.set(title=f"{ident} · {title}", xlabel="Waiting slots across workers")
            ax.grid(alpha=0.22)
            ax.legend(frameon=False)
        panels[0].set_ylabel("Dropped detector calls")
    fig.suptitle("Finite detector queues using recorded host delivery times")
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "queue.png", dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("extract", "score"))
    parser.add_argument("--report", type=local_output, default=REPORT)
    parser.add_argument("--out", type=local_output)
    parser.add_argument("--include-schedule", action="store_true")
    args = parser.parse_args()
    if args.action == "extract":
        extract(args.report, include_schedule=args.include_schedule)
    else:
        score(args.report, args.out or args.report)


if __name__ == "__main__":
    main()
