from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from leo.analysis.research import final_holdout_protocol as protocol


def _association() -> dict[str, object]:
    latitude = 37.858988
    longitude = -122.478103
    latitude_delta = 50.0 / 111_320.0
    longitude_delta = 50.0 / (111_320.0 * math.cos(math.radians(latitude)))
    return {
        "catalog_scope": "Starlink-only",
        "time_shift_s": 0.0,
        "primary_lane": "lean_500ms_quadratic",
        "baseline_lane": "fixed_500ms_linear",
        "bin_width_ms": 20.0,
        "training_fraction_of_full_target_span": 0.6,
        "maximum_pre_response_compute_seconds": 3600.0,
        "minimum_total_bins": 10,
        "minimum_training_bins": 6,
        "minimum_evaluation_bins": 4,
        "minimum_visible_candidates": 2,
        "nuisance_primary": "one-constant-CFO-offset-per-capture",
        "free_candidate_rate_primary": False,
        "shared_rate_diagnostic_only": True,
        "shared_rate_group": "physical_receiver_id",
        "shared_rate_prior_sigma_hz_s": 50.0,
        "shared_rate_hard_bound_hz_s": 150.0,
        "shared_rate_objective": (
            "(sum_capture_training_MSE + 50^2*sum_group(rate/50)^2)/capture_count"
        ),
        "wrong_time_offsets_s": [float(value) for value in range(-18000, 0, 900)]
        + [float(value) for value in range(900, 18001, 900)],
        "within_track_permutations": 20,
        "within_track_permutation_seed": 20260826,
        "rolling_origin_training_fractions": [0.4, 0.6, 0.8],
        "minimum_claim_heldout_odd_bins": 8,
        "minimum_heldout_odd_bin_fraction": 0.5,
        "maximum_claim_rank_one_heldout_odd_rms_hz": 100.0,
        "training_runner_margin_ratio_minimum": 1.10,
        "heldout_runner_margin_ratio_minimum": 1.10,
        "wrong_time_minimum_scored": 38,
        "null_empirical_p_maximum": 0.05,
        "all_20_permutations_required": True,
        "minimum_stable_rolling_origins": 2,
        "primary_baseline_rank_one_agreement_required": True,
        "utc_site_predecessor_identity_stability_required": True,
        "absolute_secure_norad_forced_false": True,
        "site_sensitivity": [
            {
                "control_id": "site-north-50m",
                "latitude_deg": latitude + latitude_delta,
                "longitude_deg": longitude,
                "altitude_m": -29.0,
                "label": "Spinnaker, Sausalito north 50 m sensitivity",
            },
            {
                "control_id": "site-south-50m",
                "latitude_deg": latitude - latitude_delta,
                "longitude_deg": longitude,
                "altitude_m": -29.0,
                "label": "Spinnaker, Sausalito south 50 m sensitivity",
            },
            {
                "control_id": "site-east-50m",
                "latitude_deg": latitude,
                "longitude_deg": longitude + longitude_delta,
                "altitude_m": -29.0,
                "label": "Spinnaker, Sausalito east 50 m sensitivity",
            },
            {
                "control_id": "site-west-50m",
                "latitude_deg": latitude,
                "longitude_deg": longitude - longitude_delta,
                "altitude_m": -29.0,
                "label": "Spinnaker, Sausalito west 50 m sensitivity",
            },
        ],
    }


def test_json_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema":"first","schema":"second"}')

    with pytest.raises(ValueError, match="duplicate JSON key"):
        protocol._load_json_without_duplicate_keys(path)


def test_authorized_chunks_require_exact_paths_and_keys() -> None:
    chunks = [
        {
            "session_id": session,
            "stream_id": stream,
            "relative_path": relative,
            "sample_start": start,
            "sample_count": count,
            "compressed_sha256": digest,
        }
        for session, stream, relative, start, count, digest in protocol._EXPECTED_CHUNKS
    ]
    protocol._validate_chunks(chunks)

    substituted = json.loads(json.dumps(chunks))
    substituted[0]["relative_path"] = "radio-substituted/iq-000006.ci16.zst"
    with pytest.raises(ValueError, match="geometry/digest"):
        protocol._validate_chunks(substituted)

    extra = json.loads(json.dumps(chunks))
    extra[0]["unexpected"] = True
    with pytest.raises(ValueError, match="key set"):
        protocol._validate_chunks(extra)


def test_association_protocol_freezes_coordinates_and_availability() -> None:
    association = _association()
    protocol._validate_association(association)

    changed_fraction = json.loads(json.dumps(association))
    changed_fraction["minimum_heldout_odd_bin_fraction"] = 0.49
    with pytest.raises(ValueError, match="association/control"):
        protocol._validate_association(changed_fraction)

    changed_site = json.loads(json.dumps(association))
    changed_site["site_sensitivity"][0]["latitude_deg"] += 1e-9
    with pytest.raises(ValueError, match="association/control"):
        protocol._validate_association(changed_site)
