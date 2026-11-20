"""Score all frozen whole-RF attempts and render acquisition and position evidence."""

import argparse
import csv
from collections import Counter
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch

from matplotlib import pyplot as plt

from ..__main__ import ROOT, local_output, save_json
from ..scoring import ARMS, ROLES, validate_result
from ..variants.compact_tile_interior import guard
from . import complete_detector_roster as fixed
from . import rf_lane_panel as trial
from . import screening_figures, staggered_benchmark
from . import two_rate_holdout_results as prior_results
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .scout_stage_figures import canvas

LABELS = {
    "whole": "Original on one RF",
    "spread": "Count-matched across RFs",
    "fast": "Full fast four",
    "original": "Full original compact",
    "twelfth": "Original every twelfth",
}
COLORS = {"whole": "#146C5F", "spread": "#4E74A4", "twelfth": "#A96124"}
SELECTOR_TIMING_LOCK = "689158cc9ed81425f6cfed5b686a10b9c6491a8d7fb0ade62f2add88ecbf2044"
read, checked = trial.read, trial.checked


def require_positions(report):
    seal = read(report / "prediction-lock.json")
    for name, fingerprint in seal["files"].items():
        checked(report / name, fingerprint)
    membership = read(report / "membership-lock.json")
    if membership["selected"] != seal["cases"]:
        raise ValueError("sealed positions differ from the enrolled recordings")
    rows = trial.prior.rows_from(report / "positions.jsonl.gz")
    audit = read(report / "packet-audit.json")
    expected = [(ident, policy) for ident in seal["cases"] for policy in trial.POLICIES]
    keys = [(r["id"], r["condition"]) for r in rows]
    if keys != expected or audit.keys() != set(seal["cases"]):
        raise ValueError("positions must cover every enrolled case and policy in frozen order")
    for row in rows:
        if any(row[field] != audit[row["id"]][field] for field in fixed.BINDINGS):
            raise ValueError("position differs from its archived factor binding")
        validate_result(row["result"])
    return membership, rows, audit


def publish(report, rows):
    """Score earlier first-attempt controls and evaluate the fixed paired terminal guard."""
    strict_original = {
        r["id"]: r
        for r in trial.prior.rows_from(report / "prior-original-first-attempts.jsonl.gz")
        if r["result"]["status"] not in ("ok", "withheld")
    }
    before, guarded, retries, receipts = [], [], [], []
    for row in rows:
        ident, policy = row["id"], row["condition"]
        if policy == "original" and ident in strict_original:
            retries.append(row)
            row = dict(
                strict_original[ident],
                method=row["method"],
                reused_prediction_lock_sha256=row["reused_prediction_lock_sha256"],
            )
        result = row["result"]
        tile = dict(center=row["tile"]["center"], width_km=25.0)
        start = perf_counter_ns()
        guarded_result = guard(result, tile)
        evaluation_ns = perf_counter_ns() - start
        validate_result(guarded_result)
        before.append(row)
        guarded.append(dict(row, result=guarded_result))
        resources = row.get("position_resources") or {}
        metrics = result["metrics"]
        stages = metrics.get("stage_s", {})
        receipts.append(
            dict(
                id=ident,
                policy=policy,
                source="reused" if "reused_prediction_lock_sha256" in row else "run",
                solver_result=result["status"],
                guarded_result=guarded_result["status"],
                guarded_reason=guarded_result.get("reason"),
                position_service_terminal=row.get("terminal"),
                position_service_wall_s=resources.get("wall_s"),
                position_service_cpu_s=resources.get("cpu_s"),
                position_service_peak_bytes=resources.get("peak_bytes"),
                supervisor_wall_s=row.get("supervisor_wall_s"),
                compact_observations=metrics.get("observations"),
                compact_tracks=metrics.get("tracks"),
                native_preparation_wall_s=stages.get("native_preparation"),
                compact_solve_stages_wall_s=sum(
                    seconds for stage, seconds in stages.items() if stage != "native_preparation"
                )
                if stages
                else None,
                guard_wall_ns=evaluation_ns,
                exact_tile_margin_c0_km=guarded_result["metrics"]
                .get("exact_tile_margin_km", {})
                .get("c0"),
                exact_tile_margin_fitted_c_km=guarded_result["metrics"]
                .get("exact_tile_margin_km", {})
                .get("fitted_c"),
            )
        )
    return before, guarded, receipts, retries


def source_costs(report, membership):
    original_membership = trial.prior.inventory()
    rows = []
    for ident in membership["anchors"]:
        original = prior_results.original_cost(ident, original_membership)
        path = checked(ROOT / original["trace_file"], original["trace_file_sha256"])
        with path.open(newline="") as stream:
            costs = {
                int(row["visit"]): float(row["cpu_ms"]) * 1e-3
                for row in csv.DictReader(stream)
                if row["status"] == "processed"
            }
        plan = read(report / "schedules" / f"{ident}.json")
        if set(costs) != {visit for visit, _ in plan["visits"]}:
            raise ValueError("prepared original timings do not cover these exact visits")
        prior_path = checked(
            trial.prior.REPORT / "schedules" / f"{ident}.json",
            original_membership["schedule_sha256"][ident],
        )
        twelfth = [r["visit"] for r in read(prior_path)["selected"]]
        total = original["measured_full_original_detector_cpu_s"]
        span = original["capture_span_s"]
        for policy, visits in (
            ("whole", plan["whole_original_visits"]),
            ("spread", plan["spread_original_visits"]),
            ("twelfth", twelfth),
            ("original", list(costs)),
        ):
            cpu = sum(costs[visit] for visit in visits)
            rows.append(
                dict(
                    id=ident,
                    policy=policy,
                    original_visits=len(visits),
                    full_valid_visits=len(costs),
                    full_original_detector_cpu_s=total,
                    source_visit_original_cpu_s=cpu,
                    source_original_cpu_pct_full=100 * cpu / total,
                    source_original_cpu_per_capture_second=cpu / span,
                    capture_span_s=span,
                    delta_original_cpu_s_vs_twelfth=cpu
                    - original["forecast_selected_original_detector_cpu_s"],
                    trace_file=original["trace_file"],
                    trace_file_sha256=original["trace_file_sha256"],
                    trace_lock_sha256=original["trace_lock_sha256"],
                )
            )
    return rows


def selector_sensitivity(report, costs):
    base = fixed.SCREEN / "receiver-deadline/selector-waveform"
    seal = read(checked(base / "timing-lock.json", SELECTOR_TIMING_LOCK))
    timing = fixed.member(base, seal, "paired-timing.csv")
    predictions = read(fixed.member(base, seal, "prediction-lock.json"))
    source = read(fixed.member(base, predictions, "source-lock.json"))
    ident = source["id"]
    original = next(row for row in costs if row["policy"] == "original" and row["id"] == ident)
    audit = read(fixed.member(base, predictions, "audit.json"))
    native = fixed.member(base, predictions, "native.json.gz")
    replayed = trial.prior.roster.stock_document(
        dict(
            path=str(native),
            file_sha256=_sha(native),
            native_sha256=audit["raw"]["measured_native_sha256"],
        )
    )
    plan = read(report / "schedules" / f"{ident}.json")
    if replayed["source"]["input_manifest_sha256"] != plan["physical_manifest_sha256"]:
        raise ValueError("the selector sensitivity requires this exact anchor recording")
    older = read(trial.prior.REPORT / "schedules" / f"{ident}.json")
    with timing.open(newline="") as stream:
        per_visit = {
            int(row["visit"]): float(row["selector_cpu_ms"]) * 1e-3
            for row in csv.DictReader(stream)
            if row["status"] == "processed"
        }
    if set(per_visit) != {visit for visit, _ in plan["visits"]}:
        raise ValueError("the selector sensitivity lacks an exact visit CPU trace")
    rows = []
    for policy, visits in (
        ("whole", plan["whole_original_visits"]),
        ("spread", plan["spread_original_visits"]),
        ("twelfth", [r["visit"] for r in older["selected"]]),
        ("original", list(per_visit)),
    ):
        cpu = sum(per_visit[visit] for visit in visits)
        rows.append(
            dict(
                id=ident,
                policy=policy,
                original_visits=len(visits),
                source_visit_original_cpu_s=cpu,
                source_original_cpu_per_capture_second=cpu / original["capture_span_s"],
                trace_file=str(timing.relative_to(ROOT)),
                trace_file_sha256=_sha(timing),
                trace_lock_sha256=SELECTOR_TIMING_LOCK,
            )
        )
    return rows


def detector_census(audit, membership):
    by_rf, totals = [], []
    for ident in membership["selected"]:
        row = audit[ident]
        for policy in trial.POLICIES:
            total = Counter()
            for rf, values in row["counts_per_rf"].items():
                stats = values[policy]
                total.update(stats)
                by_rf.append(
                    dict(
                        id=ident,
                        policy=policy,
                        rf_hz=int(rf),
                        assigned_original_rf_hz=row["assigned_rf_hz"],
                        **stats,
                    )
                )
            if total["visits"] != row["valid_visits"] or total["probes"] != 2 * total["visits"]:
                raise ValueError("a detector policy lost a valid physical pair")
            totals.append(
                dict(
                    id=ident,
                    policy=policy,
                    assigned_original_rf_hz=row["assigned_rf_hz"],
                    invalid_visits=row["invalid_visits"],
                    **total,
                )
            )
    return by_rf, totals


def geographic_rows(scored):
    positions = {(r["id"], r["arm"], r["method"]): r["error_km"] for r in scored}
    output = []
    for row in scored:
        fields = {k: v for k, v in row.items() if k not in ("rf_rms_hz", "frequency_score")}
        for policy in ("fast", "spread", "original"):
            before = positions.get((row["id"], row["arm"], f"rf_lane_{policy}"))
            after = row["error_km"]
            fields[f"delta_km_vs_{policy}"] = (
                after - before if after is not None and before is not None else None
            )
        output.append(fields)
    return output


def scores(rows, references, cohorts):
    scored = fixed.scored(rows, references)
    summary, methods = [], tuple(f"rf_lane_{policy}" for policy in trial.POLICIES)
    for cohort, ids in cohorts.items():
        for arm in ARMS:
            subset = [r for r in scored if r["id"] in ids and r["arm"] == arm]
            for method in (*methods, *ROLES):
                source = subset
                if method in ROLES:
                    source = [
                        dict(r, method=fixed.FOUR) for r in subset if r["method"] == "rf_lane_fast"
                    ]
                summary.append(fixed.summary_row(source, ids, cohort, arm, method))
    geography = geographic_rows(scored)
    frequency = [
        {k: row[k] for k in ("id", "method", "arm", "status", "rf_rms_hz", "frequency_score")}
        for row in scored
    ]
    calibration = staggered_benchmark.calibration_effects(scored, cohorts, methods)
    return geography, frequency, summary, calibration


def stage_figure(report, census, costs, membership):
    ids = membership["selected"]
    fig, axes = canvas(
        "Whole-RF routing and detector support",
        "Ten complete archived captures · two measured original-detector timing traces",
        "Positive probes pass the same margin gate. CPU sums cover the original branch. "
        "The dashed line marks 300 seconds of work on one core.",
    )
    by_id = {(r["id"], r["policy"]): r for r in census}
    for index, policy in enumerate(("whole", "spread")):
        offset = -0.17 + 0.34 * index
        positions = [i + offset for i in range(len(ids))]
        rows = [by_id[ident, policy] for ident in ids]
        for field, sign in (("gained_positive_probes", 1), ("lost_positive_probes", -1)):
            axes[0].barh(
                positions,
                [sign * row[field] for row in rows],
                height=0.28,
                color=COLORS[policy],
                alpha=1 if sign == 1 else 0.55,
            )
    axes[0].set(
        title="Positive probes versus full fast",
        xlabel="Lost ← probe count → gained",
        yticks=range(len(ids)),
        yticklabels=ids,
    )
    axes[0].axvline(0, color="#495B64", linewidth=0.8)
    axes[0].invert_yaxis()
    timing_ids = membership["anchors"]
    measured = {(r["id"], r["policy"]): r for r in costs}
    for index, policy in enumerate(("whole", "spread", "twelfth")):
        positions = [i - 0.24 + 0.24 * index for i in range(len(timing_ids))]
        values = [measured[ident, policy]["source_visit_original_cpu_s"] for ident in timing_ids]
        axes[1].barh(positions, values, height=0.20, color=COLORS[policy], label=LABELS[policy])
        for y, value in zip(positions, values, strict=True):
            axes[1].text(value + 8, y, f"{value:.0f}", fontsize=8, va="center")
    axes[1].axvline(300, color="#495B64", linewidth=0.8, linestyle="--")
    axes[1].set(
        title="Scheduled original-detector work",
        xlabel="Original detector CPU seconds",
        yticks=range(len(timing_ids)),
        yticklabels=timing_ids,
        xlim=(
            0,
            1.18
            * max(r["source_visit_original_cpu_s"] for r in costs if r["policy"] != "original"),
        ),
    )
    axes[1].invert_yaxis()
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        frameon=False,
        ncol=3,
        fontsize=9,
        loc="lower center",
        bbox_to_anchor=(0.55, 0.125),
    )
    for ext in ("png", "pdf"):
        fig.savefig(
            report / f"stage.{ext}",
            dpi=160,
            metadata={"CreationDate": None} if ext == "pdf" else {},
        )
    plt.close(fig)
    stage_rows = [
        dict(id=r["id"], policy=r["policy"], metric=metric, value=r[metric], unit="probes")
        for r in census
        if r["policy"] in ("whole", "spread")
        for metric in ("gained_positive_probes", "lost_positive_probes")
    ]
    stage_rows.extend(
        dict(
            id=r["id"],
            policy=r["policy"],
            metric="source_visit_original_cpu_s",
            value=r["source_visit_original_cpu_s"],
            unit="s",
        )
        for r in costs
    )
    csv_file(report / "stage.csv", stage_rows)
    names = (
        "source-lock.json",
        "packet-counts-by-rf.csv",
        "detector-cost.csv",
        "stage.csv",
        "stage.png",
        "stage.pdf",
    )
    save_json(
        report / "stage-figure-lock.json",
        dict(cases=ids, files={n: _sha(report / n) for n in names}),
    )
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="rf-lane-panel-stage",
            title="Whole-RF routing and detector support",
            boundary="Frozen exclusive RF assignment on complete archived stereo packets",
            sample="Ten complete recordings and two original detector CPU traces",
            note="Exact original visit sums estimate assigned work before pacing.",
            seal="stage-figure-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )


def position_figure(report, membership, fresh_spec):
    series = []
    for key, policy in zip(
        ("one", "one_native_factors", "stock", "all_visits"), trial.POLICIES, strict=True
    ):
        series.append(
            dict(
                key=key,
                file="guarded-positions.jsonl.gz",
                value=f"rf_lane_{policy}",
                native_field="paired_capture_sha256",
                label=LABELS[policy],
                match=list(fixed.BINDINGS),
            )
        )
    files = (
        "prediction-lock.json",
        "guarded-positions.jsonl.gz",
        "geographic.csv",
        "frequency.csv",
        "geographic-summary.csv",
        "publication-and-position-timing.csv",
        "calibration.csv",
        "original-v5-references.csv",
        *fresh_spec.values(),
    )
    save_json(
        report / "figure-lock.json",
        dict(
            cases=membership["selected"],
            files={name: _sha(report / name) for name in files},
        ),
    )
    save_json(
        report / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="rf-lane-panel",
                    method="rf_lane_whole",
                    scope="roof",
                    cases="sealed",
                    title="Position with the original GLRT on one physical RF",
                    caption=(
                        "Whole stereo visits are assigned exclusively to one detector. The "
                        "count-matched comparison uses the complete recorded visit census. New "
                        "compact fits use a 210 s service limit. Archived controls retain prior "
                        "first-attempt results and paired publication uses the 20 m tile guard."
                    ),
                    seal="figure-lock.json",
                    series=series,
                    provenance=list(files[:8]),
                    roof_references=fresh_spec,
                ),
            ],
        ),
    )
    screening_figures.generate(report / "charts", evidence=report)


def evaluate(report):
    membership, rows, audit = require_positions(report)
    before, guarded, receipts, retries = publish(report, rows)
    pack(report / "guarded-positions.jsonl.gz", guarded)
    with patch.object(prior_results, "REPORT", report):
        references, fresh_spec = prior_results.reference_rows(membership["selected"])
    cohorts = dict(
        all=membership["selected"],
        retained=membership["retained"],
        prospective=membership["prospective"],
        anchors=membership["anchors"],
    )
    geographic, frequency, summary, calibration = scores(guarded, references, cohorts)
    before_geography = geographic_rows(fixed.scored(before, references))
    if retries:
        csv_file(
            report / "archived-retries-geography.csv",
            [
                dict(row, prior_service_limit_s=420)
                for row in geographic_rows(fixed.scored(retries, references))
                if row["id"] in membership["retained"]
            ],
        )
    by_rf, census = detector_census(audit, membership)
    costs = source_costs(report, membership)
    csv_file(report / "geographic.csv", geographic)
    csv_file(report / "geographic-before-guard.csv", before_geography)
    csv_file(report / "frequency.csv", frequency)
    csv_file(report / "geographic-summary.csv", summary)
    csv_file(report / "calibration.csv", calibration)
    csv_file(report / "publication-and-position-timing.csv", receipts)
    csv_file(report / "packet-counts-by-rf.csv", by_rf)
    csv_file(report / "packet-counts.csv", census)
    csv_file(report / "detector-cost.csv", costs)
    csv_file(report / "detector-cost-selector-sensitivity.csv", selector_sensitivity(report, costs))
    stage_figure(report, census, costs, membership)
    position_figure(report, membership, fresh_spec)
    save_json(
        report / "score-lock.json",
        dict(
            prediction_lock_sha256=_sha(report / "prediction-lock.json"),
            exporter_sha256=_sha(Path(__file__)),
            files={p.name: _sha(p) for p in sorted(report.glob("*.csv"))},
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=trial.REPORT, type=local_output)
    evaluate(parser.parse_args().report)


if __name__ == "__main__":
    main()
