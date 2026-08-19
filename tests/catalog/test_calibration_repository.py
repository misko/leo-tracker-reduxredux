from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from leo.application.calibration_catalog import PostgresCalibrationCatalogAdapter
from leo.application.frequency_calibration import DurableCalibrationPublicationRefV1
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


class _AuthoritativeResolver:
    def __init__(self) -> None:
        self._values: dict[
            str,
            tuple[DurableCalibrationPublicationRefV1, ReceiverFrequencyCalibrationSetV1],
        ] = {}

    def admit(
        self,
        publication: DurableCalibrationPublicationRefV1,
        value: ReceiverFrequencyCalibrationSetV1,
    ) -> None:
        self._values[publication.promotion_id] = (publication, value)

    def resolve(
        self,
        ref: DurableCalibrationPublicationRefV1,
    ) -> ReceiverFrequencyCalibrationSetV1:
        expected, value = self._values[ref.promotion_id]
        if ref != expected:
            raise ValueError("durable promotion reference differs from trusted store")
        return value


def _adapter(
    harness: CatalogHarness,
) -> tuple[PostgresCalibrationCatalogAdapter, _AuthoritativeResolver]:
    resolver = _AuthoritativeResolver()
    return PostgresCalibrationCatalogAdapter(harness.repository, resolver), resolver


def _register_path(
    adapter: PostgresCalibrationCatalogAdapter,
    identity: ReceiverPathIdentityV1,
    *,
    started_utc_ns: int = START_NS - 1_000_000_000,
) -> None:
    adapter.register_receiver_path(
        identity,
        radio_uri="ip:192.0.2.20",
        transport="ethernet",
        hardware_epoch_started_utc_ns=started_utc_ns,
    )


def _register_set(
    adapter: PostgresCalibrationCatalogAdapter,
    resolver: _AuthoritativeResolver,
    calibration: ReceiverFrequencyCalibrationV1,
    *,
    set_id: str = "set-a",
) -> ReceiverFrequencyCalibrationSetV1:
    value = ReceiverFrequencyCalibrationSetV1.create(
        calibration_set_id=set_id,
        calibrations=(calibration,),
    )
    publication = DurableCalibrationPublicationRefV1(
        promotion_id=f"promotion-{set_id}",
        bundle_uri=f"bulk://calibration/{set_id}/calibration-set.json",
        manifest_digest=value.calibration_set_digest,
        sealed_utc_ns=calibration.created_utc_ns,
    )
    resolver.admit(publication, value)
    return adapter.publish(publication).calibration_set


def test_contract_adapter_round_trips_exact_ns_and_full_interval(
    catalog_harness: CatalogHarness,
) -> None:
    adapter, resolver = _adapter(catalog_harness)
    identity = _identity()
    calibration = _calibration()
    _register_path(adapter, identity)
    registered = _register_set(adapter, resolver, calibration)

    resolved = adapter.resolve(identity)
    assert registered.calibrations == (calibration,)
    assert resolved.calibration == calibration
    assert resolved.calibration_set == registered
    assert resolved.calibration.valid_from_utc_ns == START_NS
    assert adapter.lookup("promotion-set-a").calibration_set == registered
    with pytest.raises(TypeError):
        adapter.publish(  # type: ignore[call-arg]
            DurableCalibrationPublicationRefV1(
                promotion_id="hand-built",
                bundle_uri="bulk://calibration/hand-built",
                manifest_digest=DIGEST_A,
                sealed_utc_ns=START_NS,
            ),
            registered,
        )
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
    adapter, resolver = _adapter(catalog_harness)
    identity = _identity()
    calibration = _calibration()
    value = ReceiverFrequencyCalibrationSetV1.create(
        calibration_set_id="set-concurrent", calibrations=(calibration,)
    )
    publication = DurableCalibrationPublicationRefV1(
        promotion_id="promotion-set-concurrent",
        bundle_uri="bulk://calibration/set-concurrent/calibration-set.json",
        manifest_digest=value.calibration_set_digest,
        sealed_utc_ns=calibration.created_utc_ns,
    )
    resolver.admit(publication, value)

    def register() -> str:
        return adapter.publish(publication).calibration_set.calibration_set_digest

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
    resolver.admit(publication, conflicting)
    with pytest.raises(ProductConflictError, match="identity conflicts"):
        adapter.publish(publication)


def test_physical_chain_changes_are_distinct_and_ambiguity_fails_closed(
    catalog_harness: CatalogHarness,
) -> None:
    adapter, resolver = _adapter(catalog_harness)
    first_identity = _identity()
    second_identity = _identity(physical="rx-lnb-c", epoch="epoch-b")
    _register_path(adapter, first_identity)
    _register_path(adapter, second_identity)
    _register_set(adapter, resolver, _calibration())
    second = _calibration(
        calibration_id="calibration-c",
        physical="rx-lnb-c",
        epoch="epoch-b",
        center_hz=1400,
    )
    _register_set(adapter, resolver, second, set_id="set-c")
    assert adapter.resolve(second_identity).calibration == second

    overlapping = _calibration(calibration_id="calibration-overlap", center_hz=1260)
    _register_set(adapter, resolver, overlapping, set_id="set-overlap")
    with pytest.raises(InvalidStateError, match="ambiguous"):
        adapter.resolve(first_identity)


def test_authoritative_calibration_rows_are_database_immutable(
    catalog_harness: CatalogHarness,
) -> None:
    adapter, resolver = _adapter(catalog_harness)
    _register_path(adapter, _identity())
    _register_set(adapter, resolver, _calibration())
    _register_set(
        adapter,
        resolver,
        _calibration(calibration_id="calibration-b", center_hz=1400),
        set_id="set-b",
    )
    statements = (
        "UPDATE receiver_path SET physical_receiver_id = 'mutated' "
        "WHERE physical_receiver_id = 'rx-lnb-b'",
        "UPDATE hardware_epoch SET description = 'mutated' WHERE external_id = 'epoch-a'",
        "UPDATE frequency_calibration SET method = 'mutated' "
        "WHERE external_id = 'calibration-a'",
        "UPDATE frequency_calibration_set SET evidence_uri = 'mutated' WHERE id = 'set-a'",
        "UPDATE frequency_calibration_set_member SET ordinal = 2 WHERE set_id = 'set-a'",
        "INSERT INTO frequency_calibration_set_member (set_id, calibration_id, ordinal) "
        "SELECT 'set-a', calibration_id, 1 FROM frequency_calibration_set_member "
        "WHERE set_id = 'set-b'",
        "DELETE FROM frequency_calibration WHERE external_id = 'calibration-a'",
    )
    for statement in statements:
        with pytest.raises(DBAPIError), catalog_harness.engine.begin() as connection:
            connection.execute(text(statement))


def test_hardware_epoch_identity_uses_exact_nanoseconds(
    catalog_harness: CatalogHarness,
) -> None:
    adapter, _resolver = _adapter(catalog_harness)
    identity = _identity()
    exact = START_NS - 1_000_000_000
    _register_path(adapter, identity, started_utc_ns=exact)
    with pytest.raises(ProductConflictError, match="hardware epoch identity conflicts"):
        _register_path(adapter, identity, started_utc_ns=exact + 1)
