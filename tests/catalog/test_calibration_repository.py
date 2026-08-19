from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from leo.application.calibration_catalog import PostgresCalibrationCatalogAdapter
from leo.catalog import CatalogNotFoundError, InvalidStateError, ProductConflictError
from leo.contracts.calibration import (
    CalibrationEvidenceV1,
    ReceiverFrequencyCalibrationSetV1,
    ReceiverFrequencyCalibrationV1,
    ReceiverPathIdentityV1,
)

from .conftest import CatalogHarness

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
START_NS = 1_787_133_600_000_000_123
END_NS = START_NS + 60_000_000_000


def _identity(
    *,
    radio_id: str = "radio-a",
    physical: str = "rx-lnb-b",
    epoch: str = "epoch-a",
    start: int = START_NS,
    end: int = END_NS,
) -> ReceiverPathIdentityV1:
    return ReceiverPathIdentityV1(
        radio_id=radio_id,
        radio_serial="serial-a",
        receiver_id=1,
        physical_receiver_id=physical,
        capture_utc_ns=start,
        capture_end_utc_ns=end,
        hardware_epoch_id=epoch,
        session_id="session-a",
        stream_id="stream-a",
        manifest_digest=DIGEST_A,
        profile_revision_digest=DIGEST_B,
    )


def _calibration(
    *,
    calibration_id: str = "calibration-a",
    physical: str = "rx-lnb-b",
    epoch: str = "epoch-a",
    valid_from: int = START_NS,
    valid_until: int | None = END_NS,
    center_hz: float = 1250.0,
) -> ReceiverFrequencyCalibrationV1:
    return ReceiverFrequencyCalibrationV1.create(
        calibration_id=calibration_id,
        radio_id="radio-a",
        radio_serial="serial-a",
        receiver_id=1,
        physical_receiver_id=physical,
        hardware_epoch_id=epoch,
        center_hz=center_hz,
        uncertainty_lower_hz=center_hz - 50,
        uncertainty_upper_hz=center_hz + 50,
        valid_from_utc_ns=valid_from,
        valid_until_utc_ns=valid_until,
        method="trusted-wp11-v1",
        created_utc_ns=START_NS - 1,
        evidence=(
            CalibrationEvidenceV1(
                kind="promotion-receipt",
                uri="bulk://calibration/promotion/receipt.json",
                digest=DIGEST_A,
                source_revision="0123456789abcdef",
            ),
        ),
    )


def _adapter(harness: CatalogHarness) -> PostgresCalibrationCatalogAdapter:
    return PostgresCalibrationCatalogAdapter(harness.repository)


def _register_path(
    adapter: PostgresCalibrationCatalogAdapter,
    identity: ReceiverPathIdentityV1,
) -> None:
    adapter.register_receiver_path(
        identity,
        radio_uri="ip:192.0.2.20",
        transport="ethernet",
        hardware_epoch_started_utc_ns=START_NS - 1_000_000_000,
    )


def _register_set(
    adapter: PostgresCalibrationCatalogAdapter,
    calibration: ReceiverFrequencyCalibrationV1,
    *,
    set_id: str = "set-a",
) -> ReceiverFrequencyCalibrationSetV1:
    value = ReceiverFrequencyCalibrationSetV1.create(
        calibration_set_id=set_id,
        calibrations=(calibration,),
    )
    return adapter.register_promoted_set(
        value,
        evidence_uri=f"bulk://calibration/{set_id}/calibration-set.json",
        evidence_digest=value.calibration_set_digest,
    )


def test_contract_adapter_round_trips_exact_ns_and_full_interval(
    catalog_harness: CatalogHarness,
) -> None:
    adapter = _adapter(catalog_harness)
    identity = _identity()
    calibration = _calibration()
    _register_path(adapter, identity)
    registered = _register_set(adapter, calibration)

    resolved = adapter.resolve(identity)
    assert registered.calibrations == (calibration,)
    assert resolved.calibration == calibration
    assert resolved.calibration_set == registered
    assert resolved.calibration.valid_from_utc_ns == START_NS
    with pytest.raises(CatalogNotFoundError, match="no calibration covers"):
        adapter.resolve(_identity(end=END_NS + 1))
    with pytest.raises(ValueError, match="mismatches receiver identity"):
        adapter.resolve(_identity(radio_id="forged-radio-id"))
    with pytest.raises(CatalogNotFoundError, match="no calibration covers"):
        catalog_harness.repository.resolve_frequency_calibration(
            radio_serial="wrong-serial",
            receiver_id=1,
            physical_receiver_id="rx-lnb-b",
            hardware_epoch_id="epoch-a",
            capture_start_utc_ns=START_NS,
            capture_end_utc_ns=END_NS,
        )


def test_registration_is_concurrent_idempotent_and_conflict_safe(
    catalog_harness: CatalogHarness,
) -> None:
    adapter = _adapter(catalog_harness)
    identity = _identity()
    calibration = _calibration()
    value = ReceiverFrequencyCalibrationSetV1.create(
        calibration_set_id="set-concurrent", calibrations=(calibration,)
    )

    def register() -> str:
        stored = adapter.register_promoted_set(
            value,
            evidence_uri="bulk://calibration/set-concurrent/calibration-set.json",
            evidence_digest=value.calibration_set_digest,
        )
        return stored.calibration_set_digest

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(
            pool.map(lambda _index: _register_path(adapter, identity), range(8))
        ) == [None] * 8
        assert list(pool.map(lambda _index: register(), range(8))) == [
            value.calibration_set_digest
        ] * 8
    with catalog_harness.engine.connect() as connection:
        counts = connection.execute(
            text(
                "SELECT (SELECT count(*) FROM frequency_calibration), "
                "(SELECT count(*) FROM frequency_calibration_set), "
                "(SELECT count(*) FROM frequency_calibration_set_member)"
            )
        ).one()
    assert tuple(counts) == (1, 1, 1)

    conflicting = ReceiverFrequencyCalibrationSetV1.create(
        calibration_set_id="set-concurrent",
        calibrations=(_calibration(calibration_id="calibration-b", center_hz=1300),),
    )
    with pytest.raises(ProductConflictError, match="identity conflicts"):
        adapter.register_promoted_set(
            conflicting,
            evidence_uri="bulk://calibration/set-concurrent/calibration-set.json",
            evidence_digest=conflicting.calibration_set_digest,
        )


def test_physical_chain_changes_are_distinct_and_ambiguity_fails_closed(
    catalog_harness: CatalogHarness,
) -> None:
    adapter = _adapter(catalog_harness)
    first_identity = _identity()
    second_identity = _identity(physical="rx-lnb-c", epoch="epoch-b")
    _register_path(adapter, first_identity)
    _register_path(adapter, second_identity)
    _register_set(adapter, _calibration())
    second = _calibration(
        calibration_id="calibration-c",
        physical="rx-lnb-c",
        epoch="epoch-b",
        center_hz=1400,
    )
    _register_set(adapter, second, set_id="set-c")
    assert adapter.resolve(second_identity).calibration == second

    overlapping = _calibration(calibration_id="calibration-overlap", center_hz=1260)
    _register_set(adapter, overlapping, set_id="set-overlap")
    with pytest.raises(InvalidStateError, match="ambiguous"):
        adapter.resolve(first_identity)


def test_authoritative_calibration_rows_are_database_immutable(
    catalog_harness: CatalogHarness,
) -> None:
    adapter = _adapter(catalog_harness)
    _register_path(adapter, _identity())
    _register_set(adapter, _calibration())
    statements = (
        "UPDATE receiver_path SET physical_receiver_id = 'mutated' "
        "WHERE physical_receiver_id = 'rx-lnb-b'",
        "UPDATE hardware_epoch SET description = 'mutated' WHERE external_id = 'epoch-a'",
        "UPDATE frequency_calibration SET method = 'mutated' "
        "WHERE external_id = 'calibration-a'",
        "UPDATE frequency_calibration_set SET evidence_uri = 'mutated' WHERE id = 'set-a'",
        "UPDATE frequency_calibration_set_member SET ordinal = 2 WHERE set_id = 'set-a'",
        "DELETE FROM frequency_calibration WHERE external_id = 'calibration-a'",
    )
    for statement in statements:
        with pytest.raises(DBAPIError), catalog_harness.engine.begin() as connection:
            connection.execute(text(statement))
