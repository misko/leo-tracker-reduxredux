"""Audit rotating dwell packets, report observed Graph support and score matched fits."""

import argparse
import gzip
from collections import Counter

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, validate_result
from ..variants import capture_bursts, frequency_schedule
from . import frequency_schedule_results as earlier
from . import rotating_dwell_trial as trial
from . import screening_figures
from .fresh_replay_results import sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .staggered_reconstruction_results import original_rows
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
STOCK, MODES = "full", ("full", "lanes2", "rotate2", "lanes4", "rotate4")
read = whole_iq.read


def collect(work, plan, rows, scheduled, events):
    expected = {(r["id"], r["condition"]): r for r in plan["tasks"]}
    actual = {(r["id"], r["condition"]): r for r in rows}
    if len(actual) != len(rows) or actual.keys() != expected.keys():
        raise ValueError("the terminal receipts omitted a frozen input")
    resources, support = [], []
    for ident in plan["cases"]:
        source = trial.parent.incoming(ident)
        case, request, _, base, metadata, clocks = source
        rotation = trial.device_schedule(source)
        modes = {k: v[0] for k, v in rotation.items()}
        if ident in plan["prospective2"]:
            fixed = frequency_schedule.schedules(ident, metadata, clocks)
            modes.update({m: fixed[m] for m in ("full", "lanes2", "lanes4")})
        if modes != scheduled[ident] or encoded({k: v[1] for k, v in rotation.items()}) != encoded(
            events[ident]
        ):
            raise ValueError("rotation inputs did not reproduce from physical hardware counters")
        origin = base["clock_anchor"]["sample_counter"]
        rate = base["source"]["sample_rate_hz"]
        samples = {p["visit_index"]: p["valid_start_counter"] for p in base["source"]["probes"]}
        availability = Counter(((samples[i] - origin) // (15 * rate), ch) for i, ch in metadata)
        for mode, times in modes.items():
            r = actual[ident, mode]
            if any(r[k] != v for k, v in expected[ident, mode].items()):
                raise ValueError("measured result differs from its frozen request")
            validate_result(r["result"])
            leaf = work / ident / mode
            native = whole_iq.checked(leaf / "recording/native.json", r["native_sha256"])
            request_file = whole_iq.checked(
                leaf / "recording/request.json", r["prepared_request_sha256"]
            )
            setup = trial.parent.capture_bursts_trial
            setup.verify_request(
                read(request_file), request, native_path=native, native_sha256=r["native_sha256"]
            )
            if mode == "full":
                if r["native_sha256"] != case["native"]["sha256"]:
                    raise ValueError("full comparator changed original native bytes")
            else:
                lineage = whole_iq.recording.digest(
                    [setup.SALT, mode, case["native"]["sha256"], times]
                )
                exact = capture_bursts.select_document(base, times, lineage)
                if native.read_bytes() != encoded(exact) + b"\n":
                    raise ValueError("one of the selected RF packet bodies changed")
            measured = r.get("position_resources") or {}
            graph = r.get("graph") or {}
            if r["terminal"] != "not-launched":
                attempt = {k: v for k, v in r.items() if k != "graph"}
                if read(leaf / "attempt.json") != attempt:
                    raise ValueError("solver terminal row differs from its actual receipt")
                if graph and read(leaf / "geometry.json") != graph:
                    raise ValueError("graph evidence differs from actual installed solve")
                if r["terminal"] == "success" and (
                    not measured or not graph or graph["winning"] != r["positive_probes"]
                ):
                    raise ValueError("successful observed fit lacks its Graph or numerical receipt")
                message = whole_iq.checked(leaf / "service.log", r["log_sha256"])
                write(
                    REPORT / "logs" / f"{ident}-{mode}.log.gz",
                    gzip.compress(message.read_bytes(), mtime=0),
                )
            for edge in ("start", "end"):
                if measured and (
                    measured[edge]["cpus"] != [r["cpu"]]
                    or measured[edge]["memory.max"] != plan["memory_bytes"]
                    or measured[edge]["memory.swap.max"]
                    or measured[edge]["memory.swap.current"]
                ):
                    raise ValueError("Graph-observed numerical worker used a different cgroup")
            resources.append(
                dict(
                    id=ident,
                    mode=mode,
                    cohort=r["cohort"],
                    terminal=r["terminal"],
                    status=r["result"]["status"],
                    pinned_cpu=r["cpu"],
                    position_wall_s=measured.get("wall_s"),
                    position_cpu_s=measured.get("cpu_s"),
                    peak_bytes=measured.get("peak_bytes"),
                    swap_bytes=measured.get("end", {}).get("memory.swap.current"),
                )
            )
            chosen = set(times)
            count = Counter(
                ((samples[i] - origin) // (15 * rate), ch) for i, ch in metadata if i in chosen
            )
            support.extend(
                dict(
                    id=ident,
                    mode=mode,
                    cohort=r["cohort"],
                    hardware_bin_s=int(bin_id * 15),
                    channel=channel,
                    valid_calls=available,
                    selected_calls=count[bin_id, channel],
                )
                for (bin_id, channel), available in sorted(availability.items())
            )
    return resources, support


def bind_controls(plan, evaluated):
    parent = sealed(trial.parent.REPORT, "prediction-lock.json", trial.PARENT_PIN)
    historical = rows_from(trial.parent.REPORT / "positions.jsonl.gz")
    if parent["cases"] != plan["mechanism8"]:
        raise ValueError("archives cover a different prior panel")
    stock = [
        dict(r, method=trial.PREFIX + r["condition"], cohort="mechanism8", reused_prior=True)
        for r in historical
        if r["condition"] in ("full", "lanes2", "lanes4", "bursts2", "bursts4")
    ]
    output = evaluated + stock
    expected = {(i, m) for i in plan["cases"] for m in MODES}
    main = [r for r in output if r["condition"] in MODES]
    if len(main) != len(expected) or {(r["id"], r["condition"]) for r in main} != expected:
        raise ValueError("rotation, full and static comparison must retain the matched roster")
    controls = {r["id"]: r for r in output if r["condition"] == STOCK}
    for row in output:
        earlier.fixed.same_capture(row, controls[row["id"]])
    return output, controls


def score(rows, plan, refs):
    table = earlier.fixed.scored(rows, refs)
    immutable = {(r["id"], r["method"]): r for r in rows}
    positions = {(r["id"], r["arm"], r["method"]): r for r in table}
    for r in table:
        own = immutable[r["id"], r["method"]]
        geo = positions[r["id"], r["arm"], trial.PREFIX + STOCK]["error_km"]
        n = r["error_km"]
        r.update(
            condition=own["condition"],
            cohort=own["cohort"],
            within_5pct_full=n is not None and geo is not None and n <= 1.05 * geo,
            within_10pct_full=n is not None and geo is not None and n <= 1.10 * geo,
        )
    effects = []
    for ident in plan["cases"]:
        for n in (2, 4):
            after = f"rotate{n}"
            conditions = ["full", f"lanes{n}"]
            if ident in plan["mechanism8"]:
                conditions.append(f"bursts{n}")
            for before in conditions:
                a, b = (immutable[ident, trial.PREFIX + m] for m in (after, before))
                for arm in ARMS:
                    p, q = (positions[ident, arm, trial.PREFIX + m] for m in (after, before))
                    pairs = {
                        k: p[k] - q[k] if p[k] is not None and q[k] is not None else None
                        for k in ("error_km", "rf_rms_hz", "frequency_score")
                    }
                    effects.append(
                        dict(
                            id=ident,
                            arm=arm,
                            mode=after,
                            control=before,
                            cohort=p["cohort"],
                            rotating_calls=a["detector_calls"],
                            control_calls=b["detector_calls"],
                            call_ratio=a["detector_calls"] / b["detector_calls"],
                            **{f"delta_{k}": d for k, d in pairs.items()},
                        )
                    )
    return table, effects


def figures(rows, plan):
    common = (
        "prediction-lock.json",
        "scores.csv",
        "effects.csv",
        "summary.csv",
        "rf-counts.csv",
        "resources.csv",
        "graph-support.csv",
        "capture-era-v5.csv",
    )
    charts = []
    for size in (2, 4):
        name, seal = f"dwell{size}-positions.jsonl.gz", f"dwell{size}-figure-lock.json"
        choices = (f"rotate{size}", STOCK, f"lanes{size}")
        pack(REPORT / name, [r for r in rows if r["condition"] in choices])
        save_json(
            REPORT / seal,
            dict(cases=plan["cases"], files={n: _sha(REPORT / n) for n in (name, *common)}),
        )
        charts.append(
            dict(
                id=f"rotating-dwell-{size}",
                method=trial.PREFIX + choices[0],
                scope="roof",
                cases="sealed",
                title=f"Hardware-clock rotating dwell with {size} monitored RF lanes",
                caption=(
                    "Eight mechanism cases and two prospective recordings. Original capture "
                    "factors are fit at full pass length. RF availability affects call counts."
                ),
                seal=seal,
                provenance=list(common),
                series=[
                    dict(
                        key=k,
                        label=label,
                        file=name,
                        value=trial.PREFIX + mode,
                        native_field="paired_capture_sha256",
                        match=list(earlier.fixed.BINDINGS),
                    )
                    for k, mode, label in zip(
                        ("one", "stock", "one_native_factors"),
                        choices,
                        (
                            "Rotating RF dwell",
                            "Full compact reference",
                            "Fixed whole-pass RF lanes",
                        ),
                        strict=True,
                    )
                ],
            )
        )
    save_json(REPORT / "figures.json", dict(version=2, charts=charts))


def publish(work):
    sealed(REPORT, "prediction-lock.json")
    plan, scheduled, events = (
        read(REPORT / n) for n in ("plan.json", "schedule.json", "dwell-events.json")
    )
    if any(_sha(ROOT / n) != digest for n, digest in plan["sources"].items()):
        raise ValueError("one of the locked scheduling or observer sources changed")
    actual = rows_from(REPORT / "predictions.jsonl.gz")
    resources, traffic = collect(work, plan, actual, scheduled, events)
    rows, controls = bind_controls(plan, actual)
    _, refs = held_references(None, plan["cases"])
    refs = {r["id"]: r for r in refs}
    table, effects = score(rows, plan, refs)
    summary = earlier.summary(
        table,
        refs,
        {
            "all": plan["cases"],
            "mechanism8": plan["mechanism8"],
            "prospective2": plan["prospective2"],
        },
    )
    graph_rows = []
    for row in rows:
        graph = row.get("graph") or {}
        metrics = row["result"]["metrics"]
        graph_rows.append(
            dict(
                id=row["id"],
                mode=row["condition"],
                cohort=row["cohort"],
                status=row["result"]["status"],
                reused_prior=bool(row.get("reused_prior")),
                retained_calls=row["detector_calls"],
                retained_gate_positive_probes=row["positive_probes"],
                graph_status=graph.get("graph_status"),
                graph_assigned=graph.get("assigned"),
                tracks=graph.get("tracks", metrics.get("tracks")),
                active_curvature=graph.get("active_curvature"),
                longest_track_s=graph.get("longest_s"),
                reason=row["result"].get("reason"),
            )
        )
    for name, data in (
        ("resources.csv", resources),
        ("scores.csv", table),
        ("effects.csv", effects),
        ("summary.csv", summary),
        ("rf-counts.csv", traffic),
        ("graph-support.csv", graph_rows),
        ("capture-era-v5.csv", original_rows(refs, controls)),
    ):
        csv_file(REPORT / name, data)
    pack(REPORT / "positions.jsonl.gz", rows)
    figures(rows, plan)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.work)
    if args.plot:
        screening_figures.generate(args.plot, evidence=REPORT)
