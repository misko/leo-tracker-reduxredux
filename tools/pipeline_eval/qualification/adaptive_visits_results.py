"""Validate full factor and fit lineage, then score bounded visit selection."""

import argparse
import csv
import gzip
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution
from . import adaptive_visits_trial as trial
from . import cascade_audit_results as previous
from . import complete_detector_roster as fixed
from . import study_benchmark
from . import two_rate_holdout_results as cost_source
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
MODES = ("novel", "hash", "fast", "original")
LABELS = ("Track novelty", "Matched hash", "Always fast", "Always original")
COLORS = ("#926449", "#366883")
METHODS = tuple("adaptive_visits_" + mode for mode in MODES)


def route_rows(work, source):
    report = trial.prior.REPORT
    seal = whole_iq.read(whole_iq.checked(report / "endpoint-lock.json", trial.PRIOR_ENDPOINT_SHA))
    rows = []
    for r in rows_from(fixed.member(report, seal, "endpoints.jsonl.gz")):
        ident, mode = r["id"], r["condition"]
        if ident not in source["cases"]:
            continue
        case = source["cases"][ident]
        digest = case["fast_sha256" if mode == "fast" else "paired_capture_sha256"]
        source_row = {k: case[k] for k in fixed.BINDINGS}
        genuine = trial.prior.bind_control(r, source_row, mode, digest)
        rows.append(
            dict(genuine, method=f"adaptive_visits_{mode}", source="sealed earlier compact fit")
        )

    a = {(r["id"], r["condition"]): r for r in rows}
    witnesses = {}
    resources = []
    for job in source["jobs"]:
        ident, mode = job["id"], job["condition"]
        path = work / ident / mode
        row = whole_iq.read(path / "attempt.json")
        if any(row[key] != value for key, value in job.items()):
            raise ValueError("compact worker did not attest the exact frozen job")
        native = whole_iq.read(
            whole_iq.checked(path / "recording/native.json", job["native_sha256"])
        )
        whole_iq.checked(path / "recording/request.json", job["prepared_request_sha256"])
        log = whole_iq.checked(path / "service.log", row["log_sha256"])
        write(REPORT / "logs" / f"{ident}-{mode}.gz", gzip.compress(log.read_bytes(), mtime=0))
        measures = row.get("position_resources") or {}
        for stage in ("start", "end"):
            if stage in measures and (
                measures[stage]["cpus"] != [job["cpu"]]
                or measures[stage]["memory.max"] != source["memory_bytes"]
                or measures[stage]["memory.swap.max"] != source["swap_bytes"]
            ):
                raise ValueError("the compact service differs from the frozen CPU/memory bounds")
        raw = whole_iq.checked(
            REPORT / "lineage" / f"{ident}-{mode}.jsonl.gz", job["witness_sha256"]
        )
        witness = rows_from(raw)
        materialized = {(p["visit_index"], p["receiver_id"]): p for p in native["source"]["probes"]}
        selected = {(w["visit"], w["rx"]): w for w in witness}
        if len(selected) != len(witness) or any(
            trial.policy.digest(
                "candidates",
                sorted(materialized[key]["candidates"], key=lambda c: c[trial.policy.RANK]),
            )
            != item["original_candidate_sha256"]
            for key, item in selected.items()
        ):
            raise ValueError("substituted physical antenna did not reach the compact input")
        witnesses[ident, mode] = witness
        kept = trial.prior.bind_control(
            row, {k: job[k] for k in fixed.BINDINGS}, mode, job["native_sha256"]
        )
        rows.append(dict(kept, source="new independent compact service"))
        fixed.same_capture(a[ident, "fast"], kept)
        metrics = kept["result"]["metrics"]
        resources.append(
            dict(
                id=ident,
                mode=mode,
                result_status=kept["result"]["status"],
                detected_observations=metrics.get("observations"),
                graph_tracks=metrics.get("tracks"),
                elapsed_wall_s=measures.get("wall_s"),
                fit_cpu_s=measures.get("cpu_s"),
                supervisor_wall_s=kept.get("supervisor_wall_s"),
                peak_bytes=measures.get("peak_bytes"),
                input_sha256=kept["native_sha256"],
            )
        )
    expected = {(ident, mode) for ident in source["cases"] for mode in MODES}
    if len(rows) != len(expected) or {(r["id"], r["condition"]) for r in rows} != expected:
        raise ValueError("every scheduled input requires all four terminal controls")
    csv_file(REPORT / "fit-resources.csv", resources)
    pack(REPORT / "predictions.jsonl.gz", rows)
    inputs = ("source-lock.json", "rule-lock.json", "fit-resources.csv", "predictions.jsonl.gz")
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=sorted(source["cases"]),
            files={name: _sha(REPORT / name) for name in inputs},
            scoring_program_sha256=_sha(Path(__file__)),
        ),
    )
    return rows, witnesses


def ideal_serial(selected, costs, fast_delay_s):
    """Model one buffered original queue at the recorded clock with a 300 s close."""
    last = 0.0
    complete = 0
    for visit, arrival in sorted(selected.items()):
        last = max(last, arrival + fast_delay_s) + costs[visit][1]
        complete += last <= trial.policy.CAPTURE_S
    return complete, last


def costs(source, witnesses):
    parent = trial.prior.REPORT
    # The exported parent totals authenticate the matched complete fast and original sources.
    lock = whole_iq.read(parent / "figure-lock.json")
    with fixed.member(parent, lock, "costs.csv").open(newline="") as handle:
        base = {r["id"]: r for r in csv.DictReader(handle)}
    timing_folder = fixed.BASE / "complete-timing"
    ledger = whole_iq.read(timing_folder / "prediction-lock.json")
    with fixed.member(timing_folder, ledger, "resources.csv").open(newline="") as handle:
        delays = {r["id"]: r for r in csv.DictReader(handle) if r["method"] == fixed.FOUR}
    anchors = {}
    original_membership = trial.paired.inventory()["physical_manifest_sha256"]
    for ident, (virtual, pin) in cost_source.TIMINGS.items():
        directory = fixed.SCREEN / virtual
        receipt = whole_iq.read(whole_iq.checked(directory / "timing-lock.json", pin))
        with fixed.member(directory, receipt, "timing.csv").open(newline="") as handle:
            anchors[ident] = {
                int(r["visit"]): (float(r["cpu_ms"]) / 1_000, float(r["wall_ms"]) / 1_000)
                for r in csv.DictReader(handle)
                if r["status"] == "processed"
            }
        case = source["cases"][ident]
        if (
            len(anchors[ident]) != case["valid_visits"]
            or case["manifest"] != original_membership[ident]
        ):
            raise ValueError("original service clock differs from the sealed physical support")
        if delays[ident]["native_sha256"] != case["fast_sha256"]:
            raise ValueError("fast detector time differs from the matched detector input")
    rows = []
    for ident, case in source["cases"].items():
        b = base[ident]
        if int(b["valid_visits"]) != case["valid_visits"]:
            raise ValueError("matched CPU source does not contain the same physical visits")
        for mode in trial.MODES:
            chosen = {r["visit"]: r["arrival_ns"] / 1e9 for r in witnesses[ident, mode]}
            counts = trial.summarize(witnesses[ident, mode])
            fast_cpu = float(b["fast_detector_cpu_s"])
            if ident in anchors:
                original_cpu = sum(anchors[ident][visit][0] for visit in chosen)
                p50 = float(delays[ident]["detector_call_wall_p50_ms"]) / 1_000
                completed, last = ideal_serial(chosen, anchors[ident], p50)
            else:
                original_cpu = (
                    float(b["original_detector_cpu_s"]) * len(chosen) / case["valid_visits"]
                )
                completed, last = None, None
            rows.append(
                dict(
                    id=ident,
                    mode=mode,
                    **counts,
                    net_lanes=counts["gained"] - counts["lost"],
                    fast_calls=case["valid_visits"],
                    selector_assembly_cpu_ms=case["selector_cpu_ms"],
                    min_action_clock_s=min(chosen.values()),
                    max_action_clock_s=max(chosen.values()),
                    full_fast_cpu_s=fast_cpu,
                    full_original_cpu_s=float(b["original_detector_cpu_s"]),
                    selected_original_cpu_s=original_cpu,
                    measured_original_call_trace=ident in anchors,
                    modeled_fast_plus_original_cpu_s=fast_cpu + original_cpu,
                    modeled_original_arrival_completions_by_300s=completed,
                    modeled_original_arrival_final_s=last,
                )
            )
    return rows


def plot(rows):
    ids = list(dict.fromkeys(r["id"] for r in rows))
    fig, axes = plt.subplots(2, 1, figsize=(11.4, 7.1), layout="constrained")
    for ax, metric, title in zip(
        axes,
        ("net_lanes", "modeled_fast_plus_original_cpu_s"),
        ("Measured packet substitutions", "Detector CPU model includes every fast call"),
        strict=True,
    ):
        for idx, mode in enumerate(trial.MODES):
            values = [r[metric] for r in rows if r["mode"] == mode]
            ax.bar(
                [i + (idx - 0.5) * 0.36 for i in range(len(ids))],
                values,
                width=0.35,
                color=COLORS[idx],
                label=LABELS[idx],
            )
        ax.set(title=title, xticks=range(len(ids)), xticklabels=ids, axisbelow=True)
        ax.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel("Passing antenna probes gained minus lost")
    axes[0].axhline(0, color="#333333", linewidth=0.9)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside upper center", ncols=2, frameon=False)
    axes[1].set_ylabel("Detector CPU seconds")
    fig.savefig(REPORT / "stage.png", dpi=160)
    fig.savefig(REPORT / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def publish(work):
    source = whole_iq.read(REPORT / "source-lock.json")
    whole_iq.checked(REPORT / "rule-lock.json", source["rule_lock_sha256"])
    rows, witnesses = route_rows(work, source)
    ids = sorted(source["cases"])
    raw = costs(source, witnesses)
    csv_file(REPORT / "stage.csv", raw)
    plot(raw)
    descriptor = dict(
        version=1,
        id="adaptive-visits-work",
        title="Track novelty at matched original-call counts",
        sample="Six held recordings · matched RF and token windows",
        boundary="Complete archived fast factors and selected original stereo packets",
        note=(
            "Packet counts are measured from the sealed factors. Total detector CPU is a model. "
            "Compact service resources have their own table."
        ),
        seal="stage-lock.json",
        image="stage.png",
        csv="stage.csv",
        pdf="stage.pdf",
    )
    save_json(REPORT / "stage-figure.json", descriptor)
    assets = ("stage-figure.json", "stage.png", "stage.pdf", "stage.csv")
    save_json(
        REPORT / "stage-lock.json", dict(files={name: _sha(REPORT / name) for name in assets})
    )
    with patch.object(previous, "REPORT", REPORT):
        refs, roof = previous.references(ids)
    scores = fixed.scored(rows, refs)
    csv_file(REPORT / "scores.csv", scores)
    table = []
    for arm in ARMS:
        for method in METHODS:
            sample = [r for r in scores if (r["method"], r["arm"]) == (method, arm)]
            decisions = Counter(r["status"] for r in sample)
            result = fixed.summary_row(sample, ids, "held", arm, method)
            rf = distribution(r["rf_rms_hz"] for r in sample)
            table.append(
                dict(
                    result,
                    withheld=decisions["withheld"],
                    timed_out=decisions["timed_out"],
                    failed=decisions["failed"],
                    unavailable=decisions["unavailable"],
                    rf_n=rf["n"],
                    rf_p50_hz=rf["p50"],
                    rf_p95_hz=rf["p95"],
                )
            )
    csv_file(REPORT / "summary.csv", table)
    csv_file(
        REPORT / "v5-references.csv",
        [
            dict(
                id=ident,
                role=role,
                arm=arm,
                status=item["status"],
                error_km=item["error_km"],
                rf_rms_hz=item.get("rf_rms_hz"),
            )
            for ident in ids
            for role in ROLES
            for arm in ARMS
            if (item := refs[ident]["reference"][role][arm])
        ],
    )
    spec = dict(
        id="adaptive-visits-held",
        method=METHODS[0],
        scope="roof",
        cases="sealed",
        title="Select original detector visits by fast track novelty",
        caption=(
            "Six held recordings with identical per-RF original-call budgets. "
            "The scheduled compact fits use the selected archived packets."
        ),
        seal="figure-lock.json",
        provenance=["prediction-lock.json", "summary.csv", "fit-resources.csv"],
        roof_references=roof,
        series=[
            dict(
                key=key,
                label=label,
                file="predictions.jsonl.gz",
                value=method,
                native_field="paired_capture_sha256",
                match=list(fixed.BINDINGS),
            )
            for key, label, method in zip(
                ("one", "stock", "one_native_factors", "all_visits"), LABELS, METHODS, strict=True
            )
        ],
    )
    save_json(REPORT / "figures.json", dict(version=2, charts=[spec]))
    inputs = (
        "figures.json",
        "prediction-lock.json",
        "predictions.jsonl.gz",
        "summary.csv",
        "scores.csv",
        "fit-resources.csv",
        "v5-references.csv",
        "stage-lock.json",
        *roof.values(),
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=ids, files={name: _sha(REPORT / name) for name in inputs}),
    )
    study_benchmark.run(REPORT, REPORT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=local_output)
    publish(parser.parse_args().work)
