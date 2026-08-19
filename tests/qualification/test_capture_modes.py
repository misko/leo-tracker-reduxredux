from __future__ import annotations

import os
import stat
from decimal import Decimal
from pathlib import Path
from threading import Event

import numpy as np
import pytest

import leo.qualification.capture_modes as capture_modes_module
from leo.acquisition import AcquisitionConfig, AcquisitionCoordinator
from leo.contracts.profile import CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import ReceiverGainV1
from leo.contracts.recording import CompressionSettingsV1
from leo.contracts.states import (
    GainMode,
    SourceType,
    StarlinkEdge,
    SynchronizationGrade,
    SynchronizationMode,
)
from leo.domain.profiles import compile_capture_plan, load_profile_revision
from leo.qualification import (
    CaptureModeAcceptanceHarness,
    CaptureModeAcceptanceReceiptV1,
    CaptureModeCampaignAcceptanceReceiptV2,
    CaptureModeExpectationV1,
    CaptureModeSessionCheckV1,
    CaptureModeStreamTimingEvidenceV1,
)
from leo.radio import FakeRadioSource
from leo.storage import RecordingStore


class _ImmediateClock:
    def utc_ns(self) -> int:
        return 1_800_000_000_000_000_000

    def monotonic_ns(self) -> int:
        return 4_000_000_000

    def sleep(self, _seconds: float, cancel: Event) -> None:
        if cancel.is_set():
            raise RuntimeError("cancelled")

    def wait_until(self, target_monotonic_ns: int, cancel: Event) -> int:
        if cancel.is_set():
            raise RuntimeError("cancelled")
        return target_monotonic_ns + 100


def _revision(*, sample_count: int = 16) -> CaptureProfileRevisionV1:
    return CaptureProfileRevisionV1.from_profile(
        CaptureProfileV1(
            name="ch4-lower-single-rx1-test",
            center_frequency_hz=1_709_687_500,
            rf_center_frequency_hz=11_459_687_500,
            lnb_lo_hz=9_750_000_000,
            starlink_channel="ch4",
            starlink_edge=StarlinkEdge.LOWER,
            sample_rate_hz=2_500_000,
            bandwidth_hz=2_500_000,
            receivers=(1,),
            gain_mode=GainMode.MANUAL,
            gains=(ReceiverGainV1(receiver_id=1, gain_db=40.0),),
            duration_seconds=Decimal(sample_count) / Decimal(2_500_000),
            refill_samples=4,
            settle_seconds=Decimal(0),
            prime_refills=0,
            synchronization_mode=SynchronizationMode.BEST_EFFORT,
            storage_policy="capture-mode-test-v1",
            tags=("TEST",),
        )
    )


def _three_sessions(store: RecordingStore, revision: CaptureProfileRevisionV1) -> None:
    coordinator = AcquisitionCoordinator(
        store,
        compression=CompressionSettingsV1(
            policy_id="capture-mode-test-v1",
            target_uncompressed_bytes=16,
        ),
        clock=_ImmediateClock(),
        config=AcquisitionConfig(
            release_lead_ns=25_000_000,
            readiness_timeout_seconds=2,
            safety_reserve_bytes=0,
            metadata_bytes_per_refill=128,
        ),
    )
    cases = (
        ("capture-mode-independent-a", ("radio-a",)),
        ("capture-mode-independent-b", ("radio-b",)),
        ("capture-mode-synchronized", ("radio-a", "radio-b")),
    )
    for session_id, radio_ids in cases:
        plan = compile_capture_plan(revision, radio_ids, source_type=SourceType.TEST)
        result = coordinator.capture_once(
            plan,
            {
                radio_id: FakeRadioSource(radio_id, receiver_count=2, seed=10_000 + index)
                for index, radio_id in enumerate(radio_ids)
            },
            session_id=session_id,
        )
        assert result.bundle is not None, result.errors


_HARDWARE_IDS = ("radio_pluto_5d4d", "radio_pluto_19f2")
_HARDWARE_SERIALS = (
    "1040005e0b100007100010000bf33a5d4d",
    "10400056f695001322002d0010ad1719f2",
)
_HARDWARE_URIS = ("ip:192.168.1.20", "ip:192.168.1.21")
_HARDWARE_CHAINS = ("rx_lnb_b", "rx_lnb_d")


def _synthetic_hardware_check(
    expectation: CaptureModeExpectationV1,
    role: capture_modes_module.CaptureModeRole,
    session_id: str,
    expected_radios: tuple[str, ...],
    *,
    passed: bool = True,
) -> CaptureModeSessionCheckV1:
    if not passed:
        return CaptureModeSessionCheckV1(
            role=role,
            session_id=session_id,
            expected_radio_ids=expected_radios,
            digest_valid=True,
            errors=("injected wrong-role evidence",),
        )
    indexes = tuple(_HARDWARE_IDS.index(radio_id) for radio_id in expected_radios)
    timing = tuple(
        CaptureModeStreamTimingEvidenceV1(
            stream_id=f"stream-{index}",
            radio_id=radio_id,
            first_estimate_utc_ns=1_800_000_000_000_000_000 + offset * 100,
            first_earliest_utc_ns=1_800_000_000_000_000_000 + offset * 100 - 10,
            first_latest_utc_ns=1_800_000_000_000_000_000 + offset * 100 + 10,
            first_uncertainty_ns=20,
            last_estimate_utc_ns=1_800_000_059_999_999_600 + offset * 100,
            last_earliest_utc_ns=1_800_000_059_999_999_590 + offset * 100,
            last_latest_utc_ns=1_800_000_059_999_999_610 + offset * 100,
            last_uncertainty_ns=20,
            sample_interval_end_estimate_utc_ns=(1_800_000_060_000_000_000 + offset * 100),
        )
        for offset, (index, radio_id) in enumerate(zip(indexes, expected_radios, strict=True))
    )
    pair = role == "synchronized_pair"
    recomputed = (
        capture_modes_module._recompute_pair_timing((timing[0], timing[1]))
        if pair
        else (None, None, None, None, None, None)
    )
    return CaptureModeSessionCheckV1(
        role=role,
        session_id=session_id,
        expected_radio_ids=expected_radios,
        bundle_uri=f"bulk://recordings/2026/08/19/{session_id}",
        manifest_sha256="sha256:" + "0" * 64,
        digest_valid=True,
        observed_radio_ids=expected_radios,
        observed_radio_serials=tuple(_HARDWARE_SERIALS[index] for index in indexes),
        observed_radio_uris=tuple(_HARDWARE_URIS[index] for index in indexes),
        observed_receiver_chain_ids=tuple(_HARDWARE_CHAINS[index] for index in indexes),
        observed_receiver_ids=tuple((1,) for _ in expected_radios),
        observed_sample_counts=tuple(expectation.sample_count for _ in expected_radios),
        observed_gain_db=tuple(40.0 for _ in expected_radios),
        observed_gap_counts=tuple(0 for _ in expected_radios),
        observed_missing_sample_counts=tuple(0 for _ in expected_radios),
        observed_overflow_counts=tuple(0 for _ in expected_radios),
        observed_clipped_sample_counts=tuple(0 for _ in expected_radios),
        observed_clipped_sample_fractions=tuple(0.0 for _ in expected_radios),
        observed_constant_iq=tuple(False for _ in expected_radios),
        stream_timing=timing,
        synchronization_grade=(
            SynchronizationGrade.BEST_EFFORT_OBSERVED
            if pair
            else SynchronizationGrade.NOT_REQUESTED
        ),
        manifest_overlap_fraction=1.0 if pair else None,
        estimated_overlap_ns=recomputed[0],
        overlap_fraction=recomputed[1],
        guaranteed_overlap_ns=recomputed[2],
        guaranteed_overlap_fraction=recomputed[3],
        estimated_start_skew_ns=recomputed[4],
        start_skew_uncertainty_ns=recomputed[5],
        passed=True,
    )


def test_capture_mode_harness_accepts_exact_three_session_geometry(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    revision = _revision()
    _three_sessions(store, revision)
    expectation = CaptureModeExpectationV1.from_profile_revision(
        revision,
        ("radio-a", "radio-b"),
        source_type=SourceType.TEST,
    )
    receipt_path = tmp_path / "receipts" / "capture-modes.json"
    receipt_path.parent.mkdir()

    receipt = CaptureModeAcceptanceHarness(store).run(
        expectation,
        acceptance_id="capture-modes-test-v1",
        independent_radio_a_session_id="capture-mode-independent-a",
        independent_radio_b_session_id="capture-mode-independent-b",
        synchronized_pair_session_id="capture-mode-synchronized",
        receipt_path=receipt_path,
        observed_utc_ns=1_800_000_001_000_000_000,
    )

    assert receipt.accepted
    assert all(check.passed and check.digest_valid for check in receipt.checks)
    assert receipt.checks[0].observed_receiver_ids == ((1,),)
    assert receipt.checks[1].observed_receiver_ids == ((1,),)
    assert receipt.checks[2].observed_receiver_ids == ((1,), (1,))
    assert receipt.checks[0].overlap_fraction is None
    assert receipt.checks[1].overlap_fraction is None
    assert receipt.checks[2].overlap_fraction == 1.0
    assert receipt.expectation.gain_db == 40.0
    assert all(
        check.observed_gain_db == tuple(40.0 for _ in check.expected_radio_ids)
        for check in receipt.checks
    )
    assert all(
        check.observed_constant_iq == tuple(False for _ in check.expected_radio_ids)
        for check in receipt.checks
    )
    assert all(
        check.observed_clipped_sample_fractions == tuple(0.0 for _ in check.expected_radio_ids)
        for check in receipt.checks
    )
    assert receipt.acceptance_scope == "capture_only"
    assert not receipt.processing_evidence_evaluated
    assert not receipt.scientific_acceptance_claimed
    assert receipt.required_follow_up == "linked_standard_processing_and_detection_receipt"
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o440
    assert CaptureModeAcceptanceReceiptV1.model_validate_json(receipt_path.read_bytes()) == receipt

    with pytest.raises(FileExistsError, match="already exists"):
        CaptureModeAcceptanceHarness(store).run(
            expectation,
            acceptance_id="capture-modes-test-v1",
            independent_radio_a_session_id="capture-mode-independent-a",
            independent_radio_b_session_id="capture-mode-independent-b",
            synchronized_pair_session_id="capture-mode-synchronized",
            receipt_path=receipt_path,
        )


def test_capture_mode_campaign_requires_and_accepts_ten_trials_per_stratum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RecordingStore(tmp_path / "bulk")
    revision = load_profile_revision(
        Path(__file__).parents[2] / "profiles" / "starlink-ch4-lower-2p5m-60s-rx1.yaml"
    )
    expectation = CaptureModeExpectationV1.from_hardware_profile_revision(
        revision,
        _HARDWARE_IDS,
    )
    independent_a = tuple(f"campaign-independent-a-{index:02d}" for index in range(10))
    independent_b = tuple(f"campaign-independent-b-{index:02d}" for index in range(10))
    synchronized = tuple(f"campaign-synchronized-{index:02d}" for index in range(10))

    def passed_check(
        _self: CaptureModeAcceptanceHarness,
        _expectation: CaptureModeExpectationV1,
        role: capture_modes_module.CaptureModeRole,
        session_id: str,
        expected_radios: tuple[str, ...],
    ) -> CaptureModeSessionCheckV1:
        return _synthetic_hardware_check(
            _expectation,
            role,
            session_id,
            expected_radios,
        )

    monkeypatch.setattr(CaptureModeAcceptanceHarness, "_check", passed_check)
    receipt_path = tmp_path / "campaign.json"

    receipt = CaptureModeAcceptanceHarness(store).run_campaign(
        expectation,
        acceptance_id="capture-mode-campaign-v2",
        independent_radio_a_session_ids=independent_a,
        independent_radio_b_session_ids=independent_b,
        synchronized_pair_session_ids=synchronized,
        receipt_path=receipt_path,
        observed_utc_ns=1_800_000_002_000_000_000,
    )

    assert receipt.accepted
    assert len(receipt.trial_receipts) == 10
    assert sum(len(trial.checks) for trial in receipt.trial_receipts) == 30
    assert (
        CaptureModeCampaignAcceptanceReceiptV2.model_validate_json(receipt_path.read_bytes())
        == receipt
    )
    forged_identity = receipt.model_dump(mode="python")
    forged_identity["trial_receipts"][0]["checks"][0]["observed_radio_serials"] = ("wrong-serial",)
    with pytest.raises(ValueError, match="unqualified hardware identity"):
        CaptureModeCampaignAcceptanceReceiptV2.model_validate(forged_identity)

    forged_overlap = receipt.model_dump(mode="python")
    forged_overlap["trial_receipts"][0]["checks"][2]["overlap_fraction"] = 0.99
    with pytest.raises(ValueError, match="overlap is not timing-derived"):
        CaptureModeCampaignAcceptanceReceiptV2.model_validate(forged_overlap)

    forged_empty = receipt.model_dump(mode="python")
    forged_empty["trial_receipts"][0]["checks"][0]["bundle_uri"] = None
    with pytest.raises(ValueError, match="bundle identity and digest"):
        CaptureModeCampaignAcceptanceReceiptV2.model_validate(forged_empty)

    with pytest.raises(ValueError, match="exactly 10 sessions per stratum"):
        CaptureModeAcceptanceHarness(store).run_campaign(
            expectation,
            acceptance_id="capture-mode-too-short",
            independent_radio_a_session_ids=independent_a[:-1],
            independent_radio_b_session_ids=independent_b,
            synchronized_pair_session_ids=synchronized,
        )


def test_capture_mode_campaign_rejects_test_or_weakened_expectation(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    sessions = tuple(f"session-{index:02d}" for index in range(30))
    test_expectation = CaptureModeExpectationV1.from_profile_revision(
        _revision(),
        ("radio-a", "radio-b"),
        source_type=SourceType.TEST,
    )

    with pytest.raises(ValueError, match="immutable 60s CH4 LOWER"):
        CaptureModeAcceptanceHarness(store).run_campaign(
            test_expectation,
            acceptance_id="test-evidence-is-not-hardware-evidence",
            independent_radio_a_session_ids=sessions[:10],
            independent_radio_b_session_ids=sessions[10:20],
            synchronized_pair_session_ids=sessions[20:],
        )

    revision = load_profile_revision(
        Path(__file__).parents[2] / "profiles" / "starlink-ch4-lower-2p5m-60s-rx1.yaml"
    )
    weakened = CaptureModeExpectationV1.from_hardware_profile_revision(
        revision, _HARDWARE_IDS
    ).model_copy(update={"minimum_pair_overlap_fraction": 0.0})
    with pytest.raises(ValueError, match="frozen 0.99 overlap"):
        CaptureModeAcceptanceHarness(store).run_campaign(
            weakened,
            acceptance_id="weakened-overlap",
            independent_radio_a_session_ids=sessions[:10],
            independent_radio_b_session_ids=sessions[10:20],
            synchronized_pair_session_ids=sessions[20:],
        )


def test_capture_mode_passing_check_cannot_omit_mandatory_evidence() -> None:
    with pytest.raises(ValueError, match="bundle identity and digest"):
        CaptureModeSessionCheckV1(
            role="independent_radio_a",
            session_id="forged-empty-check",
            expected_radio_ids=(_HARDWARE_IDS[0],),
            digest_valid=True,
            passed=True,
        )

    revision = load_profile_revision(
        Path(__file__).parents[2] / "profiles" / "starlink-ch4-lower-2p5m-60s-rx1.yaml"
    )
    expectation = CaptureModeExpectationV1.from_hardware_profile_revision(revision, _HARDWARE_IDS)
    assert expectation.clipping_abs_threshold == 2_047
    assert expectation.clipping_semantics == "ad9361_signed_12bit_native_ci16_abs_ge_2047"
    assert expectation.clipping_provenance is not None
    assert "pluto-plus-utils@d5cd293" in expectation.clipping_provenance


def test_capture_mode_harness_fails_closed_on_wrong_radio_role(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    revision = _revision()
    _three_sessions(store, revision)
    expectation = CaptureModeExpectationV1.from_profile_revision(
        revision,
        ("radio-a", "radio-b"),
        source_type=SourceType.TEST,
    )

    receipt = CaptureModeAcceptanceHarness(store).run(
        expectation,
        acceptance_id="capture-modes-wrong-role",
        independent_radio_a_session_id="capture-mode-independent-b",
        independent_radio_b_session_id="capture-mode-independent-a",
        synchronized_pair_session_id="capture-mode-synchronized",
    )

    assert not receipt.accepted
    assert not receipt.checks[0].passed
    assert not receipt.checks[1].passed
    assert "capture-plan radios differ" in receipt.checks[0].errors
    assert "capture-plan radios differ" in receipt.checks[1].errors


def test_capture_mode_receipt_rejects_qnap_symlink_without_target_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = RecordingStore(tmp_path / "bulk")
    revision = _revision()
    _three_sessions(store, revision)
    expectation = CaptureModeExpectationV1.from_profile_revision(
        revision,
        ("radio-a", "radio-b"),
        source_type=SourceType.TEST,
    )
    linked_parent = tmp_path / "qnap-link"
    linked_parent.symlink_to(
        "/mnt/qnap01/capture-mode-must-not-be-probed", target_is_directory=True
    )
    original_lstat = capture_modes_module.os.lstat

    def guarded_lstat(path: str | os.PathLike[str]) -> os.stat_result:
        absolute = Path(capture_modes_module.os.path.abspath(path))
        qnap = Path("/mnt/qnap01")
        if absolute == qnap or qnap in absolute.parents:
            raise AssertionError("QNAP target was probed")
        return original_lstat(path)

    monkeypatch.setattr(capture_modes_module.os, "lstat", guarded_lstat)
    with pytest.raises(ValueError, match="cannot use a QNAP path"):
        CaptureModeAcceptanceHarness(store).run(
            expectation,
            acceptance_id="capture-modes-qnap-link",
            independent_radio_a_session_id="capture-mode-independent-a",
            independent_radio_b_session_id="capture-mode-independent-b",
            synchronized_pair_session_id="capture-mode-synchronized",
            receipt_path=linked_parent / "receipt.json",
        )


def test_capture_mode_receipt_refuses_existing_destination_symlink(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    revision = _revision()
    _three_sessions(store, revision)
    expectation = CaptureModeExpectationV1.from_profile_revision(
        revision,
        ("radio-a", "radio-b"),
        source_type=SourceType.TEST,
    )
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("unchanged", encoding="utf-8")
    receipt_path = tmp_path / "receipt-link.json"
    receipt_path.symlink_to(sentinel)

    with pytest.raises(FileExistsError, match="already exists"):
        CaptureModeAcceptanceHarness(store).run(
            expectation,
            acceptance_id="capture-modes-existing-link",
            independent_radio_a_session_id="capture-mode-independent-a",
            independent_radio_b_session_id="capture-mode-independent-b",
            synchronized_pair_session_id="capture-mode-synchronized",
            receipt_path=receipt_path,
        )

    assert receipt_path.is_symlink()
    assert sentinel.read_text(encoding="utf-8") == "unchanged"


class _ConstantFakeRadioSource(FakeRadioSource):
    def _samples(self, sample_count: int, receiver_ids: tuple[int, ...]) -> np.ndarray:
        return np.zeros((sample_count, len(receiver_ids), 2), dtype="<i2")


class _ClippedFakeRadioSource(FakeRadioSource):
    def _samples(self, sample_count: int, receiver_ids: tuple[int, ...]) -> np.ndarray:
        values = np.zeros((sample_count, len(receiver_ids), 2), dtype="<i2")
        values[:, :, 1] = np.arange(sample_count, dtype="<i2")[:, None]
        values[0, :, 0] = 32_767
        return values


class _Ad9361RailFakeRadioSource(FakeRadioSource):
    def _samples(self, sample_count: int, receiver_ids: tuple[int, ...]) -> np.ndarray:
        values = np.zeros((sample_count, len(receiver_ids), 2), dtype="<i2")
        values[:, :, 1] = np.arange(sample_count, dtype="<i2")[:, None]
        values[0, :, 0] = 2_047
        return values


def test_capture_mode_harness_fails_closed_on_constant_iq(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    revision = _revision()
    _three_sessions(store, revision)
    plan = compile_capture_plan(revision, ("radio-a",), source_type=SourceType.TEST)
    coordinator = AcquisitionCoordinator(
        store,
        compression=CompressionSettingsV1(
            policy_id="capture-mode-test-v1",
            target_uncompressed_bytes=16,
        ),
        clock=_ImmediateClock(),
        config=AcquisitionConfig(
            release_lead_ns=25_000_000,
            readiness_timeout_seconds=2,
            safety_reserve_bytes=0,
            metadata_bytes_per_refill=128,
        ),
    )
    result = coordinator.capture_once(
        plan,
        {"radio-a": _ConstantFakeRadioSource("radio-a", receiver_count=2)},
        session_id="capture-mode-constant-a",
    )
    assert result.bundle is not None, result.errors
    expectation = CaptureModeExpectationV1.from_profile_revision(
        revision,
        ("radio-a", "radio-b"),
        source_type=SourceType.TEST,
    )

    receipt = CaptureModeAcceptanceHarness(store).run(
        expectation,
        acceptance_id="capture-modes-constant-iq",
        independent_radio_a_session_id="capture-mode-constant-a",
        independent_radio_b_session_id="capture-mode-independent-b",
        synchronized_pair_session_id="capture-mode-synchronized",
    )

    assert not receipt.accepted
    assert receipt.checks[0].observed_constant_iq == (True,)
    assert "stream 0 IQ is constant" in receipt.checks[0].errors


def test_capture_mode_harness_fails_closed_on_clipped_iq(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    revision = _revision()
    _three_sessions(store, revision)
    plan = compile_capture_plan(revision, ("radio-a",), source_type=SourceType.TEST)
    coordinator = AcquisitionCoordinator(
        store,
        compression=CompressionSettingsV1(
            policy_id="capture-mode-test-v1",
            target_uncompressed_bytes=16,
        ),
        clock=_ImmediateClock(),
        config=AcquisitionConfig(
            release_lead_ns=25_000_000,
            readiness_timeout_seconds=2,
            safety_reserve_bytes=0,
            metadata_bytes_per_refill=128,
        ),
    )
    result = coordinator.capture_once(
        plan,
        {"radio-a": _ClippedFakeRadioSource("radio-a", receiver_count=2)},
        session_id="capture-mode-clipped-a",
    )
    assert result.bundle is not None, result.errors
    expectation = CaptureModeExpectationV1.from_profile_revision(
        revision,
        ("radio-a", "radio-b"),
        source_type=SourceType.TEST,
    )

    receipt = CaptureModeAcceptanceHarness(store).run(
        expectation,
        acceptance_id="capture-modes-clipped-iq",
        independent_radio_a_session_id="capture-mode-clipped-a",
        independent_radio_b_session_id="capture-mode-independent-b",
        synchronized_pair_session_id="capture-mode-synchronized",
    )

    assert not receipt.accepted
    assert receipt.checks[0].observed_clipped_sample_counts == (4,)
    assert receipt.checks[0].observed_clipped_sample_fractions == (1 / 4,)
    assert "stream 0 clipped sample fraction exceeds threshold" in receipt.checks[0].errors


def test_ad9361_native_ci16_positive_rail_is_2047(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    revision = _revision()
    plan = compile_capture_plan(revision, ("radio-a",), source_type=SourceType.TEST)
    coordinator = AcquisitionCoordinator(
        store,
        compression=CompressionSettingsV1(
            policy_id="capture-mode-test-v1",
            target_uncompressed_bytes=16,
        ),
        clock=_ImmediateClock(),
        config=AcquisitionConfig(
            release_lead_ns=25_000_000,
            readiness_timeout_seconds=2,
            safety_reserve_bytes=0,
            metadata_bytes_per_refill=128,
        ),
    )
    result = coordinator.capture_once(
        plan,
        {"radio-a": _Ad9361RailFakeRadioSource("radio-a", receiver_count=2)},
        session_id="ad9361-native-rail",
    )
    assert result.bundle is not None, result.errors
    stream = result.bundle.manifest.streams[0]

    clipped, fraction, constant = capture_modes_module._scan_stream_quality(
        store.reader(result.bundle, stream.stream_id),
        clipping_abs_threshold=2_047,
    )

    assert clipped == 4
    assert fraction == 1 / 4
    assert not constant


def test_capture_mode_expectation_rejects_dual_rx_profile() -> None:
    revision = _revision().model_copy(
        update={
            "profile": _revision().profile.model_copy(
                update={
                    "receivers": (0, 1),
                    "gains": (
                        ReceiverGainV1(receiver_id=0, gain_db=30.0),
                        ReceiverGainV1(receiver_id=1, gain_db=30.0),
                    ),
                }
            )
        }
    )

    with pytest.raises(ValueError, match="exactly one RX"):
        CaptureModeExpectationV1.from_profile_revision(
            revision,
            ("radio-a", "radio-b"),
        )


def test_capture_mode_expectation_rejects_non_reference_gain() -> None:
    profile = _revision().profile.model_copy(
        update={"gains": (ReceiverGainV1(receiver_id=1, gain_db=39.0),)}
    )
    revision = CaptureProfileRevisionV1.from_profile(profile)

    with pytest.raises(ValueError, match="frozen 40 dB"):
        CaptureModeExpectationV1.from_profile_revision(
            revision,
            ("radio-a", "radio-b"),
        )
