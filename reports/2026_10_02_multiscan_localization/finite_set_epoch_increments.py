#!/usr/bin/env python3
"""Truth-free frame-epoch increment diagnostics at sealed finite-set fits."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, build_likelihood_arms
from finite_set_rf_score import jsonable, validate_authoritative_bindings
from prediction_plan import SharedPredictionPlan

ROOT = Path(__file__).resolve().parent
DEFAULT_PROFILE_ROOT = ROOT / "runs" / "finite-set-tau-profile-v1"
DEFAULT_GROUPED_ROOT = ROOT / "runs" / "finite-set-grouped-cohort-v1"
DEFAULT_EXPORTS = ROOT / "runs" / "alias-family-cohort-v1"
DEFAULT_OUTPUT = ROOT / "finite-set-epoch-increments-v1.json"
EXPORT_SHA256 = "8752be16157de6c04e7242e6178d2e9e74725ec3c5eb279e9cbc3eefc43b34b1"
SUPPORTED_UNITS = ("DS10-S01", "DS11-S02")
POSTERIOR_THRESHOLD = 0.8
MAX_GAP_S = 1.0
FRAME_RATE_HZ = 750.0
SIGMA_HZ = 200.0


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def snapshot(paths):
    return {str(Path(path).resolve()): digest(path) for path in paths}


def circular_delta(value, period):
    value = np.asarray(value, dtype=float)
    if not np.isfinite(period) or period <= 0:
        raise ValueError("circular period must be positive and finite")
    return (value + 0.5 * period) % period - 0.5 * period


def _quantiles(values):
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or np.any(~np.isfinite(values)):
        raise ValueError("summary values must be a finite vector")
    if not len(values):
        return {
            "count": 0,
            "minimum": None,
            "p05": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p95": None,
            "maximum": None,
        }
    quantiles = np.quantile(values, [0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0])
    names = ("minimum", "p05", "p25", "median", "p75", "p95", "maximum")
    return {"count": len(values), **dict(zip(names, map(float, quantiles), strict=True))}


def bind_representative_metadata(data, export_receipt):
    """Bind reduced numerical rows to persisted frame-epoch metadata."""

    if (
        export_receipt.get("schema") != "alias-family-capture-export/v1"
        or export_receipt.get("sealed") is not True
    ):
        raise ValueError("alias-family export is not sealed")
    rows = export_receipt.get("grouping", {}).get("representative_rows")
    exported = np.asarray(export_receipt.get("representative_original_indices"), dtype=int)
    original = np.asarray(getattr(data, "original_rows", ()), dtype=int)
    receiver = np.asarray(data.receiver, dtype=int)
    channel = np.asarray(data.channel, dtype=int)
    measured = np.asarray(data.measured, dtype=float)
    group = np.asarray(data.group)
    count = len(data.times)
    if (
        not isinstance(rows, list)
        or len(rows) != count
        or exported.shape != (count,)
        or original.shape != (count,)
        or receiver.shape != (count,)
        or channel.shape != (count,)
        or measured.shape != (count,)
        or group.shape != (count,)
        or not np.array_equal(exported, original)
    ):
        raise ValueError("representative metadata order differs from reduced numerical rows")
    if export_receipt.get("accounting", {}).get("grouped_family_count") != count:
        raise ValueError("representative metadata count differs from export accounting")
    sample_rate_hz = float(export_receipt.get("sample_rate_hz", 0.0))
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("export sample rate must be positive and finite")
    physical_period_samples = sample_rate_hz / FRAME_RATE_HZ
    acquisition_period_samples = round(physical_period_samples)
    if acquisition_period_samples <= 0:
        raise ValueError("acquisition frame period must be positive")
    session_id = export_receipt.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("alias-family export lacks a session identity")
    device_origins = set()
    bound = []
    candidate_ids = set()
    for index, row in enumerate(rows):
        specification = row.get("candidate_spec")
        probe_key = row.get("probe_key")
        local_probe = row.get("local_probe_key")
        candidate_id = row.get("candidate_id")
        if (
            not isinstance(specification, dict)
            or not isinstance(probe_key, list)
            or not isinstance(local_probe, list)
            or len(local_probe) != 3
            or probe_key != [session_id, *local_probe]
            or not isinstance(candidate_id, str)
            or candidate_id in candidate_ids
        ):
            raise ValueError("representative candidate identity or probe lineage is malformed")
        candidate_ids.add(candidate_id)
        visit_index, receiver_id, probe_index = map(int, local_probe)
        integer_epoch = int(row["integer_epoch_sample"])
        integer_session = int(row["integer_session_sample"])
        fractional_offset = float(row["fractional_epoch_offset_samples"])
        fractional_epoch = float(row["fractional_epoch_samples"])
        integer_device = int(specification["integer_device_sample_counter"])
        specification_epoch = int(specification["integer_epoch_sample"])
        specification_session = int(specification["integer_session_sample"])
        specification_offset = float(specification["fractional_epoch_offset_samples"])
        fractional_time = float(specification["fractional_time_s"])
        expected_epoch = integer_epoch + fractional_offset
        expected_time = (integer_session + fractional_offset) / sample_rate_hz
        if (
            receiver_id != int(receiver[index])
            or not math.isclose(
                float(row["tracking_cfo_hz"]),
                float(measured[index]),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            or specification_epoch != integer_epoch
            or specification_session != integer_session
            or not math.isclose(
                specification_offset, fractional_offset, rel_tol=0.0, abs_tol=0.0
            )
            or not math.isclose(
                fractional_epoch, expected_epoch, rel_tol=0.0, abs_tol=1e-12
            )
            or not math.isclose(fractional_time, expected_time, rel_tol=0.0, abs_tol=1e-15)
        ):
            raise ValueError(
                "representative epoch metadata differs from numerical or persisted data"
            )
        device_origins.add(integer_device - integer_session)
        acquisition_phase = fractional_epoch % acquisition_period_samples
        seam_distance = min(
            acquisition_phase, acquisition_period_samples - acquisition_phase
        )
        bound.append(
            {
                "row_index": index,
                "candidate_id": candidate_id,
                "visit_index": visit_index,
                "receiver": receiver_id,
                "probe_index": probe_index,
                "channel": int(channel[index]),
                "group": int(group[index]),
                "fractional_time_s": fractional_time,
                "frame_epoch_samples": fractional_epoch,
                "frame_phase_samples": float(fractional_epoch % physical_period_samples),
                "acquisition_ring_seam": bool(seam_distance <= 2.0),
            }
        )
    if len(device_origins) != 1:
        raise ValueError("representative rows do not share one capture device-counter origin")
    return {
        "rows": bound,
        "sample_rate_hz": sample_rate_hz,
        "physical_period_samples": physical_period_samples,
        "acquisition_period_samples": acquisition_period_samples,
        "device_counter_origin": next(iter(device_origins)),
    }


def select_strongest_satellite_rows(
    metadata_rows,
    association_probability,
    selected_satellites,
    catalog_numbers,
    *,
    threshold=POSTERIOR_THRESHOLD,
):
    """Select rows whose strongest sealed finite-set posterior meets the threshold."""

    association = np.asarray(association_probability, dtype=float)
    selected_satellites = np.asarray(selected_satellites, dtype=int)
    catalog_numbers = np.asarray(catalog_numbers, dtype=int)
    if (
        association.shape != (len(metadata_rows), len(selected_satellites))
        or np.any(~np.isfinite(association))
        or np.any((association < 0) | (association > 1))
        or selected_satellites.ndim != 1
        or not len(selected_satellites)
        or len(np.unique(selected_satellites)) != len(selected_satellites)
        or np.any(selected_satellites < 0)
        or np.any(selected_satellites >= len(catalog_numbers))
    ):
        raise ValueError("posterior association or satellite bank is invalid")
    if not np.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("posterior threshold must lie in (0, 1]")
    strongest = np.argmax(association, axis=1)
    support = association[np.arange(len(association)), strongest]
    selected = []
    for row, local_satellite, probability in zip(
        metadata_rows, strongest, support, strict=True
    ):
        if probability < threshold:
            continue
        satellite_index = int(selected_satellites[local_satellite])
        selected.append(
            {
                **row,
                "selected_satellite_column": int(local_satellite),
                "satellite_index": satellite_index,
                "catalog_number": int(catalog_numbers[satellite_index]),
                "posterior_probability": float(probability),
            }
        )
    return selected


def _pair_records(selected_rows, *, sample_rate_hz, max_gap_s):
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample rate must be positive and finite")
    if not np.isfinite(max_gap_s) or max_gap_s <= 0:
        raise ValueError("maximum gap must be positive and finite")
    period_samples = sample_rate_hz / FRAME_RATE_HZ
    by_chain = defaultdict(list)
    for row in selected_rows:
        by_chain[(row["catalog_number"], row["receiver"], row["channel"])].append(row)
    pairs = []
    gap_excluded_count = 0
    nonpositive_gap_excluded_count = 0
    candidate_adjacent_pair_count = 0
    for chain, chain_rows in by_chain.items():
        ordered = sorted(
            chain_rows,
            key=lambda row: (row["fractional_time_s"], row["candidate_id"]),
        )
        for left, right in zip(ordered, ordered[1:], strict=False):
            candidate_adjacent_pair_count += 1
            gap_s = right["fractional_time_s"] - left["fractional_time_s"]
            if gap_s <= 0:
                nonpositive_gap_excluded_count += 1
                continue
            if gap_s > max_gap_s:
                gap_excluded_count += 1
                continue
            increment_samples = float(
                circular_delta(
                    right["frame_phase_samples"] - left["frame_phase_samples"],
                    period_samples,
                )
            )
            pairs.append(
                {
                    "chain": chain,
                    "same_visit": left["visit_index"] == right["visit_index"],
                    "gap_s": gap_s,
                    "frame_epoch_increment_samples": increment_samples,
                    "frame_epoch_increment_s": increment_samples / sample_rate_hz,
                    "acquisition_ring_seam": bool(
                        left["acquisition_ring_seam"] or right["acquisition_ring_seam"]
                    ),
                }
            )
    return {
        "pairs": pairs,
        "candidate_adjacent_pair_count": candidate_adjacent_pair_count,
        "gap_excluded_adjacent_pair_count": gap_excluded_count,
        "nonpositive_gap_excluded_adjacent_pair_count": nonpositive_gap_excluded_count,
    }


def _pair_summary(pairs):
    return {
        "pair_count": len(pairs),
        "acquisition_ring_seam_pair_count": sum(
            pair["acquisition_ring_seam"] for pair in pairs
        ),
        "gap_s": _quantiles([pair["gap_s"] for pair in pairs]),
        "frame_epoch_increment_samples": _quantiles(
            [pair["frame_epoch_increment_samples"] for pair in pairs]
        ),
        "absolute_frame_epoch_increment_samples": _quantiles(
            [abs(pair["frame_epoch_increment_samples"]) for pair in pairs]
        ),
        "frame_epoch_increment_us": _quantiles(
            [1e6 * pair["frame_epoch_increment_s"] for pair in pairs]
        ),
        "absolute_frame_epoch_increment_us": _quantiles(
            [1e6 * abs(pair["frame_epoch_increment_s"]) for pair in pairs]
        ),
    }


def summarize_epoch_increments(
    selected_rows,
    *,
    sample_rate_hz,
    max_gap_s=MAX_GAP_S,
):
    """Summarize adjacent same-catalog/RX/channel circular frame increments."""

    records = _pair_records(
        selected_rows,
        sample_rate_hz=float(sample_rate_hz),
        max_gap_s=max_gap_s,
    )
    pairs = records.pop("pairs")
    same_visit = [pair for pair in pairs if pair["same_visit"]]
    different_visit = [pair for pair in pairs if not pair["same_visit"]]
    strata = []
    for chain in sorted({pair["chain"] for pair in pairs}):
        subset = [pair for pair in pairs if pair["chain"] == chain]
        catalog, receiver, channel = chain
        strata.append(
            {
                "catalog_number": catalog,
                "receiver": receiver,
                "channel": channel,
                "all": _pair_summary(subset),
                "same_visit_pair_count": sum(pair["same_visit"] for pair in subset),
                "different_visit_pair_count": sum(
                    not pair["same_visit"] for pair in subset
                ),
            }
        )
    return {
        "selected_row_count": len(selected_rows),
        "maximum_gap_s": float(max_gap_s),
        **records,
        "all": _pair_summary(pairs),
        "same_visit": _pair_summary(same_visit),
        "different_visit": {
            **_pair_summary(different_visit),
            "continuity_claimed": False,
        },
        "strata": strata,
        "session_time_modulo_closure_tested": False,
    }


def _selected_trial(receipt):
    if (
        receipt.get("schema") != "finite-set-tau-profile/v1"
        or receipt.get("reference_read_before_seal") is not False
        or receipt.get("evaluation_written") is not False
        or not receipt.get("sealed_utc")
    ):
        raise ValueError("profile receipt is not sealed and truth-free")
    trial = receipt.get("fit", {}).get("selection", {}).get("score_leader")
    if not isinstance(trial, dict):
        raise ValueError("profile receipt lacks a score-leading trial")
    return trial


def diagnose_unit(
    unit_id,
    *,
    profile_root=DEFAULT_PROFILE_ROOT,
    grouped_root=DEFAULT_GROUPED_ROOT,
    exports=DEFAULT_EXPORTS,
    expected_export_sha256=EXPORT_SHA256,
    posterior_threshold=POSTERIOR_THRESHOLD,
    max_gap_s=MAX_GAP_S,
):
    """Evaluate one sealed pilot without fitting or reading reference coordinates."""

    from alias_family_joint import load_cohort_manifest, load_unit_with_family_exports

    if unit_id not in SUPPORTED_UNITS:
        raise ValueError(f"unit_id must be one of {SUPPORTED_UNITS}")
    profile_path = Path(profile_root) / unit_id / "fit.json"
    grouped_path = Path(grouped_root) / unit_id / "fit.json"
    profile = json.loads(profile_path.read_text())
    grouped = json.loads(grouped_path.read_text())
    trial = _selected_trial(profile)
    if (
        profile.get("unit", {}).get("unit_id") != unit_id
        or len(profile.get("unit", {}).get("session_ids", ())) != 1
        or profile.get("source_fit_sha256") != digest(grouped_path)
        or grouped.get("schema") != "finite-set-grouped-cohort/v1"
        or grouped.get("unit", {}).get("unit_id") != unit_id
        or grouped.get("reference_read_before_seal") is not False
        or grouped.get("evaluation_written") is not False
        or not grouped.get("sealed_utc")
    ):
        raise ValueError("profile and grouped pilot receipts are not strictly bound")
    authoritative = profile.get("source_hashes")
    if not isinstance(authoritative, dict) or not authoritative:
        raise ValueError("profile receipt lacks authoritative source hashes")
    assert_snapshot_unchanged(authoritative)
    _, data, input_paths = load_unit_with_family_exports(
        unit_id,
        exports,
        expected_manifest_sha256=expected_export_sha256,
    )
    validate_authoritative_bindings(
        authoritative,
        input_paths,
        data.geometry_receipt,
        grouped.get("fit", {}).get("grouped_geometry", {}),
    )
    source_paths = [
        Path(__file__).resolve(),
        ROOT / "alias_family_joint.py",
        ROOT / "finite_set_fit.py",
        ROOT / "finite_set_likelihood.py",
        ROOT / "finite_set_rf_score.py",
        ROOT / "prediction_plan.py",
        ROOT / "prediction_jacobian.py",
        ROOT / "joint_inputs.py",
    ]
    fixed_paths = [*input_paths, profile_path, grouped_path]
    source_hashes = snapshot(source_paths)
    input_hashes = snapshot(fixed_paths)
    cohort = load_cohort_manifest(
        exports, expected_manifest_sha256=expected_export_sha256
    )
    session_id = profile["unit"]["session_ids"][0]
    record = cohort["records_by_session"].get(session_id)
    if record is None:
        raise ValueError("pilot session is absent from alias-family cohort manifest")
    export_path = cohort["receipt_paths"][session_id]
    if digest(export_path) != record.get("sha256"):
        raise ValueError("alias-family child receipt differs from cohort manifest")
    export_receipt = json.loads(export_path.read_text())
    fixed_paths.append(export_path)
    input_hashes[str(export_path.resolve())] = digest(export_path)
    bound = bind_representative_metadata(data, export_receipt)

    satellites = np.asarray(trial["satellite_indices"], dtype=int)
    parameters = np.asarray(trial["parameters"], dtype=float)
    full_bank = np.asarray(profile["fit"]["full_bank"], dtype=int)
    evaluator = build_likelihood_arms(data, len(satellites), len(full_bank))["finite_set"]
    plan = SharedPredictionPlan(data, satellites)
    predicted, visible, _ = plan.predict(parameters)
    predicted = np.asarray(predicted, dtype=float).reshape(len(data.times), len(satellites))
    visible = np.asarray(visible, dtype=bool).reshape(predicted.shape)
    likelihood = evaluator.evaluate(
        predicted,
        visible,
        sigma_hz=SIGMA_HZ,
        satellite_weights=np.asarray(trial["satellite_weights"], dtype=float),
        background_mass=0.2,
    )
    tau = parameters[6 + satellites]
    reproduced_objective = -float(likelihood["total_log_likelihood"]) + 0.5 * float(
        np.sum(tau**2)
    )
    if not np.isclose(reproduced_objective, trial["objective"], rtol=0.0, atol=1e-6):
        raise ValueError("posterior evaluation does not reproduce sealed objective")
    selected = select_strongest_satellite_rows(
        bound["rows"],
        likelihood["row_association_probability"],
        satellites,
        np.asarray(data.numbers),
        threshold=posterior_threshold,
    )
    increments = summarize_epoch_increments(
        selected,
        sample_rate_hz=bound["sample_rate_hz"],
        max_gap_s=max_gap_s,
    )
    assert_snapshot_unchanged(authoritative)
    if snapshot(source_paths) != source_hashes or snapshot(fixed_paths) != input_hashes:
        raise RuntimeError("diagnostic sources or sealed inputs changed during evaluation")
    return {
        "unit_id": unit_id,
        "dataset": profile["dataset"],
        "session_id": session_id,
        "profile_fit_sha256": digest(profile_path),
        "grouped_source_fit_sha256": digest(grouped_path),
        "alias_family_export_sha256": digest(export_path),
        "source_sha256": source_hashes,
        "input_sha256": input_hashes,
        "selected_fit": {
            "satellite_count": len(satellites),
            "objective": float(trial["objective"]),
            "reproduced_objective": reproduced_objective,
            "success": bool(trial["success"]),
            "status": trial["status"],
            "posterior_threshold": float(posterior_threshold),
        },
        "epoch_binding": {
            "representative_row_count": len(bound["rows"]),
            "selected_row_count": len(selected),
            "sample_rate_hz": bound["sample_rate_hz"],
            "physical_frame_period_samples": bound["physical_period_samples"],
            "acquisition_ring_period_samples": bound["acquisition_period_samples"],
            "period_difference_samples": (
                bound["acquisition_period_samples"] - bound["physical_period_samples"]
            ),
            "selected_acquisition_ring_seam_row_count": sum(
                row["acquisition_ring_seam"] for row in selected
            ),
            "device_counter_origin": bound["device_counter_origin"],
        },
        "increments": increments,
        "interpretation": {
            "frame_epoch": (
                "Circular detector frame epoch uses persisted integer_epoch_sample plus "
                "fractional_epoch_offset_samples modulo 1/750 s. Session time only orders rows "
                "and applies the one-second gap filter, so no session-time modulo closure is "
                "tested or claimed. This is not complex OFDM carrier phase."
            ),
            "different_visit": (
                "Different-visit increments are descriptive only; continuity across visits or "
                "retunes is not asserted."
            ),
            "selection": (
                "Rows are selected only when the strongest sealed finite-set satellite posterior "
                "is at least the declared threshold; identity and all model parameters remain "
                "fixed."
            ),
            "dependence": (
                "Adjacent pairs and posterior-conditioned rows are descriptive and are not "
                "claimed to be independent samples."
            ),
        },
        "provenance": {
            "reference_accessed": False,
            "evaluation_artifact_accessed": False,
            "tle_queried": False,
            "iq_read": False,
            "rf_collection_performed": False,
            "replay_performed": False,
            "fit_performed": False,
            "clock_or_slope_fitted": False,
        },
        "status": "complete",
    }


def run(unit_ids, **kwargs):
    requested = tuple(unit_ids)
    if len(requested) != len(SUPPORTED_UNITS) or set(requested) != set(SUPPORTED_UNITS):
        raise ValueError(f"diagnostic requires exactly {SUPPORTED_UNITS}")
    return {
        "schema": "finite-set-epoch-increments/v1",
        "scope": (
            "Metadata-only circular frame-epoch increments for exactly two sealed pilots; no "
            "clock, slope, location, RX, RF, orbit, or timing parameter is fitted."
        ),
        "configuration": {
            "posterior_threshold": float(kwargs.get("posterior_threshold", POSTERIOR_THRESHOLD)),
            "maximum_gap_s": float(kwargs.get("max_gap_s", MAX_GAP_S)),
            "frame_rate_hz": FRAME_RATE_HZ,
            "units": list(SUPPORTED_UNITS),
        },
        "units": [diagnose_unit(unit_id, **kwargs) for unit_id in SUPPORTED_UNITS],
        "provenance": {
            "reference_accessed": False,
            "evaluation_artifact_accessed": False,
            "iq_read": False,
            "rf_collection_performed": False,
            "fit_performed": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unit_ids", nargs="*", choices=SUPPORTED_UNITS, default=SUPPORTED_UNITS)
    parser.add_argument("--profile-root", type=Path, default=DEFAULT_PROFILE_ROOT)
    parser.add_argument("--grouped-root", type=Path, default=DEFAULT_GROUPED_ROOT)
    parser.add_argument("--exports", type=Path, default=DEFAULT_EXPORTS)
    parser.add_argument("--expected-export-sha256", default=EXPORT_SHA256)
    parser.add_argument("--posterior-threshold", type=float, default=POSTERIOR_THRESHOLD)
    parser.add_argument("--max-gap-s", type=float, default=MAX_GAP_S)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    receipt = run(
        arguments.unit_ids,
        profile_root=arguments.profile_root,
        grouped_root=arguments.grouped_root,
        exports=arguments.exports,
        expected_export_sha256=arguments.expected_export_sha256,
        posterior_threshold=arguments.posterior_threshold,
        max_gap_s=arguments.max_gap_s,
    )
    if arguments.output.exists():
        raise FileExistsError(arguments.output)
    arguments.output.write_text(json.dumps(jsonable(receipt), indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(arguments.output), "unit_count": len(receipt["units"])}))


if __name__ == "__main__":
    main()
