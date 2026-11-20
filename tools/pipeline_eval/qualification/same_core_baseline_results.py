"""Seal, audit and score the four same-core original/compact v5 pairs."""

import argparse
import ast
import json
from pathlib import Path
from zipfile import ZipFile

from ..__main__ import local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from . import full_receiver_comparison as common
from . import same_core_baseline as trial
from .native_agreement_cascade_eval import compact_wall
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

REPORT, ORIGINAL, COMPACT = trial.REPORT, trial.ORIGINAL, trial.COMPACT
CHART = "same-core-original-compact-v5-roof4"
ARCHIVES = {ORIGINAL: "original-positions.jsonl.gz", COMPACT: "positions.jsonl.gz"}
SHARED = ("native_preparation", "initial", "conservative", "family", "signed", "cavity")
RENDER = ("plot_evidence", "png_rendering")
LATE = (
    "recovery_catalogue",
    "inventory",
    "predictive",
    "numerical",
    "gap",
    "residual",
    "residual_screen",
    "addition",
    "incumbent",
    "ranking",
    "admission",
    "final",
)


def tagged_map(value):
    if not isinstance(value, list) or len(value) != 2 or value[0] != "map":
        raise ValueError("original audit did not serialize a scientific record")
    return dict(value[1])


def original_audit(folder, result):
    archive = folder / trial.original_v5.EVIDENCE
    work = common.read(folder / "worker-result.json")
    verified = common.read(folder / "validated-archive.json")
    if (
        not verified["validated"]
        or verified["artifact"] != work["artifact"]
        or verified["request_sha256"] != work["request_sha256"]
        or common.sha(archive) != work["artifact"]["sha256"].removeprefix("sha256:")
        or result["evidence"]["sha256"] != work["artifact"]["sha256"]
    ):
        raise ValueError("ordinary original worker archive failed provenance checks")
    with ZipFile(archive) as files:
        document = json.loads(files.read("values.json"))
    payload = tagged_map(document["tree"])
    audit = tagged_map(payload["audit"])
    initial = tagged_map(audit["initial"])
    choices = [tagged_map(x) for x in initial["choices"][1]]
    rounds = {}
    for arm in ARMS:
        rounds[arm] = [
            len(tagged_map(tagged_map(c["arms"])[arm])["phase_rounds"][1]) for c in choices
        ]
    return dict(
        output_bytes=archive.stat().st_size,
        output_sha256=common.sha(archive),
        output_path=str(archive),
        png_count=len(document["figures"]),
        original_initial_branches=initial["fully_fitted_hypotheses"],
        original_initial_unique_proposals=initial["unique_RF_hypotheses"],
        original_initial_phase_rounds=rounds,
        native_counts=work["native_counts"],
        backend_work=work["work"],
        archive_validated_sha256=common.sha(folder / "validated-archive.json"),
    )


def same_endpoint(fresh, legacy):
    d = distance_km(fresh.get("latlon"), legacy.get("latlon"))
    a, b = fresh.get("rf_rms_hz"), legacy.get("rf_rms_hz")
    return dict(
        position_difference_km=d,
        position_exact=fresh.get("latlon") == legacy.get("latlon"),
        rf_difference_hz=a - b if a is not None and b is not None else None,
        rf_exact=a == b,
    )


def missing_result(reason, status="missing"):
    return trial.v5_lean._no_fix(reason, status=status)


def read_attempt(folder, binding, ident, method, cpu, order, source_sha):
    report = folder / "measurement.json"
    authority = dict(
        binding,
        id=ident,
        method=method,
        cpu=cpu,
        order=order,
        source_lock_sha256=source_sha,
    )
    if not report.is_file():
        active = any(
            (folder / name).is_file()
            for name in (
                "v5-worker.log",
                "worker.log",
                "experimental-request.json",
                "request.json",
            )
        )
        return dict(
            authority,
            resources={},
            result=missing_result(
                "Materialized worker did not return a sealed receipt"
                if active
                else "Scheduled ordinary worker did not start",
                "failed" if active else "missing",
            ),
        )
    receipt = common.read(report)
    common.require_fields(receipt, authority)
    validate_result(receipt["result"])
    return receipt


def seal(plan_path, work, output):
    plan = common.read(plan_path)
    if trial.sources() != plan["sources"]:
        raise ValueError("the pinned ordinary source changed")
    refs, inventory = _frozen_roof()
    inputs = common.full_roster(refs, inventory)
    canonical, ledger = common.compact_predictions(inputs, refs, audit_archive=True)
    cases, strata = trial.selection(refs, canonical)
    if cases != plan["cases"] or strata != plan["strata"] or ledger != plan["stock"]:
        raise ValueError("the original workload strata or canonical archive changed")
    rows = {m: [] for m in ARCHIVES}
    prior_sha = common.sha(plan_path)
    for pin, item in plan["schedule"].items():
        ident = item["id"]
        binding = plan["bindings"][ident]
        for order, method in enumerate(item["methods"]):
            folder = work / ident / method
            row = read_attempt(folder, binding, ident, method, int(pin), order, prior_sha)
            result = row["result"]
            if result["status"] == "ok":
                legacy = (
                    refs[ident]["reference"]["baseline"]
                    if method == ORIGINAL
                    else (canonical[ident]["result"]["arms"])
                )
                row["legacy"] = {a: same_endpoint(result["arms"][a], legacy[a]) for a in ARMS}
                if method == ORIGINAL:
                    row["original_work"] = original_audit(folder, result)
                else:
                    row["canonical_archive_source"] = canonical[ident]["source"]
                    row["canonical_archived_wall_s"] = compact_wall(canonical[ident])
            rows[method].append(row)
    for method, name in ARCHIVES.items():
        pack(output / name, rows[method])
    write(output / "source-lock.json", plan_path.read_bytes())
    times = []
    for row in plan["schedule"].values():
        for m in row["methods"]:
            path = work / row["id"] / m / "measurement.json"
            if path.is_file():
                times.append(path.stat().st_mtime_ns)
    save_json(
        output / "receipt.json",
        dict(
            cases=cases,
            source_lock_sha256=prior_sha,
            archived_reference=ledger,
            files={f: common.sha(output / f) for f in ARCHIVES.values()},
            elapsed_to_last_receipt_s=(max(times, default=plan["locked_ns"]) - plan["locked_ns"])
            / 1e9,
        ),
    )


def stage_sum(stages, desired):
    return sum(stages[k] for k in desired) if all(k in stages for k in desired) else None


def timing(row):
    metrics = row["result"]["metrics"]
    if row["method"] == ORIGINAL:
        stages = dict(zip(metrics.get("stages", ()), metrics.get("stage_s", ()), strict=True))
        if not stages:
            stages = {s["stage"]: s["seconds"] for s in row.get("original_stage_log", ())}
    else:
        stages = metrics.get("stage_s", {})
    stats = row["resources"]
    elapsed, worker = stats.get("wall_s"), metrics.get("candidate_s")
    complete = row["result"]["status"] == "ok"
    common_s = stage_sum(stages, SHARED)
    late_s = stage_sum(stages, LATE) if row["method"] == ORIGINAL else None
    computation = (
        common_s
        if row["method"] == COMPACT
        else (common_s + late_s if common_s is not None and late_s is not None else None)
    )
    render = stage_sum(stages, RENDER)
    work = row.get("original_work", {})
    user, sys = stats.get("child_user_s"), stats.get("child_system_s")
    return dict(
        id=row["id"],
        method=row["method"],
        cpu=row["cpu"],
        order=row["order"],
        status=row["result"]["status"],
        reason=row["result"].get("reason"),
        launcher_wall_s=elapsed,
        worker_wall_s=worker,
        total_cpu_s=stats.get("cpu_s"),
        child_user_s=user,
        child_system_s=sys,
        child_cpu_s=user + sys if user is not None else None,
        peak_child_rss_kib=stats.get("child_peak_rss_kib"),
        peak_launcher_rss_kib=stats.get("self_peak_rss_kib"),
        common_through_cavity_s=common_s,
        numerical_published_boundary_s=computation if complete else None,
        original_full_late_s=late_s,
        original_render_s=render,
        outer_setup_s=elapsed - worker if elapsed is not None and worker is not None else None,
        worker_other_s=worker - computation - (render or 0)
        if complete and computation is not None and worker is not None
        else None,
        original_archive_bytes=work.get("output_bytes"),
        original_png_count=work.get("png_count"),
        initial_branches=work.get("original_initial_branches", metrics.get("initial_branches")),
        original_initial_unique_proposals=work.get("original_initial_unique_proposals"),
        initial_refresh_count=(
            sum(sum(v) for v in work["original_initial_phase_rounds"].values())
            if "original_initial_phase_rounds" in work
            else sum(metrics["initial_phase_refresh_counts"])
            if "initial_phase_refresh_counts" in metrics
            else None
        ),
        native_backend_calls=work.get("native_counts", {}).get("calls"),
        compact_optimizer_calls=metrics.get("position_optimizer", {}).get("calls"),
        compact_optimizer_residual_evaluations=metrics.get("position_optimizer", {}).get(
            "evaluations"
        ),
        compact_projection_calls=metrics.get("compact_projections"),
        **{f"{k}_s": stages.get(k) for k in (*SHARED, *LATE, *RENDER)},
    )


def logic_inventory():
    fd = trial.v5_lean.SOURCE / "leo"
    tools = common.ROOT / "tools/pipeline_eval"
    surfaces = {
        ORIGINAL: (
            Path(trial.original_v5.__file__),
            trial.v5_lean.RUNNER / "evaluate_accuracy_repair.py",
            fd / "application/localization_v3_engine.py",
            fd / "application/localization_v3_result.py",
        ),
        COMPACT: (
            tools / "variants/v5_lean.py",
            tools / "variants/v5_core.py",
            tools / "variants/v5_secant_fit.py",
            tools / "variants/orbit_projector.py",
            tools / "variants/orbit_projector.c",
        ),
    }

    def file(path):
        raw = path.read_text()
        parse = ast.parse(raw) if path.suffix == ".py" else None
        funcs = (ast.FunctionDef, ast.AsyncFunctionDef)
        return dict(
            file=str(path),
            sha256=common.sha(path),
            source_lines=len(raw.splitlines()),
            python_top_level_functions=sum(isinstance(x, funcs) for x in parse.body)
            if parse is not None
            else None,
            python_all_functions=sum(isinstance(x, funcs) for x in ast.walk(parse))
            if parse is not None
            else None,
        )

    return {
        m: dict(
            scope="Listed orchestration and presentation-facing files only",
            files=[file(p) for p in paths],
        )
        for m, paths in surfaces.items()
    }


def summarize(rows):
    grouped = {m: {r["id"]: r for r in rows if r["method"] == m} for m in ARCHIVES}
    pairs = []
    scopes = (
        "launcher_wall_s",
        "numerical_published_boundary_s",
        "common_through_cavity_s",
        "child_cpu_s",
    )
    for ident in grouped[ORIGINAL]:
        before, after = [grouped[m][ident] for m in (ORIGINAL, COMPACT)]
        done = before["status"] == after["status"] == "ok"
        pairs.append(
            dict(
                id=ident,
                cpu=before["cpu"],
                original=before["status"],
                compact=after["status"],
                completed_pair=done,
                **{
                    k: before[k] / after[k] if done and before[k] is not None and after[k] else None
                    for k in scopes
                },
            )
        )
    return dict(
        pairs=pairs,
        planned_pairs=len(pairs),
        completed_pairs=sum(p["completed_pair"] for p in pairs),
        original_over_compact={k: distribution(p[k] for p in pairs) for k in scopes},
    )


def by_arm(rows):
    collected = {}
    for method in ARCHIVES:
        collected[method] = {}
        for arm in ARMS:
            group = [r for r in rows if r["method"] == method and r["arm"] == arm]
            collected[method][arm] = dict(
                offered=len(group),
                geographic_error_km=distribution(r["error_km"] for r in group),
                conditional_rms_hz=distribution(r["conditional_rms_hz"] for r in group),
                legacy_coordinate_exact=sum(r["position_exact"] is True for r in group),
                legacy_rf_exact=sum(r["rf_exact"] is True for r in group),
                legacy_coordinate_difference_km=distribution(
                    r["position_difference_km"] for r in group
                ),
            )
    return collected


def score(output):
    seal = common.seal(output, "receipt.json", ARCHIVES.values())
    if seal["source_lock_sha256"] != common.sha(output / "source-lock.json"):
        raise ValueError("paired source receipt changed")
    refs, _ = _frozen_roof()
    methods = {m: read_predictions(output / f) for m, f in ARCHIVES.items()}
    for records in methods.values():
        common.roster_matches(records, seal["cases"], "fresh matched pairs")
    measures = [timing(row) for items in methods.values() for row in items.values()]
    cases = []
    for ident in seal["cases"]:
        for arm in ARMS:
            for method, group in methods.items():
                row = group[ident]
                result = row["result"]
                point = result["arms"][arm]
                cases.append(
                    dict(
                        id=ident,
                        method=method,
                        arm=arm,
                        status=result["status"],
                        error_km=distance_km(point["latlon"], refs[ident]["truth"]),
                        conditional_rms_hz=point.get("rf_rms_hz"),
                        **row.get("legacy", {}).get(
                            arm,
                            {
                                k: None
                                for k in (
                                    "position_difference_km",
                                    "position_exact",
                                    "rf_difference_hz",
                                    "rf_exact",
                                )
                            },
                        ),
                    )
                )
    csv_file(output / "timings.csv", measures)
    csv_file(output / "scores.csv", cases)
    save_json(output / "summary.json", dict(summarize(measures), by_arm=by_arm(cases)))
    save_json(output / "logic.json", logic_inventory())
    files = ("scores.csv", "timings.csv", "summary.json", "logic.json")
    save_json(
        output / "roof-lock.json",
        dict(
            cases=seal["cases"],
            source_lock_sha256=seal["source_lock_sha256"],
            files={**seal["files"], **{f: common.sha(output / f) for f in files}},
        ),
    )
    save_json(
        output / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id=CHART,
                    method=COMPACT,
                    scope="roof",
                    cases=seal["cases"],
                    seal="roof-lock.json",
                    title="Same-core original v5 and compact secant on four matched recordings",
                    caption=(
                        "Fresh runs on the same pinned CPU within each pair. Both methods used "
                        "the same stored GLRT, causal catalogue and supplied tile. All "
                        "scheduled attempts count."
                    ),
                    source_lock=dict(file="source-lock.json", digest_key="source_lock_sha256"),
                    provenance=list(files),
                    series=[
                        dict(
                            key="one",
                            label="Fresh compact secant",
                            value=COMPACT,
                            file=ARCHIVES[COMPACT],
                        ),
                        dict(
                            key="stock",
                            label="Fresh original no repair",
                            value=ORIGINAL,
                            file=ARCHIVES[ORIGINAL],
                            match=list(trial.MATCH),
                        ),
                    ],
                )
            ],
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="action", required=True)
    freeze = command.add_parser("seal")
    freeze.add_argument("plan", type=Path)
    freeze.add_argument("work", type=Path)
    command.add_parser("score")
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    out = local_output(args.out)
    if args.action == "seal":
        seal(args.plan, args.work, out)
    else:
        score(out)


if __name__ == "__main__":
    main()
