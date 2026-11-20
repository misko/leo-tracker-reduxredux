"""Verify the frozen full-pass RF inputs, score positions and replay measured CPU costs."""

import argparse
import gzip
import json
from hashlib import sha256
from statistics import mean

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution, thresholds, validate_result
from ..variants import capture_bursts, frequency_schedule
from . import complete_detector_roster as fixed
from . import frequency_schedule_trial as trial
from . import screening_figures
from .frequency_schedule_pacing import CORES, pace
from .fresh_replay_results import sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .staggered_reconstruction_results import original_rows
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
PFX = trial.PREFIX
RAW_PIN = "6d69607b2ead5085e039ac89cebbbcb4eb8f487d41190b91f0f15977d1831e82"
read = whole_iq.read


def verify(work, plan, rows, scheduled, timing):
    expected = {(r["id"], r["condition"]): r for r in plan["tasks"]}
    if len(rows) != len(expected) or {(r["id"], r["condition"]) for r in rows} != expected.keys():
        raise ValueError("every frozen numerical input needs a terminal row")
    support, resources, paced = [], [], []
    issued = {(r["id"], r["condition"]): r for r in rows}
    for ident in plan["cases"]:
        case, request, path, base, metadata, clocks = trial.incoming(ident)
        if plan["inputs"][ident]["native_source"] != str(path) or plan["inputs"][ident][
            "clock_sha256"
        ] != whole_iq.recording.digest(base["delivery_clocks"]):
            raise ValueError("original full-pass clock or native authority changed")
        options = frequency_schedule.schedules(ident, metadata, clocks)
        if ident == trial.OVERLAP:
            options["periodic4"], _ = trial.recorded_periodic(case, metadata)
        if options != scheduled[ident]:
            raise ValueError("saved schedule does not reproduce from acquisition-only metadata")
        bins = frequency_schedule.clock_bins(clocks)
        for name, chosen in options.items():
            worker = issued[ident, name]
            if any(worker[k] != v for k, v in expected[ident, name].items()):
                raise ValueError("worker received a mismatched fit request")
            validate_result(worker["result"])
            jobdir = work / ident / name
            native = whole_iq.checked(jobdir / "recording/native.json", worker["native_sha256"])
            source = whole_iq.checked(
                jobdir / "recording/request.json", worker["prepared_request_sha256"]
            )
            capture_bursts_trial = trial.capture_bursts_trial
            capture_bursts_trial.verify_request(
                read(source), request, native_path=native, native_sha256=worker["native_sha256"]
            )
            if name == "full":
                if worker["native_sha256"] != case["native"]["sha256"]:
                    raise ValueError("full compact control changed the original native bytes")
            else:
                identity = whole_iq.recording.digest(
                    [capture_bursts_trial.SALT, name, case["native"]["sha256"], chosen]
                )
                exact = capture_bursts.select_document(base, chosen, identity)
                if native.read_bytes() != encoded(exact) + b"\n":
                    raise ValueError("masked factor stream changed clocks, metadata or candidates")
            stats = worker.get("position_resources") or {}
            if worker["terminal"] != "not-launched":
                if read(jobdir / "attempt.json") != worker:
                    raise ValueError("post-fit row does not match its genuine worker")
                log = whole_iq.checked(jobdir / "service.log", worker["log_sha256"])
                write(
                    REPORT / "logs" / f"{ident}-{name}.log.gz",
                    gzip.compress(log.read_bytes(), mtime=0),
                )
            for edge in ("start", "end"):
                if stats and (
                    stats[edge]["cpus"] != [worker["cpu"]]
                    or stats[edge]["nice"] != 10
                    or stats[edge]["memory.max"] != plan["memory_bytes"]
                    or stats[edge]["memory.swap.max"] != 0
                    or stats[edge]["memory.swap.current"] != 0
                ):
                    raise ValueError("service used a different memory or CPU boundary")
            metrics = worker["result"]["metrics"]
            observations = metrics.get("observations")
            published_without_count = worker["result"]["status"] == "ok" and observations is None
            mismatched_count = (
                observations is not None and observations != worker["positive_probes"]
            )
            if worker["terminal"] == "success" and (
                not stats or published_without_count or mismatched_count
            ):
                raise ValueError("position-observed factors differ from the sealed gate count")
            resources.append(
                dict(
                    id=ident,
                    condition=name,
                    cohort=worker["cohort"],
                    cpu=worker["cpu"],
                    terminal=worker["terminal"],
                    status=worker["result"]["status"],
                    position_wall_s=stats.get("wall_s"),
                    position_cpu_s=stats.get("cpu_s"),
                    peak_bytes=stats.get("peak_bytes"),
                    swap_bytes=stats.get("end", {}).get("memory.swap.current"),
                    supervisor_wall_s=worker.get("supervisor_wall_s"),
                )
            )
            arrivals = [(clocks[v] - clocks[0]) / 1e9 for v in chosen]
            support.append(
                dict(
                    id=ident,
                    condition=name,
                    cohort=worker["cohort"],
                    calls=len(chosen),
                    original_valid_visits=len(metadata),
                    positive_probes=worker["positive_probes"],
                    positive_stereo_visits=worker["positive_stereo_visits"],
                    tracks=metrics.get("tracks"),
                    first_s=min(arrivals),
                    last_s=max(arrivals),
                    observed_span_s=max(arrivals) - min(arrivals),
                    bins_with_visits=len(set(bins[v] for v in chosen)),
                    **{
                        f"ch{n}_calls": worker["scheduled_by_channel"].get(str(n), 0)
                        for n in range(1, 9)
                    },
                )
            )
            costs = (
                [timing[v] for v in chosen]
                if ident == trial.ANCHOR
                else [mean(timing.values())] * len(chosen)
            )
            for cores in CORES:
                estimate = pace(arrivals, costs, cores)
                detector_ready = estimate["simulated_detector_ready_s"]
                solve = stats.get("wall_s")
                earliest_fit = max(worker["delivery_span_s"], detector_ready)
                paced.append(
                    dict(
                        id=ident,
                        condition=name,
                        cohort=worker["cohort"],
                        cores=cores,
                        timing_basis="exact anchor visit CPU"
                        if ident == trial.ANCHOR
                        else "transferred anchor mean",
                        calls=len(chosen),
                        delivery_span_s=worker["delivery_span_s"],
                        **estimate,
                        position_status=worker["result"]["status"],
                        measured_position_s=solve,
                        simulated_full_stream_result_s=earliest_fit + solve
                        if solve is not None
                        else None,
                    )
                )
    return support, resources, paced


def scores(rows, refs, plan):
    data = fixed.scored(rows, refs)
    details = {(r["id"], r["method"]): r for r in rows}
    lookup = {(r["id"], r["arm"], r["method"]): r for r in data}
    for r in data:
        ident, arm, method = r["id"], r["arm"], r["method"]
        anchor = lookup[ident, arm, PFX + "full"]["error_km"]
        observed = r["error_km"]
        r.update(
            cohort=details[ident, method]["cohort"],
            condition=details[ident, method]["condition"],
            observations=details[ident, method]["result"]["metrics"].get("observations"),
            calls=details[ident, method]["detector_calls"],
            proportion_above_full=observed / anchor - 1
            if observed is not None and anchor
            else None,
            within_5pct_full=(
                observed is not None and anchor is not None and observed <= 1.05 * anchor
            ),
            within_10pct_full=(
                observed is not None and anchor is not None and observed <= 1.10 * anchor
            ),
        )
    effects = []
    for ident in plan["cases"]:
        comparisons = [(m, "full") for m in frequency_schedule.MODES if m != "full"]
        comparisons += [("lanes2", "bursts2"), ("lanes4", "bursts4")]
        if ident == trial.OVERLAP:
            comparisons += [
                ("periodic4", "lanes2"),
                ("periodic4", "bursts2"),
                ("periodic4", "full"),
            ]
        for arm in ARMS:
            for a, b in comparisons:
                candidate, parent = (lookup[ident, arm, PFX + m] for m in (a, b))
                effects.append(
                    dict(
                        id=ident,
                        cohort=candidate["cohort"],
                        arm=arm,
                        condition=a,
                        control=b,
                        calls_delta=candidate["calls"] - parent["calls"],
                        **{
                            f"delta_{key}": candidate[key] - parent[key]
                            if candidate[key] is not None and parent[key] is not None
                            else None
                            for key in ("error_km", "rf_rms_hz", "frequency_score", "observations")
                        },
                    )
                )
    return data, effects


def summary(data, refs, groups):
    out = []
    for label, ids in groups.items():
        for arm in ARMS:
            incoming = [r for r in data if r["id"] in ids and r["arm"] == arm]
            modes = sorted({r["condition"] for r in incoming})
            for method in (*modes, *ROLES):
                lines = [r for r in incoming if r["condition"] == method]
                if method in ROLES:
                    values = [refs[i]["reference"][method][arm] for i in ids]
                    errors = [r.get("error_km") for r in values]
                    rf = [r.get("rf_rms_hz") for r in values]
                else:
                    errors = [r["error_km"] for r in lines]
                    rf = [r["rf_rms_hz"] for r in lines]
                e, v = distribution(errors), distribution(rf)
                out.append(
                    dict(
                        group=label,
                        arm=arm,
                        method=method,
                        scheduled=len(errors),
                        published=e["n"],
                        median_km=e["p50"],
                        p95_km=e["p95"],
                        within_1km=thresholds(errors)["1"],
                        within_2km=thresholds(errors)["2"],
                        rf_n=v["n"],
                        median_rf_rms_hz=v["p50"],
                        within_5pct_v5=sum(r["within_5pct"] for r in lines) if lines else None,
                        within_10pct_v5=sum(r["within_10pct"] for r in lines) if lines else None,
                        within_5pct_full=sum(r["within_5pct_full"] for r in lines)
                        if lines
                        else None,
                        within_10pct_full=sum(r["within_10pct_full"] for r in lines)
                        if lines
                        else None,
                    )
                )
    return out


def figures(rows, groups):
    charts = []
    common = (
        "prediction-lock.json",
        "scores.csv",
        "effects.csv",
        "summary.csv",
        "pacing.csv",
        "support.csv",
        "resources.csv",
        "capture-era-v5.csv",
        "overlap-native-lock.json",
        "overlap-parity.json",
    )
    specs = (("all", 2), ("all", 4), ("held6", 2), ("held6", 4), ("raw-overlap", 0))
    captions = {
        "all": "The complete panel includes the timing anchor and direct waveform overlap.",
        "held6": "These six holdouts were chosen by metadata hash.",
        "raw-overlap": "The staggered factor projection uses the frozen raw-replay schedule.",
    }
    for group, budget in specs:
        cases = groups[group]
        tag = f"{group}-{budget}" if budget else group
        name, seal = f"{tag}-chart.jsonl.gz", f"{tag}-figure-lock.json"
        pack(REPORT / name, (r for r in rows if r["id"] in cases))
        modes = (
            (f"lanes{budget}", "full", f"bursts{budget}")
            if budget
            else ("periodic4", "full", "lanes2", "bursts2")
        )
        labels = (
            (f"Full-pass {budget} RF lanes", "Full compact reference", "Count-matched RF bursts")
            if budget
            else (
                "Raw-replay staggered quarter",
                "Full compact reference",
                "Full-pass 2 RF lanes",
                "Count-matched RF bursts",
            )
        )
        save_json(
            REPORT / seal, dict(cases=cases, files={f: _sha(REPORT / f) for f in (name, *common)})
        )
        charts.append(
            dict(
                id=f"frequency-schedule-{tag}",
                method=PFX + modes[0],
                scope="roof",
                cases="sealed",
                title=f"Full-pass {budget} RF lanes and equal-call bursts"
                if budget
                else "Original dual-receiver schedule overlap on DS26-0162",
                caption=(
                    "Original capture factors retain complete radio clocks. Both calibration arms "
                    f"use the installed compact position receiver. {captions[group]}"
                ),
                seal=seal,
                provenance=list(common),
                series=[
                    dict(
                        key=key,
                        label=label,
                        file=name,
                        value=PFX + m,
                        native_field="paired_capture_sha256",
                        match=list(fixed.BINDINGS),
                    )
                    for key, label, m in zip(
                        ("one", "stock", "one_native_factors", "all_visits")[: len(modes)],
                        labels,
                        modes,
                        strict=True,
                    )
                ],
            )
        )
    save_json(REPORT / "figures.json", dict(version=2, charts=charts))


def pacing_figure(pacing, scored):
    import matplotlib.pyplot as plt

    anchor = [r for r in pacing if r["id"] == trial.ANCHOR]
    lookup = {(r["arm"], r["condition"]): r["error_km"] for r in scored if r["id"] == trial.ANCHOR}
    labels = {
        "lanes2": "2 full-pass RF lanes",
        "bursts2": "2-lane count, RF bursts",
        "lanes4": "4 full-pass RF lanes",
        "bursts4": "4-lane count, RF bursts",
        "full": "Full compact input",
    }
    table = [
        dict(row, **{f"{arm}_error_km": lookup[arm, row["condition"]] for arm in ARMS})
        for row in anchor
    ]
    csv_file(REPORT / "frontier.csv", table)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.9), layout="constrained")
    fig.suptitle("DS29-0082 original detector work and measured horizontal error", fontsize=15)
    for mode, label in labels.items():
        rows = [r for r in anchor if r["condition"] == mode]
        (line,) = axes[0].plot(
            [r["cores"] for r in rows],
            [100 * r["completed_by_300_s"] / r["calls"] for r in rows],
            label=label,
            marker=".",
            linestyle="--" if mode.startswith("bursts") else "-",
        )
        for axis, arm in zip(axes[1:], ARMS, strict=True):
            error = lookup[arm, mode]
            if error is not None:
                axis.scatter(rows[0]["detector_cpu_work_s"], error, color=line.get_color(), s=45)
    axes[0].set(
        title="Ideal paced detector queue",
        xlabel="Available worker cores",
        ylabel="Scheduled detector calls finished by 300 s (%)",
        xticks=CORES,
        ylim=(0, 103),
    )
    axes[0].legend(fontsize=8, loc="lower right")
    for axis, title in zip(
        axes[1:], ("Measured position, c = 0", "Measured position, fitted c"), strict=True
    ):
        axis.set(title=title, xlabel="Selected measured detector CPU work (s)", ylabel="Error (km)")
    for axis in axes:
        axis.grid(alpha=0.22)
    fig.savefig(REPORT / "frontier.png", dpi=165)
    fig.savefig(REPORT / "frontier.pdf")
    plt.close(fig)
    names = ("frontier.csv", "frontier.png", "frontier.pdf", "prediction-lock.json")
    save_json(REPORT / "frontier-lock.json", dict(files={n: _sha(REPORT / n) for n in names}))
    save_json(
        REPORT / "stage-figure.json",
        dict(
            id="original-frequency-schedule-frontier",
            version=1,
            seal="frontier-lock.json",
            title="Original detector CPU work and full-pass RF schedule accuracy",
            image="frontier.png",
            csv="frontier.csv",
            boundary="Measured original detector costs and simulated FIFO over the recorded clock",
            sample="DS29-0082 exact selected-visit CPU on five stored-factor position inputs",
            note="Position endpoints are actually fitted. Queue completion transfers each measured "
            "call cost to an ideal core pool. It omits contention, I/O and per-visit guarantees.",
        ),
    )


def overlap_native(work, rows):
    (periodic,) = [r for r in rows if r["id"] == trial.OVERLAP and r["condition"] == "periodic4"]
    raw = trial.scheduled_capture_waveform.REPORT
    archive = sealed(raw, "prediction-lock.json", RAW_PIN)
    measured = gzip.decompress((raw / "native.json.gz").read_bytes())
    source = work / trial.OVERLAP / "periodic4/recording/native.json"
    bound = whole_iq.checked(source, periodic["native_sha256"]).read_bytes()

    def packet_clock(payload):
        doc = json.loads(payload)
        return dict(
            probes=doc["source"]["probes"],
            clock_anchor=doc["clock_anchor"],
            delivery_clocks=doc["delivery_clocks"],
            last_sample_counter=doc["last_sample_counter"],
            excluded_windows=doc["provenance"]["excluded_windows"],
        )

    logic = packet_clock(bound)
    if logic != packet_clock(measured) or archive["files"]["schedule.json"] != trial.OVERLAP_PIN:
        raise ValueError("actual selective waveform kept a different physical observation array")
    name = "native/DS26-0162-periodic4.json.gz"
    write(REPORT / name, gzip.compress(bound, mtime=0))
    save_json(
        REPORT / "overlap-native-lock.json",
        dict(
            id=trial.OVERLAP,
            condition="periodic4",
            native_sha256=periodic["native_sha256"],
            measured_native_sha256=sha256(measured).hexdigest(),
            plan_sha256=_sha(REPORT / "plan.json"),
            raw_prediction_lock_sha256=RAW_PIN,
            physical_sha256=sha256(encoded(logic)).hexdigest(),
            files={name: _sha(REPORT / name)},
        ),
    )


def overlap_control(rows):
    own = sealed(REPORT, "overlap-native-lock.json")
    raw = trial.scheduled_capture_waveform.REPORT
    archive = sealed(raw, "prediction-lock.json", own["raw_prediction_lock_sha256"])
    direct = {
        r["method"]: r
        for r in rows_from(
            whole_iq.checked(raw / "positions.jsonl.gz", archive["files"]["positions.jsonl.gz"])
        )
    }
    if own["plan_sha256"] != _sha(REPORT / "plan.json"):
        raise ValueError("overlap native documentation predates the bound schedule")
    status = []
    for mode, method in (
        ("periodic4", trial.scheduled_capture_waveform.METHOD),
        ("full", "original_capture_all_factors_compact"),
    ):
        (candidate,) = [r for r in rows if r["id"] == trial.OVERLAP and r["condition"] == mode]
        measured = direct[method]
        common = ("id", "paired_capture_sha256", "original_request_sha256", "catalog_sha256")
        location = "scheduled" if mode == "periodic4" else "full"
        name = f"receipts/{location}/recording/request.json"
        request = read(whole_iq.checked(raw / name, archive["files"][name]))["job"]
        if (
            any(candidate[k] != measured[k] for k in common)
            or candidate["tile"]["center"] != measured["tile"]["center"]
            or candidate["tile"]["center"] != request["search_center"]
            or candidate["tile"]["screen"] != request["screen_center"]
        ):
            raise ValueError("raw overlap changed the causal catalogue, clocks or offered tile")
        expected = own["native_sha256"] if mode == "periodic4" else measured["native_sha256"]
        if candidate["native_sha256"] != expected or (
            mode == "periodic4" and measured["native_sha256"] != own["measured_native_sha256"]
        ):
            raise ValueError("raw overlap comparison used a different factor document")
        a, b = candidate["result"], measured["result"]
        pair = a["status"] == b["status"] == "ok"
        status.append(
            dict(
                condition=mode,
                archived_status=a["status"],
                direct_status=b["status"],
                archived_native_sha256=candidate["native_sha256"],
                direct_native_sha256=measured["native_sha256"],
                exact_arms={arm: a["arms"][arm] == b["arms"][arm] for arm in ARMS}
                if pair
                else None,
                exact_frequency_scores={
                    arm: a["metrics"].get(f"{arm}_frequency_score")
                    == b["metrics"].get(f"{arm}_frequency_score")
                    for arm in ARMS
                }
                if pair
                else None,
            )
        )
    save_json(
        REPORT / "overlap-parity.json",
        dict(
            cases=[trial.OVERLAP],
            raw_prediction_lock_sha256=own["raw_prediction_lock_sha256"],
            archived_prediction_lock_sha256=_sha(REPORT / "prediction-lock.json"),
            native_lock_sha256=_sha(REPORT / "overlap-native-lock.json"),
            rows=status,
        ),
    )


def publish(work):
    sealed(REPORT, "prediction-lock.json")
    plan, scheduled = (read(REPORT / name) for name in ("plan.json", "schedule.json"))
    if any(_sha(ROOT / n) != h for n, h in plan["source_sha256"].items()):
        raise ValueError("prospective method source altered after launch")
    rows = rows_from(REPORT / "positions.jsonl.gz")
    _, timing = trial.timing_inputs()
    support, resource, pacing = verify(work, plan, rows, scheduled, timing)
    _, records = held_references(None, plan["cases"])
    refs = {r["id"]: r for r in records}
    values, effects = scores(rows, refs, plan)
    groups = {
        "all": plan["cases"],
        "held6": plan["held"],
        "anchor": [trial.ANCHOR],
        "raw-overlap": [trial.OVERLAP],
    }
    full = {r["id"]: r for r in rows if r["condition"] == "full"}
    for name, data in (
        ("support.csv", support),
        ("resources.csv", resource),
        ("pacing.csv", pacing),
        ("scores.csv", values),
        ("effects.csv", effects),
        ("summary.csv", summary(values, refs, groups)),
        ("capture-era-v5.csv", original_rows(refs, full)),
    ):
        csv_file(REPORT / name, data)
    overlap_native(work, rows)
    overlap_control(rows)
    pacing_figure(pacing, values)
    figures(rows, groups)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.work)
    if args.plot:
        screening_figures.generate(args.plot, evidence=REPORT)
