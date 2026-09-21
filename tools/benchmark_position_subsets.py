#!/usr/bin/env python3
"""Prepare and run the prespecified position subset benchmark.

This is a conditional fixed-identity/local-replay benchmark: the archived
assignments are inputs, not identities rediscovered from each reduced subset.
Reduced fits must start from the frozen external starts, never a full-data fit.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import math
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

from leo.analysis.research.position_subsets import (
    Observation,
    build_subset_matrix,
    canonical_hash,
    canonical_json,
)

EXTERNAL_STARTS_KM = ((0.0, 0.0), (-3000.0, 0.0), (3000.0, 0.0))
SEEDS = tuple(range(20))


def atomic_write_result(path: Path, payload: dict[str, Any]) -> str:
    """Publish one complete result, or accept an exactly identical retry."""
    encoded = canonical_json(payload) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == encoded:
            return "existing"
        raise FileExistsError(f"result collision: {path}")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() == encoded:
                return "existing"
            raise FileExistsError(f"result collision: {path}") from None
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return "written"
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def file_hash(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def prepare_manifest(polish: Path, evidence: Path, output: Path) -> dict[str, Any]:
    """Freeze stable RF metadata corresponding to the archived polish cohort."""
    inference_path = polish / "inference.json"
    inputs_path = polish / "inputs.json"
    inference = read_json(inference_path)
    records = read_json(inputs_path)["records"]
    assignments = inference["assignments"]
    if len(records) != len(assignments):
        raise ValueError("record/assignment length mismatch")
    observations: list[Observation] = []
    evidence_hashes: dict[str, str] = {}
    for record, assignment in zip(records, assignments, strict=True):
        for key in ("session_id", "episode_id"):
            if record[key] != assignment[key]:
                raise ValueError(f"record/assignment {key} mismatch")
        path = evidence / f"{record['session_id']}.json"
        doc = read_json(path)
        observed_hash = file_hash(path)
        evidence_hashes[str(path)] = observed_hash
        inventory = doc["inventory"]
        episode_id = record["episode_id"]
        series = next((x for x in doc["series"] if x["tracklet_id"] == episode_id), None)
        if series is None:
            raise ValueError(f"missing RF series {episode_id}")
        # Episode IDs and channels come from RF processing; assignment NORAD is
        # deliberately not represented in sampling metadata.
        times = series["t_s"]
        training = series.get("training")
        if training is None:
            # Strict replay loader defines the same deterministic randomized split.
            from replay_regional_doppler import load_observations

            arc = dict(load_observations(doc, 0))[episode_id]
            training = [bool(x) for x in arc.training]
            times = [float(x) for x in arc.time_s]
        if len(times) != len(training):
            raise ValueError("time/training length mismatch")
        reference = int(inventory["reference_utc_ns"])
        for index, (time_s, fitting) in enumerate(zip(times, training, strict=True)):
            observations.append(
                Observation(
                    observation_id=f"{record['session_id']}:{episode_id}:{index}",
                    track_id=f"{record['session_id']}:{episode_id}",
                    pass_group_id=f"{record['session_id']}:{episode_id}",
                    timestamp_ns=reference + round(float(time_s) * 1e9),
                    fitting=bool(fitting),
                    channel=f"ch{series['channel']}:{series.get('edge', 'unknown')}",
                    sample_rate_hz=int(inventory["sample_rate_hz"]),
                )
            )
    body = {
        "schema": "position-subset-benchmark-manifest-v1",
        "scientific_scope": "conditional-fixed-identity-local-replay",
        "identity_warning": "assignments originate in the archived full-RF analysis",
        "truth_used_for_sampling_or_inference": False,
        "seeds": list(SEEDS),
        "fractions": [0.25, 0.5, 1.0],
        "rounding": "floor",
        "external_starts_km": [list(x) for x in EXTERNAL_STARTS_KM],
        "input_files": {
            str(inference_path): file_hash(inference_path),
            str(inputs_path): file_hash(inputs_path),
            **evidence_hashes,
        },
        "observations": [asdict(x) for x in observations],
    }
    body["manifest_hash"] = canonical_hash(body)
    atomic_write_result(output, body)
    return body


def plan_jobs(manifest: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    expected = manifest.get("manifest_hash")
    check = dict(manifest)
    check.pop("manifest_hash", None)
    if expected != canonical_hash(check):
        raise ValueError("manifest hash mismatch")
    rows = tuple(Observation(**x) for x in manifest["observations"])
    row_by_id = {x.observation_id: x for x in rows}
    full_count = sum(x.fitting for x in rows)
    subsets = build_subset_matrix(
        rows, seeds=SEEDS, fractions=config.get("fractions", [0.25, 0.5, 1.0])
    )
    config_hash = canonical_hash(config)
    jobs: list[dict[str, Any]] = []
    models = config.get("models", [{"name": config["model"]}])
    for model in models:
        source_path = (
            Path(__file__).with_name("compare_positioning_cohorts.py")
            if model["name"] == "legacy-strict-fixed-orbit"
            else Path(__file__).parents[1] / "src/leo/analysis/research/formal_orbit.py"
        )
        numerical_source_hash = file_hash(source_path)
        by_membership: dict[str, dict[str, Any]] = {}
        for subset in subsets:
            membership = canonical_hash(
                {
                    "model": model,
                    "fitting_ids": subset.fitting_ids,
                    "evaluation_ids": subset.evaluation_ids,
                }
            )
            if membership in by_membership:
                by_membership[membership]["subset_aliases"].append(asdict(subset))
                continue
            request = {
                "schema": "position-subset-job-v1",
                "manifest_hash": expected,
                "config_hash": config_hash,
                "model": model["name"],
                "model_config": model.get("formal_orbit_config", {}),
                "numerical_source_hash": numerical_source_hash,
                "config": config,
                "subset": asdict(subset),
                "subset_aliases": [],
                "subset_id": subset.subset_id,
                "external_starts_km": [list(x) for x in EXTERNAL_STARTS_KM],
                "initialization": "independent-external-starts-training-objective-only",
                "scientific_scope": manifest["scientific_scope"],
                "subset_metrics": _subset_metrics(subset, row_by_id, full_count),
            }
            jobs.append(request)
            by_membership[membership] = request
    for request in jobs:
        request["job_id"] = canonical_hash(request)
    return jobs


def _subset_metrics(subset, row_by_id: dict[str, Observation], full_count: int) -> dict[str, Any]:
    selected = [row_by_id[x] for x in subset.fitting_ids]
    times = [x.timestamp_ns for x in selected]
    return {
        "requested_fraction": subset.fraction,
        "actual_fitting_count": len(selected),
        "full_fitting_count": full_count,
        "actual_fraction": len(selected) / full_count if full_count else 0.0,
        "actual_track_count": len({x.track_id for x in selected}),
        "actual_pass_group_count": len({x.pass_group_id for x in selected}),
        "actual_span_s": (max(times) - min(times)) / 1e9 if len(times) >= 2 else 0.0,
        "unusable_track_count": len(subset.unusable_track_ids),
    }


def _verify_numerical_source(request: dict[str, Any], path: Path) -> None:
    expected = request.get("numerical_source_hash")
    observed = file_hash(path)
    if expected is None or observed != expected:
        raise ValueError(f"numerical source hash mismatch: {path}")


def formal_fixed_identity_adapter(request: dict[str, Any]) -> dict[str, Any]:
    """Adapter for the pure formal-orbit API; reads no evaluation coordinate."""
    import numpy as np

    if request["model"] == "legacy-strict-fixed-orbit":
        return _legacy_strict_adapter(request)

    import leo.analysis.research.formal_orbit as formal_module
    from leo.analysis.research.formal_orbit import (
        FormalOrbitConfig,
        FormalOrbitData,
        fit_formal_orbit,
    )
    from leo.analysis.research.regional_doppler import Region

    config = request["config"]
    _verify_numerical_source(request, Path(formal_module.__file__))
    manifest = read_json(Path(config["manifest_path"]))
    manifest_check = dict(manifest)
    manifest_check.pop("manifest_hash", None)
    if canonical_hash(manifest_check) != request["manifest_hash"]:
        raise ValueError("adapter manifest hash mismatch")
    ids = np.asarray([x["observation_id"] for x in manifest["observations"]])
    states_path = Path(config["prepared_states_npz"])
    if file_hash(states_path) != config["prepared_states_hash"]:
        raise ValueError("prepared states hash mismatch")
    states = np.load(states_path)
    if str(states["schema"].item()) != "formal-orbit-phase-state-v1":
        raise ValueError("unsupported prepared orbit-phase state schema")
    if len(ids) != len(states["y_hz"]):
        raise ValueError("manifest/state row mismatch")
    if "legacy_states_npz" in config:
        legacy = np.load(config["legacy_states_npz"])
        if not (
            np.array_equal(states["y_hz"], legacy["y"])
            and np.array_equal(states["training"], legacy["training"])
            and np.array_equal(states["segment"], legacy["segment"])
            and np.array_equal(states["track"], legacy["episode"])
        ):
            raise ValueError("prepared-state row ordering differs from sealed strict rows")
    data = FormalOrbitData(
        y_hz=states["y_hz"],
        training=states["training"],
        segment=states["segment"],
        track=states["track"],
        source=states["source"],
        age_h=states["age_h"],
        p_km=states["p_km"],
        v_km_s=states["v_km_s"],
        phase_p_minus_km=states["phase_p_minus_km"],
        phase_v_minus_km_s=states["phase_v_minus_km_s"],
        phase_p_plus_km=states["phase_p_plus_km"],
        phase_v_plus_km_s=states["phase_v_plus_km_s"],
        time_s=states["time_s"],
        observation_id=ids,
    )
    selected = np.isin(ids, request["subset"]["fitting_ids"])
    fit_segments = np.unique(states["segment"][selected & states["training"]])
    supported = (~states["training"]) & np.isin(states["segment"], fit_segments)
    region = Region(**config["region"])
    settings = {**config.get("formal_orbit_config", {}), **request.get("model_config", {})}
    model_config = FormalOrbitConfig(**settings)
    attempts = []
    attempt_diagnostics = []
    for initial in request["external_starts_km"]:
        try:
            result = fit_formal_orbit(data, region, initial, model_config, fitting_mask=selected)
            attempts.append(result)
            attempt_diagnostics.append(
                {
                    "initial_x_km": initial,
                    "status": "converged" if result.converged else "nonconverged",
                    "negative_log_posterior": result.negative_log_posterior,
                }
            )
        except (ValueError, np.linalg.LinAlgError, FloatingPointError) as error:
            attempt_diagnostics.append(
                {
                    "initial_x_km": initial,
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "reason": str(error),
                }
            )
    if not attempts:
        return {
            "status": "failed",
            "failure": "all-independent-starts-failed",
            "fitting_observations": int(np.sum(selected & states["training"])),
            "supported_evaluation_observations": int(np.sum(supported)),
            "unavailable_evaluation_observations": int(
                np.sum(~states["training"]) - np.sum(supported)
            ),
            "attempts": attempt_diagnostics,
        }
    best = min(attempts, key=lambda x: x.negative_log_posterior)
    payload = dataclasses.asdict(best)
    payload.update(
        {
            "status": "converged" if best.converged else "nonconverged",
            "successful_starts": len(attempts),
            "fitting_observations": int(np.sum(selected & states["training"])),
            "supported_evaluation_observations": int(np.sum(supported)),
            "unavailable_evaluation_observations": int(
                np.sum(~states["training"]) - np.sum(supported)
            ),
            "supported_evaluation_ids": ids[supported].tolist(),
            "attempts": attempt_diagnostics,
        }
    )
    _verify_numerical_source(request, Path(formal_module.__file__))
    return payload


def _legacy_strict_adapter(request: dict[str, Any]) -> dict[str, Any]:
    """Historical robust fixed-UTC estimator on strict causal nominal states."""
    import compare_positioning_cohorts as legacy_module
    import numpy as np
    from compare_positioning_cohorts import fit

    from leo.analysis.research.regional_doppler import Region

    config = request["config"]
    _verify_numerical_source(request, Path(legacy_module.__file__))
    path = Path(config["legacy_states_npz"])
    if file_hash(path) != config["legacy_states_hash"]:
        raise ValueError("legacy strict states hash mismatch")
    z = np.load(path)
    manifest = read_json(Path(config["manifest_path"]))
    manifest_check = dict(manifest)
    manifest_check.pop("manifest_hash", None)
    if canonical_hash(manifest_check) != request["manifest_hash"]:
        raise ValueError("adapter manifest hash mismatch")
    ids = np.asarray([x["observation_id"] for x in manifest["observations"]])
    if len(ids) != len(z["y"]):
        raise ValueError("manifest/legacy-state row mismatch")
    selected = np.isin(ids, request["subset"]["fitting_ids"]) & z["training"]
    fit_segments = np.unique(z["segment"][selected])
    supported = (~z["training"]) & np.isin(z["segment"], fit_segments)
    # Discarded training rows stay discarded; only original held-out rows enter scoring.
    mask = selected | supported
    data = {key: z[key] for key in z.files}
    region = Region(**config["region"])
    attempts, diagnostics = [], []
    for initial in request["external_starts_km"]:
        try:
            result = fit(data, region, initial, "observation", True, subset=mask)
            attempts.append(result)
            diagnostics.append(
                {
                    "initial_x_km": initial,
                    "status": "converged" if result["converged"] else "nonconverged",
                    "training_rms_hz": result["training_rms_hz"],
                }
            )
        except (ValueError, np.linalg.LinAlgError, FloatingPointError) as error:
            diagnostics.append(
                {
                    "initial_x_km": initial,
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "reason": str(error),
                }
            )
    if not attempts:
        return {
            "status": "failed",
            "failure": "all-independent-starts-failed",
            "attempts": diagnostics,
        }
    best = min(attempts, key=lambda x: x["training_rms_hz"])
    payload = {
        **best,
        "status": "converged" if best["converged"] else "nonconverged",
        "fitting_observations": int(np.sum(selected)),
        "supported_evaluation_observations": int(np.sum(supported)),
        "unavailable_evaluation_observations": int(np.sum(~z["training"]) - np.sum(supported)),
        "supported_evaluation_ids": ids[supported].tolist(),
        "attempts": diagnostics,
    }
    _verify_numerical_source(request, Path(legacy_module.__file__))
    return payload


def write_plan(manifest_path: Path, config_path: Path, output: Path) -> dict[str, Any]:
    manifest, config = read_json(manifest_path), read_json(config_path)
    plan = {
        "schema": "position-subset-plan-v1",
        "manifest_hash": manifest["manifest_hash"],
        "config_hash": canonical_hash(config),
        "jobs": plan_jobs(manifest, config),
    }
    plan["plan_hash"] = canonical_hash(plan)
    atomic_write_result(output, plan)
    return plan


def _run_one(adapter: str, request: dict[str, Any], result_dir: str) -> str:
    module_name, function_name = adapter.split(":", 1)
    import importlib

    function = getattr(importlib.import_module(module_name), function_name)
    payload = function(request)
    if not isinstance(payload, dict):
        raise TypeError("fit adapter must return a JSON object")
    result = {
        "schema": "position-subset-result-v1",
        "job_id": request["job_id"],
        "manifest_hash": request["manifest_hash"],
        "config_hash": request["config_hash"],
        "subset_id": request["subset_id"],
        "result": payload,
    }
    atomic_write_result(
        Path(result_dir) / f"{request['job_id'].removeprefix('sha256:')}.json", result
    )
    return request["job_id"]


def run_plan(plan: dict[str, Any], adapter: str, result_dir: Path, workers: int) -> None:
    if not 1 <= workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    pending = []
    for request in plan["jobs"]:
        path = result_dir / f"{request['job_id'].removeprefix('sha256:')}.json"
        if path.exists():
            existing = read_json(path)
            if existing.get("job_id") != request["job_id"]:
                raise FileExistsError(f"result collision: {path}")
            continue
        pending.append(request)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run_one, adapter, request, str(result_dir)) for request in pending]
        for future in as_completed(futures):
            future.result()


def _horizontal_error_m(lat: float, lon: float, truth_lat: float, truth_lon: float) -> float:
    p1, p2 = math.radians(lat), math.radians(truth_lat)
    dp, dl = p2 - p1, math.radians(truth_lon - lon)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_008.8 * math.asin(math.sqrt(min(1.0, a)))


def summarize_plan(
    plan: dict[str, Any],
    result_dir: Path,
    output: Path,
    figure: Path,
    truth_latitude_deg: float,
    truth_longitude_deg: float,
) -> dict[str, Any]:
    """Evaluate already-sealed inference; truth is accepted only by this step."""
    rows = []
    for job in plan["jobs"]:
        path = result_dir / f"{job['job_id'].removeprefix('sha256:')}.json"
        if not path.exists():
            rows.append({"job_id": job["job_id"], "model": job["model"], "status": "missing"})
            continue
        result = read_json(path)["result"]
        row = {
            "job_id": job["job_id"],
            "subset_id": job["subset_id"],
            "model": job["model"],
            "method": job["subset"]["method"],
            "fraction": job["subset"]["fraction"],
            "seed": job["subset"]["seed"],
            "window_start_ns": job["subset"]["window_start_ns"],
            "window_end_ns": job["subset"]["window_end_ns"],
            **job["subset_metrics"],
            "status": result["status"],
            "attempts": result.get("attempts", []),
            "latitude_deg": result.get("latitude_deg"),
            "longitude_deg": result.get("longitude_deg"),
            "training_rms_hz": result.get("training_rms_hz"),
            "evaluation_rms_hz": result.get("evaluation_rms_hz"),
            "measurement_sigma_hz": result.get("measurement_sigma_hz"),
            "major_95_km": result.get("major_95_km"),
            "identifiability": result.get("identifiability"),
            "nuisance_converged": result.get("nuisance_converged"),
            "information_rank": result.get("information_rank"),
            "information_condition": result.get("information_condition"),
            "nfev": result.get("nfev"),
            "supported_evaluation_observations": result.get("supported_evaluation_observations", 0),
            "unavailable_evaluation_observations": result.get(
                "unavailable_evaluation_observations", 0
            ),
        }
        if row["latitude_deg"] is not None and row["longitude_deg"] is not None:
            row["horizontal_error_m"] = _horizontal_error_m(
                row["latitude_deg"], row["longitude_deg"], truth_latitude_deg, truth_longitude_deg
            )
        rows.append(row)
    summary = {
        "schema": "position-subset-evaluation-v1",
        "plan_hash": plan["plan_hash"],
        "truth_applied_after_inference_sealed": True,
        "truth": {"latitude_deg": truth_latitude_deg, "longitude_deg": truth_longitude_deg},
        "runs": rows,
    }
    summary["evaluation_hash"] = canonical_hash(summary)
    atomic_write_result(output, summary)
    _plot_summary(rows, figure)
    return summary


def _plot_summary(rows: list[dict[str, Any]], path: Path) -> None:
    import matplotlib.pyplot as plt

    usable = [
        x
        for x in rows
        if x.get("horizontal_error_m") is not None and x.get("status") == "converged"
    ]
    display_models = {
        "formal orbit correction": (
            {"formal-orbit-correction", "formal-orbit-correction-v6"},
            "#2b6cb0",
        ),
        "strict fixed-orbit baseline": ({"legacy-strict-fixed-orbit"}, "#c05621"),
    }
    known = set().union(*(names for names, _ in display_models.values()))
    for index, model in enumerate(sorted({row["model"] for row in usable} - known)):
        display_models[model] = ({model}, f"C{index % 10}")
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    failures = sum(x.get("status") != "converged" for x in rows)
    fig.suptitle(f"Converged fits only; {failures}/{len(rows)} runs did not converge", fontsize=12)
    for display_name, (model_versions, color) in display_models.items():
        for method, marker in (("density", "o"), ("pass", "s")):
            data = [x for x in usable if x["model"] in model_versions and x["method"] == method]
            axes[0, 0].scatter(
                [x["actual_fraction"] for x in data],
                [x["horizontal_error_m"] for x in data],
                s=18,
                alpha=0.65,
                marker=marker,
                color=color,
                label=f"{display_name}; {method}",
            )
            axes[0, 1].scatter(
                [x["actual_fitting_count"] for x in data],
                [x["evaluation_rms_hz"] for x in data],
                s=18,
                alpha=0.65,
                marker=marker,
                color=color,
            )
        duration = sorted(
            (x for x in usable if x["model"] in model_versions and x["method"] == "duration"),
            key=lambda x: x["window_end_ns"] - x["window_start_ns"],
        )
        axes[1, 0].plot(
            [(x["window_end_ns"] - x["window_start_ns"]) / 3.6e12 for x in duration],
            [x["horizontal_error_m"] for x in duration],
            "o-",
            color=color,
            label=display_name,
        )
        axes[1, 1].scatter(
            [x["horizontal_error_m"] for x in usable if x["model"] in model_versions],
            [x["evaluation_rms_hz"] for x in usable if x["model"] in model_versions],
            s=18,
            alpha=0.65,
            color=color,
            label=display_name,
        )
    axes[0, 0].set(xlabel="actual fitting fraction", ylabel="horizontal error (m)", yscale="log")
    axes[0, 1].set(
        xlabel="actual fitting observations", ylabel="supported held-out RMS (Hz)", xscale="log"
    )
    axes[1, 0].set(xlabel="duration window (h)", ylabel="horizontal error (m)")
    if any(x["method"] == "duration" for x in usable):
        axes[1, 0].set_xscale("log")
        axes[1, 0].set_yscale("log")
    axes[1, 1].set(
        xlabel="horizontal error (m)", ylabel="supported held-out RMS (Hz)", xscale="log"
    )
    axes[0, 0].legend(fontsize=7)
    axes[1, 0].legend(fontsize=7)
    axes[1, 1].legend(fontsize=7)
    for axis in axes.flat:
        axis.grid(alpha=0.25)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.png")
    fig.savefig(temporary, dpi=160)
    plt.close(fig)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--polish", type=Path, required=True)
    prepare.add_argument("--evidence", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--manifest", type=Path, required=True)
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--adapter", required=True, help="importable module:function")
    run.add_argument("--result-dir", type=Path, required=True)
    run.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    summarize = sub.add_parser("summarize")
    summarize.add_argument("--plan", type=Path, required=True)
    summarize.add_argument("--result-dir", type=Path, required=True)
    summarize.add_argument("--output", type=Path, required=True)
    summarize.add_argument("--figure", type=Path, required=True)
    summarize.add_argument("--truth-latitude-deg", type=float, required=True)
    summarize.add_argument("--truth-longitude-deg", type=float, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare_manifest(args.polish, args.evidence, args.output)
    elif args.command == "plan":
        write_plan(args.manifest, args.config, args.output)
    elif args.command == "run":
        run_plan(read_json(args.plan), args.adapter, args.result_dir, args.workers)
    else:
        summarize_plan(
            read_json(args.plan),
            args.result_dir,
            args.output,
            args.figure,
            args.truth_latitude_deg,
            args.truth_longitude_deg,
        )


if __name__ == "__main__":
    main()
