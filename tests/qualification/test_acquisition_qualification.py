from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from threading import Event

from leo.acquisition import AcquisitionApplication, AcquisitionConfig, AcquisitionCoordinator
from leo.contracts.profile import CapturePlanV1, CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import ReceiverGainV1
from leo.contracts.states import (
    CaptureState,
    GainMode,
    SourceType,
)
from leo.domain.profiles import compile_capture_plan
from leo.qualification import (
    AcquisitionQualificationHarness,
    AcquisitionQualificationReceiptV1,
    WriterBenchmarkConfigV1,
    WriterBenchmarkReceiptV1,
    WriterThroughputBenchmark,
)
from leo.radio import FakeRadioSource
from leo.storage import BundleCorruptionError, RecordingStore


class ImmediateAcquisitionClock:
    def utc_ns(self) -> int:
        return 1_800_000_000_000_000_000

    def monotonic_ns(self) -> int:
        return 4_000_000_000

    def sleep(self, seconds: float, cancel: Event) -> None:
        if cancel.is_set():
            raise RuntimeError("cancelled")

    def wait_until(self, target_monotonic_ns: int, cancel: Event) -> int:
        if cancel.is_set():
            raise RuntimeError("cancelled")
        return target_monotonic_ns


class StepClock:
    def __init__(self, *, start: int = 0, step: int = 1_000_000) -> None:
        self.value = start
        self.step = step

    def __call__(self) -> int:
        self.value += self.step
        return self.value


def _plan(radio_ids: tuple[str, ...]) -> CapturePlanV1:
    profile = CaptureProfileV1(
        name="qualification-test",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30),
            ReceiverGainV1(receiver_id=1, gain_db=30),
        ),
        sample_count=8,
        refill_samples=4,
        settle_seconds=Decimal(0),
        prime_refills=0,
        storage_policy="qualification-zstd-v1",
        tags=("TEST",),
    )
    return compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        radio_ids,
        source_type=SourceType.TEST,
    )


def _harness(store: RecordingStore) -> AcquisitionQualificationHarness:
    coordinator = AcquisitionCoordinator(
        store,
        clock=ImmediateAcquisitionClock(),
        config=AcquisitionConfig(
            release_lead_ns=0,
            safety_reserve_bytes=0,
            metadata_bytes_per_refill=64,
        ),
    )
    return AcquisitionQualificationHarness(
        store,
        AcquisitionApplication(coordinator),
        monotonic_ns=StepClock(step=10_000_000),
        utc_ns=StepClock(start=1_800_000_000_000_000_000),
    )


def test_default_dual_gate_passes_repeated_verified_fake_captures(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    receipt_path = tmp_path / "receipts" / "dual.json"

    receipt = _harness(store).run(
        _plan(("radio-a", "radio-b")),
        lambda radio_id: FakeRadioSource(radio_id, seed=17),
        qualification_id="dual-pass",
        trial_count=3,
        receipt_path=receipt_path,
    )

    assert receipt.complete
    assert receipt.passed
    assert receipt.aggregate.committed_count == 3
    assert receipt.aggregate.successful_trial_fraction == 1
    assert receipt.aggregate.overlap_passing_trial_fraction == 1
    assert receipt.aggregate.minimum_overlap_fraction == 1
    assert receipt.aggregate.total_gap_count == 0
    assert receipt.aggregate.total_overflow_count == 0
    assert receipt.aggregate.all_digests_valid
    assert receipt.aggregate.false_complete_count == 0
    assert receipt.aggregate.false_coherent_count == 0
    assert receipt.aggregate.compression_ratio is not None
    assert receipt.aggregate.mean_acquisition_throughput_mb_s is not None
    assert len(store.reconcile().committed) == 3
    assert (
        AcquisitionQualificationReceiptV1.model_validate_json(receipt_path.read_bytes()) == receipt
    )


def test_dual_overlap_below_99_percent_fails_default_gate(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")

    receipt = _harness(store).run(
        _plan(("radio-a", "radio-b")),
        lambda radio_id: FakeRadioSource(
            radio_id,
            utc_origin_ns=(
                1_700_000_000_000_000_000 if radio_id == "radio-a" else 1_700_000_000_020_000_000
            ),
        ),
        qualification_id="dual-low-overlap",
        trial_count=2,
        receipt_path=tmp_path / "low-overlap.json",
    )

    assert receipt.complete
    assert not receipt.passed
    assert receipt.aggregate.successful_trial_fraction == 1
    assert receipt.aggregate.overlap_passing_trial_fraction == 0
    assert receipt.aggregate.mean_overlap_fraction == 0


def test_single_radio_gate_does_not_invent_cross_radio_overlap(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")

    receipt = _harness(store).run(
        _plan(("radio-a",)),
        lambda radio_id: FakeRadioSource(radio_id),
        qualification_id="single-pass",
        trial_count=2,
        receipt_path=tmp_path / "single.json",
    )

    assert receipt.passed
    assert receipt.aggregate.overlap_passing_count == 0
    assert receipt.aggregate.mean_overlap_fraction is None
    assert all(trial.overlap_fraction is None for trial in receipt.trials)


def test_cancel_then_resume_skips_every_completed_trial_id(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    plan = _plan(("radio-a",))
    path = tmp_path / "resume.json"
    cancel = Event()
    first_calls: list[str] = []

    def cancelling_factory(radio_id: str) -> FakeRadioSource:
        first_calls.append(radio_id)
        if len(first_calls) == 2:
            cancel.set()
        return FakeRadioSource(radio_id)

    interrupted = _harness(store).run(
        plan,
        cancelling_factory,
        qualification_id="resume-safe",
        trial_count=3,
        receipt_path=path,
        cancel=cancel,
    )

    assert interrupted.cancelled
    assert len(interrupted.trials) == 2
    assert interrupted.trials[0].state is CaptureState.COMMITTED
    assert interrupted.trials[1].state is CaptureState.FAILED
    assert len(store.reconcile().committed) == 1

    resumed_calls: list[str] = []

    def resumed_factory(radio_id: str) -> FakeRadioSource:
        resumed_calls.append(radio_id)
        return FakeRadioSource(radio_id)

    resumed = _harness(store).run(
        plan,
        resumed_factory,
        qualification_id="resume-safe",
        trial_count=3,
        receipt_path=path,
        cancel=Event(),
    )

    assert resumed.complete
    assert not resumed.cancelled
    assert resumed_calls == ["radio-a"]
    assert tuple(trial.trial_id for trial in resumed.trials) == (
        "resume-safe-trial-000001",
        "resume-safe-trial-000002",
        "resume-safe-trial-000003",
    )
    assert len(store.reconcile().committed) == 2


def test_resume_recovers_committed_bundle_missing_from_receipt(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    plan = _plan(("radio-a",))
    lost_receipt = tmp_path / "lost.json"
    first = _harness(store).run(
        plan,
        lambda radio_id: FakeRadioSource(radio_id),
        qualification_id="recover-bundle",
        trial_count=1,
        receipt_path=lost_receipt,
    )
    assert first.passed
    lost_receipt.unlink()

    def must_not_capture(_radio_id: str) -> FakeRadioSource:
        raise AssertionError("resume attempted to duplicate an existing trial bundle")

    recovered = _harness(store).run(
        plan,
        must_not_capture,
        qualification_id="recover-bundle",
        trial_count=1,
        receipt_path=lost_receipt,
    )

    assert recovered.passed
    assert recovered.trials[0].elapsed_seconds is None
    assert len(store.reconcile().committed) == 1


def test_digest_failure_is_falsely_complete_and_rejects_receipt(tmp_path: Path) -> None:
    class RejectVerificationStore(RecordingStore):
        def verify(self, bundle):
            raise BundleCorruptionError("injected digest failure")

    store = RejectVerificationStore(tmp_path / "bulk")
    receipt = _harness(store).run(
        _plan(("radio-a",)),
        lambda radio_id: FakeRadioSource(radio_id),
        qualification_id="bad-digest",
        trial_count=1,
        receipt_path=tmp_path / "bad-digest.json",
    )

    assert not receipt.passed
    assert receipt.aggregate.digest_invalid_count == 1
    assert not receipt.aggregate.all_digests_valid
    assert receipt.aggregate.false_complete_count == 1
    assert receipt.trials[0].verification_error is not None
    assert len(store.reconcile().committed) == 1


def test_generated_writer_benchmark_is_bounded_verified_and_resumable(
    tmp_path: Path,
) -> None:
    store = RecordingStore(tmp_path / "bulk")
    path = tmp_path / "writer.json"
    config = WriterBenchmarkConfigV1(
        duration_seconds=0.005,
        minimum_throughput_mb_s=1,
        block_uncompressed_bytes=65_536,
        receiver_count=2,
        random_seed=7,
    )
    benchmark = WriterThroughputBenchmark(
        store,
        monotonic_ns=StepClock(step=1_000_000),
        utc_ns=StepClock(start=1_800_000_000_000_000_000),
    )

    receipt = benchmark.run(
        benchmark_id="writer-fast",
        receipt_path=path,
        configuration=config,
    )

    assert receipt.passed
    assert receipt.digest_valid
    assert receipt.block_count > 0
    assert receipt.elapsed_seconds < 0.1
    assert receipt.throughput_mb_s >= 1
    assert receipt.bundle_uri is not None
    assert WriterBenchmarkReceiptV1.model_validate_json(path.read_bytes()) == receipt
    store.verify("writer-fast")
    resumed = benchmark.run(
        benchmark_id="writer-fast",
        receipt_path=path,
        configuration=config,
    )
    assert resumed == receipt
    assert len(store.reconcile().committed) == 1


def test_writer_default_target_is_60_mb_s_and_threshold_is_enforced(tmp_path: Path) -> None:
    defaults = WriterBenchmarkConfigV1()
    assert defaults.minimum_throughput_mb_s == 60
    assert defaults.block_uncompressed_bytes == 128 * 1024 * 1024
    store = RecordingStore(tmp_path / "bulk")
    config = WriterBenchmarkConfigV1(
        duration_seconds=0.003,
        minimum_throughput_mb_s=1_000_000,
        block_uncompressed_bytes=65_536,
    )
    receipt = WriterThroughputBenchmark(
        store,
        monotonic_ns=StepClock(step=1_000_000),
        utc_ns=StepClock(start=1_800_000_000_000_000_000),
    ).run(
        benchmark_id="writer-slow",
        receipt_path=tmp_path / "writer-slow.json",
        configuration=config,
    )

    assert not receipt.passed
    assert receipt.digest_valid
    assert receipt.throughput_mb_s < config.minimum_throughput_mb_s
