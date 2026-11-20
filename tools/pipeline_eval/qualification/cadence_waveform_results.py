"""Audit causal retry decisions and publish measured waveform timing."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import distribution
from ..variants.negative_rescue import positive
from . import cadence_waveform as trial
from . import scout_stage_figures as plot
from .full_v5_check import _sha
from .prefix_figures import csv_file

PREFIX = "cadence-waveform: "


def opportunity(ref):
    if ref["excluded"] is not None:
        if ref["primary"] is not None or ref["full"] is not None:
            raise ValueError("an excluded visit carries historical factors")
        return None
    primary, full = ref["primary"], ref["full"]
    if len(primary) != 2 or len(full) != 2:
        raise ValueError("the release requires both physical receiver rows")
    hits = list(map(positive, primary))
    if hits[0] == hits[1]:
        if primary != full:
            raise ValueError("nonretry factors differ before the online study")
        return None
    lane = hits.index(False)
    if primary[1 - lane] != full[1 - lane]:
        raise ValueError("the archive changed the successful peer")
    p = primary[lane]
    return (p["receiver_id"], p["actual_rf_hz"]), positive(full[lane])


def expected(lock):
    """Independently replay the timer rule from the frozen conditional gate ledger."""
    selected, events = {m: set() for m in trial.MODES}, {}
    for span, (_, first, stop, offset) in enumerate(lock["spans"]):
        next_allowed = {m: {} for m in trial.MODES[1:]}
        for v in range(offset + first, offset + stop):
            ref = lock["reference"][str(v)]
            event = opportunity(ref)
            if event is None:
                continue
            key, hit = event
            now = ref["delivery_clock"]["monotonic_ns"]
            events[v] = span, key, now, hit
            selected["full"].add(v)
            for mode, state in next_allowed.items():
                if now >= state.get(key, now):
                    selected[mode].add(v)
                    if hit == (mode == "hit"):
                        state[key] = now + 2_000_000_000
                    else:
                        state.pop(key, None)
    return selected, events


def validate(worker, plan_sha, lock, exits):
    ident = worker["id"]
    if (
        exits[ident]
        or worker["plan_sha256"] != plan_sha
        or len(worker["authenticated_compressed_bytes"]) != len(lock["spans"])
        or any(n <= 0 for n in worker["authenticated_compressed_bytes"])
        or worker["start"]["cgroup"] != worker["end"]["cgroup"]
    ):
        raise ValueError("raw worker does not bind the planned service and authenticated chunks")
    for edge in ("start", "end"):
        r = worker[edge]
        if (
            r["cpus"] != lock["cpus"]
            or r["memory.max"] != whole_iq.MEMORY
            or r["memory.swap.max"]
            or r["memory.swap.current"]
            or r["memory.events.oom_kill"]
        ):
            raise ValueError("raw worker does not satisfy resource caps")
    decisions, events = expected(lock)
    rows = {}
    for record in worker["records"]:
        v, rep, mode = (record[k] for k in ("visit", "round", "mode"))
        ref = lock["reference"][str(v)]
        retry = v in decisions[mode]
        if (v, rep, mode) in rows:
            raise ValueError("repeated measured mode/visit pair")
        rows[v, rep, mode] = record
        excluded = ref["excluded"]
        span, first, _, offset = next(
            (i, first, stop, base)
            for i, (_, first, stop, base) in enumerate(lock["spans"])
            if base + first <= v < base + stop
        )
        first_mode = (v - offset - first + rep) % len(trial.MODES)
        if (
            record["span"] != span
            or trial.MODES[(first_mode + record["order"]) % len(trial.MODES)] != mode
        ):
            raise ValueError("run order differs from the frozen round rotation")
        if (
            record["status"] != ("invalid_capture" if excluded else "processed")
            or record["probes"] != ([] if excluded else ref["full" if retry else "primary"])
            or (excluded and record["iq_sha256"] != excluded["iq_sha256"])
            or min(record["cpu_ns"], record["wall_ns"]) <= 0
        ):
            raise ValueError(f"wrong complete physical factors at {ident} visit {v} mode {mode}")
        attempts = record["attempts"]
        if len(attempts) != (v in events) or bool(record["wide_grids"]) != retry:
            raise ValueError("measured wide invocation does not match the expected policy")
        if attempts:
            attempt = attempts[0]
            _, key, _, hit = events[v]
            if (
                attempt["receiver"] != key[0]
                or attempt["executed"] != retry
                or attempt["hit"] != (hit if retry else None)
                or not 0 <= attempt["cpu_ns"] <= record["cpu_ns"]
                or bool(attempt["cpu_ns"]) != retry
            ):
                raise ValueError("actual attempted retry did not yield the expected gate and cost")
    if set(rows) != {
        (int(v), rep, mode)
        for v in lock["reference"]
        for rep in range(trial.ROUNDS)
        for mode in trial.MODES
    }:
        raise ValueError("saved-IQ timings are missing a policy, round or original visit")
    for v in map(int, lock["reference"]):
        if len({rows[v, r, m]["iq_sha256"] for r in range(trial.ROUNDS) for m in trial.MODES}) != 1:
            raise ValueError("the policy comparisons did not use identical IQ")
    return rows, decisions, events


def equally_spaced(selected, events):
    """Use each timer's retry count per span, receiver and RF."""
    lanes = defaultdict(list)
    for v, (span, key, _, _) in sorted(events.items()):
        lanes[span, key].append(v)
    result = set()
    for visits in lanes.values():
        n = sum(v in selected for v in visits)
        result.update(visits[(2 * i + 1) * len(visits) // (2 * n)] for i in range(n))
    return result


def control_cost(rows, selection, events, rep):
    """Compose control costs from visits measured on the matching detector path."""
    cpu = 0
    source = Counter()
    for v in sorted({row[0] for row in rows}):
        full = rows[v, rep, "full"]
        if v not in events or v in selection:
            cpu += full["cpu_ns"]
            source["observed_full_path"] += 1
            continue
        skips = [
            rows[v, rep, mode]["cpu_ns"]
            for mode in trial.MODES[1:]
            if not rows[v, rep, mode]["attempts"][0]["executed"]
        ]
        if skips:
            cpu += sum(skips) / len(skips)
            source["observed_skipped_path"] += 1
        else:
            cpu += full["cpu_ns"] - full["attempts"][0]["cpu_ns"]
            source["inferred_skipped_path"] += 1
    return dict(
        resident_cpu_s=cpu / 1e9,
        visits_by_cost_source=dict(source),
        retries=len(selection),
        rescues=sum(events[v][-1] for v in selection),
        measured_retry_cpu_s=sum(rows[v, rep, "full"]["attempts"][0]["cpu_ns"] for v in selection)
        / 1e9,
    )


def summary(lock, rows, decisions, events):
    result, samples = {}, []
    scheduled = len(lock["reference"])
    valid = sum(r["excluded"] is None for r in lock["reference"].values())
    for mode in trial.MODES:
        selected = decisions[mode]
        times = [r for (v, _, m), r in rows.items() if m == mode and r["status"] == "processed"]
        probes = [
            probe
            for (_, i, m), row in rows.items()
            if m == mode and i == 0
            for probe in row["probes"]
        ]
        candidates = [c for probe in probes for c in probe["candidates"]]
        rounds = []
        for rep in range(trial.ROUNDS):
            batch = [r for (_, i, m), r in rows.items() if m == mode and i == rep]
            rounds.append(
                dict(
                    round=rep,
                    resident_cpu_s=sum(r["cpu_ns"] for r in batch) / 1e9,
                    resident_wall_s=sum(r["wall_ns"] for r in batch) / 1e9,
                    retry_cpu_s=sum(a["cpu_ns"] for r in batch for a in r["attempts"]) / 1e9,
                    wide_grids=sum(r["wide_grids"] for r in batch),
                    primary_grids=sum(r["primary_grids"] for r in batch),
                    valid_calls_within_20ms=sum(
                        r["wall_ns"] <= 20_000_000 for r in batch if r["status"] == "processed"
                    ),
                )
            )
        result[mode] = dict(
            rounds=rounds,
            opportunities=len(events),
            retries=len(selected),
            rescues=sum(events[v][-1] for v in selected),
            physical_probes=len(probes),
            positive_probes=sum(map(positive, probes)),
            candidates=len(candidates),
            gate_passes=sum(c["passed_fractional_margin_gate"] for c in candidates),
            cpu_ms=distribution([r["cpu_ns"] / 1e6 for r in times]),
            wall_ms=distribution([r["wall_ns"] / 1e6 for r in times]),
        )
    for rep in range(trial.ROUNDS):
        full = result["full"]["rounds"][rep]
        for mode in trial.MODES:
            row = result[mode]["rounds"][rep]
            row["resident_cpu_saved_s"] = full["resident_cpu_s"] - row["resident_cpu_s"]
            row["retry_cpu_saved_s"] = full["retry_cpu_s"] - row["retry_cpu_s"]
            samples.append(
                dict(
                    id=lock["id"],
                    policy=mode,
                    scheduled=scheduled,
                    valid=valid,
                    opportunities=result[mode]["opportunities"],
                    retries=result[mode]["retries"],
                    rescues=result[mode]["rescues"],
                    **row,
                )
            )
    control = {
        mode: [
            control_cost(rows, equally_spaced(decisions[mode], events), events, rep)
            for rep in range(trial.ROUNDS)
        ]
        for mode in trial.MODES[1:]
    }
    return dict(
        scheduled=scheduled,
        valid=valid,
        policy=result,
        equal_paced_composed_cost=control,
        spans=[
            dict(
                first=offset + a,
                last=offset + b - 1,
                valid=sum(
                    lock["reference"][str(v)]["excluded"] is None
                    for v in range(offset + a, offset + b)
                ),
                delivery_span_s=(
                    lock["reference"][str(offset + b - 1)]["delivery_clock"]["monotonic_ns"]
                    - lock["reference"][str(offset + a)]["delivery_clock"]["monotonic_ns"]
                )
                / 1e9,
            )
            for _, a, b, offset in lock["spans"]
        ],
    ), samples


def render(out, cases):
    complete = len(cases) == len(trial.CASES)
    counts = "Four 64-visit spans" if complete else "Two validated DS29-0082 64-visit spans"
    fig, axes = plot.canvas(
        "Chronological saved-IQ peer retry timing",
        counts + " · two interleaved rounds · empty timers at each span start",
        "Detector CPU includes the retry CPU shown separately.",
    )
    labels = ["Full conditional", "Wait after miss", "Wait after hit"]
    if complete:
        for ax, (ident, case) in zip(axes, cases.items(), strict=True):
            values = [
                tuple(
                    sum(r[key] for r in case["policy"][mode]["rounds"]) / trial.ROUNDS
                    for key in ("resident_cpu_s", "retry_cpu_s")
                )
                for mode in trial.MODES
            ]
            plot.paired(ax, labels, values, title=ident, xlabel="Host CPU seconds", fmt=".2f")
        plot.key(fig, "Resident detector", "Retry calls")
    else:
        (case,) = cases.values()
        for ax, key, title in zip(
            axes,
            ("resident_cpu_s", "retry_cpu_s"),
            ("Resident detector", "Retry calls"),
            strict=True,
        ):
            values = [tuple(r[key] for r in case["policy"][m]["rounds"]) for m in trial.MODES]
            plot.paired(ax, labels, values, title=title, xlabel="Host CPU seconds", fmt=".2f")
        plot.key(fig, "Round 1", "Round 2")
    fig.savefig(out / "timing.png", dpi=165, facecolor="white")
    fig.savefig(out / "timing.pdf", facecolor="white", metadata={"CreationDate": None})
    plot.plt.close(fig)


def recovery_inputs(work, fallback):
    ident = trial.CASES[0]
    original, initial_lock, _ = trial.configure(work, ident)
    plan = whole_iq.read(fallback / "plan.json")
    path = f"{ident}.json"
    lock = whole_iq.read(whole_iq.checked(fallback / path, plan["files"][path]))
    common = ("rounds", "modes", "interval_ns", "initial_state")
    if (
        plan["recovery_of_plan_sha256"] != _sha(work / "plan.json")
        or plan["cases"] != [ident]
        or plan["cpus"] != [13]
        or plan["cpus"] != lock["cpus"]
        or any(plan[k] != original[k] for k in common)
        or dict(lock, cpus=initial_lock["cpus"]) != initial_lock
    ):
        raise ValueError("recovery did not preserve the preselected spans and exact raw recipe")
    return lock


def publish(work, out):
    plan_sha = _sha(work / "plan.json")
    exits = whole_iq.read(work / "exits.json")
    cases, stats, incomplete = {}, [], {}
    assets = [
        "PROTOCOL.md",
        "plan.json",
        "audit.json",
        "stage.csv",
        "receipts/exits.json",
        "receipts/launch.json",
        "timing.png",
        "timing.pdf",
    ]
    for name in ("exits.json", "launch.json"):
        write(out / "receipts" / name, (work / name).read_bytes())
    fallback = work.with_name(work.name + "-lower-cpu13")
    recovery = None
    lower_id = trial.CASES[0]
    if fallback.exists():
        lower_lock = recovery_inputs(work, fallback)
        alternate_exits = whole_iq.read(fallback / "exits.json")
        replacement = bool(exits[lower_id])
        if replacement and not alternate_exits[lower_id]:
            recovery = (lower_lock, _sha(fallback / "plan.json"), alternate_exits)
        for source in sorted(fallback.iterdir()):
            if source.suffix in (".log", ".json"):
                name = f"receipts/recovery/{source.name}.gz"
                write(out / name, gzip.compress(source.read_bytes(), compresslevel=5, mtime=0))
                assets.append(name)
    for ident in trial.CASES:
        _, lock, _ = trial.configure(work, ident)
        for source in (work / f"{ident}.log", work / f"{ident}.json"):
            name = f"receipts/{source.name}.gz"
            write(out / name, gzip.compress(source.read_bytes(), compresslevel=5, mtime=0))
            assets.append(name)
        selected_work, selected_sha, selected_exits = work, plan_sha, exits
        if ident == lower_id and recovery:
            lock, selected_sha, selected_exits = recovery
            selected_work = fallback
        log = selected_work / f"{ident}.log"
        if selected_exits[ident]:
            attempts = [work] + ([fallback] if ident == lower_id and fallback.exists() else [])
            incomplete[ident] = dict(
                planned_visits=len(lock["reference"]),
                planned_valid_visits=sum(r["excluded"] is None for r in lock["reference"].values()),
                planned_interleaved_calls=len(lock["reference"]) * len(trial.MODES) * trial.ROUNDS,
                attempts=[
                    dict(
                        exit_code=whole_iq.read(root / "exits.json")[ident],
                        timeout="timeout" in (root / f"{ident}.log").read_text().lower(),
                        last_checkpoint=next(
                            (
                                line
                                for line in reversed(
                                    (root / f"{ident}.log").read_text().splitlines()
                                )
                                if line.startswith(ident + " span")
                            ),
                            None,
                        ),
                    )
                    for root in attempts
                ],
            )
            continue
        (record,) = [
            json.loads(line.removeprefix(PREFIX))
            for line in log.read_text().splitlines()
            if line.startswith(PREFIX)
        ]
        try:
            rows, decisions, events = validate(record, selected_sha, lock, selected_exits)
        except ValueError as reason:
            incomplete[ident] = dict(
                planned_visits=len(lock["reference"]),
                planned_interleaved_calls=len(lock["reference"]) * len(trial.MODES) * trial.ROUNDS,
                validation_error=str(reason),
            )
            continue
        result, samples = summary(lock, rows, decisions, events)
        stats.extend(samples)
        cases[ident] = dict(
            **result,
            resources={k: v for k, v in record.items() if k not in ("records",)},
            identical_valid_projections=result["valid"] * len(trial.MODES) * trial.ROUNDS,
            timing_source="CPU13 recovery" if selected_work == fallback else "original launch",
        )
    if not cases:
        raise RuntimeError("no waveform service returned a completed authenticated packet receipt")
    csv_file(out / "stage.csv", stats)
    save_json(
        out / "audit.json",
        dict(cases=cases, incomplete=incomplete, publisher_sha256=_sha(Path(__file__))),
    )
    render(out, cases)
    save_json(out / "stage-lock.json", dict(files={name: _sha(out / name) for name in assets}))
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="cadence-waveform-timing",
            title="Chronological original GLRT retry cadence",
            sample=(
                "Two 64-visit spans from each of DS26-0237 and DS29-0082, each in two rounds"
                if not incomplete
                else "Two authenticated DS29-0082 64-visit spans in two rounds"
            ),
            boundary="Resident CI16 to complete physical projections through the original producer",
            note="Full, wait-after-miss and wait-after-hit policies ran on the same host CPU per "
            "recording. The compressed receipts retain all emitted candidate factors.",
            seal="stage-lock.json",
            image="timing.png",
            pdf="timing.pdf",
            csv="stage.csv",
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output, nargs="?", default=trial.WORK)
    args = parser.parse_args()
    publish(args.work, trial.REPORT)
