from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from threading import Event

import pytest

from leo.acquisition import (
    AcquisitionApplication,
    AcquisitionConfig,
    AcquisitionCoordinator,
    CaptureSessionResult,
    StorageAdmissionDecision,
)
from leo.contracts.profile import CapturePlanV1, CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import ReceiverGainV1
from leo.contracts.states import GainMode, SourceType
from leo.domain.profiles import compile_capture_plan
from leo.qualification import (
    AcquisitionSoakHarness,
    PostCommitObservationV1,
    ProcessingBacklogObservationV1,
    SoakAcceptancePolicyV1,
    SoakConfigV1,
    SoakSummaryV1,
    SoakTrialEvidenceV1,
)
from leo.radio import FakeRadioSource, RadioSource
from leo.storage import BundleCorruptionError, RecordingStore

_POST_COMMIT_POLICY_TEXT = "post-commit observer failure count exceeds policy"


class ImmediateAcquisitionClock:
    def __init__(self) -> None:
        self.utc = 1_800_000_000_000_000_000
        self.monotonic = 4_000_000_000

    def utc_ns(self) -> int:
        self.utc += 10_000
        return self.utc

    def monotonic_ns(self) -> int:
        self.monotonic += 10_000
        return self.monotonic

    def sleep(self, seconds: float, cancel: Event) -> None:
        if cancel.is_set():
            raise RuntimeError("cancelled")

    def wait_until(self, target_monotonic_ns: int, cancel: Event) -> int:
        if cancel.is_set():
            raise RuntimeError("cancelled")
        self.monotonic = target_monotonic_ns
        return target_monotonic_ns


class SoakClock:
    def __init__(self) -> None:
        self.value = 0
        self.utc_origin = 1_900_000_000_000_000_000

    def monotonic_ns(self) -> int:
        self.value += 1_000_000
        return self.value

    def utc_ns(self) -> int:
        return self.utc_origin + self.value

    def wait(self, cancel: Event, seconds: float) -> bool:
        self.value += round(seconds * 1_000_000_000)
        return cancel.is_set()


def _plan(*, tags: tuple[str, ...] = ("TEST",)) -> CapturePlanV1:
    profile = CaptureProfileV1(
        name="soak-test",
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
        storage_policy="soak-zstd-v1",
        tags=tags,
    )
    return compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        ("radio-a",),
        source_type=SourceType.TEST,
    )


def _application(
    store: RecordingStore,
    *,
    storage_admission=None,
) -> AcquisitionApplication:
    coordinator = AcquisitionCoordinator(
        store,
        clock=ImmediateAcquisitionClock(),
        config=AcquisitionConfig(
            release_lead_ns=0,
            safety_reserve_bytes=0,
            metadata_bytes_per_refill=64,
        ),
        storage_admission=storage_admission,
    )
    return AcquisitionApplication(coordinator)


def _harness(
    store: RecordingStore,
    application: AcquisitionApplication | None = None,
    *,
    output_root: Path | None = None,
    backlog_observer=None,
    post_commit_observer=None,
    peak_rss_bytes=None,
    wait=None,
) -> AcquisitionSoakHarness:
    clock = SoakClock()
    return AcquisitionSoakHarness(
        store,
        application or _application(store),
        output_root=output_root or store.root / "qualification" / "soak",
        backlog_observer=backlog_observer,
        post_commit_observer=post_commit_observer,
        monotonic_ns=clock.monotonic_ns,
        utc_ns=clock.utc_ns,
        wait=wait or clock.wait,
        peak_rss_bytes=peak_rss_bytes,
    )


def _source(radio_id: str) -> FakeRadioSource:
    return FakeRadioSource(radio_id, seed=31)


def test_short_fake_radio_soak_records_complete_operational_evidence(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    queue = ProcessingBacklogObservationV1(
        observed_utc_ns=1_900_000_000_000_000_000,
        queued=2,
        running=1,
        failed=0,
        oldest_queued_seconds=0.5,
    )
    summary = _harness(store, backlog_observer=lambda: queue).run(
        _plan(),
        _source,
        soak_id="short-soak",
        configuration=SoakConfigV1(
            duration_seconds=0.025,
            cadence_seconds=0.01,
        ),
    )

    assert summary.status == "complete"
    assert summary.completion_reason == "duration"
    assert summary.passed
    assert summary.completed_trial_count == 3
    assert summary.committed_count == 3
    assert summary.total_requested_sample_count == 24
    assert summary.total_captured_sample_count == 24
    assert summary.total_gap_count == 0
    assert summary.total_overflow_count == 0
    assert summary.duty_cycle > 0
    assert summary.maximum_processing_backlog_queued == 2
    assert summary.minimum_storage_available_bytes > 0
    evidence = sorted((store.root / "qualification/soak/short-soak/trials").glob("*.json"))
    assert len(evidence) == 3
    first = SoakTrialEvidenceV1.model_validate_json(evidence[0].read_bytes())
    assert first.digest_valid
    assert first.bundle_uri is not None
    assert first.process_peak_rss_bytes > 0
    assert first.admission.admitted
    assert store.inspect(first.session_id).manifest.tags == ("TEST",)


def test_crash_after_publish_resumes_without_duplicate_session_id(tmp_path: Path) -> None:
    class CrashAfterCommitApplication(AcquisitionApplication):
        def once(
            self,
            plan: CapturePlanV1,
            sources: Mapping[str, RadioSource],
            *,
            session_id: str | None = None,
            cancel: Event | None = None,
            extra_tags: tuple[str, ...] = (),
        ) -> CaptureSessionResult:
            result = super().once(
                plan,
                sources,
                session_id=session_id,
                cancel=cancel,
                extra_tags=extra_tags,
            )
            assert result.bundle is not None
            raise RuntimeError("simulated process death after bundle publish")

    store = RecordingStore(tmp_path / "bulk")
    crashing = CrashAfterCommitApplication(_application(store).coordinator)
    config = SoakConfigV1(duration_seconds=60, maximum_trials=2)
    with pytest.raises(RuntimeError, match="simulated process death"):
        _harness(store, crashing).run(
            _plan(),
            _source,
            soak_id="resume-soak",
            configuration=config,
        )

    assert len(store.reconcile().committed) == 1
    resumed = _harness(store).run(
        _plan(),
        _source,
        soak_id="resume-soak",
        configuration=config,
    )

    assert resumed.passed
    evidence_root = store.root / "qualification/soak/resume-soak/trials"
    evidence = [
        SoakTrialEvidenceV1.model_validate_json(path.read_bytes())
        for path in sorted(evidence_root.glob("*.json"))
    ]
    assert [trial.session_id for trial in evidence] == [
        "resume-soak-trial-00000001",
        "resume-soak-trial-00000002",
    ]
    assert evidence[0].recovered_after_interruption
    assert evidence[0].admission.evidence_scope == "recovery"
    assert not evidence[1].recovered_after_interruption
    assert len(store.reconcile().committed) == 2


def test_backlog_and_rss_growth_are_finite_policy_failures(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    queued = iter((0, 2, 20))
    rss = iter((100, 250))

    def backlog() -> ProcessingBacklogObservationV1:
        return ProcessingBacklogObservationV1(
            observed_utc_ns=1_900_000_000_000_000_000,
            queued=next(queued),
            running=0,
            failed=0,
        )

    summary = _harness(
        store,
        backlog_observer=backlog,
        peak_rss_bytes=lambda: next(rss),
    ).run(
        _plan(),
        _source,
        soak_id="bounded-resources",
        configuration=SoakConfigV1(duration_seconds=60, maximum_trials=5),
        policy=SoakAcceptancePolicyV1(
            maximum_peak_rss_growth_bytes=100,
            maximum_processing_backlog_queued=10,
            maximum_processing_backlog_growth=10,
        ),
    )

    assert summary.status == "failed"
    assert not summary.complete
    assert not summary.passed
    assert summary.completed_trial_count == 1
    assert summary.peak_rss_growth_bytes == 150
    assert summary.maximum_processing_backlog_queued == 20
    assert "process peak RSS growth exceeds policy" in summary.policy_violations
    assert "processing backlog queue exceeds policy" in summary.policy_violations
    assert "processing backlog growth exceeds policy" in summary.policy_violations


def test_false_complete_digest_claim_fails_versioned_policy(tmp_path: Path) -> None:
    class InvalidDigestStore(RecordingStore):
        def verify(self, bundle):
            raise BundleCorruptionError("injected digest mismatch")

    store = InvalidDigestStore(tmp_path / "bulk")
    summary = _harness(store).run(
        _plan(),
        _source,
        soak_id="false-complete",
        configuration=SoakConfigV1(duration_seconds=60, maximum_trials=5),
    )

    assert summary.status == "failed"
    assert summary.completed_trial_count == 1
    assert summary.false_complete_count == 1
    assert summary.digest_invalid_count == 1
    assert "false-complete count exceeds policy" in summary.policy_violations
    assert "one or more recording digests are invalid or unverified" in (summary.policy_violations)


def test_post_commit_callback_precedes_backlog_after_and_exposes_queue_drain(
    tmp_path: Path,
) -> None:
    store = RecordingStore(tmp_path / "bulk")
    queue = {"value": 0}
    events: list[str] = []
    clock = SoakClock()

    def backlog() -> ProcessingBacklogObservationV1:
        events.append(f"backlog:{queue['value']}")
        return ProcessingBacklogObservationV1(
            observed_utc_ns=clock.utc_ns(),
            queued=queue["value"],
            running=0,
            failed=0,
        )

    def post_commit(bundle) -> PostCommitObservationV1:
        events.append(f"post:{bundle.session_id}")
        queue["value"] += 2
        return PostCommitObservationV1(
            observed_utc_ns=clock.utc_ns(),
            target_session_id=bundle.session_id,
            attempted=True,
            succeeded=True,
            registered_session_ids=(bundle.session_id,),
            queued_run_ids=(f"run-{bundle.session_id}",),
        )

    def wait(cancel: Event, seconds: float) -> bool:
        queue["value"] = max(0, queue["value"] - 1)
        return clock.wait(cancel, seconds)

    harness = AcquisitionSoakHarness(
        store,
        _application(store),
        output_root=store.root / "qualification/soak",
        backlog_observer=backlog,
        post_commit_observer=post_commit,
        monotonic_ns=clock.monotonic_ns,
        utc_ns=clock.utc_ns,
        wait=wait,
    )
    summary = harness.run(
        _plan(),
        _source,
        soak_id="queue-evidence",
        configuration=SoakConfigV1(
            duration_seconds=60,
            cadence_seconds=0.01,
            maximum_trials=2,
        ),
        policy=SoakAcceptancePolicyV1(maximum_post_commit_failure_count=0),
    )

    trial_root = store.root / "qualification/soak/queue-evidence/trials"
    trials = [
        SoakTrialEvidenceV1.model_validate_json(path.read_bytes())
        for path in sorted(trial_root.glob("*.json"))
    ]
    assert summary.passed
    assert summary.post_commit_success_count == 2
    assert summary.post_commit_failure_count == 0
    assert summary.queued_run_count == 2
    observed_queue = [
        (trial.processing_backlog_before.queued, trial.processing_backlog_after.queued)
        for trial in trials
    ]
    assert observed_queue == [
        (0, 2),
        (1, 3),
    ]
    for trial in trials:
        post_index = events.index(f"post:{trial.session_id}")
        assert events[post_index + 1].startswith("backlog:")


def test_database_outage_is_evidence_only_and_later_callback_recovers_bundle(
    tmp_path: Path,
) -> None:
    store = RecordingStore(tmp_path / "bulk")
    callback_sessions: list[str] = []

    def post_commit(bundle) -> PostCommitObservationV1:
        callback_sessions.append(bundle.session_id)
        if len(callback_sessions) == 1:
            raise ConnectionError("database is down")
        committed_ids = tuple(item.session_id for item in store.reconcile().committed)
        return PostCommitObservationV1(
            observed_utc_ns=1_900_000_000_000_000_000,
            target_session_id=bundle.session_id,
            attempted=True,
            succeeded=True,
            registered_session_ids=committed_ids,
            queued_run_ids=("recovered-run-1", "current-run-2"),
        )

    summary = _harness(store, post_commit_observer=post_commit).run(
        _plan(),
        _source,
        soak_id="database-recovery",
        configuration=SoakConfigV1(duration_seconds=60, maximum_trials=2),
        policy=SoakAcceptancePolicyV1(maximum_post_commit_failure_count=0),
    )

    trial_root = store.root / "qualification/soak/database-recovery/trials"
    trials = [
        SoakTrialEvidenceV1.model_validate_json(path.read_bytes())
        for path in sorted(trial_root.glob("*.json"))
    ]
    assert summary.status == "complete"
    assert not summary.passed
    assert summary.committed_count == 2
    assert summary.post_commit_failure_count == 1
    assert summary.post_commit_success_count == 1
    assert all(trial.digest_valid for trial in trials)
    assert all(not trial.errors for trial in trials)
    assert not trials[0].post_commit.succeeded
    assert "database is down" in (trials[0].post_commit.error or "")
    assert set(trials[1].post_commit.registered_session_ids) == set(callback_sessions)
    assert _POST_COMMIT_POLICY_TEXT in summary.policy_violations
    assert len(store.reconcile().committed) == 2


def test_storage_admission_rejection_is_recorded_and_fails_policy(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    application = _application(
        store,
        storage_admission=lambda _path: StorageAdmissionDecision(
            allowed=False,
            used_fraction=0.81,
            warning=True,
            reason="automatic admission stop at 80%",
        ),
    )
    called = False

    def source(radio_id: str) -> FakeRadioSource:
        nonlocal called
        called = True
        return FakeRadioSource(radio_id)

    summary = _harness(store, application).run(
        _plan(),
        source,
        soak_id="admission-stop",
        configuration=SoakConfigV1(duration_seconds=60, maximum_trials=2),
    )

    assert not called
    assert summary.status == "failed"
    assert summary.failed_count == 1
    assert summary.admission_rejection_count == 1
    trial_path = store.root / "qualification/soak/admission-stop/trials/trial-00000000.json"
    trial = SoakTrialEvidenceV1.model_validate_json(trial_path.read_bytes())
    assert not trial.admission.admitted
    assert trial.admission.evidence_scope == "capture"
    assert trial.admission.warning
    assert trial.admission.reason == "automatic admission stop at 80%"
    assert "storage admission rejection count exceeds policy" in summary.policy_violations


def test_summary_is_bounded_and_trial_evidence_is_never_rewritten(tmp_path: Path) -> None:
    class CancelAfterFirstApplication(AcquisitionApplication):
        def __init__(self, coordinator, cancel: Event) -> None:
            super().__init__(coordinator)
            self.cancel = cancel

        def once(
            self,
            plan: CapturePlanV1,
            sources: Mapping[str, RadioSource],
            *,
            session_id: str | None = None,
            cancel: Event | None = None,
            extra_tags: tuple[str, ...] = (),
        ) -> CaptureSessionResult:
            result = super().once(
                plan,
                sources,
                session_id=session_id,
                cancel=cancel,
                extra_tags=extra_tags,
            )
            self.cancel.set()
            return result

    store = RecordingStore(tmp_path / "bulk")
    event = Event()
    base = _application(store)
    cancelling = CancelAfterFirstApplication(base.coordinator, event)
    config = SoakConfigV1(duration_seconds=60, maximum_trials=40)
    interrupted = _harness(store, cancelling).run(
        _plan(),
        _source,
        soak_id="bounded-summary",
        configuration=config,
        cancel=event,
    )
    assert interrupted.status == "interrupted"
    first_path = store.root / "qualification/soak/bounded-summary/trials/trial-00000000.json"
    first_payload = first_path.read_bytes()

    completed = _harness(store).run(
        _plan(),
        _source,
        soak_id="bounded-summary",
        configuration=config,
        cancel=Event(),
    )

    summary_path = store.root / "qualification/soak/bounded-summary/summary.json"
    assert completed.passed
    assert completed.completed_trial_count == 40
    assert first_path.read_bytes() == first_payload
    assert summary_path.stat().st_size < 64 * 1024
    assert b'"trials"' not in summary_path.read_bytes()
    assert SoakSummaryV1.model_validate_json(summary_path.read_bytes()) == completed
    trial_paths = tuple(summary_path.parent.joinpath("trials").glob("*.json"))
    assert len(trial_paths) == 40
    assert max(path.stat().st_size for path in trial_paths) < 256 * 1024


def test_qnap_output_is_hard_rejected(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    with pytest.raises(ValueError, match="qnap01"):
        AcquisitionSoakHarness(
            store,
            _application(store),
            output_root=Path("/mnt/qnap01/qualification/soak"),
        )


def test_soak_explicitly_forbids_qualification_tag_that_skips_processing(
    tmp_path: Path,
) -> None:
    store = RecordingStore(tmp_path / "bulk")
    with pytest.raises(ValueError, match="must enter the normal processing queue"):
        _harness(store).run(
            _plan(tags=("QUALIFICATION", "TEST")),
            _source,
            soak_id="wrong-tag-policy",
            configuration=SoakConfigV1(duration_seconds=1, maximum_trials=1),
        )
    assert not store.reconcile().committed
