"""Verify projected capture-era packets and separately score positions and detector cost."""

import argparse
from collections import defaultdict
from pathlib import Path
from statistics import mean

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, ROLES
from ..variants import capture_bursts
from . import capture_bursts_trial as trial
from .full_held_scores import held_references
from .full_v5_check import BULK, _sha
from .margin_admission_results import fit, sealed
from .mixed_duty_cost import capture_panel
from .prefix_figures import csv_file
from .screening_figures import generate
from .support_cross_results import outside_treatment

REPORT = trial.REPORT
DEADLINE_MS = 20
ADJACENT_S = 0.60


def backlog(arrivals, per_call_s):
    """Single-detector-core FIFO with a constant transferred cost and no parallelism."""
    ready, worst = 0.0, 0.0
    for arrival in arrivals:
        ready = max(ready, arrival) + per_call_s
        worst = max(worst, ready - arrival)
    return worst


def largest_gap_connected_count(times, maximum_gap_s):
    largest, size, previous = 0, 0, float("-inf")
    for sample in times:
        size = size + 1 if sample - previous <= maximum_gap_s else 1
        largest = max(largest, size)
        previous = sample
    return largest


def audit_case(work, ident, entries, schedule):
    case, parent = whole_iq.binding(ident)
    config = parent["job"]["track_config"]
    config_source = whole_iq.checked(Path(config["path"]), config["sha256"])
    max_gap = trial.read(config_source)["config"]["max_gap_s"]
    raw = whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
    baseline = trial.read(raw)
    metadata = capture_bursts.inventories(baseline)
    clocks = [row["monotonic_ns"] for row in baseline["delivery_clocks"]]
    arrivals = [(clock - clocks[0]) / 1e9 for clock in clocks]
    audit = []
    for row in entries:
        mode = row["condition"]
        folder = work / ident / mode / "recording"
        candidate = whole_iq.checked(folder / "native.json", row["native_sha256"])
        whole_iq.checked(folder / "request.json", row["prepared_request_sha256"])
        doc = trial.read(candidate)
        if mode == "full":
            visits = [visit for visit, _ in metadata]
            if candidate.read_bytes() != raw.read_bytes():
                raise ValueError("full compact control did not use the exact archived factors")
        else:
            visits = schedule[mode]
            if visits != capture_bursts.scheduled_visits(metadata, mode):
                raise ValueError("frozen schedule does not reproduce from valid opportunities")
            if outside_treatment(doc) != outside_treatment(baseline):
                raise ValueError("a condition changed counters, source, or acquisition ledger")
        chosen = set(visits)
        hits = defaultdict(list)
        for old, new in zip(baseline["source"]["probes"], doc["source"]["probes"], strict=True):
            visit = old["visit_index"]
            if new != (old if visit in chosen else dict(old, candidates=[])):
                raise ValueError("valid probe headers or retained capture-era packet changed")
            if any(c[trial.GATE] for c in new["candidates"]):
                key = (new["channel"], new["actual_rf_hz"], new["receiver_id"])
                hits[key].append(arrivals[visit])
        short = sum(
            right - left <= ADJACENT_S
            for times in hits.values()
            for left, right in zip(times, times[1:], strict=False)
        )
        if (
            len(visits) != row["detector_calls"]
            or sum(map(len, hits.values())) != row["positive_probes"]
        ):
            raise ValueError("worker metadata differs from the applied schedule")
        audit.append(
            dict(
                id=ident,
                condition=mode,
                positive_same_rx_rf_pairs_within_600ms=short,
                max_same_rx_rf_gap_connected_winners=max(
                    (largest_gap_connected_count(times, max_gap) for times in hits.values()),
                    default=0,
                ),
            )
        )
    return audit, arrivals


def costs(rows, schedules, arrivals):
    by_case = capture_panel()
    samples = [
        [call for visit in obj["visits"] for call in visit["calls"]] for obj in by_case.values()
    ]
    point = mean(mean(call["cpu_ms"] for call in samples_i) for samples_i in samples)
    rates = [call for cohort in samples for call in cohort]
    minimum = min(call["cpu_ms"] for call in rates)
    maximum = max(call["cpu_ms"] for call in rates)
    modeled = []
    for row in rows:
        ident, mode, calls = (row[k] for k in ("id", "condition", "detector_calls"))
        t = arrivals[ident]
        per_visit = calls / row["total_visits"]
        scheduled = [t[i] for i in schedules[ident][mode]] if mode != "full" else None
        modeled.append(
            dict(
                id=ident,
                condition=mode,
                total_recorded_visits=row["total_visits"],
                valid_recorded_visits=row["valid_visits"],
                detector_calls=calls,
                fraction_all_visits=per_visit,
                delivery_span_s=t[-1],
                transferred_cpu_ms_per_call=point,
                detector_cpu_s=calls * point / 1000,
                amortized_cpu_ms_per_visit=point * per_visit,
                observed_low_amortized_cpu_ms=minimum * per_visit,
                observed_high_amortized_cpu_ms=maximum * per_visit,
                nominal_one_core_utilization=calls * point / (1000 * t[-1]),
                modeled_max_latency_s=backlog(scheduled, point / 1000)
                if scheduled is not None
                else None,
            )
        )
    save_json(
        REPORT / "cost-authority.json",
        dict(
            cohorts=by_case,
            measured_calls=len(rates),
            measured_wall_calls_on_time=sum(call["wall_ms"] <= DEADLINE_MS for call in rates),
            measured_wall_range_ms=[
                min(r["wall_ms"] for r in rates),
                max(r["wall_ms"] for r in rates),
            ],
            cpu_range_ms=[minimum, maximum],
            transfer_mean_cpu_ms=point,
        ),
    )
    return modeled


def historical(refs, full):
    return [
        dict(
            id=ref["id"],
            role=role,
            arm=arm,
            native_sha256=full[ref["id"]]["native_sha256"],
            status=value["status"],
            latitude=(value.get("latlon") or [None, None])[0],
            longitude=(value.get("latlon") or [None, None])[1],
            error_km=value.get("error_km"),
            conditional_rf_rms_hz=value.get("rf_rms_hz"),
            archived_wall_s=value.get("wall_s"),
        )
        for ref in refs
        for role in ROLES
        for arm in ARMS
        for value in [ref["reference"][role][arm]]
    ]


def descriptor(cases):
    provenance = (
        "plan.json",
        "schedule.json",
        "prediction-lock.json",
        "packet-audit.csv",
        "scores.csv",
        "capture-era-v5.csv",
        "detector-costs.csv",
        "solver-resources.csv",
        "graph-tracks.csv",
        "graph-lock.json",
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(
            cases=cases,
            files={name: _sha(REPORT / name) for name in (*provenance, "positions.jsonl.gz")},
        ),
    )

    def series(condition, key, label):
        return dict(
            key=key,
            label=label,
            file="positions.jsonl.gz",
            value="capture_bursts_" + condition,
            native_field="paired_capture_sha256",
            match=["tile", "catalog_sha256", "original_request_sha256", "paired_capture_sha256"],
        )

    save_json(
        REPORT / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="capture-bursts-" + label,
                    method="capture_bursts_burst" + variant,
                    scope="roof",
                    cases="sealed",
                    seal="figure-lock.json",
                    provenance=provenance,
                    title=f"Original detector only · {duty} valid calls per channel",
                    caption=(
                        "Four adjacent same-channel visits and equal-duty uniform spacing. "
                        "Both use original detector packets and fresh capped compact fits."
                    ),
                    series=[
                        series("burst" + variant, "one", "Four-visit bursts"),
                        series(
                            "periodic" + variant, "one_native_factors", "Matched periodic calls"
                        ),
                        series("full", "stock", "Complete capture-era compact"),
                    ],
                )
                for label, variant, duty in (("primary", "", 12), ("high", "_high", 52))
            ],
        ),
    )


def publish(work):
    lock = trial.read(REPORT / "prediction-lock.json")
    plan = trial.read(whole_iq.checked(REPORT / "plan.json", lock["files"]["plan.json"]))
    for path, digest in plan["sources"].items():
        whole_iq.checked(ROOT / path, digest)
    schedule = trial.read(whole_iq.checked(REPORT / "schedule.json", plan["schedule_sha256"]))
    records = sealed(REPORT, "prediction-lock.json", "positions.jsonl.gz")
    cases = plan["cases"]
    if [(r["id"], r["condition"]) for r in records] != [
        (r["id"], r["condition"]) for r in plan["trials"]
    ]:
        raise ValueError("terminal results differ from the predetermined cases and attempt order")
    for row in records:
        folder = work / row["id"] / row["condition"]
        whole_iq.checked(folder / "service.log", row["log_sha256"])
    audits, arrivals = [], {}
    for ident in cases:
        rows, clock = audit_case(
            work, ident, [r for r in records if r["id"] == ident], schedule[ident]
        )
        audits.extend(rows)
        arrivals[ident] = clock
    csv_file(REPORT / "packet-audit.csv", audits)
    cost_rows = costs(records, schedule, arrivals)
    csv_file(REPORT / "detector-costs.csv", cost_rows)
    _, refs = held_references("roof16", cases)
    truth = {r["id"]: r for r in refs}
    csv_file(
        REPORT / "scores.csv", [fit(row, truth[row["id"]], arm) for row in records for arm in ARMS]
    )
    csv_file(
        REPORT / "capture-era-v5.csv",
        historical(refs, {r["id"]: r for r in records if r["condition"] == "full"}),
    )
    csv_file(REPORT / "solver-resources.csv", [resource(row) for row in records])
    graph_receipt(work, records, cases)
    descriptor(cases)
    generate(REPORT / "charts", evidence=REPORT)
    frontier(audits, cost_rows, cases)


def graph_receipt(work, records, cases):
    rows, files = [], {}
    for ident in cases:
        for suffix in ("json", "log"):
            name = f"{ident}-graph.{suffix}"
            write(REPORT / name, (work / name).read_bytes())
            files[name] = _sha(REPORT / name)
        log = (REPORT / (ident + "-graph.log")).read_text()
        if "Finished with result: success" not in log:
            raise ValueError("independent Graph stage did not complete")
        rows.extend(trial.read(REPORT / (ident + "-graph.json")))
    for stage, prediction in zip(rows, records, strict=True):
        if any(stage[k] != prediction[k] for k in ("id", "condition", "native_sha256")):
            raise ValueError("Graph stage did not run on the exactly matched factors")
        expected = prediction["result"]["metrics"].get("tracks")
        if expected is not None and stage["tracks"] != expected:
            raise ValueError("Graph counts differ from the complete solver")
    csv_file(REPORT / "graph-tracks.csv", rows)
    files["graph-tracks.csv"] = _sha(REPORT / "graph-tracks.csv")
    runner = Path(__file__).with_name("capture_bursts_graph.py")
    save_json(
        REPORT / "graph-lock.json",
        dict(
            files=files,
            plan_sha256=_sha(REPORT / "plan.json"),
            source={str(runner.relative_to(ROOT)): _sha(runner)},
        ),
    )


def frontier(audit, costs, cases):
    import matplotlib.pyplot as plt

    modes = ("periodic", "burst", "periodic_high", "burst_high")
    matched = {(r["id"], r["condition"]): r for r in audit}
    rows = [
        dict(
            r,
            **{
                k: v
                for k, v in matched[r["id"], r["condition"]].items()
                if k not in ("id", "condition")
            },
        )
        for r in costs
        if r["condition"] in modes
    ]
    csv_file(REPORT / "frontier.csv", rows)
    fig, (support, queue) = plt.subplots(1, 2, layout="constrained", figsize=(9.2, 3.7))
    labels = ["Periodic\n96", "Burst\n96", "Periodic\n416", "Burst\n416"]
    for ident, offset, color in zip(cases, (-0.14, 0.14), ("#3f6481", "#0e776b"), strict=True):
        by_mode = {row["condition"]: row for row in rows if row["id"] == ident}
        x = [i + offset for i in range(len(modes))]
        support.bar(
            x,
            [by_mode[m]["max_same_rx_rf_gap_connected_winners"] for m in modes],
            width=0.25,
            label=ident,
            color=color,
        )
        queue.scatter(x, [by_mode[m]["modeled_max_latency_s"] for m in modes], s=26, color=color)
    support.axhline(8, color="#a04340", linestyle="--", label="Graph requires at least 8")
    support.set(
        title="Available Doppler continuity",
        ylabel="Most gap-connected winners in one lane",
        ylim=(0, 10.5),
    )
    queue.set(
        title="Modeled one-core detector queue",
        ylabel="Worst arrival-to-completion time (s)",
        yscale="log",
        ylim=(1, 600),
    )
    for axis in (support, queue):
        axis.set_xticks(range(len(modes)), labels)
        axis.grid(axis="y", alpha=0.25)
        axis.set_axisbelow(True)
    support.legend(loc="upper left", frameon=False, fontsize=8, ncols=2)
    fig.suptitle("Original detector at matched sparse call budgets")
    fig.savefig(REPORT / "frontier.png", dpi=175)
    fig.savefig(REPORT / "frontier.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="capture-bursts-frontier",
            title="Original detector duty frontier",
            image="frontier.png",
            pdf="frontier.pdf",
            csv="frontier.csv",
            seal="frontier-lock.json",
            boundary="Archived original detector packets into Graph and a separate queue model",
            sample="Two held roof recordings, two matched visit budgets and full compact controls",
            note="The support panel uses observed arrivals. The queue transfers detector timing.",
        ),
    )
    members = (
        "stage-figure.json",
        "frontier.csv",
        "frontier.png",
        "frontier.pdf",
        "cost-authority.json",
        "detector-costs.csv",
        "packet-audit.csv",
        "graph-lock.json",
        "figure-lock.json",
        "README.md",
    )
    save_json(
        REPORT / "frontier-lock.json",
        dict(
            cases=cases,
            files={name: _sha(REPORT / name) for name in members},
            source_sha256=_sha(Path(__file__)),
        ),
    )


def resource(row):
    metrics = row["result"]["metrics"]
    times = row["position_resources"] or {}
    return dict(
        id=row["id"],
        condition=row["condition"],
        status=row["result"]["status"],
        terminal=row["terminal"],
        cpu=row["cpu"],
        cpu_s=times.get("cpu_s"),
        wall_s=times.get("wall_s"),
        peak_bytes=times.get("peak_bytes"),
        swap_bytes=times.get("end", {}).get("memory.swap.current"),
        supervisor_wall_s=row["supervisor_wall_s"],
        observations=metrics.get("observations"),
        tracks=metrics.get("tracks"),
        c0_frequency_score=metrics.get("c0_frequency_score"),
        fitted_c_frequency_score=metrics.get("fitted_c_frequency_score"),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    publish(parser.parse_args().work)
