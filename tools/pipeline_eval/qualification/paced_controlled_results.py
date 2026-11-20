"""Seal all measured receiver clocks and refit their exact retained outputs."""

import argparse
import csv
import gzip
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import adaptive_arrival_position as emitted
from . import arrival_queue as pace
from . import bracketed_position, screening_figures
from . import equal_pace as prior
from . import paced_controlled as trial
from .arrival_queue_results import observed, terminal, timing_ms
from .bracketed_position_results import service_result
from .diagnostic_whole_results import PHYSICAL_KEYS
from .equal_pace_results import retained_packets, startup_summary
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

LOCK = "prediction-lock.json"
RAW_LOCK = "raw-prediction-lock.json"
POS = "positions.jsonl.gz"
OLD = "0ba006d89ad261a278c3f028e9d8ffea378fd413a9f0eaf86874a217938c715a"
LABELS = {prior.FOUR: "Fused four", prior.MIXED: "Staggered fifth"}


def method(pair, role):
    return f"paced_controlled_{pair.lower()}_{role.replace('-', '_')}"


def summarize(rows, witness, service, ready, events, pair, role, complete, external_charge):
    result = observed(rows, witness, trial.CASE, role, complete, events)
    if witness and (witness["compressed_chunks"] or witness["compressed_bytes"]):
        raise ValueError("individual receiver replay accessed compressed archive payloads")
    start, end = (external_charge[mark] for mark in ("start", "end"))
    for mark in (start, end):
        if (
            mark["memory.swap.current"]
            or mark["memory.swap.max"]
            or mark["memory.events.oom_kill"]
            or mark["memory.stat.shmem"] < ready["bytes"]
            or mark["cgroup"] != ready["end"]["cgroup"]
            or (witness and mark["cgroup"] == witness["start"]["cgroup"])
        ):
            raise ValueError("source was not measured under its own distinct resident cap")
    live = [r for r in rows if r["outcome"] == "emitted"]
    return dict(
        result,
        pair=pair,
        method=method(pair, role),
        live_service_result=service["systemd"].get("Result"),
        live_service_wall_s=service.get("service_wall_s"),
        valid_fraction_emitted=len(live) / result["valid_slots"],
        calls_within_20ms=sum(r["native_wall_ns"] <= 20_000_000 for r in live),
        emissions_with_age_20ms=sum(r["emitted_ns"] - r["arrival_ns"] <= 20_000_000 for r in live),
        source_start_bytes=start["memory.current"],
        source_end_bytes=end["memory.current"],
        source_shmem_bytes=end["memory.stat.shmem"],
        source_peak_bytes=end["memory.peak"],
        source_during_receiver_cpu_s=(end["cpu.stat.usage_usec"] - start["cpu.stat.usage_usec"])
        / 1e6,
        receiver_swap_bytes=witness["end"]["memory.swap.current"] if witness else None,
    )


def archive_raw(work, out):
    if (out / RAW_LOCK).exists():
        raise FileExistsError("raw controlled outcomes have already been sealed")
    plan = trial.plan(work)
    spec = plan["cases"][trial.CASE]
    ready = whole_iq.read(whole_iq.checked(out / "ready.json", plan["source_ready_sha256"]))
    timing, startup = [], []
    files = [
        "source-lock.json",
        "source-stage-lock.json",
        "PROTOCOL.md",
        "ready.json",
        "members.json.gz",
        "source-terminal.json",
    ]
    files.extend(bound["events"] for bound in spec["modes"].values())
    for pair, role, attempt in trial.work_paths(work):
        parent = f"raw/{pair}/{role}"
        branch = spec["modes"][role]
        events = pace.readgz(whole_iq.checked(out / branch["events"], branch["sha256"]))
        if (attempt / "visits.jsonl").is_file():
            rows, witness, service, complete = terminal(attempt, events)
        else:
            rows, witness, complete = [], None, False
            service = whole_iq.read(attempt / "service.json")
            whole_iq.checked(attempt / "service.log", service["log_sha256"])
        names = dict(
            plan=whole_iq.read(attempt / "plan.json"),
            witness=witness,
            service=service,
            outcome=dict(complete=complete, rows=len(rows)),
        )
        for name, value in names.items():
            save_json(out / f"{parent}/{name}.json", value)
        pace.writegz(out / f"{parent}/trace.json.gz", rows)
        write(out / f"{parent}/service.log", (attempt / "service.log").read_bytes())
        charge = whole_iq.read(out / f"{parent}/source-charge.json")
        timing.append(
            summarize(rows, witness, service, ready, events, pair, role, complete, charge)
        )
        startup.extend(dict(r, pair=pair) for r in startup_summary(rows, trial.CASE, role))
        extensions = [name + ".json" for name in (*names, "source-charge")]
        files.extend(f"{parent}/{name}" for name in [*extensions, "trace.json.gz", "service.log"])
    csv_file(out / "timing.csv", timing)
    csv_file(out / "startup.csv", startup)
    files.extend(("timing.csv", "startup.csv"))
    save_json(out / RAW_LOCK, dict(cases=[trial.CASE], files={n: _sha(out / n) for n in files}))


def position_input(work, out, plan, pair, role, references, case, original, release, cpu):
    doc, stock, fifth = references
    anchor = out / f"raw/{pair}/{role}"
    complete = whole_iq.read(anchor / "outcome.json")["complete"]
    witness = whole_iq.read(anchor / "witness.json")
    trace = anchor / "trace.json.gz"
    probes, visits = retained_packets(pace.readgz(trace), stock, fifth) if complete else ([], [])
    row = dict(
        id=trial.CASE,
        method=method(pair, role),
        mode="matched-tile",
        cohort=pair,
        cpu=cpu,
        paced_mode=role,
        tile=case["regions"][0],
        catalog_sha256=case["catalog"]["sha256"],
        original_request_sha256=case["request"]["sha256"],
        paired_capture_sha256=case["native"]["sha256"],
        native_sha256=None,
        raw_verified=complete,
        raw_trace_sha256=_sha(trace),
        emitted_visits=visits,
    )
    folder = work / pair / trial.CASE / f"position-{role}"
    folder.mkdir(exist_ok=False)
    assets = []
    if probes:
        lineage = pace.recording_to_v5.digest([pair, role, witness["output_sha256"], visits])
        derived = dict(
            doc,
            source=dict(doc["source"], probes=probes, analysis_manifest_sha256=lineage),
            provenance=dict(
                doc["provenance"],
                run_id="replay-" + lineage[7:39],
                detector_sha256="sha256:" + plan["assets"][role]["sha256"],
                processed_windows=len(visits),
                scope="Actual verified emissions from local IQ pace",
            ),
        )
        row["native_sha256"], row["position_request_sha256"] = emitted.position_input(
            folder, case, original, release, derived, cpu
        )
        native = f"native/{pair}/{role}.json.gz"
        write(out / native, gzip.compress((folder / "native.json").read_bytes(), mtime=0))
        assets.append(native)
        row["positive_probes"] = sum(
            any(c["passed_fractional_margin_gate"] for c in probe["candidates"]) for probe in probes
        )
    else:
        reason = "no emitted visits" if complete else "incomplete verified IQ clock"
        row["result"] = emitted.empty_result("withheld" if complete else "unavailable", reason)
    return folder, row, assets


def fit(work, out):
    if (out / LOCK).exists():
        raise FileExistsError("controlled fit already sealed")
    prior_raw = sealed(out, RAW_LOCK)
    plan = trial.plan(work)
    case, original = whole_iq.binding(trial.CASE)
    if case != plan["cases"][trial.CASE]["capture"]["case"]:
        raise ValueError("position solver would use a different original recording or region")
    release = whole_iq.read(prior.BASE / "fifth-completion/source-lock.json")
    bracketed_position.check_release(release)
    (doc, stock, old_logical), (_, fifth, new_logical) = prior.references(trial.CASE)
    if [old_logical, new_logical] != plan["raw_logical_sha256"]:
        raise ValueError("complete detector factors changed since exact-packet freeze")
    refs = doc, stock, fifth
    jobs = [
        position_input(
            work,
            out,
            plan,
            pair,
            role,
            refs,
            case,
            original,
            release,
            plan["cpus"][0 if role == prior.FOUR else 1],
        )
        for pair, role in trial.ORDER
    ]
    files = [name for _, _, assets in jobs for name in assets]
    save_json(
        out / "position-input-lock.json",
        dict(
            cases=[trial.CASE],
            jobs=[row for _, row, _ in jobs],
            raw_lock_sha256=_sha(out / RAW_LOCK),
            files={n: _sha(out / n) for n in files},
            materializer_sha256=_sha(Path(__file__)),
        ),
    )

    def lane(cpu):
        answers = []
        for folder, row, _ in jobs:
            if row["cpu"] != cpu:
                continue
            if row["native_sha256"] is None:
                answers.append((row, []))
                continue
            whole_iq.checked(folder / "native.json", row["native_sha256"])
            whole_iq.checked(folder / "request.json", row["position_request_sha256"])
            bracketed_position.launch_case(folder, cpu)
            result, resource = service_result(folder, cpu)
            name = f"position/{row['cohort']}-{row['paced_mode']}.service.log"
            write(out / name, (folder / "service.log").read_bytes())
            answers.append((dict(row, result=result, position_resources=resource), [name]))
        return answers

    with ThreadPoolExecutor(max_workers=2) as pool:
        pairs = [result for batch in pool.map(lane, plan["cpus"]) for result in batch]
    by_method = {r["method"]: r for r, _ in pairs}
    pack(out / POS, [by_method[method(pair, role)] for pair, role in trial.ORDER])
    files.extend(name for _, assets in pairs for name in assets)
    files.extend((POS, RAW_LOCK, "position-input-lock.json"))
    save_json(
        out / LOCK,
        dict(cases=[trial.CASE], files=prior_raw["files"] | {n: _sha(out / n) for n in files}),
    )


def stage_figure(out, old):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig, (count, jitter) = plt.subplots(1, 2, figsize=(11.4, 4.6))
    colours = {prior.FOUR: "#285777", prior.MIXED: "#b03f32"}
    clocks = [
        (f"{pair} · {LABELS[role]}", role, pace.readgz(out / f"raw/{pair}/{role}/trace.json.gz"))
        for pair, role in trial.ORDER
    ]
    for i, (_, role, rows) in enumerate(clocks):
        totals = [
            sum(r["outcome"] == k for r in rows)
            for k in ("emitted", "queue_drop", "invalid_capture")
        ]
        count.barh(i, totals[0], color=colours[role])
        count.barh(i, totals[1], left=totals[0], color="#9b9b9b")
        count.barh(i, totals[2], left=sum(totals[:2]), color="#222222")
        jitter.plot(i, old[role], marker="x", color=colours[role], alpha=0.65, linestyle="none")
        if rows:
            delay = timing_ms((r["released_ns"] - r["arrival_ns"] for r in rows), "release")
            p95 = delay["release_p95_ms"]
            jitter.plot(i, p95, marker="o", color=colours[role], linestyle="none")
    count.set(
        yticks=list(range(4)),
        yticklabels=[label for label, _, _ in clocks],
        xlabel="Physical visits · colour emitted, grey dropped, black invalid",
    )
    count.invert_yaxis()
    jitter.set(
        yscale="log",
        ylabel="Release delay P95 (ms)",
        xticks=list(range(4)),
        xticklabels=[pair for pair, _ in trial.ORDER],
    )
    jitter.plot([], [], "ko", label="Predecoded local IQ")
    jitter.plot([], [], "kx", label="Previous QNAP-fed observation")
    jitter.legend(frameon=False)
    fig.suptitle("Recorded receiver pace with an independently charged local IQ source")
    fig.tight_layout()
    image, stat, lock = "pace.png", "timing.csv", "stage-figure-lock.json"
    fig.savefig(out / image, dpi=160)
    plt.close(fig)
    save_json(out / lock, dict(files={n: _sha(out / n) for n in (image, stat, "prior-timing.csv")}))
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="predecoded-live-pace",
            title="Predecoded-IQ host pacing and delivery jitter",
            sample="DS29-0174, four real five-minute clocks in counterbalanced orders",
            boundary="Common CPUs 22/23 and one waiting slot. Separate source and receiver caps.",
            note="The earlier QNAP-fed observations use the same recording. The dots show "
            "measured P95 release delays for the predecoded source.",
            seal=lock,
            image=image,
            csv=stat,
        ),
    )


def score(out):
    prediction = sealed(out, LOCK)
    ids = prediction["cases"]
    _, refs = held_references(None, ids)
    rows = rows_from(out / POS)
    csv_file(out / "scores.csv", geographic(rows, {r["id"]: r for r in refs}))
    previous = sealed(prior.REPORT, LOCK, OLD)
    name = "timing.csv"
    write(
        out / "prior-timing.csv",
        whole_iq.checked(prior.REPORT / name, previous["files"][name]).read_bytes(),
    )
    with (out / "prior-timing.csv").open() as table:
        old = {r["mode"]: float(r["release_delay_p95_ms"]) for r in csv.DictReader(table)}
    common = [LOCK, RAW_LOCK, "source-lock.json", "scores.csv", "timing.csv", "prior-timing.csv"]
    specs = []
    for pair in ("BA", "AB"):
        figure = f"{pair.lower()}-figure-lock.json"
        save_json(out / figure, dict(cases=ids, files={n: _sha(out / n) for n in [POS, *common]}))
        specs.append(
            dict(
                id=f"predecoded-live-pace-{pair.lower()}",
                method=method(pair, prior.MIXED),
                title=f"Local IQ delivery, {pair} receiver order",
                scope="roof",
                cases="sealed",
                caption="DS29-0174, CPU22/23, one waiting visit and the exact recorded clock. "
                "Both c arms fit each actual emission set against the original four v5 options.",
                seal=figure,
                provenance=common,
                series=[
                    dict(
                        key=key,
                        file=POS,
                        value=method(pair, role),
                        label=LABELS[role],
                        native_field="paired_capture_sha256",
                        **({"match": PHYSICAL_KEYS} if key == "stock" else {}),
                    )
                    for key, role in (("one", prior.MIXED), ("stock", prior.FOUR))
                ],
            )
        )
    save_json(out / "figures.json", dict(version=2, charts=specs))
    screening_figures.generate(out / "charts", evidence=out)
    stage_figure(out, old)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("raw", "fit", "score"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    if args.action == "score":
        score(trial.REPORT)
    else:
        {"raw": archive_raw, "fit": fit}[args.action](args.work, trial.REPORT)
