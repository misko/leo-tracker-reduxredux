import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SHARED = REPOSITORY / "reports/2026_10_02_shared_rx_position"
GLRT = REPOSITORY / "reports/2026_10_02_full_curve_glrt"
COHERENT = REPOSITORY / "reports/2026_10_02_coherent_localization"

MODEL_IDS = (
    "track_independent",
    "track_constant",
    "track_linear",
    "glrt_fixed_8",
    "glrt_fixed_16",
    "glrt_fixed_32",
    "glrt_fixed_64",
    "glrt_free_16",
    "glrt_timing_3s",
    "glrt_timing_10s",
    "anchors",
    "extensions",
    "coherent_timing",
)

FIELDS = (
    "model_id",
    "family",
    "scan_id",
    "scope",
    "training_coverage",
    "holdout",
    "no_holdout",
    "comparison_class",
    "objective_id",
    "objective_definition",
    "nearest_curve_metric_role",
    "free_parameters",
    "profiled_or_selected_parameters",
    "fixed_parameters",
    "candidate_satellite_count",
    "candidate_satellite_scope",
    "candidate_satellite_ids",
    "assigned_satellite_count",
    "assigned_satellite_ids",
    "fit_unit",
    "fit_unit_count",
    "accepted_unit_count",
    "within_1000hz_unit_count",
    "reference_error_km",
    "track_training_mean_capped_soft_l1_cost_hz2",
    "track_evaluation_mean_capped_soft_l1_cost_hz2",
    "all_group_nearest_curve_mean_capped_soft_l1_loss_hz2",
    "within_1000hz_rms_hz",
    "assigned_weighted_rms_hz",
    "weighted_fixed_assignment_frequency_objective",
    "timing_prior_objective",
    "penalized_objective",
    "timing_sigma_s",
    "timing_bound_s",
    "active_timing_satellite_count",
    "timing_shifts_at_bound",
    "runtime_s",
    "runtime_scope",
    "converged",
    "convergence_detail",
    "qualification",
    "provenance",
)


def _load(path):
    return json.loads(path.read_text())


def _relative(path):
    return str(path.relative_to(REPOSITORY))


def _receipt(path, role):
    return {
        "role": role,
        "path": _relative(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _provenance(result_paths, definition_paths, input_paths=()):
    return [
        *[_receipt(path, "result") for path in result_paths],
        *[_receipt(path, "definition") for path in definition_paths],
        *[_receipt(path, "input_metadata") for path in input_paths],
    ]


def _row(**values):
    unknown = set(values) - set(FIELDS)
    if unknown:
        raise ValueError(f"Unknown historical-table fields: {sorted(unknown)}")
    return {field: values.get(field) for field in FIELDS}


def _refinement_status(refinements):
    successes = sum(bool(row["success"]) for row in refinements)
    return successes == len(refinements) and bool(refinements), (
        f"{successes}/{len(refinements)} recorded continuous refinements reported success"
    )


def _track_rows(scan_id, source, result):
    rows = []
    definitions = [SHARED / "model.py", SHARED / "run.py"]
    result_path = SHARED / "results.json"
    specifications = {
        "independent": {
            "model_id": "track_independent",
            "free_parameters": ["east_km", "north_km", "one profiled offset per track/candidate"],
            "profiled": ["per-track satellite identity", "per-track frequency offset"],
            "fixed": ["altitude=0m", "satellite time shifts=0s", "receiver slope not shared"],
        },
        "constant": {
            "model_id": "track_constant",
            "free_parameters": ["east_km", "north_km", "rx0_intercept_hz", "rx1_intercept_hz"],
            "profiled": ["per-track satellite identity", "per-track alias branch"],
            "fixed": [
                "rx0_slope_hz_s=0",
                "rx1_slope_hz_s=0",
                "altitude=0m",
                "satellite time shifts=0s",
            ],
        },
        "linear": {
            "model_id": "track_linear",
            "free_parameters": [
                "east_km",
                "north_km",
                "rx0_intercept_hz",
                "rx0_slope_hz_s",
                "rx1_intercept_hz",
                "rx1_slope_hz_s",
            ],
            "profiled": ["per-track satellite identity", "per-track alias branch"],
            "fixed": [
                "altitude=0m",
                "satellite time shifts=0s",
                "receiver slopes bounded +/-10Hz/s",
            ],
        },
    }
    for name, specification in specifications.items():
        model = result["models"][name]
        converged, detail = _refinement_status(model["refinements"])
        accepted_ids = sorted(
            {track["catalog_number"] for track in model["tracks"] if track["accepted"]}
        )
        rows.append(
            _row(
                model_id=specification["model_id"],
                family="legacy_track_shortlist",
                scan_id=scan_id,
                scope=(
                    "60 pre-existing tracks, each with its conditional fixed-site top-five "
                    "candidate shortlist"
                ),
                training_coverage="first two thirds of each track time span",
                holdout=(
                    "final one third of each track time span; evaluation only; not used for "
                    "model selection"
                ),
                no_holdout=False,
                comparison_class="legacy_per_track_two_thirds_training",
                objective_id="mean_track_capped_soft_l1_cost",
                objective_definition=(
                    "Equal-weight mean over tracks of capped candidate cost; soft-L1 scale 200Hz "
                    "and unmatched cap equivalent to 2000Hz"
                ),
                nearest_curve_metric_role="not reported",
                free_parameters=specification["free_parameters"],
                profiled_or_selected_parameters=specification["profiled"],
                fixed_parameters=specification["fixed"],
                candidate_satellite_count=5,
                candidate_satellite_scope=(
                    "five candidates per track; not one common five-satellite pool"
                ),
                candidate_satellite_ids=sorted(
                    {
                        catalog_number
                        for track in source["tracks"]
                        for catalog_number in track["catalog_numbers"]
                    }
                ),
                assigned_satellite_count=len(accepted_ids),
                assigned_satellite_ids=accepted_ids,
                fit_unit="track",
                fit_unit_count=len(source["tracks"]),
                accepted_unit_count=model["accepted_tracks"],
                reference_error_km=model["reference_error_km"],
                track_training_mean_capped_soft_l1_cost_hz2=model["training_cost"],
                track_evaluation_mean_capped_soft_l1_cost_hz2=model["evaluation_cost"],
                runtime_s=result["elapsed_s"],
                runtime_scope=(
                    "whole sequential three-model legacy run; per-model runtime unavailable"
                ),
                converged=converged,
                convergence_detail=detail,
                qualification=(
                    "Conditional known-site candidate provenance; historical split-fit baseline, "
                    "not apples-to-apples with all-training rows and not blind validation"
                ),
                provenance=_provenance([result_path], definitions, [SHARED / "inputs.json"]),
            )
        )
    return rows


def _glrt_fixed_rows(scan_id, metadata, position, sweep):
    rows = []
    sweep_path = GLRT / "satellite-sweep-results.json"
    position_path = GLRT / "position-results-all-training.json"
    definitions = [
        GLRT / "position_loss.py",
        GLRT / "position_search.py",
        GLRT / "satellite_sweep.py",
    ]
    fixed_16 = position["models"]["fixed_rx"]
    sweep_16 = sweep["models"]["16"]
    for field in (
        "point",
        "training_loss",
        "training_groups",
        "within_gate_training_rms_hz",
        "reference_error_km",
    ):
        if fixed_16[field] != sweep_16[field]:
            raise ValueError(f"Fixed-16 artifacts disagree on {field}")
    for count in (8, 16, 32, 64):
        model = sweep["models"][str(count)]
        converged, detail = _refinement_status(model["refinements"])
        result_paths = [sweep_path]
        if count == 16:
            result_paths.append(position_path)
            detail += "; numerically identical fixed-16 result in all-training position artifact"
        rows.append(
            _row(
                model_id=f"glrt_fixed_{count}",
                family="group_nearest_curve_fixed_rx",
                scan_id=scan_id,
                scope=metadata["scope"],
                training_coverage="all 3192 exclusive source groups",
                holdout="none",
                no_holdout=True,
                comparison_class="all_training_group_nearest_curve_fixed_rx",
                objective_id="mean_group_capped_soft_l1_nearest_curve_loss",
                objective_definition=(
                    "Equal-source-group mean capped soft-L1 circular residual to the nearest "
                    "visible "
                    "candidate curve; scale 200Hz, cap 2000Hz"
                ),
                nearest_curve_metric_role="fit objective",
                free_parameters=["east_km", "north_km"],
                profiled_or_selected_parameters=[
                    "nearest visible satellite/GLRT candidate per source group"
                ],
                fixed_parameters=[
                    "two previously fitted receiver intercepts",
                    "two previously fitted receiver slopes",
                    "satellite time shifts=0s",
                    "altitude=0m",
                    f"nested ranked satellite prefix of length {count}",
                ],
                candidate_satellite_count=count,
                candidate_satellite_scope=(
                    "nested support-ranked prefix; original conditional 16 first"
                ),
                candidate_satellite_ids=model["satellite_ids"],
                fit_unit="exclusive source group",
                fit_unit_count=model["training_groups"],
                within_1000hz_unit_count=model["training_within_1000hz"],
                reference_error_km=model["reference_error_km"],
                all_group_nearest_curve_mean_capped_soft_l1_loss_hz2=model["training_loss"],
                within_1000hz_rms_hz=model["within_gate_training_rms_hz"],
                runtime_s=sweep["elapsed_s"],
                runtime_scope="whole sequential 8/16/32/64 sweep; per-model runtime unavailable",
                converged=converged,
                convergence_detail=detail,
                qualification=(
                    "Conditional known-site shortlist/ranking and prior RX fit; all-training "
                    "baseline "
                    "with no holdout, not blind validation"
                ),
                provenance=_provenance(result_paths, definitions, [GLRT / "inputs.json"]),
            )
        )
    return rows


def _glrt_free_row(scan_id, metadata, position):
    model = position["models"]["profiled_rx"]
    converged, detail = _refinement_status(model["refinements"])
    return _row(
        model_id="glrt_free_16",
        family="group_nearest_curve_profiled_rx",
        scan_id=scan_id,
        scope=metadata["scope"],
        training_coverage="all 3192 exclusive source groups",
        holdout="none",
        no_holdout=True,
        comparison_class="all_training_group_nearest_curve_profiled_rx",
        objective_id="mean_group_capped_soft_l1_nearest_curve_loss",
        objective_definition=(
            "Equal-source-group mean capped soft-L1 circular residual to the nearest visible "
            "candidate curve; scale 200Hz, cap 2000Hz; RX lines profiled at each position"
        ),
        nearest_curve_metric_role="fit objective",
        free_parameters=[
            "east_km",
            "north_km",
            "rx0_intercept_hz",
            "rx0_slope_hz_s",
            "rx1_intercept_hz",
            "rx1_slope_hz_s",
        ],
        profiled_or_selected_parameters=[
            "four receiver-line parameters",
            "nearest visible satellite/GLRT candidate per source group",
        ],
        fixed_parameters=[
            "satellite time shifts=0s",
            "altitude=0m",
            "conditional 16-satellite pool",
            "receiver slopes bounded +/-10Hz/s",
        ],
        candidate_satellite_count=16,
        candidate_satellite_scope="persisted conditional fixed-site 16-satellite shortlist",
        candidate_satellite_ids=metadata["selected_satellites"],
        fit_unit="exclusive source group",
        fit_unit_count=model["training_groups"],
        within_1000hz_unit_count=model["training_within_1000hz"],
        reference_error_km=model["reference_error_km"],
        all_group_nearest_curve_mean_capped_soft_l1_loss_hz2=model["training_loss"],
        within_1000hz_rms_hz=model["within_gate_training_rms_hz"],
        runtime_s=position["elapsed_s"],
        runtime_scope=(
            "whole sequential original/fixed/free all-training run; per-model runtime unavailable"
        ),
        converged=converged,
        convergence_detail=detail,
        qualification=(
            "Conditional known-site shortlist and prior nuisance initialization; all-training "
            "baseline "
            "with no holdout, not blind validation"
        ),
        provenance=_provenance(
            [GLRT / "position-results-all-training.json"],
            [GLRT / "position_loss.py", GLRT / "position_search.py"],
            [GLRT / "inputs.json"],
        ),
    )


def _timing_row(scan_id, metadata, model_id, result, result_paths, definition_path, sigma, bound):
    return _row(
        model_id=model_id,
        family="group_nearest_curve_satellite_timing",
        scan_id=scan_id,
        scope=metadata["scope"],
        training_coverage="all 3192 exclusive source groups",
        holdout="none",
        no_holdout=True,
        comparison_class=f"all_training_penalized_satellite_timing_sigma_{sigma:g}_bound_{bound:g}",
        objective_id="penalized_group_nearest_curve_timing_objective",
        objective_definition=(
            "sum(group rho/(2*200Hz^2)) plus independent Gaussian satellite-time prior; "
            "nearest visible candidate selected per source group"
        ),
        nearest_curve_metric_role="unpenalized data diagnostic underlying the penalized fit",
        free_parameters=["east_km", "north_km", "64 satellite orbit-time shifts"],
        profiled_or_selected_parameters=[
            "nearest visible satellite/GLRT candidate per source group"
        ],
        fixed_parameters=[
            "two previously fitted receiver intercepts",
            "two previously fitted receiver slopes at unshifted receive time",
            "altitude=0m",
            "frozen 64-satellite pool",
        ],
        candidate_satellite_count=64,
        candidate_satellite_scope="frozen nested 64-satellite conditional pool",
        candidate_satellite_ids=result["satellite_numbers"],
        assigned_satellite_count=sum(count > 0 for count in result["assignment_counts"]),
        assigned_satellite_ids=[
            number
            for number, count in zip(
                result["satellite_numbers"], result["assignment_counts"], strict=True
            )
            if count > 0
        ],
        fit_unit="exclusive source group",
        fit_unit_count=result["groups"],
        within_1000hz_unit_count=result["groups_within_1000hz"],
        reference_error_km=result["reference_error_km"],
        all_group_nearest_curve_mean_capped_soft_l1_loss_hz2=result["mean_frequency_loss"],
        timing_prior_objective=result["gaussian_penalty"],
        penalized_objective=result["penalized_objective"],
        timing_sigma_s=sigma,
        timing_bound_s=bound,
        active_timing_satellite_count=64,
        timing_shifts_at_bound=result["shifts_at_bound"],
        runtime_s=result["elapsed_s"],
        runtime_scope=(
            "single refinement run from the prior 3s solution"
            if bound == 3
            else "selected warm-start run; companion artifact contains both recorded starts"
        ),
        converged=result["success"],
        convergence_detail=(
            f"{result['message']}; {result['iterations']} iterations"
            + (f"; {result['evaluations']} evaluations" if "evaluations" in result else "")
        ),
        qualification=(
            "Conditional frozen shortlist and fixed prior RX solution; penalized surrogate, "
            "not a calibrated posterior, blind validation, or holdout result"
        ),
        provenance=_provenance(
            result_paths,
            [GLRT / "time_shift_model.py", GLRT / "time_shift_search.py", definition_path],
            [GLRT / "inputs.json"],
        ),
    )


def _coherent_rows(scan_id, result, candidate_satellite_ids):
    rows = []
    result_path = COHERENT / "results.json"
    definitions = [
        COHERENT / "common.py",
        COHERENT / "anchors.py",
        COHERENT / "association.py",
        COHERENT / "refinement.py",
        COHERENT / "run.py",
    ]
    specifications = {
        "anchors": {
            "model_id": "anchors",
            "coverage": (
                "737 selected whole-track anchor groups from the full sample; no held-out "
                "partition"
            ),
            "profiled": ["whole-track anchor identity selection before fitting"],
            "fixed": ["anchor assignments fixed during fit", "all 64 satellite time shifts=0s"],
        },
        "extensions": {
            "model_id": "extensions",
            "coverage": (
                "1315 coherently assigned groups from the full sample; no held-out partition"
            ),
            "profiled": ["alternating coherent association until group/satellite pairs stabilized"],
            "fixed": [
                "assignments fixed within each refinement",
                "all 64 satellite time shifts=0s",
            ],
        },
        "timing": {
            "model_id": "coherent_timing",
            "coverage": (
                "same 1315 extension assignments from the full sample; no held-out partition"
            ),
            "profiled": ["extension-stage assignments frozen for timing ablation"],
            "fixed": [
                "57 unsupported satellite time shifts=0s",
                "post-timing reassociation is diagnostic only",
            ],
        },
    }
    for name, specification in specifications.items():
        stage = result["stages"][name]
        fit = stage["fit"]
        diagnostics = fit["diagnostics"]
        metrics = stage["metrics"]
        active_timing = diagnostics["active_timing_satellites"]
        free = [
            "east_km",
            "north_km",
            "rx0_intercept_hz",
            "rx0_slope_hz_s",
            "rx1_intercept_hz",
            "rx1_slope_hz_s",
        ]
        if name == "timing":
            free.append("7 support-gated satellite time shifts")
        rows.append(
            _row(
                model_id=specification["model_id"],
                family="coherent_fixed_assignment_weighted",
                scan_id=scan_id,
                scope=result["protocol"]["scope"],
                training_coverage=specification["coverage"],
                holdout="none",
                no_holdout=True,
                comparison_class="coherent_weighted_fixed_assignment",
                objective_id="weighted_fixed_assignment_soft_l1_residual",
                objective_definition=(
                    "Weighted fixed-assignment soft-L1 frequency residuals, with a Gaussian timing "
                    "prior only for the coherent timing stage"
                ),
                nearest_curve_metric_role="diagnostic only; not the fitted coherent objective",
                free_parameters=free,
                profiled_or_selected_parameters=specification["profiled"],
                fixed_parameters=[
                    "altitude=0m",
                    "receiver slopes bounded +/-10Hz/s",
                    "frozen conditional 64-satellite pool",
                    *specification["fixed"],
                ],
                candidate_satellite_count=64,
                candidate_satellite_scope=(
                    "frozen conditional pool inherited from the 64-satellite sweep"
                ),
                candidate_satellite_ids=candidate_satellite_ids,
                assigned_satellite_count=metrics["assigned_satellites"],
                assigned_satellite_ids=[
                    row["catalog_number"] for row in metrics["satellite_support"]
                ],
                fit_unit="weighted fixed assigned source group",
                fit_unit_count=metrics["assigned_groups"],
                within_1000hz_unit_count=metrics["assigned_visible_within_1000hz"],
                reference_error_km=stage["reference_error_km"],
                all_group_nearest_curve_mean_capped_soft_l1_loss_hz2=metrics[
                    "all_group_nearest_curve_loss_diagnostic_only"
                ],
                assigned_weighted_rms_hz=metrics["assigned_weighted_rms_hz"],
                weighted_fixed_assignment_frequency_objective=diagnostics["frequency_objective"],
                timing_prior_objective=diagnostics["timing_prior_objective"],
                penalized_objective=fit["objective"],
                timing_sigma_s=diagnostics["timing_sigma_s"] if name == "timing" else None,
                timing_bound_s=diagnostics["timing_bound_s"] if name == "timing" else None,
                active_timing_satellite_count=len(active_timing),
                timing_shifts_at_bound=(
                    sum(diagnostics["timing_at_bound"]) if name == "timing" else 0
                ),
                runtime_s=result["elapsed_s"],
                runtime_scope="whole sequential coherent run; per-stage runtime unavailable",
                converged=fit["success"]
                and (name != "extensions" or result["association_converged"]),
                convergence_detail=(
                    f"{fit['message']}; {fit['nfev']} evaluations; optimizer status "
                    f"{diagnostics['optimizer_status']}"
                    + (
                        "; association group/satellite pairs stabilized"
                        if name == "extensions" and result["association_converged"]
                        else ""
                    )
                ),
                qualification=(
                    "Conditional on previous position/RX initialization, anchor selection, and a "
                    "frozen "
                    "64-satellite pool; local prototype with no holdout, not blind validation"
                ),
                provenance=_provenance([result_path], definitions, [GLRT / "inputs.json"]),
            )
        )
    return rows


def build_document():
    shared_source = _load(SHARED / "inputs.json")
    metadata = _load(GLRT / "inputs.json")
    shared = _load(SHARED / "results.json")
    position = _load(GLRT / "position-results-all-training.json")
    sweep = _load(GLRT / "satellite-sweep-results.json")
    narrow = _load(GLRT / "time-shift-refined.json")
    wide = _load(GLRT / "time-shift-10s.json")
    coherent = _load(COHERENT / "results.json")
    selection = _load(ROOT / "selection.json")

    scan_id = metadata["session_id"]
    identities = {
        scan_id,
        metadata["source"]["session_id"],
        shared_source["session_id"],
        coherent["session_id"],
        selection["original_sample"],
    }
    if identities != {scan_id}:
        raise ValueError(f"Historical artifacts disagree on scan identity: {sorted(identities)}")
    if scan_id != "scan-fw-4971402f107cf8e1":
        raise ValueError(f"Unexpected historical scan: {scan_id}")
    if tuple(selection["models"]) != MODEL_IDS:
        raise ValueError("Historical-table model IDs disagree with frozen benchmark selection")
    if position["protocol"]["partition"] != "all source groups used for fitting; no holdout":
        raise ValueError("Position artifact is not the required all-training fit")
    if len(shared_source["tracks"]) != 60 or metadata["source_group_count"] != 3192:
        raise ValueError("Historical sample counts changed")

    rows = _track_rows(scan_id, shared_source, shared)
    rows.extend(_glrt_fixed_rows(scan_id, metadata, position, sweep))
    rows.append(_glrt_free_row(scan_id, metadata, position))
    rows.extend(
        [
            _timing_row(
                scan_id,
                metadata,
                "glrt_timing_3s",
                narrow,
                [GLRT / "time-shift-refined.json"],
                GLRT / "refine_time_shift.py",
                1.0,
                3.0,
            ),
            _timing_row(
                scan_id,
                metadata,
                "glrt_timing_10s",
                wide,
                [GLRT / "time-shift-10s.json", GLRT / "time-shift-10s-runs.json"],
                GLRT / "wide_time_shift.py",
                10 / 3,
                10.0,
            ),
        ]
    )
    rows.extend(_coherent_rows(scan_id, coherent, sweep["models"]["64"]["satellite_ids"]))
    order = {name: index for index, name in enumerate(MODEL_IDS)}
    rows.sort(key=lambda row: order[row["model_id"]])
    if tuple(row["model_id"] for row in rows) != MODEL_IDS:
        raise ValueError("Historical table is incomplete or duplicated")
    for row in rows:
        if "blind validation" not in row["qualification"]:
            raise ValueError(f"Qualification lost for {row['model_id']}")

    return {
        "schema": "coherent-localization-historical-sample/v1",
        "artifact_role": (
            "Historical baseline for the original sample only; not a controlled rerun and not a "
            "source for benchmark model or hyperparameter selection"
        ),
        "scan_id": scan_id,
        "row_count": len(rows),
        "reference_truth_policy": (
            "Reference coordinates were used only to compute post-fit error; they were not used to "
            "select a winning fit, model, or hyperparameter"
        ),
        "comparability_warning": (
            "Legacy track rows train on the first two thirds of each track and report a different "
            "track-level objective. All remaining rows use no holdout, and coherent rows fit a "
            "weighted fixed-assignment objective. Compare errors descriptively; do not rank the "
            "unlike loss columns as one objective."
        ),
        "rows": rows,
    }


def render_csv(document):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in document["rows"]:
        writer.writerow(
            {
                key: json.dumps(value, separators=(",", ":"))
                if isinstance(value, (list, dict))
                else value
                for key, value in row.items()
            }
        )
    return output.getvalue()


def main():
    document = build_document()
    (ROOT / "historical-sample.json").write_text(
        json.dumps(document, indent=2, allow_nan=False) + "\n"
    )
    (ROOT / "historical-sample.csv").write_text(render_csv(document))
    print(json.dumps({"scan_id": document["scan_id"], "rows": document["row_count"]}))


if __name__ == "__main__":
    main()
