from __future__ import annotations

import json
from pathlib import Path

import pytest
import zstandard as zstd

from leo.analysis.catalogue_prediction import ExactTauPolicy, Sgp4SupportPredictionPolicy
from leo.analysis.research.long_arc_observability_rebuild import (
    LongArcObservabilityRebuildError,
    load_sealed_response_free_bank_inventory,
    rebuild_digest_identical_field_banks,
)
from leo.contracts.catalogue_association import (
    CataloguePredictionSupportObservationV1,
    CataloguePredictionSupportV1,
)
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1


def _digest(label: str, value: object) -> str:
    return canonical_digest({label: value})


def _candidate(number: int) -> dict[str, object]:
    return {
        "catalog_number": number,
        "object_name": f"STARLINK-{number}",
        "selected_element_digest": _digest("element", number),
        "element_epoch_utc_ns": 1_700_000_000_000_000_000 + number,
        "element_age_s_at_reference": 10.0,
    }


def _field(delta: int, number: int) -> dict[str, object]:
    return {
        "field_delta_s": delta,
        "population_receipt_digest": _digest("population", delta),
        "selection_policy_digest": _digest("selection", delta),
        "candidate_universe_digest": _digest("universe", delta),
        "prediction_bank_digest": _digest("bank", delta),
        "candidate_count": 1,
        "candidates": [_candidate(number)],
        "propagation_complete_for_association": True,
    }


def _archive_bytes(*, suffix: bytes = b', "partitions": RESPONSE-MUST-NOT-BE-PARSED') -> bytes:
    prefix = json.dumps(
        {
            "algorithm_version": "fixture",
            "field_banks": [_field(-500, 100), _field(0, 200), _field(500, 300)],
        },
        sort_keys=True,
    ).encode("utf-8")
    document = prefix[:-1] + suffix
    return zstd.ZstdCompressor(level=1).compress(document)


def _write_archive(path: Path, compressed: bytes) -> str:
    path.write_bytes(compressed)
    return sha256_digest(compressed)


def test_loader_authenticates_and_stops_before_response_section(tmp_path: Path) -> None:
    compressed = _archive_bytes()
    path = tmp_path / "result.json.zst"
    digest = _write_archive(path, compressed)

    first = load_sealed_response_free_bank_inventory(
        path,
        expected_archive_sha256=digest,
    )
    second = load_sealed_response_free_bank_inventory(
        path,
        expected_archive_sha256=digest,
    )

    assert tuple(item.field_delta_s for item in first.field_banks) == (-500, 0, 500)
    assert tuple(item.candidate_count for item in first.field_banks) == (1, 1, 1)
    assert first.response_section_parsed is False
    assert first.candidate_ranking_performed is False
    assert first.content_digest == second.content_digest


def test_loader_rejects_hash_schema_order_and_prefix_poison(tmp_path: Path) -> None:
    valid = _archive_bytes(suffix=b"}")
    path = tmp_path / "result.json.zst"
    digest = _write_archive(path, valid)
    with pytest.raises(LongArcObservabilityRebuildError, match="SHA-256 drifted"):
        load_sealed_response_free_bank_inventory(
            path,
            expected_archive_sha256=_digest("wrong", 1),
        )

    wrong_order_document = json.dumps(
        {"field_banks": [_field(0, 200), _field(-500, 100), _field(500, 300)]}
    ).encode("utf-8")
    wrong_order = zstd.ZstdCompressor().compress(wrong_order_document)
    wrong_path = tmp_path / "wrong.json.zst"
    wrong_digest = _write_archive(wrong_path, wrong_order)
    with pytest.raises(LongArcObservabilityRebuildError, match="ordered"):
        load_sealed_response_free_bank_inventory(
            wrong_path,
            expected_archive_sha256=wrong_digest,
        )

    with pytest.raises(LongArcObservabilityRebuildError, match="prefix cap"):
        load_sealed_response_free_bank_inventory(
            path,
            expected_archive_sha256=digest,
            maximum_decompressed_prefix_bytes=1_000,
        )


def test_rebuild_authenticates_tle_before_propagation(tmp_path: Path) -> None:
    compressed = _archive_bytes(suffix=b"}")
    path = tmp_path / "result.json.zst"
    digest = _write_archive(path, compressed)
    inventory = load_sealed_response_free_bank_inventory(
        path,
        expected_archive_sha256=digest,
    )
    episode_id = _digest("episode", 1)
    observations = tuple(
        CataloguePredictionSupportObservationV1(
            observation_id=_digest("observation", index),
            episode_id=episode_id,
            support_start_utc_ns=1_800_000_000_000_000_000 + index * 1_000_000_000,
            support_center_utc_ns=1_800_000_000_010_000_000 + index * 1_000_000_000,
            support_end_utc_ns=1_800_000_000_020_000_000 + index * 1_000_000_000,
            factorial_support_moments_s=(1.0, 0.0, 0.0, 0.0),
        )
        for index in range(2)
    )
    payload = {
        "schema_version": 1,
        "algorithm_version": "catalogue-prediction-support-v1",
        "episode_ids": (episode_id,),
        "observations": [item.model_dump(mode="json") for item in observations],
        "response_fields_excluded": True,
    }
    support = CataloguePredictionSupportV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )
    snapshot = TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=1_700_000_000_000_000_000,
        digest=_digest("different-tle", 1),
        object_count=3,
    )

    with pytest.raises(LongArcObservabilityRebuildError, match="authentication"):
        rebuild_digest_identical_field_banks(
            support,
            b"not-the-authorized-tle",
            tle_snapshot=snapshot,
            observer_site=ObserverSiteV1(
                latitude_deg=37.0,
                longitude_deg=-122.0,
                altitude_m=0.0,
                label="fixture",
            ),
            nominal_rf_hz=11_440_312_498.0,
            selection_protocol_digest=_digest("protocol", 1),
            tau_policy=ExactTauPolicy.fixed_zero(),
            prediction_policy=Sgp4SupportPredictionPolicy(),
            inventory=inventory,
        )
