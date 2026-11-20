"""Seal actual original-quality and fast-wide paced emissions and their compact fits."""

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
from . import paced_original as trial
from .arrival_queue_results import observed, terminal
from .bracketed_position_results import service_result
from .diagnostic_whole_results import PHYSICAL_KEYS
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .paced_controlled_arrival_audit import summarize as arrival_parts
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

METHOD = {role: "paced_capture_" + role for role in trial.ORDER}
LABEL = {trial.ORIGINAL: "Original-quality combined", trial.WIDE: "Fast released four"}
RAW_LOCK = "raw-prediction-lock.json"
LOCK, POS = "prediction-lock.json", "positions.jsonl.gz"


def retained(rows, packets):
    visits, probes = [], []
    timely, timely_positive, timely_probes = 0, 0, 0
    for row in rows:
        if row["outcome"] != "emitted":
            continue
        visit = row["visit"]
        packet = packets[visit]
        if (
            packet["visit"] != visit
            or packet["status"] != "processed"
            or pace.fingerprint(packet) != row["full_visit_sha256"]
            or [p["receiver_id"] for p in packet["probes"]] != [0, 1]
        ):
            raise ValueError(
                "retained emission does not authenticate its actual full candidate packet"
            )
        visits.append(visit)
        probes.extend(packet["probes"])
        if row["emitted_ns"] - row["arrival_ns"] <= 20_000_000:
            timely += 1
            observed_positive = sum(map(positive, packet["probes"]))
            timely_positive += observed_positive > 0
            timely_probes += observed_positive
    return (
        visits,
        probes,
        dict(
            emissions_with_age_20ms=timely,
            timely_positive_visits=timely_positive,
            timely_positive_probes=timely_probes,
            positive_probes=sum(map(positive, probes)),
            positive_visits=sum(
                any(map(positive, probes[i : i + 2])) for i in range(0, len(probes), 2)
            ),
        ),
    )


def raw_seal(work, out):
    if (out / RAW_LOCK).exists():
        raise FileExistsError("paired live acquisition already sealed")
    plan = pace.plan(work, out)
    spec = plan["cases"][trial.CASE]
    data, _ = trial.references()
    timing, arrival = [], []
    files = [
        "source-lock.json",
        "source-stage-lock.json",
        "source-timing.json",
        "PROTOCOL.md",
        "ready.json",
        "members.json.gz",
        "preflight.json",
        "preflight.service.log",
        "clock-events.json.gz",
        "source-terminal.json",
    ]
    for role in trial.ORDER:
        attempt = work / trial.CASE / role
        branch = spec["modes"][role]
        events = pace.readgz(whole_iq.checked(out / branch["events"], branch["sha256"]))
        if (attempt / "visits.jsonl").is_file():
            rows, witness, service, complete = terminal(attempt, events)
        else:
            rows, witness, complete = [], None, False
            service = whole_iq.read(attempt / "service.json")
            whole_iq.checked(attempt / "service.log", service["log_sha256"])
        folder = f"raw/{role}"
        names = [
            f"{folder}/{n}"
            for n in (
                "trace.json.gz",
                "service.json",
                "witness.json",
                "status.json",
                "plan.json",
                "service.log",
                "source-charge.json",
            )
        ]
        values = (service, witness, dict(complete=complete), whole_iq.read(attempt / "plan.json"))
        pace.writegz(out / names[0], rows)
        for name, value in zip(names[1:5], values, strict=True):
            save_json(out / name, value)
        write(out / names[5], (attempt / "service.log").read_bytes())
        charge = whole_iq.read(out / names[6])
        source_start, source_end = (charge[k] for k in ("start", "end"))
        if witness and (
            witness["end"]["cpus"] != [trial.source.MAIN]
            or witness["start"]["cpus"] != [trial.source.MAIN]
            or witness["compressed_chunks"]
            or witness["compressed_bytes"]
            or witness["end"]["memory.swap.current"]
            or witness["end"]["cgroup"] == source_end["cgroup"]
        ):
            raise ValueError("live receiver crossed its own core/memory/input boundary")
        _, _, support = retained(rows, data[role][1])
        summary = observed(rows, witness, trial.CASE, role, complete, events)
        summary.update(
            support,
            valid_fraction_emitted=summary["native_packets_emitted"] / summary["valid_slots"],
            native_calls_20ms=sum(
                row["native_wall_ns"] <= 20_000_000 for row in rows if row["outcome"] == "emitted"
            ),
            service_result=service["systemd"].get("Result"),
            systemd_wall_s=service.get("service_wall_s"),
            source_current_bytes=source_end["memory.current"],
            source_peak_bytes=source_end["memory.peak"],
            source_cpu_s=(source_end["cpu.stat.usage_usec"] - source_start["cpu.stat.usage_usec"])
            / 1e6,
            receiver_swap_bytes=witness["end"]["memory.swap.current"] if witness else None,
        )
        timing.append(summary)
        arrival.append(dict(mode=role, **arrival_parts(rows)))
        files.extend([*names, branch["events"]])
    csv_file(out / "timing.csv", timing)
    csv_file(out / "arrival-decomposition.csv", arrival)
    files.extend(("timing.csv", "arrival-decomposition.csv"))
    save_json(out / RAW_LOCK, dict(cases=[trial.CASE], files={n: _sha(out / n) for n in files}))


def fit(work, out):
    if (out / LOCK).exists():
        raise FileExistsError("paired compact fits already sealed")
    prior = sealed(out, RAW_LOCK)
    plan = pace.plan(work, out)
    spec = plan["cases"][trial.CASE]
    case, request = whole_iq.binding(trial.CASE)
    data, former = trial.references()
    release = whole_iq.read(
        trial.source.SCREEN / "latency-and-support/fifth-completion/source-lock.json"
    )
    bracketed_position.check_release(release)
    if case != spec["capture"]["case"] or release["receiver_files"] != former["receiver_files"]:
        raise ValueError(
            "actual compact fit would change the bound causal request or implementation"
        )
    files = [RAW_LOCK]
    jobs = []
    for role, cpu in zip(trial.ORDER, plan["cpus"], strict=True):
        raw = out / f"raw/{role}"
        complete = whole_iq.read(raw / "status.json")["complete"]
        trace = raw / "trace.json.gz"
        witness = whole_iq.read(raw / "witness.json")
        doc, packets = data[role]
        kept, probes, support = retained(pace.readgz(trace), packets) if complete else ([], [], {})
        row = dict(
            id=trial.CASE,
            method=METHOD[role],
            mode="matched-tile",
            role=role,
            cohort="recorded arrival",
            cpu=cpu,
            raw_verified=complete,
            emitted_visits=kept,
            tile=case["regions"][0],
            catalog_sha256=case["catalog"]["sha256"],
            original_request_sha256=case["request"]["sha256"],
            paired_capture_sha256=case["native"]["sha256"],
            native_sha256=None,
            trace_sha256=_sha(trace),
            **support,
        )
        folder = work / trial.CASE / f"position-{role}"
        folder.mkdir(exist_ok=False)
        if complete and probes:
            lineage = pace.recording_to_v5.digest([role, witness["output_sha256"], kept])
            material = dict(
                doc,
                source=dict(doc["source"], probes=probes, analysis_manifest_sha256=lineage),
                provenance=dict(
                    doc["provenance"],
                    processed_windows=len(kept),
                    run_id="replay-" + lineage[7:39],
                    scope="Actual verified FIFO emissions",
                ),
            )
            row["native_sha256"], row["position_request_sha256"] = emitted.position_input(
                folder, case, request, release, material, cpu
            )
            name = f"native/{role}/{trial.CASE}.json.gz"
            write(out / name, gzip.compress((folder / "native.json").read_bytes(), mtime=0))
            files.append(name)
        else:
            reason = "no valid emissions" if complete else "incomplete recorded-arrival service"
            row["result"] = emitted.empty_result("withheld" if complete else "unavailable", reason)
        jobs.append((folder, row))
    save_json(
        out / "position-input-lock.json",
        dict(
            cases=[trial.CASE],
            jobs=[row for _, row in jobs],
            files={n: _sha(out / n) for n in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )

    def solve(job):
        folder, row = job
        if row["native_sha256"] is None:
            return row, []
        whole_iq.checked(folder / "native.json", row["native_sha256"])
        whole_iq.checked(folder / "request.json", row["position_request_sha256"])
        bracketed_position.launch_case(folder, row["cpu"])
        result, resources = service_result(folder, row["cpu"])
        name = f"position/{row['role']}.service.log"
        write(out / name, (folder / "service.log").read_bytes())
        return dict(row, result=result, position_resources=resources), [name]

    with ThreadPoolExecutor(max_workers=2) as pool:
        fits = list(pool.map(solve, jobs))
    pack(out / POS, [row for row, _ in fits])
    files.extend((POS, "position-input-lock.json", *[name for _, names in fits for name in names]))
    save_json(
        out / LOCK,
        dict(cases=[trial.CASE], files=prior["files"] | {n: _sha(out / n) for n in files}),
    )


def stage(out):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig, (inventory, age) = plt.subplots(1, 2, figsize=(10.4, 4.1))
    palette = ("#b03f32", "#285777")
    for i, (role, color) in enumerate(zip(trial.ORDER, palette, strict=True)):
        rows = pace.readgz(out / f"raw/{role}/trace.json.gz")
        counts = [
            sum(r["outcome"] == name for r in rows)
            for name in ("emitted", "queue_drop", "invalid_capture")
        ]
        inventory.barh(i, counts[0], color=color)
        inventory.barh(i, counts[1], left=counts[0], color="#a0a0a0")
        inventory.barh(i, counts[2], left=sum(counts[:2]), color="#222222")
        times = sorted(
            (r["emitted_ns"] - r["arrival_ns"]) / 1e6 for r in rows if r["outcome"] == "emitted"
        )
        if times:
            age.plot(
                times,
                [(n + 1) / len(times) for n in range(len(times))],
                color=color,
                label=LABEL[role],
            )
    inventory.set(
        yticks=[0, 1],
        yticklabels=[LABEL[role] for role in trial.ORDER],
        xlabel="Visit count · colour emitted, grey dropped, black invalid",
    )
    inventory.invert_yaxis()
    age.axvline(20, color="#555555", linestyle="--", linewidth=1, label="20 ms")
    age.set(
        xscale="log",
        ylim=(0, 1.01),
        xlabel="Arrival-to-emission age (ms)",
        ylabel="Fraction of emitted visits",
    )
    age.legend(frameon=False)
    fig.suptitle("Original-quality and fast-four detection at the same recorded pace")
    fig.tight_layout()
    name, table, seal = "pace.png", "timing.csv", "stage-figure-lock.json"
    fig.savefig(out / name, dpi=165)
    plt.close(fig)
    save_json(out / seal, dict(files={n: _sha(out / n) for n in (name, table)}))
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="paced-original-quality",
            title="Original-quality and fast-four recorded pace",
            sample="DS29-0082, 6,772 original arrivals and a common pinned CPU10",
            boundary="One detector worker, one waiting visit, separate source and 512 MiB",
            note="Outcome counts cover the physical ledger. Age conditions on emission.",
            seal=seal,
            image=name,
            csv=table,
        ),
    )


def score(out):
    prediction = sealed(out, LOCK)
    _, refs = held_references(None, prediction["cases"])
    csv_file(out / "scores.csv", geographic(rows_from(out / POS), {r["id"]: r for r in refs}))
    files = [LOCK, RAW_LOCK, "source-lock.json", "timing.csv", "scores.csv"]
    save_json(
        out / "figure-lock.json",
        dict(cases=prediction["cases"], files={n: _sha(out / n) for n in [POS, *files]}),
    )
    spec = dict(
        id="paced-original-quality",
        method=METHOD[trial.ORIGINAL],
        scope="roof",
        cases="sealed",
        title="Original-quality and fast-four at live recorded pace",
        caption="DS29-0082. Both c arms fit the actual emitted factors on the original offer. "
        "The four original v5 options use their full capture-era inputs.",
        seal="figure-lock.json",
        provenance=files,
        series=[
            dict(
                key=key,
                file=POS,
                value=METHOD[role],
                label=LABEL[role],
                native_field="paired_capture_sha256",
                **({"match": PHYSICAL_KEYS} if key == "stock" else {}),
            )
            for key, role in (("one", trial.ORIGINAL), ("stock", trial.WIDE))
        ],
    )
    save_json(out / "figures.json", dict(version=2, charts=[spec]))
    screening_figures.generate(out / "charts", evidence=out)
    stage(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("raw", "fit", "score"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    if args.action == "score":
        score(trial.REPORT)
    else:
        {"raw": raw_seal, "fit": fit}[args.action](args.work, trial.REPORT)
