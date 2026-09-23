#!/usr/bin/env python3
"""Post-seal exact replay audit of a frozen blind shared-orbit solution."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

from leo.analysis.research.formal_orbit import phase_state
from leo.analysis.research.identity_mixture import (
    logsumexp,
    profile_offsets,
    pseudo_huber_log_likelihood,
)
from leo.operations.tle_archive import TleArchiveReader


def _load_validator():
    path = Path(__file__).with_name("validate_blind_shared_orbit.py")
    spec = importlib.util.spec_from_file_location("sealed_validation_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("validation helper module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def _quartic(batch, phases):
    rows = []
    for index in range(len(batch.norad)):
        rows.append(
            phase_state(
                batch.nominal_hz[index, :, None],
                batch.phase_minus1_hz[index, :, None],
                batch.phase_plus1_hz[index, :, None],
                phases[index],
                1.0,
                minus2=batch.phase_minus2_hz[index, :, None],
                plus2=batch.phase_plus2_hz[index, :, None],
            )[:, 0]
        )
    return np.asarray(rows)


def audit_episode(track, batch, exact, diagnostic, rates, config):
    norad = np.asarray(diagnostic["candidate_norad"], dtype=np.int64)
    if not np.array_equal(norad, batch.norad):
        raise ValueError("sealed candidate order differs from reconstructed support")
    phases = np.asarray([rates[str(int(number))] for number in norad])[:, None] * batch.age_h
    approximate = _quartic(batch, phases)
    exact_hz = np.asarray(
        [
            exact.predict_hz(track["episode_id"], int(number), phase)
            for number, phase in zip(norad, phases, strict=True)
        ]
    )
    raw = approximate - exact_hz
    observed = track["observed_hz"]
    training = track["training"]
    segment = track["segment"]
    approx_centered, _ = profile_offsets(observed[None, :] - approximate, segment, training)
    exact_centered, _ = profile_offsets(observed[None, :] - exact_hz, segment, training)
    centered_error = approx_centered - exact_centered
    approx_heldout = pseudo_huber_log_likelihood(
        approx_centered, ~training, config["signal_sigma_hz"]
    )
    exact_heldout = pseudo_huber_log_likelihood(
        exact_centered, ~training, config["signal_sigma_hz"]
    )
    null_centered, _ = profile_offsets(observed, segment, training)
    null_train = float(
        pseudo_huber_log_likelihood(null_centered, training, config["unassigned_sigma_hz"])
    )
    null_heldout = float(
        pseudo_huber_log_likelihood(null_centered, ~training, config["unassigned_sigma_hz"])
    )
    frozen_weights = np.r_[diagnostic["candidate_posterior"], diagnostic["unassigned_posterior"]]
    frozen_exact_predictive = logsumexp(np.log(frozen_weights) + np.r_[exact_heldout, null_heldout])
    exact_train = pseudo_huber_log_likelihood(
        exact_centered, training, config["signal_sigma_hz"]
    ) + np.log(config["signal_prior"] / track["catalogue_size"])
    visible = np.ones(len(norad), dtype=bool) if batch.visible is None else batch.visible
    exact_train = np.where(visible, exact_train, -np.inf)
    components = np.r_[exact_train, null_train + np.log1p(-config["signal_prior"])]
    updated_weights = np.exp(components - logsumexp(components))
    updated_exact_predictive = logsumexp(
        np.log(updated_weights) + np.r_[exact_heldout, null_heldout]
    )
    worst = np.unravel_index(np.argmax(np.abs(raw)), raw.shape)
    return {
        "episode_id": track["episode_id"],
        "raw_rms_error_hz": float(np.sqrt(np.mean(raw**2))),
        "raw_maximum_error_hz": float(np.max(np.abs(raw))),
        "offset_centered_rms_error_hz": float(np.sqrt(np.mean(centered_error**2))),
        "offset_centered_maximum_error_hz": float(np.max(np.abs(centered_error))),
        "sealed_approximate_heldout_log_predictive": diagnostic["heldout_log_predictive"],
        "recomputed_approximate_heldout_log_predictive": logsumexp(
            np.log(frozen_weights) + np.r_[approx_heldout, null_heldout]
        ),
        "approximate_heldout_recomputation_absolute_error": abs(
            diagnostic["heldout_log_predictive"]
            - logsumexp(np.log(frozen_weights) + np.r_[approx_heldout, null_heldout])
        ),
        "frozen_approximate_weights_exact_heldout_log_predictive": frozen_exact_predictive,
        "exact_training_updated_weights_heldout_log_predictive": updated_exact_predictive,
        "worst_norad": int(norad[worst[0]]),
        "worst_candidate_frozen_weight": float(frozen_weights[worst[0]]),
        "worst_candidate_nominally_visible": bool(visible[worst[0]]),
        "worst_observation_index": int(worst[1]),
        "worst_candidate_phase_s_range": [
            float(np.min(phases[worst[0]])),
            float(np.max(phases[worst[0]])),
        ],
        "worst_candidate_age_h_range": [
            float(np.min(batch.age_h[worst[0]])),
            float(np.max(batch.age_h[worst[0]])),
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sealed-result", type=Path, required=True)
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    validator, validator_path = _load_validator()
    sealed = json.loads(args.sealed_result.read_text())
    documents = validator._load_shards(args.shards)
    tracks, _ = validator._tracks(documents)
    catalogues = validator._load_catalogues(TleArchiveReader(args.tle_root), documents)
    selected = sealed["selected_shared"]
    diagnostics = {
        item["episode_id"]: item
        for item in sealed["selected_shared_result"]["shared_fit"]["episodes"]
    }
    rates = sealed["selected_shared_result"]["rate_corrections_s_h"]
    config = sealed["protocol"]["configuration"]
    rows = []
    for track in tracks:
        diagnostic = diagnostics[track["episode_id"]]
        info = catalogues[track["snapshot_digest"]]
        numbers = np.asarray(info["catalogue"].satellite_numbers)[info["indices"]]
        lookup = {
            int(number): int(index) for number, index in zip(numbers, info["indices"], strict=True)
        }
        chosen = np.asarray([lookup[int(number)] for number in diagnostic["candidate_norad"]])
        receiver = validator.geodetic_to_ecef_km(
            selected["latitude_deg"], selected["longitude_deg"], 0.0
        )
        lat, lon = np.deg2rad([selected["latitude_deg"], selected["longitude_deg"]])
        up = np.asarray([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
        batch = validator._candidate_batch(track, info, receiver, up, chosen)
        exact = validator._ExactReplay(
            {
                track["episode_id"]: (
                    receiver,
                    info["catalogue"],
                    info["indices"],
                    track["utc_ns"],
                )
            }
        )
        enriched = dict(track, catalogue_size=len(info["indices"]))
        rows.append(audit_episode(enriched, batch, exact, diagnostic, rates, config))
    worst_raw = max(rows, key=lambda row: row["raw_maximum_error_hz"])
    worst_centered = max(rows, key=lambda row: row["offset_centered_maximum_error_hz"])
    approximate_predictive = np.asarray(
        [row["sealed_approximate_heldout_log_predictive"] for row in rows]
    )
    frozen_exact_predictive = np.asarray(
        [row["frozen_approximate_weights_exact_heldout_log_predictive"] for row in rows]
    )
    updated_exact_predictive = np.asarray(
        [row["exact_training_updated_weights_heldout_log_predictive"] for row in rows]
    )
    document = {
        "schema": "blind-shared-orbit-postseal-exact-audit/v1",
        "selection_frozen": True,
        "truth_accessed": False,
        "nuisance_adaptation": "per-track constant offsets refit on training points only",
        "sealed_result_sha256": validator._file_digest(args.sealed_result),
        "validator_helper_sha256": validator._file_digest(validator_path),
        "audit_source_sha256": "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "episode_count": len(rows),
        "maximum_approximate_heldout_recomputation_absolute_error": max(
            row["approximate_heldout_recomputation_absolute_error"] for row in rows
        ),
        "worst_raw": worst_raw,
        "worst_offset_centered": worst_centered,
        "heldout_predictive_totals": {
            "sealed_approximate": float(np.sum(approximate_predictive)),
            "frozen_approximate_weights_exact": float(np.sum(frozen_exact_predictive)),
            "exact_training_updated_weights": float(np.sum(updated_exact_predictive)),
            "frozen_exact_minus_approximate": float(
                np.sum(frozen_exact_predictive - approximate_predictive)
            ),
            "updated_exact_minus_approximate": float(
                np.sum(updated_exact_predictive - approximate_predictive)
            ),
            "maximum_episode_absolute_frozen_exact_delta": float(
                np.max(np.abs(frozen_exact_predictive - approximate_predictive))
            ),
        },
        "episodes": rows,
    }
    document["receipt_sha256"] = validator._digest(document)
    validator._atomic_create(args.output, document)
    print(json.dumps({"output": str(args.output), "receipt_sha256": document["receipt_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
