"""Pure paired known-truth Qin injection and parity-isolated evidence rows."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np
import numpy.typing as npt

from leo.analysis.research.cross_family_injection_protocol import (
    CrossFamilyInjectionProtocol,
    CrossFamilyTruthPair,
)
from leo.analysis.research.cross_family_orbit_truth import VerifiedCrossFamilyTruthPair
from leo.analysis.research.polynomial_injection import FrameCfoEvidence, InjectionDiagnostics
from leo.analysis.research.trajectory_qin_injection import (
    PiecewiseLinearCfoTrajectory,
    TrajectoryQinInjectionConfig,
    evaluate_exact_qin_trajectory_frames,
    inject_exact_qin_trajectory,
)
from leo.contracts.digests import canonical_digest

type TruthFamily = Literal["catalogue-orbit", "radio-polynomial"]
type ObservationSplit = Literal["training-even-qin", "future-odd-qin"]


class CrossFamilyInjectionInputError(ValueError):
    """The paired background, protocol, or truth authority does not close."""


@dataclass(frozen=True, slots=True)
class CrossFamilyObservationRow:
    """One opportunity with a split-selected response and every no-result retained."""

    scenario_id: str
    frame_index: int
    split: ObservationSplit
    reference_time_s: float
    absolute_frame_start_sample: int
    occupied: bool
    status: str
    even_training_gate_passed: bool
    rejection_reasons: tuple[str, ...]
    measured_cfo_hz: float | None
    standard_uncertainty_hz: float | None
    truth_cfo_hz: float
    residual_hz: float | None
    usable: bool


@dataclass(frozen=True, slots=True)
class CrossFamilyInjectedArmEvidence:
    """One truth arm measured through the exact same public Qin kernel."""

    truth_family: TruthFamily
    scenario_id: str
    diagnostics: InjectionDiagnostics
    frame_evidence: tuple[FrameCfoEvidence, ...]
    observation_rows: tuple[CrossFamilyObservationRow, ...]
    training_opportunity_count: int
    future_opportunity_count: int
    training_usable_count: int
    future_usable_count: int
    evidence_digest: str
    training_uses_even_qin_only: Literal[True] = field(default=True, init=False)
    future_uses_odd_qin_only: Literal[True] = field(default=True, init=False)
    future_response_used_for_training: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class CrossFamilyInjectedPairEvidence:
    """Paired arms on one independent real-background unit."""

    pair_id: str
    background_session_id: str
    orbit: CrossFamilyInjectedArmEvidence
    radio: CrossFamilyInjectedArmEvidence
    occupancy_identical: bool
    pair_evidence_digest: str
    independent_unit: Literal["background-pair"] = field(default="background-pair", init=False)
    independent_unit_count: Literal[1] = field(default=1, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)
    threshold_fitted: Literal[False] = field(default=False, init=False)


def generate_cross_family_injected_evidence(
    background: npt.ArrayLike,
    pair: CrossFamilyTruthPair,
    truth: VerifiedCrossFamilyTruthPair,
    protocol: CrossFamilyInjectionProtocol,
) -> CrossFamilyInjectedPairEvidence:
    """Inject and measure both truth arms without mutating the supplied background."""

    values = np.asarray(background, dtype=np.complex64)
    if pair not in protocol.pairs:
        raise CrossFamilyInjectionInputError("truth pair is absent from the frozen protocol")
    if pair.pair_id != truth.pair_id or pair.true_catalog_number != truth.true_catalog_number:
        raise CrossFamilyInjectionInputError("verified truth does not bind the requested pair")
    background_binding = protocol.background(pair.background_session_id)
    if values.ndim != 1 or values.size != background_binding.sample_count:
        raise CrossFamilyInjectionInputError("background does not match the frozen span")
    if not np.all(np.isfinite(values)):
        raise CrossFamilyInjectionInputError("background contains non-finite samples")
    before = values.copy()
    orbit, orbit_occupancy = _generate_arm(
        values,
        pair,
        truth.orbit_trajectory,
        truth_family="catalogue-orbit",
        protocol=protocol,
    )
    radio, radio_occupancy = _generate_arm(
        values,
        pair,
        truth.radio_trajectory,
        truth_family="radio-polynomial",
        protocol=protocol,
    )
    if not np.array_equal(values, before):
        raise CrossFamilyInjectionInputError("injection kernel mutated the caller background")
    occupancy_identical = bool(np.array_equal(orbit_occupancy, radio_occupancy))
    if not occupancy_identical:
        raise CrossFamilyInjectionInputError("paired truth arms received different occupancy")
    pair_payload = {
        "algorithm_version": "paired-cross-family-qin-evidence-v1",
        "protocol_digest": protocol.protocol_digest,
        "truth_digest": truth.truth_digest,
        "pair_id": pair.pair_id,
        "background_session_id": pair.background_session_id,
        "background_recording_manifest_sha256": background_binding.recording_manifest_sha256,
        "background_analysis_manifest_sha256": background_binding.analysis_manifest_sha256,
        "background_chunk_compressed_sha256": background_binding.chunk.compressed_sha256,
        "background_chunk_uncompressed_sha256": background_binding.chunk.uncompressed_sha256,
        "orbit_evidence_digest": orbit.evidence_digest,
        "radio_evidence_digest": radio.evidence_digest,
        "occupancy_identical": occupancy_identical,
        "independent_unit": "background-pair",
        "independent_unit_count": 1,
        "identity_claimed": False,
        "threshold_fitted": False,
    }
    return CrossFamilyInjectedPairEvidence(
        pair_id=pair.pair_id,
        background_session_id=pair.background_session_id,
        orbit=orbit,
        radio=radio,
        occupancy_identical=occupancy_identical,
        pair_evidence_digest=canonical_digest(pair_payload),
    )


def _generate_arm(
    background: np.ndarray,
    pair: CrossFamilyTruthPair,
    trajectory: PiecewiseLinearCfoTrajectory,
    *,
    truth_family: TruthFamily,
    protocol: CrossFamilyInjectionProtocol,
) -> tuple[CrossFamilyInjectedArmEvidence, np.ndarray]:
    background_binding = protocol.background(pair.background_session_id)
    scenario_id = (
        pair.orbit_scenario_id if truth_family == "catalogue-orbit" else pair.radio_scenario_id
    )
    config = TrajectoryQinInjectionConfig(
        scenario_id=scenario_id,
        sample_rate_hz=background_binding.sample_rate_hz,
        sample_count=background_binding.sample_count,
        frame_count=protocol.base_protocol.frame_count,
        snr_db=protocol.snr_db,
        frame_occupancy=protocol.frame_occupancy,
        seed=pair.seed,
        frame_cfo_search_half_width_hz=protocol.base_protocol.frame_cfo_search_half_width_hz,
        profile_step_hz=protocol.base_protocol.profile_step_hz,
        minimum_exact_coherence=protocol.base_protocol.minimum_exact_coherence,
        minimum_coherence_margin=protocol.base_protocol.minimum_coherence_margin,
    )
    injected, occupancy, diagnostics = inject_exact_qin_trajectory(background, trajectory, config)
    frame_evidence = evaluate_exact_qin_trajectory_frames(
        injected,
        occupancy,
        trajectory,
        config,
        absolute_span_start_sample=background_binding.sample_start,
    )
    cutoff = round(config.frame_count * protocol.training_fraction)
    if cutoff <= 0 or cutoff >= config.frame_count:
        raise CrossFamilyInjectionInputError("training split leaves an empty partition")
    rows = tuple(_observation_row(item, cutoff=cutoff) for item in frame_evidence)
    training_rows = tuple(item for item in rows if item.split == "training-even-qin")
    future_rows = tuple(item for item in rows if item.split == "future-odd-qin")
    payload = {
        "algorithm_version": "cross-family-qin-arm-evidence-v1",
        "protocol_digest": protocol.protocol_digest,
        "pair_id": pair.pair_id,
        "truth_family": truth_family,
        "scenario_id": scenario_id,
        "diagnostics": asdict(diagnostics),
        "observation_rows": [asdict(item) for item in rows],
        "training_uses_even_qin_only": True,
        "future_uses_odd_qin_only": True,
        "future_response_used_for_training": False,
    }
    return (
        CrossFamilyInjectedArmEvidence(
            truth_family=truth_family,
            scenario_id=scenario_id,
            diagnostics=diagnostics,
            frame_evidence=frame_evidence,
            observation_rows=rows,
            training_opportunity_count=len(training_rows),
            future_opportunity_count=len(future_rows),
            training_usable_count=sum(item.usable for item in training_rows),
            future_usable_count=sum(item.usable for item in future_rows),
            evidence_digest=canonical_digest(payload),
        ),
        occupancy,
    )


def _observation_row(item: FrameCfoEvidence, *, cutoff: int) -> CrossFamilyObservationRow:
    training = item.frame_index < cutoff
    measured = item.even_canonical_cfo_hz if training else item.odd_canonical_cfo_hz
    uncertainty = (
        item.even_frequency_uncertainty_hz if training else item.odd_frequency_uncertainty_hz
    )
    usable = bool(
        item.training_supported
        and measured is not None
        and uncertainty is not None
        and math.isfinite(measured)
        and math.isfinite(uncertainty)
        and uncertainty > 0.0
    )
    residual = None if not usable or measured is None else measured - item.receiver_truth_cfo_hz
    return CrossFamilyObservationRow(
        scenario_id=item.scenario_id,
        frame_index=item.frame_index,
        split="training-even-qin" if training else "future-odd-qin",
        reference_time_s=item.reference_time_s,
        absolute_frame_start_sample=item.absolute_frame_start_sample,
        occupied=item.occupied,
        status=item.status,
        even_training_gate_passed=item.training_supported,
        rejection_reasons=item.training_rejection_reasons,
        measured_cfo_hz=measured,
        standard_uncertainty_hz=uncertainty,
        truth_cfo_hz=item.receiver_truth_cfo_hz,
        residual_hz=residual,
        usable=usable,
    )
