"""Publish matched paced gate outcomes and actual compact positions."""

import argparse
import gzip
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..variants.negative_rescue import positive
from . import adaptive_arrival_position as emitted
from . import arrival_queue as pace
from . import bracketed_position, screening_figures
from . import paced_hit as trial
from .arrival_queue_results import observed, terminal, timing_ms
from .bracketed_position_results import service_result
from .diagnostic_whole_results import PHYSICAL_KEYS
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .paced_controlled_arrival_audit import summarize as arrival_parts
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

POS = "positions.jsonl.gz"
LOCK = "prediction-lock.json"
METHOD = {trial.DUAL: "paced_hit_stock_dual", trial.HIT: "paced_hit_conditional"}
LABEL = {trial.DUAL: "Stock dual", trial.HIT: "Partner on hit"}


def observed_factors(rows, stock, role):
    probes, kept = [], []
    counts = dict(primary_hits=0, omitted_partner_calls=0, omitted_positive_partner_probes=0)
    for row in rows:
        if row["outcome"] != "emitted":
            continue
        visit, primary = row["visit"], row["primary_receiver"]
        if type(primary) is not int or primary not in (0, 1):
            raise ValueError("emitted window has no valid physical primary receiver")
        original = stock[visit]
        projected, did_hit = trial.projection(original, primary)
        if did_hit is not row["primary_hit"]:
            raise ValueError("emitted window changed its exact primary hit decision")
        raw = projected if role == trial.HIT else original
        required = 1 + did_hit if role == trial.HIT else 2
        if pace.fingerprint(raw) != row["full_visit_sha256"] or required != row["measured_lanes"]:
            raise ValueError("retained probe body or conditional native call count changed")
        counts["primary_hits"] += did_hit
        if required == 1:
            counts["omitted_partner_calls"] += 1
            counts["omitted_positive_partner_probes"] += positive(original["probes"][1 - primary])
        probes.extend(raw["probes"])
        kept.append(visit)
    counts.update(
        native_lane_calls=2 * len(kept) - counts["omitted_partner_calls"],
        positive_probes=sum(map(positive, probes)),
    )
    return probes, kept, counts


def measured_raw(out, attempt, role, events):
    if (attempt / "visits.jsonl").is_file():
        rows, witness, service, complete = terminal(attempt, events)
    else:
        rows, witness, complete = [], None, False
        service = whole_iq.read(attempt / "service.json")
        whole_iq.checked(attempt / "service.log", service["log_sha256"])
    parent = f"raw/{role}"
    charge = whole_iq.read(out / f"{parent}/source-charge.json")
    start, end = (charge[k] for k in ("start", "end"))
    single = witness["end"]["cpus"] if witness else []
    if witness and (
        witness["compressed_chunks"]
        or witness["compressed_bytes"]
        or single != [trial.MAIN]
        or witness["start"]["cpus"] != single
        or witness["end"]["memory.swap.current"]
        or start["cgroup"] == witness["end"]["cgroup"]
    ):
        raise ValueError("receiver ran outside the frozen single-worker and staging boundary")
    names = [
        f"{parent}/{n}"
        for n in (
            "trace.json.gz",
            "service.json",
            "witness.json",
            "service.log",
            "source-charge.json",
        )
    ]
    pace.writegz(out / names[0], rows)
    save_json(out / names[1], service)
    save_json(out / names[2], witness)
    write(out / names[3], (attempt / "service.log").read_bytes())
    summary = observed(rows, witness, trial.CASE, role, complete, events)
    live = [r for r in rows if r["outcome"] == "emitted"]
    summary.update(
        valid_fraction_emitted=len(live) / summary["valid_slots"],
        calls_within_20ms=sum(r["native_wall_ns"] <= 20_000_000 for r in live),
        emissions_with_age_20ms=sum(r["emitted_ns"] - r["arrival_ns"] <= 20_000_000 for r in live),
        manager_wall_s=service.get("service_wall_s"),
        source_peak_bytes=end["memory.peak"],
        source_current_bytes=end["memory.current"],
        source_during_receiver_cpu_s=(end["cpu.stat.usage_usec"] - start["cpu.stat.usage_usec"])
        / 1e6,
        receiver_swap_current_bytes=witness["end"]["memory.swap.current"] if witness else None,
    )
    return rows, witness, complete, names, summary


def fit(work, out):
    if (out / LOCK).exists():
        raise FileExistsError("direct partner-on-hit measurements already sealed")
    plan = pace.plan(work, out)
    spec = plan["cases"][trial.CASE]
    case, original = whole_iq.binding(trial.CASE)
    doc, stock, logical = trial.reference()
    if logical != plan["stock_logical_sha256"] or case != spec["capture"]["case"]:
        raise ValueError("compact input provision differs from frozen physical authority")
    release = whole_iq.read(trial.old.BASE / "fifth-completion/source-lock.json")
    bracketed_position.check_release(release)
    traces, timing, arrival, jobs = {}, [], [], []
    files = [
        "PROTOCOL.md",
        "detector-lock.json",
        "source-lock.json",
        "source-stage-lock.json",
        "ready.json",
        "members.json.gz",
        "preflight.json",
        "source-terminal.json",
    ]
    for role, cpu in zip(trial.ORDER, plan["cpus"], strict=True):
        event = spec["modes"][role]
        events = pace.readgz(whole_iq.checked(out / event["events"], event["sha256"]))
        attempt = work / trial.CASE / role
        rows, witness, complete, raw_names, summary = measured_raw(out, attempt, role, events)
        traces[role] = rows
        probes, visits, support = observed_factors(rows, stock, role)
        summary.update(support)
        timing.append(summary)
        arrival.append(dict(mode=role, **arrival_parts(rows)))
        files.extend([*raw_names, event["events"]])
        row = dict(
            id=trial.CASE,
            method=METHOD[role],
            mode="matched-tile",
            cohort="one-worker pace",
            role=role,
            cpu=cpu,
            raw_verified=complete,
            emitted_visits=visits,
            tile=case["regions"][0],
            catalog_sha256=case["catalog"]["sha256"],
            original_request_sha256=case["request"]["sha256"],
            native_sha256=None,
            paired_capture_sha256=case["native"]["sha256"],
            raw_trace_sha256=_sha(out / raw_names[0]),
            **support,
        )
        folder = work / trial.CASE / f"position-{role}"
        folder.mkdir(exist_ok=False)
        if complete and probes:
            lineage = pace.recording_to_v5.digest([role, witness["output_sha256"], visits])
            material = dict(
                doc,
                source=dict(doc["source"], probes=probes, analysis_manifest_sha256=lineage),
                provenance=dict(
                    doc["provenance"],
                    processed_windows=len(visits),
                    run_id="replay-" + lineage[7:39],
                    scope="Verified single-worker pace",
                ),
            )
            row["native_sha256"], row["position_request_sha256"] = emitted.position_input(
                folder, case, original, release, material, cpu
            )
            name = f"native/{role}/{trial.CASE}.json.gz"
            write(out / name, gzip.compress((folder / "native.json").read_bytes(), mtime=0))
            files.append(name)
        else:
            reason = "no emitted visits" if complete else "incomplete original-arrival replay"
            row["result"] = emitted.empty_result("withheld" if complete else "unavailable", reason)
        jobs.append((folder, row))
    csv_file(out / "timing.csv", timing)
    csv_file(out / "arrival-decomposition.csv", arrival)
    common = {
        role: {r["visit"]: r for r in rows if r["outcome"] == "emitted"}
        for role, rows in traces.items()
    }
    d, h = (common[role] for role in trial.ORDER)
    joint = sorted(d.keys() & h.keys())
    _, _, dual_support = observed_factors([d[i] for i in joint], stock, trial.DUAL)
    _, _, hit_support = observed_factors([h[i] for i in joint], stock, trial.HIT)
    save_json(
        out / "common-cost.json",
        dict(
            same_emitted=len(joint),
            dual_only=len(d) - len(joint),
            hit_only=len(h) - len(joint),
            dual_positive_probes=dual_support["positive_probes"],
            hit_positive_probes=hit_support["positive_probes"],
            **timing_ms(
                (h[i]["native_cpu_ns"] - d[i]["native_cpu_ns"] for i in joint), "hit_minus_dual_cpu"
            ),
            **timing_ms(
                (h[i]["native_wall_ns"] - d[i]["native_wall_ns"] for i in joint),
                "hit_minus_dual_wall",
            ),
        ),
    )
    files.extend(("timing.csv", "arrival-decomposition.csv", "common-cost.json"))
    save_json(
        out / "position-input-lock.json",
        dict(
            cases=[trial.CASE],
            jobs=[r for _, r in jobs],
            files={n: _sha(out / n) for n in files},
            exporter_sha256=_sha(Path(__file__)),
        ),
    )

    def solve(job):
        folder, row = job
        if row["native_sha256"] is None:
            return row, []
        whole_iq.checked(folder / "native.json", row["native_sha256"])
        whole_iq.checked(folder / "request.json", row["position_request_sha256"])
        bracketed_position.launch_case(folder, row["cpu"])
        result, resource = service_result(folder, row["cpu"])
        name = f"position/{row['role']}.service.log"
        write(out / name, (folder / "service.log").read_bytes())
        return dict(row, result=result, position_resources=resource), [name]

    with ThreadPoolExecutor(max_workers=2) as pool:
        positions = list(pool.map(solve, jobs))
    pack(out / POS, [row for row, _ in positions])
    files.extend([POS, "position-input-lock.json", *[n for _, a in positions for n in a]])
    save_json(out / LOCK, dict(cases=[trial.CASE], files={n: _sha(out / n) for n in files}))


def stage_figure(out):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig, (inventory, age) = plt.subplots(1, 2, figsize=(9.6, 4.05))
    colors = ("#285777", "#b03f32")
    for i, (role, color) in enumerate(zip(trial.ORDER, colors, strict=True)):
        rows = pace.readgz(out / f"raw/{role}/trace.json.gz")
        values = [
            sum(r["outcome"] == k for r in rows)
            for k in ("emitted", "queue_drop", "invalid_capture")
        ]
        inventory.barh(i, values[0], color=color)
        inventory.barh(i, values[1], left=values[0], color="#a0a0a0")
        inventory.barh(i, values[2], left=sum(values[:2]), color="#222222")
        observed_age = sorted(
            (r["emitted_ns"] - r["arrival_ns"]) / 1e6 for r in rows if r["outcome"] == "emitted"
        )
        if observed_age:
            probability = [(rank + 1) / len(observed_age) for rank in range(len(observed_age))]
            age.plot(observed_age, probability, color=color, label=LABEL[role])
    inventory.set(
        yticks=[0, 1],
        yticklabels=[LABEL[role] for role in trial.ORDER],
        xlabel="Visit count · colour emitted, grey dropped, black invalid",
    )
    inventory.invert_yaxis()
    age.axvline(20, color="#555555", ls="--", linewidth=1, label="20 ms")
    age.set(
        xscale="log",
        ylim=(0, 1.01),
        xlabel="Arrival-to-emission age (ms)",
        ylabel="Fraction of emitted visits",
    )
    age.legend(frameon=False, loc="lower right")
    fig.suptitle("One detector worker on the same saved-IQ arrival schedule")
    fig.tight_layout()
    image, csv, lock = "pace.png", "timing.csv", "stage-figure-lock.json"
    fig.savefig(out / image, dpi=165)
    plt.close(fig)
    save_json(out / lock, dict(files={n: _sha(out / n) for n in (image, csv)}))
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="direct-partner-hit-pace",
            title="Direct partner-on-hit and stock dual",
            sample="DS29-0174, two genuine complete saved-IQ clocks with a common caller CPU10",
            boundary="One detector worker, one waiting visit, 512 MiB, separately staged input",
            note="Earlier archived data supply the arrival clock and packet authentication. "
            "Age percentiles are conditional on emission. The outcome ledger retains all drops.",
            seal=lock,
            image=image,
            csv=csv,
        ),
    )


def score(out):
    prediction = sealed(out, LOCK)
    _, refs = held_references(None, prediction["cases"])
    rows = rows_from(out / POS)
    csv_file(out / "scores.csv", geographic(rows, {r["id"]: r for r in refs}))
    names = [
        LOCK,
        "source-lock.json",
        "timing.csv",
        "scores.csv",
        "common-cost.json",
        "arrival-decomposition.csv",
    ]
    save_json(
        out / "figure-lock.json",
        dict(cases=prediction["cases"], files={n: _sha(out / n) for n in [POS, *names]}),
    )
    spec = dict(
        id="pace-direct-partner-hit",
        method=METHOD[trial.HIT],
        scope="roof",
        cases="sealed",
        title="Direct partner-on-hit versus stock dual under the original receive clock",
        caption="One saved roof waveform, a shared native ABI and one detector worker. "
        "Both calibration arms fit each clock's actual emitted data.",
        seal="figure-lock.json",
        provenance=names,
        series=[
            dict(
                key=key,
                file=POS,
                value=METHOD[role],
                label=LABEL[role],
                native_field="paired_capture_sha256",
                **({"match": PHYSICAL_KEYS} if key == "stock" else {}),
            )
            for key, role in (("one", trial.HIT), ("stock", trial.DUAL))
        ],
    )
    save_json(out / "figures.json", dict(version=2, charts=[spec]))
    screening_figures.generate(out / "charts", evidence=out)
    stage_figure(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fit", "score"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    if args.action == "fit":
        fit(args.work, trial.REPORT)
    else:
        score(trial.REPORT)
