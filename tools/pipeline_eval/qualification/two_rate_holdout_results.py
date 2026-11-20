"""Score and render the sealed eight-recording two-rate factor replay."""

import argparse
import csv
import gzip
from collections import Counter
from hashlib import sha256
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..scoring import ARMS, ROLES, distribution, validate_result
from . import complete_detector_roster as fixed
from . import screening_figures, staggered_benchmark
from . import two_rate_holdout_trial as trial
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .scout_stage_figures import canvas

REPORT = trial.REPORT
LABELS = {
    "wide": "Fast four",
    "replace": "Whole-visit replacement",
    "fill": "Negative-lane fill",
    "original": "Full original compact",
}
TIMINGS = {
    "DS26-0237": (
        "original-support/prepared-waveform",
        "f84c7da2d6953cc509e310bca1480540ab47d30abdf245eab259f6300c151d75",
    ),
    "DS29-0082": (
        "antenna-confirmation/capture-whole",
        "4d7db8aa8d4613cc3f2a6ae1222bbc0d1d06dabe20161a12eef43b32575e7afb",
    ),
}
FRESH_FIGURE_SHA = "96f387396bdebf354cd5aab753df85f2fb75f58ebe941f6ee2463794271682ac"
read = whole_iq.read
checked = whole_iq.checked


def cohorts(membership):
    all_ids = membership["selected"]
    anchors = membership["timing_anchors"]
    sample = [ident for ident in all_ids if ident not in anchors]
    fresh = set(membership["prior_roster_membership"]["fresh"])
    return dict(
        all=all_ids,
        anchors=anchors,
        sampled=sample,
        sampled_held=[ident for ident in sample if ident not in fresh],
        sampled_fresh=[ident for ident in sample if ident in fresh],
        ds26=[ident for ident in all_ids if ident.startswith("DS26-")],
        ds29=[ident for ident in all_ids if ident.startswith("DS29-")],
    )


def predictions(membership, plan, source_sha):
    reuse = checked(REPORT / "reused-controls.jsonl.gz", plan["reused_controls_sha256"])
    rows = trial.rows_from(reuse)
    audited = read(checked(REPORT / "packet-audit.json", plan["packet_audit_sha256"]))
    jobs = plan["jobs"]
    for batch in sorted({row["batch"] for row in jobs}):
        receipt = read(REPORT / f"batch-{batch}-lock.json")
        if receipt["source_lock_sha256"] != source_sha:
            raise ValueError("terminal batch ran on a different frozen plan")
        archive = checked(REPORT / f"batch-{batch}-positions.jsonl.gz", receipt["positions_sha256"])
        completed = trial.rows_from(archive)
        expected = {(r["id"], r["condition"]): r for r in jobs if r["batch"] == batch}
        if len(completed) != len(expected):
            raise ValueError("batch omitted a terminal result")
        for row in completed:
            job = expected.pop((row["id"], row["condition"]))
            if any(row[k] != v for k, v in job.items()):
                raise ValueError("terminal result does not match its compact-fit request")
            if row["terminal"] == "success" and not row["position_resources"]:
                raise ValueError("successful compact fit lacks its charged measurements")
        rows.extend(completed)
    indexed = {(r["id"], r["condition"]): r for r in rows}
    ordered = [(ident, policy) for ident in membership["selected"] for policy in trial.POLICIES]
    if indexed.keys() != set(ordered) or len(indexed) != len(rows):
        raise ValueError("a recording-policy pair is missing or repeated")
    initial = [indexed[key] for key in ordered]
    for receipt_path in sorted(REPORT.glob("retry-*-lock.json")):
        stem = receipt_path.name.removesuffix("-lock.json")
        receipt = read(receipt_path)
        recovery = read(checked(REPORT / f"{stem}-plan.json", receipt["retry_plan_sha256"]))
        archive = checked(REPORT / f"{stem}-positions.jsonl.gz", receipt["positions_sha256"])
        expected_retry = {(r["id"], r["condition"]): r for r in recovery["retries"]}
        completed = trial.rows_from(archive)
        if recovery["source_lock_sha256"] != source_sha or len(completed) != len(expected_retry):
            raise ValueError("retry result ledger differs from the first-run plan")
        for row in completed:
            key = row["id"], row["condition"]
            planned = expected_retry.pop(key)
            first = indexed[key]
            if (
                first["terminal"] != "timeout"
                or "initial_terminal" in first
                or any(row[k] != v for k, v in planned.items())
                or row["initial_cpu"] != first["cpu"]
                or any(row[k] != first[k] for k in ("prepared_request_sha256", "native_sha256"))
                or (row["terminal"] == "success" and not row["position_resources"])
            ):
                raise ValueError("retried fit changed its authenticated numerical request")
            indexed[key] = dict(
                row, initial_terminal=first["terminal"], retry_s=recovery["limit_s"]
            )
    for row in indexed.values():
        audit = audited[row["id"]]
        if any(row[k] != audit[k] for k in fixed.BINDINGS):
            raise ValueError("compact fits have different source authority")
        validate_result(row["result"])
        if row["result"]["status"] in ("ok", "withheld") and set(row["result"]["arms"]) != set(
            ARMS
        ):
            raise ValueError("a terminal numerical fit lacked a calibration arm")
    return [indexed[key] for key in ordered], initial, audited


def attempt_counts(first, final, group_ids):
    for group, ids in group_ids.items():
        for policy in trial.POLICIES:
            initial = [r for r in first if r["condition"] == policy and r["id"] in ids]
            reruns = [
                r for r in final if r["condition"] == policy and r["id"] in ids and "retry_s" in r
            ]
            status = Counter(r["result"]["status"] for r in initial)
            retry_status = Counter(r["result"]["status"] for r in reruns)
            reused = sum("reused_prediction_lock_sha256" in r for r in initial)
            yield dict(
                cohort=group,
                policy=policy,
                scheduled=len(initial),
                reused=reused,
                submitted_first_attempts=len(initial) - reused,
                first_ok=status["ok"],
                first_withheld=status["withheld"],
                first_timed_out=status["timed_out"],
                first_failed=status["failed"],
                first_unavailable=status["unavailable"],
                retry_attempted=len(reruns),
                retry_ok=retry_status["ok"],
                retry_withheld=retry_status["withheld"],
                retry_timed_out=retry_status["timed_out"],
                retry_failed=retry_status["failed"],
            )


def reference_rows(ids):
    frozen, frozen_metadata = screening_figures._roof_authority()
    selected = {ident: frozen[ident] for ident in ids if ident in frozen}
    for ident, reference in selected.items():
        meta = frozen_metadata[ident]
        if any(k not in reference["reference"] for k in ROLES):
            raise ValueError(f"frozen v5 roles incomplete for {meta['id']}")
    receipt = read(checked(trial.roster.FRESH / "all-figure-lock.json", FRESH_FIGURE_SHA))
    authority = read(fixed.member(trial.roster.FRESH, receipt, fixed.REFS["authority"]))["cases"]
    positions = trial.rows_from(
        fixed.member(trial.roster.FRESH, receipt, fixed.REFS["predictions"])
    )
    spec, fresh = staggered_benchmark.export_references(REPORT, "fresh", ids, authority, positions)
    for row in positions:
        if row["id"] not in fresh:
            continue
        for arm in ARMS:
            fit = row["result"]["arms"][arm]
            fresh[row["id"]]["reference"][row["method"]][arm].update(
                rf_rms_hz=fit.get("rf_rms_hz"),
                frequency_score=row["result"]["metrics"].get(f"{arm}_frequency_score"),
            )
    selected.update(fresh)
    if selected.keys() != set(ids):
        raise ValueError("position scoring requires four original v5 roles for each recording")
    table = []
    for ident in ids:
        for role in ROLES:
            for arm in ARMS:
                fit = selected[ident]["reference"][role][arm]
                table.append(
                    dict(
                        id=ident,
                        role=role,
                        arm=arm,
                        status=fit["status"],
                        error_km=fit["error_km"],
                        rf_rms_hz=fit.get("rf_rms_hz"),
                        frequency_score=fit.get("frequency_score"),
                    )
                )
    csv_file(REPORT / "original-v5-references.csv", table)
    return selected, spec


def analyze(rows, refs, membership, audit):
    results = fixed.scored(rows, refs)
    by = {(r["id"], r["method"], r["arm"]): r for r in results}
    count_rows = []
    totals = {}
    for ident in membership["selected"]:
        totals[ident] = {p: Counter() for p in trial.POLICIES}
        for rf, counts in audit[ident]["counts_per_rf"].items():
            for policy in trial.POLICIES:
                stats = counts[policy]
                totals[ident][policy].update(stats)
                count_rows.append(
                    dict(
                        id=ident,
                        physical_rf_hz=int(rf),
                        policy=policy,
                        **stats,
                        net_passing_candidates_vs_fast=stats["passing_candidates"]
                        - counts["wide"]["passing_candidates"],
                    )
                )
    position = {(r["id"], r["method"]): r for r in rows}
    for row in results:
        ident, method, arm = [row[k] for k in ("id", "method", "arm")]
        policy = method.removeprefix("two_rate_")
        error, original_km = row["error_km"], row["baseline_km"]
        fast = by[ident, "two_rate_wide", arm]["error_km"]
        stats = totals[ident][policy]
        fit = position[ident, method]
        resource = fit.get("position_resources") or {}
        row.update(
            policy=policy,
            reference_cohort="fresh"
            if ident in membership["prior_roster_membership"]["fresh"]
            else "held",
            timing_anchor=ident in membership["timing_anchors"],
            returned=error is not None,
            delta_pct_original=100 * (error / original_km - 1)
            if error is not None and original_km
            else None,
            delta_km_fast=error - fast if error is not None and fast is not None else None,
            original_donor_probes=stats["original_probes"],
            passing_probes=stats["positive_probes"],
            gained_positive_probes=stats["gained_positive_probes"],
            lost_positive_probes=stats["lost_positive_probes"],
            net_passing_candidates_vs_fast=stats["passing_candidates"]
            - totals[ident]["wide"]["passing_candidates"],
            wall_position_s=resource.get("wall_s"),
            cpu_position_s=resource.get("cpu_s"),
            peak_charged_bytes=resource.get("peak_bytes"),
            reused=bool(fit.get("reused_prediction_lock_sha256")),
            initial_terminal=fit.get("initial_terminal", fit.get("terminal")),
            retry_s=fit.get("retry_s"),
        )
    return results, count_rows, totals


def original_cost(ident, membership):
    folder, pin = TIMINGS[ident]
    folder = fixed.SCREEN / folder
    lock = read(checked(folder / "timing-lock.json", pin))
    seal = read(checked(folder / "prediction-lock.json", lock["files"]["prediction-lock.json"]))
    timing = fixed.member(folder, seal, "timing.csv")
    if _sha(timing) != lock["files"][timing.name]:
        raise ValueError("original timing and prediction seals disagree")
    source = read(fixed.member(folder, seal, "source-lock.json"))
    if source["id"] != ident:
        raise ValueError("original cost trace names a different physical capture")
    raw = fixed.member(folder, seal, "native.json.gz")
    document = trial.roster.stock_document(
        dict(
            path=str(raw),
            file_sha256=_sha(raw),
            native_sha256=read(fixed.member(folder, seal, "audit.json"))["raw"][
                "measured_native_sha256"
            ],
        )
    )
    if document["source"]["input_manifest_sha256"] != membership["physical_manifest_sha256"][ident]:
        raise ValueError("original cost trace used a different physical manifest")
    scheduled = read(
        checked(REPORT / "schedules" / f"{ident}.json", membership["schedule_sha256"][ident])
    )
    selected = {row["visit"] for row in scheduled["selected"]}
    with timing.open(newline="") as fh:
        all_rows = list(csv.DictReader(fh))
    valid = {int(row["visit"]): row for row in all_rows if row["status"] == "processed"}
    visits = [
        visit for visit, _ in trial.selective_capture.visit_pairs(document["source"]["probes"])
    ]
    clocks = document["delivery_clocks"]
    if set(valid) != set(visits) or not selected <= set(valid) or len(all_rows) != len(clocks):
        raise ValueError("original cost trace lacks exact physical visit timing coverage")
    duration = (clocks[-1]["monotonic_ns"] - clocks[0]["monotonic_ns"]) * 1e-9
    cpu = [float(row["cpu_ms"]) for row in valid.values()]
    per_selected = [float(valid[i]["cpu_ms"]) for i in sorted(selected)]
    sparse = sum(per_selected) * 1e-3
    full = sum(cpu) * 1e-3
    return dict(
        id=ident,
        full_valid_visits=len(valid),
        scheduled_original_visits=len(selected),
        capture_span_s=duration,
        measured_full_original_detector_cpu_s=full,
        measured_full_original_visit_cpu_p50_ms=distribution(cpu)["p50"],
        measured_full_original_visit_cpu_p95_ms=distribution(cpu)["p95"],
        forecast_selected_original_detector_cpu_s=sparse,
        forecast_selected_original_cpu_pct_full=100 * sparse / full,
        forecast_selected_original_fraction_of_one_core=sparse / duration,
        trace_file=str(timing.relative_to(ROOT)),
        trace_file_sha256=_sha(timing),
        trace_lock_sha256=pin,
    )


def stage_figure(membership, totals, costs):
    fig, axes = canvas(
        "Sparse original packets change fast-detector support",
        "Eight complete archived recordings · exact physical lanes and clocks",
        "Original CPU totals were measured in separate complete raw replays. The selected-visit "
        "CPU sums forecast incremental detector work. They exclude wait, decoding and position.",
    )
    ids = membership["selected"]
    labels = ("Whole-visit replacement", "Negative-lane fill")
    colors = ("#A96124", "#146C5F")
    for j, (policy, label, color) in enumerate(
        zip(("replace", "fill"), labels, colors, strict=True)
    ):
        offsets = [i - 0.17 + 0.34 * j for i in range(len(ids))]
        for field, sign in (("gained_positive_probes", 1), ("lost_positive_probes", -1)):
            axes[0].barh(
                offsets,
                [sign * totals[i][policy][field] for i in ids],
                height=0.28,
                color=color,
                label=label if sign == 1 else None,
                alpha=1 if sign == 1 else 0.55,
            )
    axes[0].axvline(0, color="#44545D", lw=0.8)
    axes[0].set(
        title="Positive physical probes",
        yticks=range(len(ids)),
        yticklabels=ids,
        xlabel="Lost ← relative to fast four → gained",
    )
    axes[0].invert_yaxis()
    axes[0].legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.175), ncol=2, frameon=False, fontsize=8
    )
    for j, (field, label, color) in enumerate(
        (
            ("measured_full_original_detector_cpu_s", "Measured full original", "#54646A"),
            (
                "forecast_selected_original_detector_cpu_s",
                "Forecast selected donor work",
                "#34769F",
            ),
        )
    ):
        vals = [r[field] for r in costs]
        offsets = [i - 0.16 + 0.32 * j for i in range(len(costs))]
        axes[1].barh(offsets, vals, height=0.24, label=label, color=color)
        for offset, value in zip(offsets, vals, strict=True):
            axes[1].text(value + 30, offset, f"{value:,.0f}", va="center", fontsize=9)
    axes[1].set(
        title="Original detector work",
        yticks=range(len(costs)),
        yticklabels=[r["id"] for r in costs],
        xlabel="Detector CPU seconds",
        xlim=(0, 3500),
    )
    axes[1].invert_yaxis()
    axes[1].legend(frameon=False, fontsize=8, loc="lower right")
    for extension in ("png", "pdf"):
        fig.savefig(
            REPORT / f"stage.{extension}",
            dpi=160,
            metadata={"CreationDate": None} if extension == "pdf" else {},
        )
    plt.close(fig)
    stage_rows = []
    for ident in ids:
        for policy in ("replace", "fill"):
            stage_rows.extend(
                dict(
                    id=ident,
                    policy=policy,
                    kind="counted packets",
                    metric=key,
                    value=val,
                    unit="probes",
                )
                for key, val in totals[ident][policy].items()
                if key in {"gained_positive_probes", "lost_positive_probes"}
            )
    for cost in costs:
        for kind in ("measured_full_original", "forecast_selected_original"):
            stage_rows.append(
                dict(
                    id=cost["id"],
                    policy="original",
                    kind=kind,
                    metric="detector_cpu",
                    value=cost[f"{kind}_detector_cpu_s"],
                    unit="s",
                )
            )
    csv_file(REPORT / "stage.csv", stage_rows)
    names = (
        "prediction-lock.json",
        "packet-gains-by-rf.csv",
        "cost.csv",
        "stage.csv",
        "stage.png",
        "stage.pdf",
    )
    save_json(
        REPORT / "stage-figure-lock.json",
        dict(cases=ids, files={n: _sha(REPORT / n) for n in names}),
    )
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="two-rate-holdout-stage",
            title="Original packets in sparse two-rate replay",
            boundary="Archived fast GLRT and sampled original packets before compact positioning",
            sample="Eight complete recordings and two original detector cost traces",
            note="The measured traces cover full original replay. Sparse CPU sums are forecasts.",
            seal="stage-figure-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )


def chart_spec(first, retries, fresh_spec):
    filename = "positions-first.jsonl.gz" if first else "positions.jsonl.gz"
    scores = "first-attempt-scores.csv" if first else "scores.csv"
    chart = dict(
        id="two-rate-holdout-first-attempt" if first else "two-rate-holdout",
        method="two_rate_fill",
        scope="roof",
        cases="sealed",
        title=(
            "Two-rate replay at the ordinary compact deadline"
            if first
            else "Two-rate accuracy with same-input timeout retries"
        ),
        seal="figure-lock.json",
        provenance=[
            "prediction-lock.json",
            scores,
            "cost.csv",
            "packet-audit.json",
            "fit-attempts.csv",
        ],
        caption=(
            "First compact runs used a 210 s outer service limit. The chart retains "
            "their timeouts and includes authenticated reused controls."
            if first
            else "Accuracy shown with same-input retries at a 420 s outer service limit. "
            "See the first-attempt chart for the 210 s terminal outcomes."
        ),
        series=[
            dict(
                key=key,
                file=filename,
                value=f"two_rate_{policy}",
                native_field="paired_capture_sha256",
                label=(
                    f"{LABELS[policy]} ({retries[policy]} retried)"
                    if retries[policy] and not first
                    else LABELS[policy]
                ),
                match=list(fixed.BINDINGS),
            )
            for key, policy in zip(
                ("one", "stock", "one_native_factors", "all_visits"),
                ("fill", "wide", "replace", "original"),
                strict=True,
            )
        ],
        roof_references=fresh_spec,
    )
    return chart


def render(membership, fresh_spec, positions):
    retries = Counter(row["condition"] for row in positions if "retry_s" in row)
    charts = [chart_spec(first, retries, fresh_spec) for first in (True, False)]
    files = [
        *dict.fromkeys(name for chart in charts for name in chart["provenance"]),
        *fresh_spec.values(),
        "positions.jsonl.gz",
        "positions-first.jsonl.gz",
        "summary.csv",
        "first-attempt-summary.csv",
        "calibration.csv",
        "original-v5-references.csv",
    ]
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=membership["selected"], files={name: _sha(REPORT / name) for name in files}),
    )
    save_json(REPORT / "figures.json", dict(version=2, charts=charts))
    screening_figures.generate(REPORT / "charts", evidence=REPORT)


def score():
    membership = trial.inventory()
    plan_path = REPORT / "source-lock.json"
    plan = read(plan_path)
    source_sha = _sha(plan_path)
    positions, initial, audit = predictions(membership, plan, source_sha)
    group_ids = cohorts(membership)
    pack(REPORT / "positions.jsonl.gz", positions)
    pack(REPORT / "positions-first.jsonl.gz", initial)
    members = (
        "membership-lock.json",
        "source-lock.json",
        "packet-audit.json",
        "positions.jsonl.gz",
        "positions-first.jsonl.gz",
        "reused-controls.jsonl.gz",
        "PROTOCOL.md",
    )
    files = {name: _sha(REPORT / name) for name in members}
    for sub in ("schedules", "lineage", "logs", "stock"):
        files.update(
            {str(p.relative_to(REPORT)): _sha(p) for p in sorted((REPORT / sub).iterdir())}
        )
    files.update({p.name: _sha(p) for p in sorted(REPORT.glob("batch-*"))})
    files.update({p.name: _sha(p) for p in sorted(REPORT.glob("retry-*"))})
    executed = REPORT / "executed-lock.json"
    if executed.is_file():
        original = read(executed)
        if original["source_lock_sha256"] != source_sha:
            raise ValueError("the executed source snapshot belongs to a different run")
        files[executed.name] = _sha(executed)
        for name, source in original["files"].items():
            archive = checked(REPORT / name, source["archive_sha256"])
            digest = sha256(gzip.decompress(archive.read_bytes())).hexdigest()
            if digest != source["source_sha256"] or digest != plan["sources"][source["path"]]:
                raise ValueError("archived execution code differs from the frozen source lock")
            files[name] = _sha(archive)
    save_json(REPORT / "prediction-lock.json", dict(cases=membership["selected"], files=files))
    refs, fresh_spec = reference_rows(membership["selected"])
    scores, per_rf, totals = analyze(positions, refs, membership, audit)
    first_scores, _, _ = analyze(initial, refs, membership, audit)
    csv_file(REPORT / "scores.csv", scores)
    csv_file(REPORT / "first-attempt-scores.csv", first_scores)
    csv_file(REPORT / "packet-gains-by-rf.csv", per_rf)
    csv_file(REPORT / "fit-attempts.csv", list(attempt_counts(initial, positions, group_ids)))
    methods = [f"two_rate_{p}" for p in trial.POLICIES]
    for path, score_rows in (("summary.csv", scores), ("first-attempt-summary.csv", first_scores)):
        reference_control_rows = [
            dict(row, method=fixed.FOUR) for row in score_rows if row["policy"] == "wide"
        ]
        csv_file(
            REPORT / path,
            [
                fixed.summary_row(
                    [
                        r
                        for r in (reference_control_rows if method in ROLES else score_rows)
                        if r["id"] in ids and r["arm"] == arm
                    ],
                    ids,
                    label,
                    arm,
                    method,
                )
                for label, ids in group_ids.items()
                for arm in ARMS
                for method in (*methods, *ROLES)
            ],
        )
    csv_file(
        REPORT / "calibration.csv",
        staggered_benchmark.calibration_effects(scores, group_ids, methods),
    )
    costs = [original_cost(ident, membership) for ident in membership["timing_anchors"]]
    csv_file(REPORT / "cost.csv", costs)
    stage_figure(membership, totals, costs)
    render(membership, fresh_spec, positions)
    save_json(
        REPORT / "score-lock.json",
        dict(
            prediction_lock_sha256=_sha(REPORT / "prediction-lock.json"),
            exporter_sha256=_sha(Path(__file__)),
            fresh_reference_lock_sha256=FRESH_FIGURE_SHA,
            files={p.name: _sha(p) for p in sorted(REPORT.glob("*.csv"))},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=local_output, default=REPORT)
    args = parser.parse_args()
    REPORT = trial.REPORT = args.report
    score()
