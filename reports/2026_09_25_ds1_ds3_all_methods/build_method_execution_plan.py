#!/usr/bin/env python3
"""Build the DS3 coverage plan for distinct historical method arms.

The plan is an execution inventory, not a scheduler and not an inference
runner.  It distinguishes a method's DS1 provenance from the DS3-native
adapter still needed to replay it.  In particular, it never declares a
historical coordinate, association, timing value, or cone direction reusable
as DS3 state.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DS3_MANIFEST = "reports/2026_09_24_ds3_all_captures/inference-manifest.json"
RESULT_SCHEMA = "ds3-method-arm-result/v1"
DIAGNOSTIC_SCHEMA = "ds3-method-arm-diagnostic/v1"


def arm(
    method_id: str,
    source: list[str],
    adapter: str,
    command: list[str],
    dependencies: list[str],
    gate: str,
    runtime: str,
    *,
    output_schema: str = RESULT_SCHEMA,
    execution_state: str = "planned",
    adapter_state: str = "needs_implementation",
    note: str = "",
) -> dict[str, Any]:
    return {
        "method_id": method_id,
        "source_ds1_artifacts": source,
        "ds3_adapter": adapter,
        "command": command,
        "dependencies": dependencies,
        "expected_output_schema": output_schema,
        "terminal_gate": gate,
        "runtime_estimate": runtime,
        "execution_state": execution_state,
        "adapter_state": adapter_state,
        "note": note,
    }


def arms() -> list[dict[str, Any]]:
    joint = "reports/2026_09_24_ds1_joint_rate_search"
    timing = "reports/2026_09_24_ds1_train_full_timing/run.py"
    orbit = "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
    phase = "reports/2026_09_25_ds3_all_iterations_backfill/batch-b/phase_atlas_chain.py"
    return [
        arm(
            "i02.shared_global_time",
            ["reports/2026_09_24_ds1_iteration2/iteration2-inference-manifest.json"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-a/iteration02_adapter.py",
            ["reuse-sealed", "iteration-02", "--arm", "shared_global_tau"],
            ["sealed DS3 iteration-02 result"],
            "terminal status is qualified only when timing and geographic winner are interior",
            "already sealed; no new compute",
            execution_state="accounted",
            adapter_state="implemented",
        ),
        arm(
            "i02.regularized_per_scan_time",
            ["reports/2026_09_24_ds1_iteration2/iteration2-inference-manifest.json"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-a/iteration02_adapter.py",
            ["reuse-sealed", "iteration-02", "--arm", "regularized_per_scan_tau"],
            ["sealed DS3 iteration-02 result"],
            "terminal status is qualified only when timing and geographic winner are interior",
            "already sealed; no new compute",
            execution_state="accounted",
            adapter_state="implemented",
        ),
        arm(
            "i03.rate_aware_joint_geographic_screen",
            [f"{joint}/iteration3_prefix6.py", f"{joint}/iteration3-results.json"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/i03_rate_screen.py",
            [".venv/bin/python", "batch-c/i03_rate_screen.py", "--ds3-manifest", DS3_MANIFEST],
            ["sealed DS3 all56 manifest", "fresh DS3 global-time seed plans"],
            "exact SGP4 finalist replay passes and final tau/rate/geographic winner is interior",
            "40–80 CPU-min; four independent seed workers",
        ),
        arm(
            "i04.seed_union_exact_selection",
            [f"{joint}/iteration4_group_union.py", f"{joint}/iteration4-results.json"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/i04_seed_union.py",
            [".venv/bin/python", "batch-c/i04_seed_union.py", "--ds3-manifest", DS3_MANIFEST],
            ["sealed DS3 I03 candidate rows"],
            "exact union replay and group-union selection agree; final point is interior",
            "25–50 CPU-min after I03",
        ),
        arm(
            "i05.common_grid_timing_refinement",
            [f"{joint}/iteration5-results.json", f"{joint}/ITERATION5_REPORT.md"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/i05_common_grid.py",
            [".venv/bin/python", "batch-c/i05_common_grid.py", "--ds3-manifest", DS3_MANIFEST],
            ["sealed DS3 I04 selection"],
            "shared timing-grid winner and geographic winner are both interior under exact replay",
            "20–40 CPU-min after I04",
        ),
        arm(
            "i06.matched_cap300_cap800_ablation",
            [f"{joint}/iteration6_matched_exact_ablation.py", f"{joint}/iteration6-results.json"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/i06_matched_ablation.py",
            [".venv/bin/python", "batch-c/i06_matched_ablation.py", "--ds3-manifest", DS3_MANIFEST],
            ["sealed DS3 I05 selection"],
            "cap-300 proposal and cap-800 exact rank agree under exact SGP4 gate",
            "30–60 CPU-min after I05",
        ),
        arm(
            "i06b.legacy_joint_session_scale_lbfgsb",
            ["reports/2026_09_24_ds1_iteration6b_session_scale/REPORT.md"],
            "none",
            ["terminal-accounting", "i06b"],
            [],
            "not applicable: historical L-BFGS-B session-scale implementation is "
            "rejected/not portable",
            "no compute",
            execution_state="not_portable",
            adapter_state="none",
            note="Separate from canonical I06; must never satisfy I06 coverage.",
        ),
        arm(
            "i07.independent_gaussian_rerank",
            [f"{joint}/iteration7_residual_likelihood.py", f"{joint}/iteration7-results.json"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/i07_likelihood.py",
            [".venv/bin/python", "batch-c/i07_likelihood.py", "--arm", "gaussian"],
            ["sealed DS3 I06 exact residual sequences"],
            "fixed identities/rates are replayed exactly; no refit is permitted",
            "10–20 CPU-min after I06",
        ),
        arm(
            "i07.ar1_student_t_rerank",
            [f"{joint}/iteration7_residual_likelihood.py", f"{joint}/iteration7-results.json"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/i07_likelihood.py",
            [".venv/bin/python", "batch-c/i07_likelihood.py", "--arm", "ar1_student_t"],
            ["sealed DS3 I06 exact residual sequences"],
            "fixed identities/rates are replayed exactly; no refit is permitted",
            "10–20 CPU-min after I06",
        ),
        arm(
            "i12.expanded_exact_rate_only",
            ["reports/2026_09_24_ds1_iteration12_session_scale/run.py"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/i12_rate_only.py",
            [".venv/bin/python", "batch-c/i12_rate_only.py", "--ds3-manifest", DS3_MANIFEST],
            ["sealed DS3 I10"],
            "all exact-rate fits converge, no active rate boundary, and closure is interior",
            "45–90 CPU-min after I10",
        ),
        arm(
            "i12.regularized_common_plus_session_scale",
            ["reports/2026_09_24_ds1_iteration12_session_scale/run.py"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-b/iteration12_adapter.py",
            [".venv/bin/python", "batch-b/iteration12_adapter.py", "--ds3-parent", "I10"],
            ["sealed DS3 I10"],
            "joint scale fit converges with all support and every refinement level interior",
            "45–90 CPU-min after I10",
            adapter_state="implemented",
        ),
        arm(
            "i12.shared_norad_rate_control",
            ["reports/2026_09_24_ds1_iteration12_session_scale/run.py"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/i12_shared_norad.py",
            [".venv/bin/python", "batch-c/i12_shared_norad.py", "--ds3-manifest", DS3_MANIFEST],
            ["sealed DS3 I10", "fresh DS3 NORAD overlap audit"],
            "overlap support is nonzero; otherwise terminal not_applicable with measured overlap",
            "30–60 CPU-min after I10",
        ),
        arm(
            "i12.consistent_cap800_objective",
            ["reports/2026_09_24_ds1_iteration12_session_scale/refinement.json"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/i12_cap800.py",
            [".venv/bin/python", "batch-c/i12_cap800.py", "--ds3-manifest", DS3_MANIFEST],
            ["sealed DS3 I10 support"],
            "proposal and final cap-800 exact objective use identical support and "
            "agree on an interior winner",
            "30–60 CPU-min after I10",
        ),
        arm(
            "baseline_doppler",
            [timing, "reports/2026_09_24_ds1_train_full/runner_registry.json"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/timing_arms.py",
            [".venv/bin/python", "batch-c/timing_arms.py", "--arm", "baseline"],
            ["sealed DS3 all56 manifest"],
            "fresh DS3 blind association; interior geographic result or explicit "
            "unqualified terminal",
            "20–45 CPU-min",
        ),
        arm(
            "independent_per_track_time",
            ["reports/2026_09_24_ds1_timing_ablations/run.py"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/timing_arms.py",
            [".venv/bin/python", "batch-c/timing_arms.py", "--arm", "independent_per_track"],
            ["sealed DS3 all56 manifest"],
            "per-track timing is bounded/interior; report degrees of freedom and held support",
            "30–75 CPU-min",
        ),
        arm(
            "causal_per_norad_orbit_rate",
            ["reports/2026_09_24_ds1_orbit_arm/run.py"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/orbit_soft_arms.py",
            [".venv/bin/python", "batch-c/orbit_soft_arms.py", "--arm", "per_norad_rate"],
            ["sealed DS3 all56 manifest"],
            "causal rate fits pass exact SGP4 and active-bound checks",
            "60–120 CPU-min; up to eight NORAD workers",
        ),
        arm(
            "global_time_plus_per_norad_orbit_rate",
            [orbit, "reports/2026_09_24_ds1_train_full/runner_registry.json"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/orbit_soft_arms.py",
            [".venv/bin/python", "batch-c/orbit_soft_arms.py", "--arm", "global_time_plus_rate"],
            ["sealed DS3 all56 manifest"],
            "global tau and causal rates are interior; exact SGP4 replay passes",
            "60–120 CPU-min; up to eight NORAD workers",
        ),
        arm(
            "soft_identity_mixture",
            [orbit, "reports/2026_09_24_ds1_train_full/runner_registry.json"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/orbit_soft_arms.py",
            [".venv/bin/python", "batch-c/orbit_soft_arms.py", "--arm", "soft_association"],
            ["sealed DS3 candidate-state cache"],
            "ESS, candidate influence, and temperature stability pass; I30/I31 are not aliases",
            "90–180 CPU-min",
        ),
        arm(
            "soft_association_plus_global_time",
            [orbit, "reports/2026_09_24_ds1_train_full/runner_registry.json"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/orbit_soft_arms.py",
            [
                ".venv/bin/python",
                "batch-c/orbit_soft_arms.py",
                "--arm",
                "soft_association_global_time",
            ],
            ["sealed DS3 candidate-state cache"],
            "ESS, candidate influence, temperature, and global-tau interior gates pass",
            "90–180 CPU-min",
        ),
        arm(
            "learned_pointing_cone_quantiles",
            ["reports/2026_09_23_train_pointing_cone/run.py"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/cone_arms.py",
            [".venv/bin/python", "batch-c/cone_arms.py", "--arm", "learned_quantiles"],
            ["sealed DS3 geometry and all56 support"],
            "learned cone is fitted only on DS3 TRAIN support; report not_applicable "
            "if geometry support is absent",
            "20–50 CPU-min",
        ),
        arm(
            "fixed_hard_cone_orientation",
            ["reports/2026_09_23_train_fixed_cone/run.py"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/cone_arms.py",
            [".venv/bin/python", "batch-c/cone_arms.py", "--arm", "fixed_hard"],
            ["sealed DS3 geometry and all56 support"],
            "fixed orientation is declared before scoring; retained support is measured",
            "15–35 CPU-min",
        ),
        arm(
            "staged_full_fov_cone_sweep",
            ["reports/2026_09_23_staged_cone_width_sweep/run.py"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/cone_arms.py",
            [".venv/bin/python", "batch-c/cone_arms.py", "--arm", "staged_fov"],
            ["sealed DS3 geometry and all56 support"],
            "every FOV stage reports support; selected FOV and position must be interior",
            "30–75 CPU-min",
        ),
        arm(
            "local_fitted_full_fov_cone_position",
            ["reports/2026_09_24_ds2_geometry_cone_evaluation/run.py"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/cone_arms.py",
            [".venv/bin/python", "batch-c/cone_arms.py", "--arm", "local_fitted_position"],
            ["sealed DS3 geometry", "sealed DS3 all56 support"],
            "joint cone/position closure and held support gate pass; otherwise unqualified",
            "60–120 CPU-min",
        ),
        arm(
            "i22.randomized_time_predictive_diagnostic",
            ["reports/2026_09_25_ds1_iteration22_randomized_time_predictive/run.py"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/diagnostics.py",
            [".venv/bin/python", "batch-c/diagnostics.py", "--diagnostic", "i22"],
            ["sealed DS3 exact parent"],
            "fresh DS3 folds and randomized-time control complete; always diagnostic",
            "10–25 CPU-min",
            output_schema=DIAGNOSTIC_SCHEMA,
        ),
        arm(
            "i23.widened_rate_diagnostic",
            ["reports/2026_09_25_ds1_iteration23_widened_rate/run.py"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/diagnostics.py",
            [".venv/bin/python", "batch-c/diagnostics.py", "--diagnostic", "i23"],
            ["sealed DS3 exact parent"],
            "fresh widened rate audit completes; cannot alter a selected location",
            "10–25 CPU-min",
            output_schema=DIAGNOSTIC_SCHEMA,
        ),
        arm(
            "i24.crossfit_rate_diagnostic",
            ["reports/2026_09_25_ds1_iteration24_crossfit_rate/run.py"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/diagnostics.py",
            [".venv/bin/python", "batch-c/diagnostics.py", "--diagnostic", "i24"],
            ["sealed DS3 exact parent", "fresh DS3 folds"],
            "fresh cross-fit folds complete; output is diagnostic only",
            "15–35 CPU-min",
            output_schema=DIAGNOSTIC_SCHEMA,
        ),
        arm(
            "i25.source_admission_diagnostic",
            ["reports/2026_09_25_ds1_iteration25_source_admission/run.py"],
            "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/diagnostics.py",
            [".venv/bin/python", "batch-c/diagnostics.py", "--diagnostic", "i25"],
            ["sealed DS3 source inventory", "sealed DS3 exact parent"],
            "fresh source-admission control completes; output is diagnostic only",
            "10–25 CPU-min",
            output_schema=DIAGNOSTIC_SCHEMA,
        ),
        arm(
            "i15.information_weighted_historical",
            ["reports/2026_09_24_ds1_iteration15_information_weighted/qualification.json"],
            "none",
            ["terminal-accounting", "i15"],
            ["sealed I19 corrected rate-bound audit"],
            "superseded: I19 invalidates the historical rate-bound qualification",
            "no independent replay; successor is repaired Batch-B I15",
            execution_state="superseded_invalidated",
            adapter_state="none",
            note="Historical output remains diagnostic and must not rank.",
        ),
        arm(
            "i26.legacy_quartic_rate_surrogate",
            ["reports/2026_09_25_ds1_iteration26_rate_marginal/REPORT.md"],
            "none",
            ["terminal-accounting", "i26"],
            ["I27 exact phase-atlas successor"],
            "not portable: quartic rate surrogate is numerically superseded by the "
            "exact phase atlas",
            "no compute",
            execution_state="not_portable_superseded",
            adapter_state="none",
            note="Do not manufacture a DS3 position for this legacy surrogate.",
        ),
        arm(
            "i27.exact_phase_atlas",
            ["reports/2026_09_25_ds1_iteration27_phase_cache/run.py"],
            phase,
            [".venv/bin/python", phase, "run-i27"],
            ["sealed DS3 I8 parent", "passing DS3 phase-atlas preflight"],
            "midpoint atlas error ≤0.2 Hz, exact replay, and stencil qualification",
            "60–120 CPU-min after I8",
            output_schema="ds3-all-iterations-result/v1",
            execution_state="blocked_on_live_parent",
            adapter_state="implemented",
        ),
        arm(
            "i28.phase_atlas_basin_search",
            ["reports/2026_09_25_ds1_iteration28_basin_search/run.py"],
            phase,
            [".venv/bin/python", phase, "run-i28"],
            ["sealed terminal DS3 I27"],
            "direction, ray, and transverse brackets pass under truth-blind DS3 cells",
            "30–90 CPU-min after I27",
            output_schema="ds3-all-iterations-result/v1",
            execution_state="blocked_on_live_parent",
            adapter_state="implemented",
        ),
        arm(
            "i29.phase_atlas_final_proposal",
            ["reports/2026_09_25_ds1_iteration29_resolution_safe_search/REPORT.md"],
            phase,
            [".venv/bin/python", phase, "run-i29"],
            ["sealed terminal DS3 I28", "sealed DS3 phase-atlas cell cache"],
            "non-duplicate final proposal converges and all checkpoint bindings validate",
            "20–60 CPU-min after I28",
            output_schema="ds3-all-iterations-result/v1",
            execution_state="blocked_on_live_parent",
            adapter_state="implemented",
        ),
    ]


def build() -> dict[str, Any]:
    value = {
        "schema": "ds3-method-execution-coverage-plan/v1",
        "dataset": {"name": "DS3", "scope": "all56", "manifest": DS3_MANIFEST},
        "source_audit": "reports/2026_09_25_ds1_ds3_all_methods/method-coverage-audit.json",
        "iteration_ledger": (
            "reports/2026_09_25_ds3_all_iterations_backfill/paired-completion-matrix-v4.json"
        ),
        "policy": {
            "inference_inputs": "fresh DS3 state only",
            "no_compute_by_this_plan": True,
            "i15": "superseded and unrankable after sealed I19 audit",
            "i26": "not portable and superseded by I27 exact phase atlas",
        },
        "arms": arms(),
    }
    ids = [row["method_id"] for row in value["arms"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate method ID")
    return value


def write(path: Path, value: dict[str, Any]) -> None:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "\n"
    )


def markdown(value: dict[str, Any]) -> str:
    lines = [
        "# DS3 distinct-method execution coverage plan",
        "",
        "This is a scheduler-independent, no-compute plan. Every fresh run uses "
        "only the sealed DS3 all56 manifest and DS3-local parents. A planned "
        "adapter is not an executed replay.",
        "",
        "| Method arm | State | DS3 adapter | Dependencies | Terminal gate | Runtime |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in value["arms"]:
        lines.append(
            "| {method} | {state} | `{adapter}` | {dependencies} | {gate} | {runtime} |".format(
                method=item["method_id"],
                state=item["execution_state"],
                adapter=item["ds3_adapter"],
                dependencies="; ".join(item["dependencies"]) or "—",
                gate=item["terminal_gate"],
                runtime=item["runtime_estimate"],
            )
        )
    lines.extend(
        [
            "",
            "I15 is represented only as a superseded, unrankable historical arm "
            "because the sealed I19 audit invalidated its rate-bound qualification. "
            "I26 remains not portable because I27 replaces its quartic surrogate "
            "with an exact phase atlas.",
            "",
            "The machine-readable plan carries source artifacts, command, output "
            "schema, gate, and adapter state for each arm.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    value = build()
    write(HERE / "DS3_METHOD_EXECUTION_COVERAGE_PLAN.json", value)
    (HERE / "DS3_METHOD_EXECUTION_COVERAGE_PLAN.md").write_text(markdown(value))
