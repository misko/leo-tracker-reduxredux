from __future__ import annotations

from dataclasses import replace

import numpy as np
import numpy.typing as npt
import pytest

import leo.scanner.persistent_hop_analysis as persistent_analysis
from leo.analysis.starlink import (
    PilotMethod,
    StarlinkEdge,
    TrajectoryBankConfig,
    TrajectoryMethodConfig,
    fit_trajectory_bank,
)
from leo.scanner import (
    PersistentHopAnalysisSource,
    PersistentHopGlrt64CfoObservation,
    PersistentHopGlrt64Configuration,
    build_persistent_hop_analysis_source,
    compile_persistent_hop_plan_v1,
)
from leo.scanner.detector import (
    DwellGlrt64Analysis,
    Glrt64CandidateResponse,
    Glrt64ProbeResponse,
)
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop import PersistentHopSessionReceiptV1


class _LazyValidCi16Reader:
    def __init__(
        self,
        receipt: PersistentHopSessionReceiptV1,
        *,
        sample_count: int | None = None,
        dtype: npt.DTypeLike = "<i2",
    ) -> None:
        self._sample_count = receipt.valid_sample_count if sample_count is None else sample_count
        self._receiver_ids = receipt.plan.receiver_ids
        self._dtype = dtype
        self.calls: list[tuple[int, int]] = []

    @property
    def sample_count(self) -> int:
        return self._sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return self._receiver_ids

    def read_valid_ci16(self, sample_start: int, sample_count: int) -> npt.NDArray[np.int16]:
        self.calls.append((sample_start, sample_count))
        values = np.zeros((sample_count, len(self.receiver_ids), 2), dtype=self._dtype)
        values[0, :, 0] = sample_start % 32_767
        return values  # type: ignore[return-value]


def _cancelled_receipt(*, visit_count: int = 24) -> PersistentHopSessionReceiptV1:
    radio = FakePersistentHopRadio()
    radio.open()
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    session = radio.begin_session(plan, session_id=f"analysis-{visit_count}")
    for _ in range(visit_count):
        session.read_visit()
    session.request_cancel()
    receipt = session.finish()
    radio.close()
    return receipt


def _source(
    receipt: PersistentHopSessionReceiptV1,
    reader: _LazyValidCi16Reader | None = None,
) -> PersistentHopAnalysisSource:
    selected_reader = reader or _LazyValidCi16Reader(receipt)
    return build_persistent_hop_analysis_source(
        receipt=receipt,
        reader=selected_reader,
        input_uri="persistent-hop-valid://analysis-fixture",
        input_manifest_sha256="sha256:" + "0" * 64,
    )


def _candidate(*, rank: int, tracking_cfo_hz: float) -> Glrt64CandidateResponse:
    return Glrt64CandidateResponse(
        candidate_rank=rank,
        epoch_sample=125,
        acquired_cfo_hz=tracking_cfo_hz - 20.0,
        residual_cfo_hz=20.0,
        tracking_cfo_hz=tracking_cfo_hz,
        exact_score=0.80,
        control_score=0.10,
        margin=0.70,
        passed_margin_gate=True,
    )


def _observation(
    source: PersistentHopAnalysisSource, visit_index: int
) -> PersistentHopGlrt64CfoObservation:
    tracking_cfo_hz = 15_000.0 + 125.0 * visit_index
    candidate = _candidate(rank=0, tracking_cfo_hz=tracking_cfo_hz)
    probe = Glrt64ProbeResponse(
        receiver_id=0,
        probe_index=2,
        probe_start_ms=20,
        candidates=(candidate,),
    )
    return source.glrt64_cfo_observation(
        visit_index,
        probe=probe,
        candidate=candidate,
    )


def test_source_is_lazy_and_preserves_payload_and_device_counter_coordinates() -> None:
    receipt = _cancelled_receipt(visit_count=2)
    reader = _LazyValidCi16Reader(receipt)

    source = _source(receipt, reader)

    assert reader.calls == []
    assert not hasattr(source, "configuration")
    assert source.sample_rate_hz == 2_500_000
    assert source.bandwidth_hz == source.sample_rate_hz
    assert source.receiver_ids == (0, 1)
    assert source.stream_generation == receipt.stream_generation
    first, second = source.visits
    assert first.payload_sample_start == 0
    assert first.payload_sample_end_exclusive == 300_000
    assert second.payload_sample_start == 300_000
    assert second.valid_device_sample_counter - first.valid_device_sample_counter == (
        first.valid_sample_count + second.transition_invalid_before.sample_count
    )
    assert second.valid_device_sample_counter - first.valid_device_sample_counter > (
        second.payload_sample_start - first.payload_sample_start
    )
    assert second.transition_invalid_before.sample_count > 0
    assert source.transition_invalid_spans == tuple(
        item.transition_invalid_before for item in receipt.visits
    )
    assert second.sample_rate_hz == source.sample_rate_hz
    assert second.bandwidth_hz == source.bandwidth_hz
    assert second.fastlock_profile_index == 1
    assert second.actual_if_center_hz == second.requested_if_center_hz

    loaded = source.read_visit(1)

    assert reader.calls == [(300_000, 300_000)]
    assert loaded.span is second
    assert loaded.samples_ci16.shape == (300_000, 2, 2)
    assert loaded.samples_ci16.dtype == np.dtype("<i2")
    assert loaded.samples_ci16.flags.writeable is False
    assert loaded.complex_samples().shape == (300_000, 2)


def test_source_rejects_payload_length_and_reader_shape_or_dtype_mismatch() -> None:
    receipt = _cancelled_receipt(visit_count=1)

    with pytest.raises(ValueError, match="payload length disagrees"):
        _source(receipt, _LazyValidCi16Reader(receipt, sample_count=receipt.valid_sample_count - 1))

    source = _source(receipt, _LazyValidCi16Reader(receipt, dtype=np.float32))
    with pytest.raises(ValueError, match="shape/dtype"):
        source.read_visit(0)
    with pytest.raises(ValueError, match="outside the session"):
        source.read_visit(-1)


def test_persistent_glrt_uses_structural_dwell_port_without_legacy_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _cancelled_receipt(visit_count=1)
    source = _source(receipt)
    observed: dict[str, object] = {}

    def fake_analyze(samples, configuration, *, edge):
        observed.update(samples=samples, configuration=configuration, edge=edge)
        return DwellGlrt64Analysis(
            first=None,
            decision_best_margin=None,
            full_best_margin=None,
            reason="deterministic adapter probe",
            probes=(),
        )

    monkeypatch.setattr(persistent_analysis, "analyze_glrt64_dwell", fake_analyze)

    result = source.analyze_glrt64_visit(0)

    configuration = observed["configuration"]
    assert isinstance(configuration, PersistentHopGlrt64Configuration)
    assert configuration.plan is source.plan
    assert configuration.dwell_samples == 300_000
    assert configuration.probe_samples == 50_000
    assert configuration.probe_stride_samples == 25_000
    assert configuration.scheduled_probe_count == 11
    assert np.asarray(observed["samples"]).shape == (300_000, 2)
    assert observed["edge"] is StarlinkEdge.LOWER
    assert result.reason == "deterministic adapter probe"


def test_glrt_cfo_groups_are_deterministic_edge_separated_and_trajectory_ready() -> None:
    receipt = _cancelled_receipt(visit_count=24)
    source = _source(receipt)
    chronological = tuple(_observation(source, index) for index in range(24))

    channels = source.group_glrt64_cfo_by_channel(tuple(reversed(chronological)))

    assert [item.channel for item in channels] == [1, 2, 3, 4]
    assert [item.visit_index for item in channels[0].lower] == [0, 8, 16]
    assert [item.visit_index for item in channels[0].upper] == [4, 12, 20]
    assert all(item.target.edge is StarlinkEdge.LOWER for item in channels[0].lower)
    assert all(item.target.edge is StarlinkEdge.UPPER for item in channels[0].upper)
    first = channels[0].lower[0]
    assert first.payload_sample_start == 50_125
    assert first.device_sample_counter == (receipt.visits[0].valid_device_sample_counter + 50_125)
    assert first.trajectory.sample_start == (
        first.device_sample_counter - receipt.session_start_device_sample_counter
    )
    assert first.trajectory.sample_start != first.payload_sample_start
    assert first.trajectory.time_s == pytest.approx(
        first.trajectory.sample_start / source.sample_rate_hz
    )
    assert first.trajectory.method is PilotMethod.GLRT64

    trajectory_input = channels[0].trajectory_observations(
        edge=StarlinkEdge.LOWER,
        receiver_id=0,
    )
    result = fit_trajectory_bank(
        trajectory_input,
        TrajectoryBankConfig(
            methods=(
                TrajectoryMethodConfig(
                    method=PilotMethod.GLRT64,
                    high_gate=0.5,
                    low_gate=0.0,
                    minimum_local_points=2,
                    minimum_high_points=1,
                    maximum_merge_gap_s=2.0,
                ),
            ),
            polynomial_degrees=(1,),
            local_window_s=3.0,
            minimum_final_duration_s=0.5,
        ),
    )
    assert result.observation_count == 3
    assert result.trajectories


def test_cfo_grouping_rejects_duplicate_or_counter_tampered_observations() -> None:
    receipt = _cancelled_receipt(visit_count=8)
    source = _source(receipt)
    observation = _observation(source, 0)

    with pytest.raises(ValueError, match="IDs must be unique"):
        source.group_glrt64_cfo_by_channel((observation, observation))
    with pytest.raises(ValueError, match="disagrees with source evidence"):
        source.group_glrt64_cfo_by_channel(
            (replace(observation, device_sample_counter=observation.device_sample_counter + 1),)
        )


def test_cfo_observation_rejects_candidate_from_another_probe() -> None:
    receipt = _cancelled_receipt(visit_count=1)
    source = _source(receipt)
    candidate = _candidate(rank=0, tracking_cfo_hz=1_000.0)
    probe = Glrt64ProbeResponse(
        receiver_id=0,
        probe_index=0,
        probe_start_ms=0,
        candidates=(),
    )

    with pytest.raises(ValueError, match="not owned by its probe"):
        source.glrt64_cfo_observation(0, probe=probe, candidate=candidate)


def test_full_glrt_projection_filters_margin_and_keeps_receivers_separate() -> None:
    receipt = _cancelled_receipt(visit_count=1)
    source = _source(receipt)
    passed = _candidate(rank=0, tracking_cfo_hz=1_000.0)
    rejected = replace(
        _candidate(rank=1, tracking_cfo_hz=2_000.0),
        passed_margin_gate=False,
    )
    analysis = DwellGlrt64Analysis(
        first=None,
        decision_best_margin=passed.margin,
        full_best_margin=passed.margin,
        reason="deterministic candidate projection",
        probes=(
            Glrt64ProbeResponse(
                receiver_id=0,
                probe_index=0,
                probe_start_ms=0,
                candidates=(passed, rejected),
            ),
            Glrt64ProbeResponse(
                receiver_id=1,
                probe_index=0,
                probe_start_ms=0,
                candidates=(passed,),
            ),
        ),
    )

    observations = source.glrt64_cfo_observations(0, analysis)
    channel = source.group_glrt64_cfo_by_channel(observations)[0]

    assert [(item.receiver_id, item.candidate_rank) for item in observations] == [(0, 0), (1, 0)]
    assert len(channel.trajectory_observations(edge=StarlinkEdge.LOWER, receiver_id=0)) == 1
    assert len(channel.trajectory_observations(edge=StarlinkEdge.LOWER, receiver_id=1)) == 1
    assert len(source.glrt64_cfo_observations(0, analysis, passed_margin_only=False)) == 3
