"""Publish roof accounting, compact position and calibration evidence for rank prefixes."""

import argparse
import csv
import gzip
import json
from collections import Counter
from pathlib import Path
from time import perf_counter_ns

from matplotlib import pyplot as plt

from ..__main__ import local_output, save_json
from ..scoring import ARMS, ROLES, validate_result
from ..variants.compact_tile_interior import guard
from . import complete_detector_roster as fixed
from . import first_gate_panel as trial
from . import screening_figures, staggered_benchmark
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .scout_stage_figures import canvas

LABELS = {"first": "First pass", "second": "Two passes", "full": "Full original GLRT"}
COLORS = {"first": "#146C5F", "second": "#456F9C"}
RAW = trial.REPORT.with_name("first-gate-raw")
read, checked = trial.read, trial.checked


def verified(report, name):
    lock = read(report / name)
    for path, sha in lock["files"].items():
        checked(report / path, sha)
    return lock


def archive_summary(rows, membership):
    tallies = []
    for cohort in ("all", "DS26", "DS29"):
        for policy in trial.POLICIES[:2]:
            subset = [
                r
                for r in rows
                if r["policy"] == policy and (cohort == "all" or r["id"][:4] == cohort)
            ]
            total = Counter()
            for row in subset:
                total.update({k: int(v) for k, v in row.items() if k not in ("id", "policy")})
            expected = [i for i in membership["accounting"] if cohort == "all" or i[:4] == cohort]
            if sorted(r["id"] for r in subset) != sorted(expected):
                raise ValueError("archive tally lacks part of the immutable accounting roster")
            lower = total["skipped_anchor_calls_lower"]
            upper = total["skipped_anchor_calls_upper"]
            full_upper = (
                total["full_final_anchor_calls_upper"] + total["unobserved_primary_calls_upper"]
            )
            clipped = total["removed_complete_continuous_calls"]
            tallies.append(
                dict(
                    cohort=cohort,
                    policy=policy,
                    recordings=len(subset),
                    **total,
                    complete_continuous_calls_removed_pct=100
                    * clipped
                    / total["available_complete"],
                    winner_rank_flips_pct_positive=100
                    * total["winner_rank_flips"]
                    / total["positive_lanes"],
                    compact_observation_flips_pct_positive=100
                    * total["compact_observation_flips"]
                    / total["positive_lanes"],
                    avoided_fractional_anchor_pct_lower=100 * lower / full_upper,
                    avoided_fractional_anchor_pct_upper=100
                    * upper
                    / (total["kept_anchor_calls_lower"] + upper),
                )
            )
    return tallies


def plot_stage(report, rows, membership):
    fig, axes = canvas(
        "Fractional work after the first passing rank",
        "Exact capture-era GLRT on 135 complete roof recordings",
        "Bounds include unexported ranks and possible replaced primary attempts. "
        "The plot counts fractional work and winner changes from stored factors.",
    )
    cohorts = ("all", "DS26", "DS29")
    labels = ("All · 135", "DS26 · 127", "DS29 · 8")
    for p_index, policy in enumerate(trial.POLICIES[:2]):
        records = {r["cohort"]: r for r in rows if r["policy"] == policy}
        y = [i + (-0.16 + 0.32 * p_index) for i in range(len(cohorts))]
        for i, (index, row) in enumerate(zip(y, (records[g] for g in cohorts), strict=True)):
            lo = row["avoided_fractional_anchor_pct_lower"]
            hi = row["avoided_fractional_anchor_pct_upper"]
            axes[0].hlines(index, lo, hi, color=COLORS[policy], linewidth=4, alpha=0.7)
            axes[0].scatter([lo, hi], [index, index], s=22, color=COLORS[policy])
            axes[1].barh(
                index,
                row["compact_observation_flips_pct_positive"],
                height=0.25,
                color=COLORS[policy],
                label=LABELS[policy] if i == 0 else None,
            )
    for ax, title, label in zip(
        axes,
        ("Possible fractional-anchor work avoided", "Changed compact observations"),
        ("Percent of full original candidate calls", "Percent of positive receiver lanes"),
        strict=True,
    ):
        ax.set(title=title, xlabel=label, yticks=range(len(cohorts)), yticklabels=labels)
        ax.set_xlim(left=0)
        ax.set_ylim(len(cohorts) - 0.55, -0.45)
    handles, keys = axes[1].get_legend_handles_labels()
    fig.legend(
        handles, keys, loc="lower center", bbox_to_anchor=(0.55, 0.125), ncol=2, frameon=False
    )
    for ext in ("png", "pdf"):
        fig.savefig(
            report / f"stage.{ext}",
            dpi=160,
            metadata={"CreationDate": None} if ext == "pdf" else {},
        )
    plt.close(fig)
    names = (
        "archive-accounting.csv",
        "archive-summary.csv",
        "accounting-lock.json",
        "stage.png",
        "stage.pdf",
    )
    save_json(
        report / "stage-figure-lock.json",
        dict(cases=membership["accounting"], files={n: _sha(report / n) for n in names}),
    )
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="first-gate-panel-stage",
            title="Fractional work after the first passing rank",
            boundary="Post-acquisition rank prefixes on original recorded GLRT factors",
            sample="135 complete roof recordings",
            note="Candidate work bounds and winner differences from archived factors.",
            seal="stage-figure-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="archive-summary.csv",
        ),
    )


def publish(rows):
    guarded, timings = [], []
    for row in rows:
        result = row["result"]
        validate_result(result)
        start = perf_counter_ns()
        returned = guard(result, dict(center=row["tile"]["center"], width_km=25.0))
        guard_wall_ns = perf_counter_ns() - start
        validate_result(returned)
        guarded.append(dict(row, result=returned))
        resources = row.get("position_resources") or {}
        metrics = result["metrics"]
        timings.append(
            dict(
                id=row["id"],
                policy=row["condition"],
                reused="reused_full_original_lock_sha256" in row,
                status=result["status"],
                guarded_status=returned["status"],
                guarded_reason=returned.get("reason"),
                guard_wall_ns=guard_wall_ns,
                position_wall_s=resources.get("wall_s"),
                position_cpu_s=resources.get("cpu_s"),
                position_peak_bytes=resources.get("peak_bytes"),
                supervisor_wall_s=row.get("supervisor_wall_s"),
                observations=metrics.get("observations"),
                tracks=metrics.get("tracks"),
            )
        )
    return guarded, timings


def numeric_table(rows):
    positions = {(r["id"], r["arm"], r["method"]): r["error_km"] for r in rows}
    geographic, frequency = [], []
    for row in rows:
        fields = {k: v for k, v in row.items() if k not in ("rf_rms_hz", "frequency_score")}
        full = positions.get((row["id"], row["arm"], "first_gate_full"))
        fields["delta_km_full"] = (
            row["error_km"] - full if row["error_km"] is not None and full is not None else None
        )
        geographic.append(fields)
        frequency.append(
            {k: row[k] for k in ("id", "method", "arm", "status", "rf_rms_hz", "frequency_score")}
        )
    return geographic, frequency


def plot_position(report, cases):
    files = (
        "prediction-lock.json",
        "guarded-positions.jsonl.gz",
        "geographic.csv",
        "geographic-summary.csv",
        "frequency.csv",
        "calibration.csv",
        "publication-and-position-timing.csv",
        "original-v5-references.csv",
    )
    save_json(
        report / "figure-lock.json",
        dict(cases=cases, files={name: _sha(report / name) for name in files}),
    )
    save_json(
        report / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="first-gate-panel",
                    method="first_gate_first",
                    scope="roof",
                    cases="sealed",
                    title="Compact position after one or two GLRT passes",
                    caption=(
                        "Six original recordings. Prefixes retain every earlier rejected row "
                        "in post-acquisition rank order. The figure includes first-attempt "
                        "outcomes and four original v5 options."
                    ),
                    seal="figure-lock.json",
                    provenance=list(files),
                    series=[
                        dict(
                            key=key,
                            file="guarded-positions.jsonl.gz",
                            value=f"first_gate_{policy}",
                            native_field="paired_capture_sha256",
                            label=LABELS[policy],
                            match=list(fixed.BINDINGS),
                        )
                        for key, policy in zip(
                            ("one", "one_native_factors", "stock"), trial.POLICIES, strict=True
                        )
                    ],
                ),
            ],
        ),
    )
    screening_figures.generate(report / "charts", evidence=report)


def audit_stage(report):
    seal = verified(report, "accounting-lock.json")
    membership = read(report / "membership-lock.json")
    if seal["cases"] != membership["accounting"]:
        raise ValueError("the accounting seal differs from the original enrollment")
    with (report / "archive-accounting.csv").open(newline="") as stream:
        rows = archive_summary(list(csv.DictReader(stream)), membership)
    csv_file(report / "archive-summary.csv", rows)
    plot_stage(report, rows, membership)


def compare_witness(archived, input_probes, witness):
    if archived != input_probes:
        raise ValueError("the independent raw witness cites different original native evidence")
    attempts = witness["attempts"]
    complete = attempts["full"]

    def attempt_key(row):
        return row["receiver"], row["probe"], row["retry"], row["available"]

    facts = {}
    for policy, limit in (("first", 1), ("second", 2)):
        cut = attempts[policy]
        if [attempt_key(r) for r in complete] != [attempt_key(r) for r in cut]:
            raise ValueError("the original physical attempts or retry decision changed")
        full_last = {(r["receiver"], r["probe"]): r for r in complete}
        cut_last = {(r["receiver"], r["probe"]): r for r in cut}
        for probe in archived:
            lane = probe["receiver_id"], probe["probe_index"]
            old = probe["candidates"]
            retained, _ = trial.prefix(old, limit)
            projected = {c["candidate_rank"] for c in old}
            ranks = cut_last[lane]["retained_ranks"]
            full_ranks = full_last[lane]["retained_ranks"]
            if (
                [r for r in full_ranks if r in projected] != [c["candidate_rank"] for c in old]
                or [r for r in ranks if r in projected] != [c["candidate_rank"] for c in retained]
                or bool(full_last[lane]["passing_ranks"]) != bool(cut_last[lane]["passing_ranks"])
            ):
                raise ValueError("raw final attempt disagrees with the complete exported prefix")
        facts[policy] = dict(
            physical_receiver_attempts=len(cut),
            retry_attempts=sum(r["retry"] for r in cut),
            original_fractional_calls=sum(r["scored"] for r in complete),
            stopped_fractional_calls=sum(r["scored"] for r in cut),
            final_native_probes=len(archived),
            projected_ranks_matched=True,
        )
    return facts


def raw_witnesses(report, raw=RAW):
    raw_seal_path = raw / "qualification-lock.json"
    seal = read(raw_seal_path)
    plan = read(checked(raw / "input-lock.json", seal["files"]["input-lock.json"]))
    memberships = read(report / "membership-lock.json")
    cases = trial.inputs()
    checks = []
    receipts = {}
    for ident, data in plan["cases"].items():
        if ident not in memberships["accounting"]:
            raise ValueError("raw witness is outside the authenticated archive")
        _, document = trial.archive(cases[ident])
        by_visit = dict(trial.visit_pairs(document["source"]["probes"]))
        inputs_by_visit = {w["visit"]: w for w in data["rows"]}
        path = checked(raw / f"{ident}.json.gz", seal["files"][f"{ident}.json.gz"])
        receipts[path.name] = _sha(path)
        outcome = json.loads(gzip.decompress(path.read_bytes()))
        if (
            outcome["id"] != ident
            or outcome["input_lock_sha256"] != seal["files"]["input-lock.json"]
            or {r["visit"] for r in outcome["rows"]} != inputs_by_visit.keys()
        ):
            raise ValueError("raw receipts changed their frozen input roster")
        for row in outcome["rows"]:
            visit = row["visit"]
            witness = inputs_by_visit[visit]
            if row["iq_sha256"] != witness["iq_sha256"]:
                raise ValueError("raw witness used a different saved CI16 visit")
            facts = compare_witness(list(by_visit[visit]), witness["probes"], row)
            for policy, counts in facts.items():
                checks.append(
                    dict(
                        id=ident,
                        visit=visit,
                        policy=policy,
                        iq_sha256=row["iq_sha256"],
                        compact_panel_case=ident in memberships["fits"],
                        **counts,
                    )
                )
    output = report / "raw-witness-comparison.csv"
    csv_file(output, checks)
    save_json(
        report / "raw-witness-lock.json",
        dict(
            panel_accounting_lock_sha256=_sha(report / "accounting-lock.json"),
            raw_source_lock_sha256=_sha(raw / "input-lock.json"),
            raw_qualification_lock_sha256=_sha(raw_seal_path),
            case_receipts=receipts,
            files={output.name: _sha(output)},
        ),
    )


def evaluate(report):
    seal = verified(report, "prediction-lock.json")
    membership = read(report / "membership-lock.json")
    cases = membership["fits"]
    if seal["cases"] != cases:
        raise ValueError("the position seal differs from the frozen enrollment")
    audit = read(report / "position-input-audit.json")
    rows = trial.rows_from(report / "positions.jsonl.gz")
    expected = [(ident, policy) for ident in cases for policy in trial.POLICIES]
    if [(r["id"], r["condition"]) for r in rows] != expected:
        raise ValueError("position replay omitted a case or policy")
    for row in rows:
        if any(row[k] != audit[row["id"]][k] for k in fixed.BINDINGS):
            raise ValueError("position replay changed its original matched authority")
    guarded, timings = publish(rows)
    pack(report / "guarded-positions.jsonl.gz", guarded)
    reference, _ = screening_figures._roof_authority()
    cols = [
        dict(
            id=ident,
            role=role,
            arm=arm,
            **{
                k: reference[ident]["reference"][role][arm].get(k)
                for k in ("status", "error_km", "rf_rms_hz", "frequency_score")
            },
        )
        for ident in cases
        for role in ROLES
        for arm in ARMS
    ]
    scores = fixed.scored(guarded, reference)
    geography, frequency = numeric_table(scores)
    before, _ = numeric_table(fixed.scored(rows, reference))
    cohorts = dict(
        all=cases,
        anchors=membership["anchors"],
        prospective=[i for i in cases if i not in membership["anchors"]],
    )
    methods = tuple(f"first_gate_{p}" for p in trial.POLICIES)
    summary = []
    for cohort, ids in cohorts.items():
        for arm in ARMS:
            subset = [r for r in scores if r["id"] in ids and r["arm"] == arm]
            reference_rows = [
                dict(r, method=fixed.FOUR) for r in subset if r["method"] == methods[0]
            ]
            summary.extend(
                fixed.summary_row(reference_rows if m in ROLES else subset, ids, cohort, arm, m)
                for m in (*methods, *ROLES)
            )
    for name, value in (
        ("geographic.csv", geography),
        ("geographic-before-guard.csv", before),
        ("frequency.csv", frequency),
        ("geographic-summary.csv", summary),
        ("calibration.csv", staggered_benchmark.calibration_effects(scores, cohorts, methods)),
        ("original-v5-references.csv", cols),
        ("publication-and-position-timing.csv", timings),
    ):
        csv_file(report / name, value)
    plot_position(report, cases)
    save_json(
        report / "score-lock.json",
        dict(
            files={p.name: _sha(p) for p in report.glob("*.csv")},
            exporter_sha256=_sha(Path(__file__)),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "position", "raw"))
    parser.add_argument("--report", default=trial.REPORT, type=local_output)
    args = parser.parse_args()
    {"stage": audit_stage, "position": evaluate, "raw": raw_witnesses}[args.action](args.report)


if __name__ == "__main__":
    main()
