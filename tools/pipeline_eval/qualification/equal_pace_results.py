"""Seal actual retained packets and score both measured equal-pace positions."""

import argparse
import gzip
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import adaptive_arrival_position as emitted
from . import arrival_queue as pace
from . import bracketed_position, screening_figures
from . import equal_pace as trial
from .arrival_queue_results import observed, terminal, timing_ms
from .bracketed_position_results import service_result
from .diagnostic_whole_results import PHYSICAL_KEYS
from .fifth_completion_results import PRIMARY, STOCK_LOCK
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

MODES = (trial.FOUR, trial.MIXED)
METHOD = {role: "equal_pace_" + role.replace("-", "_") for role in MODES}
POS = "positions.jsonl.gz"
LOCK = "prediction-lock.json"


def retained_packets(rows, stock, fifth):
    kept = []
    events = []
    for row in rows:
        if row["outcome"] != "emitted":
            continue
        ident, lane = row["visit"], row["fifth_lane"]
        original, optional = stock[ident], fifth[ident]
        if (lane is not None and (type(lane) is not int or lane not in (0, 1))) or (
            row["status"] != "processed" or not trial.comparable(original, optional)
        ):
            raise ValueError("retained row lacks identical physical packet metadata")
        probes = [
            optional["probes"][rx] if rx == lane else p for rx, p in enumerate(original["probes"])
        ]
        if (
            len(probes) != 2
            or pace.fingerprint(dict(original, probes=probes)) != row["full_visit_sha256"]
        ):
            raise ValueError("retained packet cannot recreate its proven emission hash")
        kept.extend(probes)
        events.append(ident)
    return kept, events


def startup_summary(rows, ident, role):
    live = [r for r in rows if r["outcome"] == "emitted"]
    return [
        dict(
            id=ident,
            mode=role,
            phase=phase,
            emitted=len(batch),
            **timing_ms((r["native_wall_ns"] for r in batch), "native_wall"),
            **timing_ms((r["native_cpu_ns"] for r in batch), "native_cpu"),
            **timing_ms((r["emitted_ns"] - r["arrival_ns"] for r in batch), "age"),
        )
        for phase, batch in (("first 32 emissions", live[:32]), ("later emissions", live[32:]))
    ]


def fit(work, out):
    if (out / LOCK).exists():
        raise FileExistsError("the equal-pace predictions already have a terminal seal")
    plan = pace.plan(work, out)
    ident = plan["case"]
    spec = plan["cases"][ident]
    (doc, stock, stock_logical), (_, fifth, fifth_logical) = trial.references(ident)
    if plan["raw_logical_sha256"] != [stock_logical, fifth_logical]:
        raise ValueError("packet materialization uses different reference inputs from paced replay")
    release = whole_iq.read(trial.BASE / "fifth-completion/source-lock.json")
    bracketed_position.check_release(release)
    case, request = whole_iq.binding(ident)
    if case != spec["capture"]["case"]:
        raise ValueError("compact fit binds a different original recording or request")
    files = ("PROTOCOL.md", "source-lock.json", "preflight-source-lock.json", "preflight-plan.json")
    failed = sorted(
        str(path.relative_to(out)) for path in (out / "setup-failed").rglob("*") if path.is_file()
    )
    jobs, timing, startup, names = [], [], [], [*files, *failed]
    for role, cpu in zip(MODES, plan["cpus"], strict=True):
        raw = work / ident / role
        bound = spec["modes"][role]
        events = pace.readgz(whole_iq.checked(out / bound["events"], bound["sha256"]))
        if (raw / "visits.jsonl").is_file():
            trace, witness, state, complete = terminal(raw, events)
        else:
            trace, witness, complete = [], None, False
            state = whole_iq.read(raw / "service.json")
            whole_iq.checked(raw / "service.log", state["log_sha256"])
        stem = f"raw/{role}"
        artifacts = {
            f"{stem}/trace.json.gz": trace,
            f"{stem}/service.json": state,
            f"{stem}/witness.json": witness,
        }
        for name, data in artifacts.items():
            if name.endswith(".gz"):
                pace.writegz(out / name, data)
            else:
                save_json(out / name, data)
        log = f"{stem}/service.log"
        write(out / log, (raw / "service.log").read_bytes())
        summary = observed(trace, witness, ident, role, complete, events)
        summary.update(
            host_service_result=state["systemd"].get("Result"),
            fraction_valid_emitted=summary["native_packets_emitted"] / summary["valid_slots"],
            calls_within_20ms=sum(
                r.get("native_wall_ns", 0) <= 20_000_000 for r in trace if r["outcome"] == "emitted"
            ),
            packets_with_age_20ms=sum(
                r.get("emitted_ns", 0) - r["arrival_ns"] <= 20_000_000
                for r in trace
                if r["outcome"] == "emitted"
            ),
        )
        timing.append(summary)
        startup.extend(startup_summary(trace, ident, role))
        names.extend((*artifacts, log, bound["events"]))
        probes, visits = retained_packets(trace, stock, fifth) if complete else ([], [])
        row = dict(
            id=ident,
            method=METHOD[role],
            paced_mode=role,
            mode="matched-tile",
            cpu=cpu,
            cohort="equal pace",
            tile=case["regions"][0],
            catalog_sha256=case["catalog"]["sha256"],
            original_request_sha256=case["request"]["sha256"],
            paired_capture_sha256=case["native"]["sha256"],
            native_sha256=None,
            raw_verified=complete,
            raw_trace_sha256=_sha(out / f"{stem}/trace.json.gz"),
            emitted_visits=visits,
        )
        folder = work / ident / f"position-{role}"
        folder.mkdir(exist_ok=False)
        if probes:
            lineage = pace.recording_to_v5.digest([role, witness["output_sha256"], visits])
            native = dict(
                doc,
                source=dict(doc["source"], probes=probes, analysis_manifest_sha256=lineage),
                provenance=dict(
                    doc["provenance"],
                    run_id="replay-" + lineage[7:39],
                    detector_sha256="sha256:" + plan["assets"][role]["sha256"],
                    processed_windows=len(visits),
                    scope="Equal-pace emissions verified against complete raw branches",
                ),
            )
            row["native_sha256"], row["position_request_sha256"] = emitted.position_input(
                folder, case, request, release, native, cpu
            )
            native_name = f"native/{role}/{ident}.json.gz"
            write(out / native_name, gzip.compress((folder / "native.json").read_bytes(), mtime=0))
            names.append(native_name)
            row["positive_probes"] = sum(
                any(c["passed_fractional_margin_gate"] for c in p["candidates"]) for p in probes
            )
        else:
            reason = "no retained valid emissions" if complete else "paced service incomplete"
            status = "withheld" if complete else "unavailable"
            row["result"] = emitted.empty_result(status, reason)
        jobs.append((folder, row))
    save_json(
        out / "position-input-lock.json",
        dict(
            cases=[ident],
            attempts=[row for _, row in jobs],
            files={n: _sha(out / n) for n in names},
            materializer_sha256=_sha(Path(__file__)),
        ),
    )

    def execute(job):
        folder, row = job
        if row["native_sha256"] is None:
            return row, []
        cpu = row["cpu"]
        whole_iq.checked(folder / "native.json", row["native_sha256"])
        whole_iq.checked(folder / "request.json", row["position_request_sha256"])
        bracketed_position.launch_case(folder, cpu)
        result, report = service_result(folder, cpu)
        log = f"position/{row['paced_mode']}.service.log"
        write(out / log, (folder / "service.log").read_bytes())
        return dict(row, result=result, position_resources=report), [log]

    with ThreadPoolExecutor(max_workers=2) as pool:
        fitted = list(pool.map(execute, jobs))
    pack(out / POS, [row for row, _ in fitted])
    csv_file(out / "timing.csv", timing)
    csv_file(out / "startup.csv", startup)
    names.extend([POS, "position-input-lock.json", "timing.csv", "startup.csv"])
    names.extend(log for _, logs in fitted for log in logs)
    save_json(out / LOCK, dict(cases=[ident], files={n: _sha(out / n) for n in names}))


def stage_figure(out):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig, (outcomes, age) = plt.subplots(1, 2, figsize=(10, 4.2))
    colors = {trial.FOUR: "#285777", trial.MIXED: "#b03f32"}
    labels = {trial.FOUR: "Fused four", trial.MIXED: "Staggered fifth"}
    groups = ("emitted", "queue_drop", "invalid_capture")
    for j, role in enumerate(MODES):
        trace = pace.readgz(out / f"raw/{role}/trace.json.gz")
        counts = [sum(r["outcome"] == group for r in trace) for group in groups]
        outcomes.bar(
            [idx + (j - 0.5) * 0.33 for idx in range(3)],
            counts,
            width=0.33,
            color=colors[role],
            label=labels[role],
        )
        seen = sorted(
            (r["emitted_ns"] - r["arrival_ns"]) / 1e6 for r in trace if r["outcome"] == "emitted"
        )
        if seen:
            age.plot(seen, [(i + 1) / len(seen) for i in range(len(seen))], color=colors[role])
    outcomes.set(
        xticks=list(range(3)),
        xticklabels=["Emitted", "Queue drop", "Invalid"],
        ylabel="Count of delivered visits",
    )
    outcomes.legend(frameon=False)
    age.axvline(20, color="#555555", linestyle="--", lw=1, label="20 ms")
    age.legend(frameon=False, loc="lower right")
    age.set(
        xscale="log",
        ylim=(0, 1.01),
        xlabel="Arrival-to-emission age (ms)",
        ylabel="Fraction of emitted visits",
    )
    fig.suptitle("Matched recorded-IQ delivery on DS29-0174")
    fig.tight_layout()
    image, stat, lock = "timing.png", "timing.csv", "stage-figure-lock.json"
    fig.savefig(out / image, dpi=160)
    plt.close(fig)
    save_json(out / lock, dict(files={n: _sha(out / n) for n in (image, stat)}))
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="equal-pace-staggered-host",
            title="Fused four and staggered arrival outcomes",
            sample="One whole saved-IQ roof recording, CPU22/23 and its captured arrival clock",
            boundary="Actual host replay with one waiting visit, 512 MiB cap and zero swap",
            note="Age starts at the recorded arrival time and conditions on emissions. Drops and "
            "invalid captures appear in the adjacent complete visit inventory.",
            seal=lock,
            image=image,
            csv=stat,
        ),
    )


def score(out):
    prediction = sealed(out, LOCK)
    _, refs = held_references(None, prediction["cases"])
    candidate = rows_from(out / POS)
    scores = geographic(candidate, {r["id"]: r for r in refs})
    csv_file(out / "scores.csv", scores)
    # Keep earlier unpaced measurements separate from the equal-pace observations.
    closed = trial.SCREEN / "track-recovery/wide-roster"
    old = sealed(closed, "prediction-lock.json", STOCK_LOCK)
    old_rows = [
        r
        for r in rows_from(closed / POS)
        if r["id"] in prediction["cases"] and r["method"] == PRIMARY
    ]
    (case,) = prediction["cases"]
    (prior,) = old_rows
    named = dict(
        prior, cohort="archived unpaced", paired_capture_sha256=prior["capture_era_native_sha256"]
    )
    if any(row[k] != named[k] for row in candidate for k in PHYSICAL_KEYS):
        raise ValueError("archived unpaced endpoints used a different original input")
    (old_resource,) = [
        r for r in whole_iq.read(closed / "attempts.json") if r["id"] == case and r["primary"]
    ]
    timing_keys = (
        "wall_s",
        "cpu_s",
        "raw_s",
        "position_s",
        "dual_calls",
        "within_20ms",
        "cpu_pins",
    )
    historic = [
        dict(r, **{k: old_resource[k] for k in timing_keys})
        for r in geographic([named], {r["id"]: r for r in refs})
    ]
    csv_file(out / "archived-unpaced.csv", historic)
    save_json(out / "archived-stock-authority.json", dict(files=old["files"], sha256=STOCK_LOCK))
    files = [
        LOCK,
        "source-lock.json",
        "scores.csv",
        "timing.csv",
        "startup.csv",
        "archived-stock-authority.json",
        "archived-unpaced.csv",
    ]
    save_json(
        out / "figure-lock.json",
        dict(cases=prediction["cases"], files={n: _sha(out / n) for n in [POS, *files]}),
    )
    series = [
        dict(
            key=key,
            file=POS,
            value=METHOD[role],
            label=label,
            native_field="paired_capture_sha256",
            **({"match": PHYSICAL_KEYS} if key == "stock" else {}),
        )
        for key, role, label in (
            ("one", trial.MIXED, "Staggered fifth"),
            ("stock", trial.FOUR, "Fused four"),
        )
    ]
    save_json(
        out / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="equal-pace-staggered",
                    method=METHOD[trial.MIXED],
                    cases="sealed",
                    scope="roof",
                    title="Staggered fifth and fused four at identical archived IQ delivery pace",
                    caption="One roof recording. CPU22 and CPU23, one waiting visit and the same "
                    "delivery clock. Both arms fit actual retained emissions. The four original "
                    "v5 options use their capture-era detector factors.",
                    provenance=files,
                    seal="figure-lock.json",
                    series=series,
                )
            ],
        ),
    )
    screening_figures.generate(out / "charts", evidence=out)
    stage_figure(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fit", "score"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    if args.mode == "fit":
        fit(args.work, trial.REPORT)
    else:
        score(trial.REPORT)
