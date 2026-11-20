"""Audit the locked four-anchor experiment and render its matched position and support figures."""

import argparse
from collections import Counter
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..scoring import ARMS, ROLES, arm_outcome, distance_km
from ..variants import consistent_peaks as policy
from . import complete_detector_roster as official
from . import consistent_peaks_trial as trial
from . import factor_cross, hard_pilots_eval, screening_figures, staggered_reconstruction_trial
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

CATEGORIES = ("physical_gated", "physical_below_gate", "alias_only", "other_cfo", "absent_phase")
SUPPORT = (
    "original_winners",
    "retained_original",
    "latent_gated_original",
    "original_recovered",
    "original_lost",
    "changed_without_original_match",
    *CATEGORIES,
)


def physical_audit(capture, stock, selected, edits):
    if hard_pilots_eval.support(capture) != hard_pilots_eval.support(stock):
        raise ValueError("Original winner clock or probe validity differs from stock")
    if hard_pilots_eval.support(stock) != hard_pilots_eval.support(selected):
        raise ValueError("Selected factor changed recording metadata")
    by_index = {e["index"]: e for e in edits}
    counts = Counter({key: 0 for key in SUPPORT})
    altered = []
    sources = (d["source"]["probes"] for d in (capture, stock, selected))
    for index, (old, base, new) in enumerate(zip(*sources, strict=True)):
        metadata = hard_pilots_eval.metadata
        if metadata(old) != metadata(base) or metadata(base) != metadata(new):
            raise ValueError("Original and candidate probe order differ")
        edit = by_index.pop(index, None)
        before, after = base["candidates"], new["candidates"]
        expected = [c for j, c in enumerate(before) if edit is None or j not in edit["removed"]]
        if after != expected:
            raise ValueError("Selection changed a native candidate score, gate, rank or row order")
        winner = factor_cross.winner(old["candidates"])
        target = old["candidates"][winner] if winner is not None else None
        if target is None:
            if edit is not None:
                counts["changed_without_original_match"] += 1
                altered.append(dict(edit, original_category="no_original_gate"))
            continue
        counts["original_winners"] += 1
        prior = hard_pilots_eval.classify(target, before)
        subsequent = hard_pilots_eval.classify(target, after)
        matched, later = prior["actual_winner_matches"], subsequent["actual_winner_matches"]
        counts[prior["category"]] += 1
        counts["retained_original"] += matched
        counts["latent_gated_original"] += prior["category"] == "physical_gated" and not matched
        counts["original_recovered"] += later and not matched
        counts["original_lost"] += matched and not later
        counts["changed_without_original_match"] += edit is not None and not (matched or later)
        if edit is not None:
            altered.append(
                dict(
                    edit,
                    original_category=prior["category"],
                    matched_before=matched,
                    matched_after=later,
                )
            )
    if by_index:
        raise ValueError("Edited probe outside the authenticated recording")
    if counts["physical_gated"] != counts["retained_original"] + counts["latent_gated_original"]:
        raise ValueError("Physical gate ceiling disagrees with strict winner census")
    return dict(counts), altered


def audit(work, prepared, edits):
    counters, rows = {}, []
    for ident in hard_pilots_eval.HARD:
        case, _ = whole_iq.binding(ident)
        documents, bindings = hard_pilots_eval.resolve(ident, case)
        native = prepared[ident]
        if bindings["four"]["native_sha256"] != native["stock_native_sha256"]:
            raise ValueError(f"{ident} archived winner audit uses a different stock detector")
        selected = observed_factor(work, native, documents["four"], edits[ident])
        counts, changes = physical_audit(
            documents["capture"], documents["four"], selected, edits[ident]
        )
        counters[ident] = dict(counts=counts, changed=changes, sources=bindings)
        rows.append(dict(id=ident, **counts))
    return counters, rows


def observed_factor(work, native, stock, edits):
    if not edits and native["native_sha256"] == native["stock_native_sha256"]:
        return stock
    file = work / native["id"] / "selected/recording/native.json"
    return whole_iq.read(whole_iq.checked(file, native["native_sha256"]))


def scores(selected, stock):
    _, references = held_references(None, trial.CASES)
    return score_rows(selected, stock, references)


def score_rows(selected, stock, references):
    geography, frequency = [], []
    for ref in references:
        ident = ref["id"]
        known = stock[ident]
        candidate = selected[ident]
        for row in (known, candidate):
            result = row["result"]
            for arm in ARMS:
                point = result.get("arms", {}).get(arm, {})
                geography.append(
                    dict(
                        id=ident,
                        method=row["method"],
                        arm=arm,
                        status=arm_outcome(result, point)[0],
                        error_km=distance_km(point.get("latlon"), ref["truth"]),
                    )
                )
                frequency.append(
                    dict(
                        id=ident,
                        method=row["method"],
                        arm=arm,
                        rf_rms_hz=point.get("rf_rms_hz"),
                        frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                    )
                )
        for role in ROLES:
            for arm in ARMS:
                result = ref["reference"][role][arm]
                geography.append(
                    dict(
                        id=ident,
                        method=f"capture-era-v5/{role}",
                        arm=arm,
                        status=result["status"],
                        error_km=result.get("error_km"),
                    )
                )
                frequency.append(
                    dict(
                        id=ident,
                        method=f"capture-era-v5/{role}",
                        arm=arm,
                        rf_rms_hz=result.get("rf_rms_hz"),
                        frequency_score=None,
                    )
                )
    return geography, frequency


def stage_figure(out, rows, support):
    sample = [p["id"] for p in rows]
    hard = [p["id"] for p in support]
    fig = Figure(figsize=(12, 6.1), layout="constrained")
    FigureCanvasAgg(fig)
    a, b = fig.subplots(1, 2)
    keep = [max(r["forecast_opportunity"] - r["winner_supported"], 0) for r in rows]
    a.barh(sample, [r["winner_supported"] for r in rows], label="Incumbent corroborated")
    a.barh(sample, keep, left=[r["winner_supported"] for r in rows], label="Other abstention")
    a.set_title("Probes with two valid forecasts")
    a.set_xlabel(f"Probes ({sum(r['changed_winners'] for r in rows)} winner changes)")
    a.invert_yaxis()
    b.barh(hard, [s["latent_gated_original"] for s in support], label="Hidden, already gated")
    b.barh(
        hard,
        [s["original_winners"] - s["physical_gated"] for s in support],
        left=[s["latent_gated_original"] for s in support],
        label="Unavailable at existing gate",
    )
    b.set_title("Missed original physical winners on the hard six")
    b.set_xlabel("Original winners missed by the four-region winner rule")
    b.invert_yaxis()
    for ax in (a, b):
        ax.grid(axis="x", alpha=0.24)
        ax.set_axisbelow(True)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), frameon=False, ncols=2)
    for ext in ("png", "pdf"):
        fig.savefig(out / f"stage.{ext}", dpi=150)


def publish(work, out):
    measured_path = trial.REPORT / "prediction-lock.json"
    measured = whole_iq.read(measured_path)
    if measured["cases"] != list(trial.CASES):
        raise ValueError("Blind compact predictions differ from the frozen hard/control roster")
    for file, digest in measured["files"].items():
        whole_iq.checked(trial.REPORT / file, digest)
    prepared = whole_iq.read(trial.REPORT / "prepared.json")
    edits = whole_iq.read(trial.REPORT / "edits.json")
    selected = official.select(
        rows_from(trial.REPORT / "positions.jsonl.gz"), policy.METHOD, trial.CASES
    )
    _, _, stock, _ = staggered_reconstruction_trial.load_controls()
    stage, table = [], []
    for ident in trial.CASES:
        original = stock[ident]
        fit = selected[ident]
        source = prepared[ident]
        official.same_capture(original, fit)
        if (
            fit["native_sha256"] != source["native_sha256"]
            or original["native_sha256"] != source["stock_native_sha256"]
        ):
            raise ValueError("An unchanged detector input or actual prepared input differs")
        table.extend((original, fit))
        counts = source["counts"]
        keys = (
            "probes",
            "positive",
            "ambiguous",
            "incomplete_anchors",
            "inconsistent_anchors",
            "forecast_opportunity",
            "winner_supported",
            "ambiguous_alternate",
            "no_alternate",
            "changed_winners",
            "withheld_candidates",
        )
        stage.append(
            dict(
                id=ident,
                cohort=source["cohort"],
                **{name: counts.get(name, 0) for name in keys},
                selection_cpu_s=source["selection_cost"]["cpu_s"],
                selection_wall_s=source["selection_cost"]["wall_s"],
                identical_native=fit["native_sha256"] == original["native_sha256"],
                compact_status=fit["result"]["status"],
                supervisor_wall_s=fit["supervisor_wall_s"],
            )
        )
    support, physical = audit(work, prepared, edits)
    physical_by_case = {row["id"]: row for row in physical}
    for row in stage:
        case = physical_by_case.get(row["id"])
        row.update(
            hidden_gated_original=None if case is None else case["latent_gated_original"],
            original_unavailable_at_gate=(
                None if case is None else case["original_winners"] - case["physical_gated"]
            ),
        )
    actual_geo, rf = scores(selected, stock)
    out.mkdir(parents=True, exist_ok=True)
    pack(out / "chart-positions.jsonl.gz", table)
    for name, rows in (
        ("stage", stage),
        ("physical-support", physical),
        ("geographic", actual_geo),
        ("frequency-fit", rf),
    ):
        csv_file(out / f"{name}.csv", rows)
    save_json(out / "support-audit.json", support)
    stage_figure(out, stage, physical)
    unchanged = sum(r["identical_native"] for r in stage)
    changes = sum(r["changed_winners"] for r in stage)
    stage_spec = dict(
        version=1,
        id="consistent-peaks",
        title="Four-anchor native winner selection",
        boundary="Complete stored four-region factors → batch selection → compact",
        sample="Six frozen hard recordings and two controls; audit after prediction",
        note=f"{unchanged}/{len(stage)} input digests were unchanged. {changes} winner changes.",
        image="stage.png",
        pdf="stage.pdf",
        csv="stage.csv",
        seal="figure-lock.json",
    )
    save_json(out / "stage-figure.json", stage_spec)
    evidence = (
        "stage.csv",
        "stage.png",
        "stage.pdf",
        "stage-figure.json",
        "physical-support.csv",
        "support-audit.json",
        "geographic.csv",
        "frequency-fit.csv",
    )
    position_spec = dict(
        id="consistent-peaks",
        method=policy.METHOD,
        scope="roof",
        cases="sealed",
        title="Four-anchor winner selection on stored four-region factors",
        caption=(
            f"{len(stage)} fresh compact replays with {changes} winner changes and {unchanged} "
            "unchanged native inputs. Same recorded roof, original v5 roles and both c arms."
        ),
        seal="figure-lock.json",
        provenance=list(evidence),
        series=[
            dict(
                key=key,
                file="chart-positions.jsonl.gz",
                value=method,
                label=label,
                native_field=official.BINDINGS[0],
                match=list(official.BINDINGS),
            )
            for key, method, label in (
                ("one", policy.METHOD, "Four-anchor selector"),
                ("stock", official.FOUR, "Fixed four regions"),
            )
        ],
    )
    save_json(out / "figures.json", dict(version=2, charts=[position_spec]))
    files = (*evidence, "chart-positions.jsonl.gz", "figures.json")
    source_paths = (
        measured_path,
        official.REPORT / "all-figure-lock.json",
        Path(__file__),
        ROOT / "tests/pipeline_eval/test_consistent_peaks.py",
    )
    save_json(
        out / "figure-lock.json",
        dict(
            cases=trial.CASES,
            files={n: _sha(out / n) for n in files},
            sources={str(p.relative_to(ROOT)): _sha(p) for p in source_paths},
        ),
    )
    screening_figures._chart(out, position_spec, version=2)
    screening_figures.generate(out / "charts", evidence=out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    publish(args.work, args.out)
