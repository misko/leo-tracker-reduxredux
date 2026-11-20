"""Audit causal dwell packets and score positions, geometry, and detector work."""

import argparse
import csv
from collections import Counter, defaultdict
from statistics import mean

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, ROLES
from ..variants import capture_bursts
from .channel_dwell_trial import MODES, PARENT, REPLAY, REPORT, read
from .full_held_scores import held_references
from .full_v5_check import BULK, _sha
from .margin_admission_results import fit, sealed
from .mixed_duty_cost import capture_panel
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file


def connected(times):
    """Measure physically ordered winning chains before any CFO compatibility test."""
    groups = []
    for lane in times.values():
        group = []
        for t in lane:
            if group and t - group[-1] > 10:
                groups.append(group)
                group = []
            group.append(t)
        if group:
            groups.append(group)
    viable = [g for g in groups if len(g) >= 8 and g[-1] - g[0] >= 6]
    return dict(
        viable_time_chains=len(viable),
        biggest_chain=max(map(len, groups), default=0),
        longest_time_chain_s=max((g[-1] - g[0] for g in groups), default=0),
    )


def fifo(arrivals, per_call):
    finish, worst = 0.0, 0.0
    for at in arrivals:
        finish = max(finish, at) + per_call
        worst = max(worst, finish - at)
    return finish, worst


def full_controls():
    all = sealed(PARENT, "prediction-lock.json", "positions.jsonl.gz")
    graph_path = PARENT / "graph-tracks.csv"
    whole_iq.checked(graph_path, read(PARENT / "graph-lock.json")["files"][graph_path.name])
    with graph_path.open() as stream:
        graph = {r["id"]: r for r in csv.DictReader(stream) if r["condition"] == "full"}
    output = []
    for ident in REPLAY:
        (row,) = [r for r in all if r["id"] == ident and r["condition"] == "full"]
        evidence = graph[ident]
        output.append(
            dict(
                row,
                method="channel_dwell_full",
                cohort="burst-replication",
                calls=row["detector_calls"],
                original_valid_visits=row["valid_visits"],
                geometry=dict(
                    graph_status=evidence["graph_status"],
                    winning=int(evidence["winning_observations"]),
                    assigned=int(evidence["graph_assigned_observations"]),
                    tracks=int(evidence["tracks"]),
                    active_curvature=int(evidence["active_curvature_tracks"]),
                    longest_s=float(evidence["longest_track_s"]),
                ),
            )
        )
    return output


def timing_panel():
    panel = capture_panel()
    clocks = {key: [p for visit in v["visits"] for p in visit["calls"]] for key, v in panel.items()}
    cpu = [r["cpu_ms"] / 1000 for pool in clocks.values() for r in pool]
    anchor = dict(
        mid_s=mean(mean(x["cpu_ms"] / 1000 for x in pool) for pool in clocks.values()),
        low_s=min(cpu),
        high_s=max(cpu),
        raw_calls=len(cpu),
        calls_within_20ms=sum(r["wall_ms"] <= 20 for pool in clocks.values() for r in pool),
        source_pins={k: v["sha256"] for k, v in panel.items()},
    )
    save_json(REPORT / "cost-authority.json", anchor)
    return anchor


def audit(work, rows, schedule):
    coverage, runtime, geometry = [], [], []
    panel = timing_panel()
    for ident, opening in schedule.items():
        case, _ = whole_iq.binding(ident)
        baseline = read(whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"]))
        meta = capture_bursts.inventories(baseline)
        clock = [r["monotonic_ns"] for r in baseline["delivery_clocks"]]
        arrivals = [(x - clock[0]) / 1e9 for x in clock]
        source = baseline["source"]
        sample_anchor = baseline["clock_anchor"]["sample_counter"]
        rate = source["sample_rate_hz"]
        for row in (r for r in rows if r["id"] == ident):
            mode = row["condition"]
            head = opening[mode] if mode in opening else [v for v, _ in meta]
            chosen = set(head)
            if len(chosen) != row["calls"]:
                raise ValueError("packet policy differs from fixed detector-call budget")
            phases = defaultdict(list)
            stop = max(chosen)
            stock = [p for p in source["probes"] if p["visit_index"] <= stop]
            measuring = mode != "full" or ident not in REPLAY
            if measuring:
                folder = work / ident / mode / "recording"
                measured = read(whole_iq.checked(folder / "native.json", row["native_sha256"]))
                whole_iq.checked(folder / "request.json", row["prepared_request_sha256"])
            else:
                measured = baseline
            considered = measured["source"]["probes"]
            for original, actual in zip(stock, considered, strict=True):
                expected = (
                    original if original["visit_index"] in chosen else dict(original, candidates=[])
                )
                if actual != expected:
                    raise ValueError("selected original packet or unselected header changed")
                if any(c["passed_fractional_margin_gate"] is True for c in actual["candidates"]):
                    lane = tuple(
                        actual[k] for k in ("receiver_id", "channel", "edge", "actual_rf_hz")
                    )
                    phases[lane].append((actual["valid_start_counter"] - sample_anchor) / rate)
            end = measured["last_sample_counter"]
            inferred_end = max(p["valid_start_counter"] for p in considered) + round(
                rate * source["probe_ms"] / 1000
            )
            if end < inferred_end or (
                mode != "full"
                and (
                    end != inferred_end
                    or end != row["final_sample_counter"]
                    or measured["delivery_clocks"] != baseline["delivery_clocks"][: stop + 1]
                    or measured["provenance"]["excluded_windows"]
                    != [x for x in baseline["provenance"]["excluded_windows"] if x["visit"] <= stop]
                )
            ):
                raise ValueError("scored prefix includes a later or mismatched sample frontier")
            counts = Counter(ch for visit, ch in meta if visit in chosen)
            coverage.append(
                dict(
                    id=ident,
                    condition=mode,
                    calls=len(chosen),
                    rf_channels=len(counts),
                    opportunity_span_s=arrivals[stop] - arrivals[min(chosen)],
                    original_total_s=arrivals[-1],
                    sample_frontier_s=(end - sample_anchor) / rate,
                    valid_joint_probes=len(considered),
                    positive_probes=sum(map(len, phases.values())),
                    **connected(phases),
                )
            )
            clocks = [arrivals[v] for v in sorted(chosen)]
            estimate = {name: fifo(clocks, panel[name + "_s"]) for name in ("low", "mid", "high")}
            usage = row.get("position_resources") or {}
            terminal = usage.get("wall_s", row["supervisor_wall_s"])
            runtime.append(
                dict(
                    id=ident,
                    condition=mode,
                    first_delivery_s=clocks[0],
                    last_delivery_s=clocks[-1],
                    detector_cost_mean_cpu_s=panel["mid_s"] * len(chosen),
                    modeled_ready_s=estimate["mid"][0],
                    modeled_max_delivery_delay_s=estimate["mid"][1],
                    modeled_terminal_s=estimate["mid"][0] + terminal,
                    modeled_terminal_low_s=estimate["low"][0] + terminal,
                    modeled_terminal_high_s=estimate["high"][0] + terminal,
                    solver_service_cpu_s=usage.get("cpu_s"),
                    solver_service_wall_s=usage.get("wall_s"),
                    service_supervisor_wall_s=row["supervisor_wall_s"],
                    peak_bytes=usage.get("peak_bytes"),
                )
            )
            proof = row.get("geometry") or {}
            for arm in ARMS:
                candidate = proof.get("arms", {}).get(arm, {})
                singular = candidate.get("centered_doppler_singular_hz_km", [])
                geometry.append(
                    dict(
                        id=ident,
                        condition=mode,
                        arm=arm,
                        status=row["result"]["status"],
                        graph_status=proof.get("graph_status"),
                        graph_tracks=proof.get("tracks"),
                        curved_graph_tracks=proof.get("active_curvature"),
                        longest_graph_track_s=proof.get("longest_s"),
                        compatible_curved_tracks=candidate.get("compatible_tracks"),
                        unique_compatible_satellites=len(candidate["norads"])
                        if "norads" in candidate
                        else None,
                        compatible_norads=" ".join(map(str, candidate.get("norads", ()))),
                        geometry_stage=proof.get("geometry_stage"),
                        causal_sky_catalogue_candidates=proof.get("sky_catalogue_candidates"),
                        singular_max_hz_km=singular[0] if singular else None,
                        singular_min_hz_km=singular[1] if len(singular) > 1 else None,
                    )
                )
    csv_file(REPORT / "packet-audit.csv", coverage)
    csv_file(REPORT / "time-work.csv", runtime)
    csv_file(REPORT / "graph-geometry.csv", geometry)


def figures(cases):
    labels = {
        "dwell96": "Early single-channel 96-call dwell",
        "delayed96": "Delayed single-channel 96-call dwell",
        "dwell416": "Early two-channel 416-call dwell",
        "delayed416": "Delayed two-channel 416-call dwell",
        "full": "Complete original native factors",
    }
    ids = dict(
        zip(
            MODES,
            (
                "channel-dwell-96",
                "channel-dwell-96-delayed",
                "channel-dwell-416",
                "channel-dwell-416-delayed",
            ),
            strict=True,
        )
    )
    evidence = (
        "positions.jsonl.gz",
        "prediction-lock.json",
        "scores.csv",
        "packet-audit.csv",
        "graph-geometry.csv",
        "time-work.csv",
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=cases, files={n: _sha(REPORT / n) for n in evidence}),
    )

    def series(key, mode):
        return dict(
            key=key,
            label=labels[mode],
            file=evidence[0],
            value="channel_dwell_" + mode,
            native_field="paired_capture_sha256",
            match=["catalog_sha256", "original_request_sha256", "tile"],
        )

    save_json(
        REPORT / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id=ids[m],
                    method="channel_dwell_" + m,
                    scope="roof",
                    cases="sealed",
                    title=labels[m],
                    seal="figure-lock.json",
                    provenance=list(evidence[1:]),
                    caption=(
                        "Exact RF packets through each chosen sample frontier. Each variant "
                        "spends its original-detector budget on one or two lanes."
                    ),
                    series=[
                        series("one", m),
                        series("stock", "full"),
                        series("one_native_factors", other),
                    ],
                )
                for m, other in zip(
                    MODES, ("delayed96", "dwell96", "delayed416", "dwell416"), strict=True
                )
            ],
        ),
    )


def stage_figure():
    import matplotlib.pyplot as plt

    panel = {}
    for file in ("packet-audit.csv", "time-work.csv", "graph-geometry.csv"):
        with (REPORT / file).open() as stream:
            for row in csv.DictReader(stream):
                if row["condition"] not in MODES or row.get("arm", "c0") != "c0":
                    continue
                panel.setdefault((row["id"], row["condition"]), {}).update(row)
    output = list(panel.values())
    csv_file(
        REPORT / "stage.csv",
        [
            dict(
                recording=r["id"],
                mode=r["condition"],
                status=r["status"],
                detector_calls=r["calls"],
                graph_tracks=r["graph_tracks"],
                curved_graph_tracks=r["curved_graph_tracks"],
                modeled_terminal_s=r["modeled_terminal_s"],
                modeled_terminal_low_s=r["modeled_terminal_low_s"],
                modeled_terminal_high_s=r["modeled_terminal_high_s"],
                solver_service_wall_s=r["solver_service_wall_s"],
            )
            for r in output
        ],
    )
    labels = ("96 early", "96 delayed", "416 early", "416 delayed")
    fig, (left, right) = plt.subplots(1, 2, figsize=(11.5, 4.6), layout="constrained")
    for offset, ident in zip(
        (-0.24, -0.08, 0.08, 0.24), sorted({r["id"] for r in output}), strict=True
    ):
        x = [i + offset for i in range(len(MODES))]
        points = [panel[ident, mode] for mode in MODES]
        color = left.plot(
            x, [int(r["curved_graph_tracks"] or 0) for r in points], "o", label=ident
        )[0].get_color()
        ready = [float(r["modeled_terminal_s"]) for r in points]
        right.plot(x, ready, "o", color=color)
        for j, row in enumerate(points):
            if row["status"] != "ok":
                right.plot(x[j], ready[j], "x", color="black", markersize=7)
    left.set(title="Measured active-curvature tracks", ylabel="Tracks")
    right.set(title="Modeled query time on one detector core", ylabel="Seconds from first delivery")
    right.axhline(
        300, color="#777777", linewidth=1, linestyle="--", label="Complete capture (~300 s)"
    )
    right.plot([], [], "kx", label="Position attempt failed or withheld")
    for axes in (left, right):
        axes.set_xticks(range(len(MODES)), labels, rotation=15)
        axes.grid(axis="y", alpha=0.2)
        axes.legend(fontsize=8)
    fig.savefig(REPORT / "dwell-frontier.png", dpi=160)
    plt.close(fig)
    paths = ("stage.csv", "dwell-frontier.png")
    save_json(REPORT / "stage-lock.json", dict(files={p: _sha(REPORT / p) for p in paths}))
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="channel-dwell-frontier",
            title="Track support and detector queue for RF dwell",
            sample="Four recordings and 16 sparse fits with exact 96- and 416-call budgets",
            boundary="Stored original packets → measured Graph and modeled query completion",
            note=(
                "Graph counts and position terminal states are measured. Queue time transfers "
                "archived original-detector costs onto recorded visit arrivals."
            ),
            seal="stage-lock.json",
            image=paths[1],
            csv=paths[0],
        ),
    )


def publish(work):
    rows = sealed(REPORT, "prediction-lock.json", "predictions.jsonl.gz")
    plan = read(REPORT / "plan.json")
    cases = list(plan["cases"])
    if (
        len(rows) != len(plan["tasks"])
        or {(x["id"], x["condition"]) for x in rows}
        != {(x["id"], x["condition"]) for x in plan["tasks"]}
        or any(_sha(ROOT / key) != digest for key, digest in plan["files"].items())
    ):
        raise ValueError("the fixed prospective plan or all-attempt denominator changed")
    rows.extend(full_controls())
    audit(work, rows, read(REPORT / "schedule.json"))
    refs = {r["id"]: r for r in held_references(None, cases)[1]}
    report = []
    for row in rows:
        for arm in ARMS:
            ref = refs[row["id"]]
            target = ref["reference"]["baseline"][arm]["error_km"]
            s = fit(row, ref, arm)
            error = s["error_km"]
            report.append(
                dict(
                    s,
                    condition=row["condition"],
                    cohort=row["cohort"],
                    original_v5_km=target,
                    within_5pct=error is not None and error <= 1.05 * target,
                    within_10pct=error is not None and error <= 1.10 * target,
                )
            )
    csv_file(REPORT / "scores.csv", report)
    csv_file(
        REPORT / "capture-era-v5.csv",
        [
            dict(
                id=id,
                role=role,
                arm=arm,
                **{
                    k: ref["reference"][role][arm].get(k)
                    for k in ("status", "error_km", "rf_rms_hz")
                },
            )
            for id, ref in refs.items()
            for role in ROLES
            for arm in ARMS
        ],
    )
    write(REPORT / "positions.jsonl.gz", compressed_rows(rows))
    figures(cases)
    stage_figure()
    files = (
        "positions.jsonl.gz",
        "prediction-lock.json",
        "scores.csv",
        "capture-era-v5.csv",
        "time-work.csv",
        "cost-authority.json",
        "graph-geometry.csv",
        "packet-audit.csv",
        "figure-lock.json",
        "figures.json",
        "stage-figure.json",
        "stage-lock.json",
    )
    save_json(REPORT / "score-lock.json", dict(files={n: _sha(REPORT / n) for n in files}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.work)
    if args.plot:
        from .screening_figures import generate

        generate(args.plot, evidence=REPORT)
