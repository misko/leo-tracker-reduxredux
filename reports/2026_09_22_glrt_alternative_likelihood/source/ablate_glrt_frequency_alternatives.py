#!/usr/bin/env python3
"""Frozen-position diagnostic for finite fractional-GLRT CFO alternatives.

The alternative nuisance profile is deterministic multi-start EM. It is a local
profile approximation, not a proof of the global mixture maximum and not a
global marginalization over the constant offset.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.research.regional_doppler import (
    LIGHT_KM_S,
    REFERENCE_RF_HZ,
    ObservationArc,
    Region,
    ScoreConfig,
    logsumexp,
    score_states,
)
from leo.sky.propagation import parse_element_sets

ALIAS_PERIOD_HZ = 1.0 / 4.4e-6
CANONICAL_RF_HZ = 11_200_000_000.0
DEFAULT_SIGMA_HZ = 250.0


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def wrap_period(value, period=ALIAS_PERIOD_HZ):
    value = np.asarray(value, dtype=float)
    return (value + period / 2) % period - period / 2


def canonical_alternatives(group: dict) -> np.ndarray:
    """Map passing raw CFO alternatives around the exported selected CFO."""
    actual_rf = float(group["actual_rf_hz"])
    selected_rank = int(group["selected_candidate_rank"])
    candidates = [row for row in group["candidates"] if row["passed_fractional_margin_gate"]]
    candidates.sort(key=lambda row: row["candidate_rank"] != selected_rank)
    selected_rows = [row for row in group["candidates"] if row["candidate_rank"] == selected_rank]
    if len(selected_rows) != 1 or actual_rf <= 0 or not candidates:
        raise ValueError("selected and passing CFO candidates are required")
    selected_raw = float(selected_rows[0]["fractional_tracking_cfo_hz"])
    selected_canonical = float(group["selected_trajectory_cfo_hz"])
    return np.asarray(
        [
            selected_canonical
            + wrap_period(float(row["fractional_tracking_cfo_hz"]) - selected_raw)
            * CANONICAL_RF_HZ
            / actual_rf
            for row in candidates
        ]
    )


def deduplicate_passing(group: dict, cfo_tolerance_hz=0.01, epoch_tolerance_samples=0.01):
    """Uniform unique passing alternatives; GLRT score is deliberately not a weight."""
    passing = [row for row in group["candidates"] if row["passed_fractional_margin_gate"]]
    passing.sort(key=lambda row: row["candidate_rank"] != group["selected_candidate_rank"])
    canonical = canonical_alternatives(group)
    kept = []
    for row, frequency in zip(passing, canonical, strict=True):
        epoch = float(row["integer_epoch_sample"]) + float(row["fractional_epoch_offset_samples"])
        if any(
            abs(frequency - prior[0]) < cfo_tolerance_hz
            and abs(epoch - prior[1]) < epoch_tolerance_samples
            for prior in kept
        ):
            continue
        kept.append((float(frequency), epoch, int(row["candidate_rank"])))
    if not kept:
        raise ValueError("deduplication removed every passing alternative")
    return tuple(kept)


def _row_log_mixture(residual_rows: tuple[np.ndarray, ...], offset_hz: float, sigma_hz: float):
    output = np.empty(len(residual_rows), dtype=float)
    for index, values in enumerate(residual_rows):
        exponent = -0.5 * ((values - offset_hz) / sigma_hz) ** 2
        maximum = np.max(exponent)
        output[index] = maximum + np.log(np.mean(np.exp(exponent - maximum))) - np.log(sigma_hz)
    return output


def profile_alternative_offset(
    observed_alternatives: tuple[np.ndarray, ...],
    predicted_hz: np.ndarray,
    training: np.ndarray,
    sigma_hz: float = DEFAULT_SIGMA_HZ,
    *,
    maximum_iterations: int = 80,
    tolerance_hz: float = 1e-9,
) -> dict[str, object]:
    """Deterministic local multi-start profile of one candidate's constant offset."""
    prediction = np.asarray(predicted_hz, dtype=float)
    mask = np.asarray(training, dtype=bool)
    if (
        len(observed_alternatives) != len(prediction)
        or mask.shape != prediction.shape
        or min(np.sum(mask), np.sum(~mask)) < 1
        or sigma_hz <= 0
    ):
        raise ValueError("aligned train/heldout rows and positive sigma required")
    residual = tuple(
        np.asarray(values, dtype=float) - prediction[index]
        for index, values in enumerate(observed_alternatives)
    )
    train_rows = tuple(residual[index] for index in np.flatnonzero(mask))
    maximum_width = max(len(values) for values in train_rows)
    seeds = [float(np.mean([values[0] for values in train_rows]))]
    for column in range(maximum_width):
        seeds.append(
            float(np.mean([values[min(column, len(values) - 1)] for values in train_rows]))
        )
    candidates = []
    for seed in seeds:
        offset = seed
        converged = False
        for _iteration in range(maximum_iterations):
            numerator = 0.0
            denominator = 0.0
            for values in train_rows:
                exponent = -0.5 * ((values - offset) / sigma_hz) ** 2
                weights = np.exp(exponent - np.max(exponent))
                weights /= np.sum(weights)
                numerator += float(np.sum(weights * values))
                denominator += 1.0
            updated = numerator / denominator
            if abs(updated - offset) <= tolerance_hz:
                offset, converged = updated, True
                break
            offset = updated
        train_row_log = _row_log_mixture(train_rows, offset, sigma_hz)
        candidates.append((float(np.sum(train_row_log)), offset, converged, _iteration + 1))
    best = max(candidates, key=lambda row: row[0])
    all_rows = _row_log_mixture(residual, best[1], sigma_hz)
    return {
        "offset_hz": best[1],
        "training_row_log_likelihood": all_rows[mask],
        "heldout_row_log_likelihood": all_rows[~mask],
        "converged": best[2],
        "iterations": best[3],
        "start_count": len(seeds),
        "profile_status": "deterministic-local-multistart-not-global-certified",
    }


def selected_only_offset(observed_hz, predicted_hz, training, sigma_hz=DEFAULT_SIGMA_HZ):
    observed = np.asarray(observed_hz, dtype=float)
    prediction = np.asarray(predicted_hz, dtype=float)
    mask = np.asarray(training, dtype=bool)
    if observed.shape != prediction.shape or mask.shape != observed.shape:
        raise ValueError("selected observations, predictions, and mask must align")
    offset = float(np.mean((observed - prediction)[mask]))
    row_log = -0.5 * ((observed - prediction - offset) / sigma_hz) ** 2 - np.log(sigma_hz)
    return offset, row_log[mask], row_log[~mask]


def profile_candidate_batch(
    observed_alternatives: tuple[np.ndarray, ...],
    predicted_hz: np.ndarray,
    training: np.ndarray,
    sigma_hz: float = DEFAULT_SIGMA_HZ,
    *,
    maximum_iterations: int = 120,
    tolerance_hz: float = 1e-6,
) -> dict[str, object]:
    """Vectorized form of the same local multistart profile for many candidates."""
    prediction = np.asarray(predicted_hz, dtype=float)
    mask = np.asarray(training, dtype=bool)
    if prediction.ndim != 2 or prediction.shape[1] != len(observed_alternatives):
        raise ValueError("predictions must be candidate by observation")
    width = max(len(row) for row in observed_alternatives)
    observed = np.zeros((len(observed_alternatives), width), dtype=float)
    valid = np.zeros_like(observed, dtype=bool)
    for index, row in enumerate(observed_alternatives):
        values = np.asarray(row, dtype=float)
        observed[index, : len(values)] = values
        valid[index, : len(values)] = True
    residual = observed[None] - prediction[:, :, None]
    starts = []
    first = np.mean(residual[:, mask, 0], axis=1)
    starts.append(first)
    for column in range(width):
        selected = np.minimum(column, np.sum(valid, axis=1) - 1)
        trajectory = residual[:, np.arange(len(observed)), selected]
        starts.append(np.mean(trajectory[:, mask], axis=1))
    offsets = np.stack(starts, axis=1)
    converged = np.zeros_like(offsets, dtype=bool)
    iterations = np.zeros_like(offsets, dtype=int)
    train_valid = valid[mask]
    train_residual = residual[:, mask]
    for iteration in range(1, maximum_iterations + 1):
        exponent = -0.5 * ((train_residual[:, None] - offsets[:, :, None, None]) / sigma_hz) ** 2
        exponent = np.where(train_valid[None, None], exponent, -np.inf)
        maximum = np.max(exponent, axis=-1, keepdims=True)
        weight = np.exp(exponent - maximum)
        weight = np.where(train_valid[None, None], weight, 0.0)
        weight /= np.sum(weight, axis=-1, keepdims=True)
        updated = np.mean(np.sum(weight * train_residual[:, None], axis=-1), axis=-1)
        newly = (~converged) & (np.abs(updated - offsets) <= tolerance_hz)
        iterations[newly] = iteration
        converged |= newly
        offsets = np.where(converged, offsets, updated)
        if np.all(converged):
            break
    iterations[~converged] = maximum_iterations
    exponent = -0.5 * ((residual[:, None] - offsets[:, :, None, None]) / sigma_hz) ** 2
    exponent = np.where(valid[None, None], exponent, -np.inf)
    maximum = np.max(exponent, axis=-1)
    row_log = (
        maximum
        + np.log(
            np.sum(np.exp(exponent - maximum[..., None]), axis=-1)
            / np.sum(valid, axis=-1)[None, None]
        )
        - np.log(sigma_hz)
    )
    score = np.sum(row_log[:, :, mask], axis=-1)
    best = np.argmax(score, axis=1)
    index = np.arange(len(prediction))
    selected_rows = row_log[index, best]
    return {
        "offset_hz": offsets[index, best],
        "training_row_log_likelihood": selected_rows[:, mask],
        "heldout_row_log_likelihood": selected_rows[:, ~mask],
        "converged": converged[index, best],
        "iterations": iterations[index, best],
        "start_count": offsets.shape[1],
        "profile_status": "deterministic-local-multistart-not-global-certified",
    }


def effective_log_likelihood(row_log_likelihood, effective_count=6.0):
    values = np.asarray(row_log_likelihood, dtype=float)
    if not len(values) or effective_count <= 0:
        raise ValueError("nonempty rows and positive effective count required")
    return float(effective_count * np.mean(values))


def gaussian_rows_at_frozen_offsets(observed_hz, predicted_hz, offset_hz, sigma_hz):
    """Score one selected CFO target with candidate-specific frozen offsets."""
    observed = np.asarray(observed_hz, dtype=float)
    prediction = np.asarray(predicted_hz, dtype=float)
    offset = np.asarray(offset_hz, dtype=float)
    if prediction.ndim != 2 or prediction.shape[1] != len(observed):
        raise ValueError("predictions must be candidate by observation")
    if offset.shape != (len(prediction),) or sigma_hz <= 0:
        raise ValueError("one frozen offset per candidate and positive sigma required")
    return -0.5 * ((observed[None] - prediction - offset[:, None]) / sigma_hz) ** 2 - np.log(
        sigma_hz
    )


def _load_replay():
    path = Path(__file__).parents[1] / "replay_regional_doppler.py"
    spec = importlib.util.spec_from_file_location("glrt_alt_replay", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("replay helper unavailable")
    spec.loader.exec_module(module)
    return module, path


def _content_digest(document: dict) -> str:
    body = dict(document)
    claimed = body.pop("content_digest", None)
    actual = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    if claimed != actual:
        raise ValueError("content digest mismatch")
    return actual


def _five_block_indices(row: dict) -> tuple[np.ndarray, np.ndarray]:
    time_s = np.asarray(row["t_s"], dtype=float)
    order = np.argsort(time_s, kind="stable")
    blocks = np.array_split(order, 5)
    training = np.concatenate([blocks[index] for index in (0, 2, 4)])
    heldout = np.concatenate([blocks[index] for index in (1, 3)])
    return (
        training[np.argsort(time_s[training], kind="stable")],
        heldout[np.argsort(time_s[heldout], kind="stable")],
    )


def _mixture_evidence(
    candidate_train, candidate_heldout, null_train, null_heldout, population, prior
):
    log_prior = np.log(prior / population)
    null_prior = np.log1p(-prior)
    train = float(np.logaddexp(logsumexp(candidate_train + log_prior), null_train + null_prior))
    joint = float(
        np.logaddexp(
            logsumexp(candidate_train + candidate_heldout + log_prior),
            null_train + null_heldout + null_prior,
        )
    )
    return train - (null_train + null_prior), joint - train - null_heldout


def _alternative_lookup(document: dict) -> dict[tuple[str, str], dict]:
    _content_digest(document)
    if document.get("truth_accessed") or document.get("inference_performed"):
        raise ValueError("truth-free raw alternative export required")
    output = {}
    for session in document["sessions"]:
        digest_body = dict(session)
        # The exporter binds the public-port document before the outer writer
        # adds the on-disk source-shard file digest.
        digest_body.pop("source_shard_file_digest", None)
        digest_body["content_digest"] = session["content_digest"]
        _content_digest(digest_body)
        session_id = session["session_id"]
        for group in session["groups"]:
            key = (session_id, group["source_group_id"])
            if key in output:
                raise ValueError("duplicate alternative source group")
            output[key] = group
    return output


def _write_checkpoint(path: Path, document: dict) -> None:
    document["content_digest"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    path.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")


def run_diagnostic(args) -> None:
    if args.output.exists():
        raise FileExistsError(args.output)
    started = time.monotonic()
    refinement = json.loads(args.refinement.read_text())
    checksum = args.refinement.with_name("result.sha256")
    seal = json.loads(args.refinement.with_name("refinement-seal.json").read_text())
    if (
        checksum.read_text().strip() != hashlib.sha256(args.refinement.read_bytes()).hexdigest()
        or seal.get("result_digest") != digest(args.refinement)
        or not seal.get("all_fits_converged")
        or refinement.get("position_truth_used") is not False
    ):
        raise ValueError("sealed converged truth-free refinement required")
    alternative_document = json.loads(args.alternatives.read_text())
    alternatives = _alternative_lookup(alternative_document)
    replay, replay_path = _load_replay()
    acquisition = json.loads((Path(refinement["run"]) / "result.json").read_text())
    config = ScoreConfig(**acquisition["score"])
    if config.signal_sigma_hz != DEFAULT_SIGMA_HZ:
        raise ValueError("diagnostic requires the declared 250 Hz signal sigma")
    region = Region(**refinement["region"])
    selected = refinement["selected"]
    grid = region.points([selected["east_km"]], [selected["north_km"]])
    output = {
        "schema": "frozen-position-glrt-frequency-alternatives/v1",
        "status": "running",
        "truth_accessed": False,
        "position_optimized": False,
        "profile_status": "deterministic-local-multistart-not-global-certified",
        "refinement": str(args.refinement),
        "tracks": [],
        "failures": [],
        "provenance": {
            "refinement_digest": digest(args.refinement),
            "alternative_export_digest": digest(args.alternatives),
            "source_digest": digest(Path(__file__)),
            "replay_digest": digest(replay_path),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    selected_total = np.zeros(2)
    alternative_total = np.zeros(2)
    common_target_total = np.zeros(2)
    maximum_parity = 0.0
    selected_profile_nonconverged = 0
    null_profile_nonconverged = 0
    for session_id in refinement["sessions"]:
        evidence_path = args.evidence / "evidence" / f"{session_id}.json"
        evidence = json.loads(evidence_path.read_text())
        provenance = refinement["provenance"][session_id]
        if digest(evidence_path) != provenance["rf_digest"]:
            raise ValueError("evidence binding mismatch")
        inventory = evidence["inventory"]
        tle_path = evidence_path.parent / inventory["tle_file"]
        if (
            Path(inventory["tle_file"]).name != inventory["tle_file"]
            or digest(tle_path) != inventory["tle_digest"]
        ):
            raise ValueError("unsafe or mismatched TLE")
        if inventory["tle_collected_ns"] >= inventory["reference_utc_ns"] - 5_000_000_000:
            raise ValueError("noncausal TLE")
        catalogue = parse_element_sets(tle_path.read_text())
        indices, population = replay.regional_catalogue(
            catalogue, inventory["reference_utc_ns"], region
        )
        for row in evidence["series"]:
            if time.monotonic() - started > args.budget_seconds:
                output.update(
                    {
                        "status": "partial_resource_budget",
                        "qualified": False,
                        "elapsed_s": time.monotonic() - started,
                        "selected_total": selected_total.tolist(),
                        "alternative_total": alternative_total.tolist(),
                        "alternative_common_target_total": common_target_total.tolist(),
                        "maximum_selected_control_parity_error": maximum_parity,
                        "selected_candidate_profile_nonconverged_count": (
                            selected_profile_nonconverged
                        ),
                        "null_profile_nonconverged_count": null_profile_nonconverged,
                    }
                )
                _write_checkpoint(args.output, output)
                return
            track_started = time.monotonic()
            try:
                train_index, heldout_index = _five_block_indices(row)
                order = np.r_[train_index, heldout_index]
                training = np.r_[
                    np.ones(len(train_index), dtype=bool), np.zeros(len(heldout_index), dtype=bool)
                ]
                arc = ObservationArc(
                    np.asarray(row["t_s"])[order],
                    np.asarray(row["y_hz"])[order],
                    np.zeros(len(order), dtype=int),
                    training,
                    partition="randomized",
                )
                observed_alternatives = tuple(
                    np.asarray(
                        [
                            item[0]
                            for item in deduplicate_passing(
                                alternatives[(session_id, row["paired_visit_ids"][index])]
                            )
                        ]
                    )
                    for index in order
                )
                p, v, retained = replay.state_arrays(
                    catalogue, indices, inventory["reference_utc_ns"], arc.time_s
                )
                norad = np.asarray(catalogue.satellite_numbers)[retained]
                baseline = next(
                    item
                    for item in provenance["evaluated_support"]
                    if item["episode_id"] == row["tracklet_id"]
                )
                support_digest = (
                    "sha256:" + hashlib.sha256(np.sort(norad).astype("<i8").tobytes()).hexdigest()
                )
                if support_digest != baseline["evaluated_norad_digest"]:
                    raise ValueError("candidate support differs from refinement")
                delta = p - grid.ecef_km[0]
                distance = np.linalg.norm(delta, axis=-1)
                prediction = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * v, axis=-1) / distance
                elevation = np.sum(delta * grid.up[0], axis=-1) / distance
                visible = np.min(elevation[:, training], axis=1) >= np.sin(
                    np.deg2rad(config.minimum_elevation_deg)
                )
                selected_offset = np.mean(
                    arc.frequency_hz[None, training] - prediction[:, training], axis=1
                )
                selected_row = -0.5 * (
                    (arc.frequency_hz[None] - prediction - selected_offset[:, None])
                    / config.signal_sigma_hz
                ) ** 2 - np.log(config.signal_sigma_hz)
                selected_train = config.effective_count * np.mean(selected_row[:, training], axis=1)
                selected_heldout = config.effective_count * np.mean(
                    selected_row[:, ~training], axis=1
                )
                selected_train = np.where(visible, selected_train, -np.inf)
                selected_heldout = np.where(visible, selected_heldout, -np.inf)
                null_offset, null_train_row, null_heldout_row = selected_only_offset(
                    arc.frequency_hz, np.zeros(len(order)), training, config.null_sigma_hz
                )
                del null_offset
                selected_score = _mixture_evidence(
                    selected_train,
                    selected_heldout,
                    effective_log_likelihood(null_train_row, config.effective_count),
                    effective_log_likelihood(null_heldout_row, config.effective_count),
                    population,
                    config.signal_prior,
                )
                core = score_states(arc, p, v, grid, population, config)
                parity = max(
                    abs(selected_score[0] - float(core["train_logbf"][0])),
                    abs(selected_score[1] - float(core["heldout_logbf"][0])),
                )
                maximum_parity = max(maximum_parity, parity)
                if parity > 1e-6:
                    raise ValueError(f"selected control parity failed: {parity}")
                profile = profile_candidate_batch(
                    observed_alternatives,
                    prediction[visible],
                    training,
                    config.signal_sigma_hz,
                )
                alternative_train = np.full(len(prediction), -np.inf)
                alternative_heldout = np.full(len(prediction), -np.inf)
                alternative_train[visible] = config.effective_count * np.mean(
                    profile["training_row_log_likelihood"], axis=1
                )
                alternative_heldout[visible] = config.effective_count * np.mean(
                    profile["heldout_row_log_likelihood"], axis=1
                )
                null_profile = profile_candidate_batch(
                    observed_alternatives,
                    np.zeros((1, len(order))),
                    training,
                    config.null_sigma_hz,
                )
                alternative_score = _mixture_evidence(
                    alternative_train,
                    alternative_heldout,
                    effective_log_likelihood(
                        null_profile["training_row_log_likelihood"][0], config.effective_count
                    ),
                    effective_log_likelihood(
                        null_profile["heldout_row_log_likelihood"][0], config.effective_count
                    ),
                    population,
                    config.signal_prior,
                )
                common_candidate_rows = gaussian_rows_at_frozen_offsets(
                    arc.frequency_hz,
                    prediction[visible],
                    profile["offset_hz"],
                    config.signal_sigma_hz,
                )
                common_candidate_heldout = np.full(len(prediction), -np.inf)
                common_candidate_heldout[visible] = config.effective_count * np.mean(
                    common_candidate_rows[:, ~training], axis=1
                )
                common_null_rows = gaussian_rows_at_frozen_offsets(
                    arc.frequency_hz,
                    np.zeros((1, len(order))),
                    null_profile["offset_hz"],
                    config.null_sigma_hz,
                )[0]
                common_target_score = _mixture_evidence(
                    alternative_train,
                    common_candidate_heldout,
                    effective_log_likelihood(
                        null_profile["training_row_log_likelihood"][0],
                        config.effective_count,
                    ),
                    effective_log_likelihood(common_null_rows[~training], config.effective_count),
                    population,
                    config.signal_prior,
                )
                selected_total += selected_score
                alternative_total += alternative_score
                common_target_total += common_target_score
                output["tracks"].append(
                    {
                        "session_id": session_id,
                        "tracklet_id": row["tracklet_id"],
                        "observation_count": len(order),
                        "candidate_count": len(norad),
                        "training_visible_candidate_count": int(np.sum(visible)),
                        "selected_train_logbf": selected_score[0],
                        "selected_heldout_logbf": selected_score[1],
                        "alternative_train_logbf": alternative_score[0],
                        "alternative_heldout_logbf": alternative_score[1],
                        "alternative_common_target_heldout_logbf": (common_target_score[1]),
                        "candidate_profile_nonconverged": int(np.sum(~profile["converged"])),
                        "null_profile_converged": bool(null_profile["converged"][0]),
                        "selected_control_parity_error": parity,
                        "elapsed_s": time.monotonic() - track_started,
                    }
                )
                selected_profile_nonconverged += int(np.sum(~profile["converged"]))
                null_profile_nonconverged += int(not null_profile["converged"][0])
            except Exception as error:
                output["failures"].append(
                    {
                        "session_id": session_id,
                        "tracklet_id": row["tracklet_id"],
                        "reason": str(error),
                    }
                )
            _write_checkpoint(args.output, output)
    qualified = bool(
        not output["failures"]
        and selected_profile_nonconverged == 0
        and null_profile_nonconverged == 0
        and maximum_parity <= 1e-6
    )
    output.update(
        {
            "status": "complete" if qualified else "insufficient_profile_or_failures",
            "qualified": qualified,
            "elapsed_s": time.monotonic() - started,
            "selected_total": selected_total.tolist(),
            "alternative_total": alternative_total.tolist(),
            "alternative_minus_selected": (alternative_total - selected_total).tolist(),
            "alternative_common_target_total": common_target_total.tolist(),
            "alternative_common_target_minus_selected": (
                common_target_total - selected_total
            ).tolist(),
            "maximum_selected_control_parity_error": maximum_parity,
            "track_count": len(output["tracks"]),
            "failure_count": len(output["failures"]),
            "selected_candidate_profile_nonconverged_count": selected_profile_nonconverged,
            "null_profile_nonconverged_count": null_profile_nonconverged,
        }
    )
    _write_checkpoint(args.output, output)


def benchmark(candidate_count: int, observation_count: int, alternatives: int) -> dict:
    rng = np.random.default_rng(20260922)
    observed = tuple(
        np.sort(rng.normal(0, 350, size=alternatives)) for _ in range(observation_count)
    )
    prediction = rng.normal(0, 150, size=(candidate_count, observation_count))
    training = np.arange(observation_count) % 5 < 3
    started = time.monotonic()
    profile = profile_candidate_batch(observed, prediction, training)
    elapsed = time.monotonic() - started
    return {
        "schema": "glrt-frequency-alternative-profile-benchmark/v1",
        "candidate_count": candidate_count,
        "observation_count": observation_count,
        "alternatives_per_row": alternatives,
        "elapsed_s": elapsed,
        "candidate_profiles_per_s": candidate_count / elapsed,
        "converged_count": int(np.sum(profile["converged"])),
        "profile_status": "deterministic-local-multistart-not-global-certified",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-output", type=Path)
    parser.add_argument("--candidate-count", type=int, default=3000)
    parser.add_argument("--observation-count", type=int, default=32)
    parser.add_argument("--alternatives", type=int, default=3)
    parser.add_argument("--refinement", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--alternatives-input", dest="alternatives_input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--budget-seconds", type=float, default=600.0)
    args = parser.parse_args()
    if args.benchmark_output:
        result = benchmark(args.candidate_count, args.observation_count, args.alternatives)
        args.benchmark_output.write_text(json.dumps(result, indent=2) + "\n")
    elif all((args.refinement, args.evidence, args.alternatives_input, args.output)):
        args.alternatives = args.alternatives_input
        run_diagnostic(args)
    else:
        parser.error("provide benchmark output or all diagnostic inputs")
