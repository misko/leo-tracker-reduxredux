"""Build and replay first-slice known-position satellite corrections.

This pure analyzer projects a *fully reported, single-emitter* catalogue
posterior into the solver-safe :class:`SatelliteCorrectionProductV1` boundary.
It deliberately refuses ``K=2`` posteriors because the V1 correction contract
stores mutually exclusive per-catalogue modes; coexisting satellites need an
additive joint-mode contract rather than a misleading probability projection.

The transferable product contains only a bounded equivalent-epoch posterior
and a separately supplied satellite/beam frequency calibration.  Receiver,
LNB, path, and component nuisance estimates from association are never copied.
They are represented only by an opaque digest in the access-controlled known-
position receipt.

The replay helper is a known-position predictive diagnostic.  It applies a
frozen correction to a later, response-free prediction bank, fits a *new*
proper component-offset nuisance for the target observations, and reports
conditional scores.  It does not score an unassigned/radio-only model and
therefore cannot make an identity or navigation claim.  Blinded navigation
must use the separate challenge/estimate/reveal boundary.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from leo.contracts.catalogue_association import (
    CatalogueAssociationResultV1,
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    PhysicalEpisodeGraphV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.satellite_pnt import (
    CalibrationSourceSpanV1,
    CorrectionEvidenceClass,
    CorrectionExpiryReason,
    EquivalentEpochCorrectionV1,
    KnownPositionCalibrationReceiptV1,
    SatelliteCorrectionModeV1,
    SatelliteCorrectionProductV1,
    SatelliteCorrectionReasonCode,
    SatelliteFrequencyScope,
    SatelliteFrequencyStateV1,
    VerifiedTleMemberV1,
)
from leo.contracts.sky import ObserverSiteV1
from leo.contracts.standard_pipeline import StandardScientificStatus

_VALIDITY_HORIZON_NS = 30_000_000_000
_PROBABILITY_TOLERANCE = 1e-9
_TAU_TOLERANCE_S = 0.5e-9


class SatelliteCorrectionInputError(ValueError):
    """The calibration or replay inputs cannot support the declared product."""


class SatelliteCorrectionNumericalError(ValueError):
    """A correction or replay calculation is not numerically trustworthy."""


@dataclass(frozen=True, slots=True)
class SatelliteFrequencyCalibrationEstimate:
    """Satellite-side frequency state supplied by known-position calibration.

    This narrow input intentionally has no receiver, radio, LNB, path, or
    continuity-component field.  ``calibration_evidence_eligible`` is an
    externally frozen calibration verdict; this builder does not invent a
    numerical promotion threshold.
    """

    catalog_number: int
    activity_epoch_id: str
    scope: SatelliteFrequencyScope
    beam_channel_id: str | None
    reference_utc_ns: int
    bias_hz: float
    drift_hz_s: float
    bias_variance_hz2: float
    drift_variance_hz2_s2: float
    bias_drift_covariance_hz2_s: float
    calibration_evidence_eligible: bool

    def __post_init__(self) -> None:
        if (
            isinstance(self.catalog_number, bool)
            or not isinstance(self.catalog_number, int)
            or self.catalog_number <= 0
        ):
            raise SatelliteCorrectionInputError("catalog_number must be a positive integer")
        if not self.activity_epoch_id:
            raise SatelliteCorrectionInputError("activity_epoch_id cannot be empty")
        if not isinstance(self.scope, SatelliteFrequencyScope):
            raise SatelliteCorrectionInputError("scope must be an explicit SatelliteFrequencyScope")
        if not isinstance(self.calibration_evidence_eligible, bool):
            raise SatelliteCorrectionInputError(
                "calibration_evidence_eligible must be a boolean verdict"
            )
        if isinstance(self.reference_utc_ns, bool) or not isinstance(self.reference_utc_ns, int):
            raise SatelliteCorrectionInputError("reference_utc_ns must be an integer")
        if self.reference_utc_ns <= 0:
            raise SatelliteCorrectionInputError("reference_utc_ns must be positive")
        values = (
            self.bias_hz,
            self.drift_hz_s,
            self.bias_variance_hz2,
            self.drift_variance_hz2_s2,
            self.bias_drift_covariance_hz2_s,
        )
        if any(not math.isfinite(item) for item in values):
            raise SatelliteCorrectionInputError("frequency calibration values must be finite")
        if self.bias_variance_hz2 < 0.0 or self.drift_variance_hz2_s2 < 0.0:
            raise SatelliteCorrectionInputError("frequency variances cannot be negative")
        # Reuse the persisted contract as the covariance/scope oracle.
        SatelliteFrequencyStateV1(
            activity_epoch_id=self.activity_epoch_id,
            scope=self.scope,
            beam_channel_id=self.beam_channel_id,
            reference_utc_ns=self.reference_utc_ns,
            bias_hz=self.bias_hz,
            drift_hz_s=self.drift_hz_s,
            bias_variance_hz2=self.bias_variance_hz2,
            drift_variance_hz2_s2=self.drift_variance_hz2_s2,
            bias_drift_covariance_hz2_s=self.bias_drift_covariance_hz2_s,
        )


@dataclass(frozen=True, slots=True)
class ReplayComponentOffsetEstimate:
    continuity_component_id: Sha256Digest
    mean_hz: float
    standard_uncertainty_hz: float


@dataclass(frozen=True, slots=True)
class CorrectionReplayModeScore:
    catalog_number: int
    correction_mode_digest: Sha256Digest
    observation_count: int
    root_mean_square_residual_hz: float
    standardized_root_mean_square: float
    negative_log_predictive_density: float
    target_component_offsets: tuple[ReplayComponentOffsetEstimate, ...]


@dataclass(frozen=True, slots=True)
class KnownPositionCorrectionReplayResult:
    """Conditional future score; deliberately not an association posterior."""

    correction_product_digest: Sha256Digest
    graph_digest: Sha256Digest
    prediction_bank_digest: Sha256Digest
    target_component_offset_prior_sigma_hz: float
    mode_scores: tuple[CorrectionReplayModeScore, ...]
    null_model_scored: bool
    conditioned_on_assigned_correction_mode: bool
    receiver_local_state_exportable: bool
    identity_claimed: bool
    navigation_fix_claimed: bool


def build_single_emitter_known_position_correction(
    *,
    association: CatalogueAssociationResultV1,
    prediction_bank: CataloguePredictionBankV1,
    frequency_estimates: tuple[SatelliteFrequencyCalibrationEstimate, ...],
    calibration_source_spans: tuple[CalibrationSourceSpanV1, ...],
    calibration_site: ObserverSiteV1,
    calibration_site_authority_digest: Sha256Digest,
    calibration_protocol_digest: Sha256Digest,
    full_joint_state_digest: Sha256Digest,
    receiver_local_state_digest: Sha256Digest,
    produced_utc_ns: int,
    sealed_utc_ns: int,
) -> KnownPositionCalibrationReceiptV1:
    """Project a complete ``K<=1`` posterior into a safe correction receipt."""

    association = CatalogueAssociationResultV1.model_validate(association.model_dump(mode="json"))
    prediction_bank = CataloguePredictionBankV1.model_validate(
        prediction_bank.model_dump(mode="json")
    )
    calibration_site = ObserverSiteV1.model_validate(calibration_site.model_dump(mode="json"))
    spans = tuple(
        CalibrationSourceSpanV1.model_validate(item.model_dump(mode="json"))
        for item in calibration_source_spans
    )
    estimates = tuple(_revalidate_frequency_estimate(item) for item in frequency_estimates)

    _validate_association_bank_join(association, prediction_bank)
    if calibration_site.model_dump(mode="json") != prediction_bank.observer_site.model_dump(
        mode="json"
    ):
        raise SatelliteCorrectionInputError(
            "calibration receipt site must equal the prediction bank observer site"
        )
    if association.unreported_hypothesis_count != 0 or not math.isclose(
        association.unreported_posterior_mass,
        0.0,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise SatelliteCorrectionInputError(
            "correction projection requires every association hypothesis to be reported"
        )
    if any(len(mode.active_catalog_numbers) > 1 for mode in association.hypotheses):
        raise SatelliteCorrectionInputError(
            "V1 correction projection rejects coexisting K=2 satellite hypotheses"
        )
    if not spans:
        raise SatelliteCorrectionInputError("calibration requires at least one source span")
    if isinstance(produced_utc_ns, bool) or not isinstance(produced_utc_ns, int):
        raise SatelliteCorrectionInputError("produced_utc_ns must be an integer")
    if isinstance(sealed_utc_ns, bool) or not isinstance(sealed_utc_ns, int):
        raise SatelliteCorrectionInputError("sealed_utc_ns must be an integer")

    calibration_start_utc_ns = min(item.start_utc_ns for item in spans)
    calibration_end_utc_ns = max(item.end_utc_ns for item in spans)
    if produced_utc_ns < calibration_end_utc_ns or sealed_utc_ns < produced_utc_ns:
        raise SatelliteCorrectionInputError("correction production/seal chronology is invalid")
    support_start = min(item.support_start_utc_ns for item in prediction_bank.support.observations)
    support_end = max(item.support_end_utc_ns for item in prediction_bank.support.observations)
    if support_start < calibration_start_utc_ns or support_end > calibration_end_utc_ns:
        raise SatelliteCorrectionInputError(
            "prediction support must lie inside the declared calibration interval"
        )

    candidate_by_number = {item.catalog_number: item for item in prediction_bank.candidates}
    member_by_number = {item.catalog_number: item for item in prediction_bank.verified_tle_members}
    estimate_by_number = {item.catalog_number: item for item in estimates}
    if len(estimate_by_number) != len(estimates):
        raise SatelliteCorrectionInputError("frequency calibration repeats a catalogue number")

    presence_by_number = {
        item.catalog_number: item.posterior_probability
        for item in association.catalogue_presence_posterior
        if item.posterior_probability > 0.0
    }
    if set(estimate_by_number) != set(presence_by_number):
        raise SatelliteCorrectionInputError(
            "frequency calibrations must exactly cover positive catalogue posterior mass"
        )
    if not set(presence_by_number) <= set(candidate_by_number):
        raise SatelliteCorrectionInputError("association posterior names an unknown candidate")

    active_count_probability = {
        item.active_count: item.posterior_probability for item in association.active_count_posterior
    }
    if any(
        active_count > 1 and probability > _PROBABILITY_TOLERANCE
        for active_count, probability in active_count_probability.items()
    ):
        raise SatelliteCorrectionInputError("single-emitter correction received positive K=2 mass")
    unassigned_probability = active_count_probability.get(0, 0.0)
    if not math.isclose(
        unassigned_probability + math.fsum(presence_by_number.values()),
        1.0,
        rel_tol=0.0,
        abs_tol=_PROBABILITY_TOLERANCE,
    ):
        raise SatelliteCorrectionInputError(
            "K<=1 presence probabilities do not close with the null probability"
        )
    if len(presence_by_number) > 512:
        raise SatelliteCorrectionInputError("correction mode inventory exceeds V1 capacity")

    correction_modes: list[SatelliteCorrectionModeV1] = []
    ambiguous = len(presence_by_number) > 1
    for catalog_number in sorted(presence_by_number):
        estimate = estimate_by_number[catalog_number]
        candidate = candidate_by_number[catalog_number]
        member = member_by_number.get(catalog_number)
        if member is None:
            raise SatelliteCorrectionInputError("candidate lacks verified TLE membership")
        tau_mean, tau_variance, map_tau_boundary = _conditional_tau_moments(
            association,
            catalog_number=catalog_number,
            expected_presence_probability=presence_by_number[catalog_number],
        )
        if not -5.0 <= tau_mean <= 5.0:
            raise SatelliteCorrectionNumericalError("conditional tau mean left frozen support")
        boundary_hit = math.isclose(abs(tau_mean), 5.0, rel_tol=0.0, abs_tol=1e-12)
        reference_utc_ns = estimate.reference_utc_ns
        if not calibration_start_utc_ns <= reference_utc_ns <= calibration_end_utc_ns:
            raise SatelliteCorrectionInputError(
                "frequency/ephemeris reference must lie inside calibration"
            )
        ephemeris = EquivalentEpochCorrectionV1(
            reference_utc_ns=reference_utc_ns,
            offset_s=tau_mean,
            variance_s2=0.0 if boundary_hit else tau_variance,
            boundary_hit=boundary_hit,
        )
        frequency = SatelliteFrequencyStateV1(
            activity_epoch_id=estimate.activity_epoch_id,
            scope=estimate.scope,
            beam_channel_id=estimate.beam_channel_id,
            reference_utc_ns=reference_utc_ns,
            bias_hz=estimate.bias_hz,
            drift_hz_s=estimate.drift_hz_s,
            bias_variance_hz2=estimate.bias_variance_hz2,
            drift_variance_hz2_s2=estimate.drift_variance_hz2_s2,
            bias_drift_covariance_hz2_s=estimate.bias_drift_covariance_hz2_s,
        )
        navigation_eligible = (
            estimate.calibration_evidence_eligible
            and association.status is StandardScientificStatus.COMPLETE
            and not map_tau_boundary
            and not boundary_hit
            and abs(reference_utc_ns - candidate.element_epoch_utc_ns) / 1e9 <= 86_400.0
        )
        mode_values: dict[str, object] = {
            "catalog_number": catalog_number,
            "posterior_probability": presence_by_number[catalog_number],
            "evidence_class": (
                CorrectionEvidenceClass.AMBIGUITY_MEMBER
                if ambiguous
                else CorrectionEvidenceClass.CALIBRATED_CANDIDATE
            ),
            "selected_element_digest": member.selected_element_digest,
            "element_epoch_utc_ns": member.element_epoch_utc_ns,
            "element_age_s_at_reference": (
                abs(reference_utc_ns - member.element_epoch_utc_ns) / 1e9
            ),
            "ephemeris": ephemeris,
            "frequency": frequency,
            "valid_from_utc_ns": produced_utc_ns,
            "valid_until_utc_ns": produced_utc_ns + _VALIDITY_HORIZON_NS,
            "expiry_reason": CorrectionExpiryReason.FIXED_VALIDITY_HORIZON,
            "navigation_eligible": navigation_eligible,
        }
        correction_modes.append(_seal_mode(mode_values))

    modes = tuple(correction_modes)
    usable = any(item.navigation_eligible for item in modes)
    status = (
        StandardScientificStatus.COMPLETE
        if usable
        else StandardScientificStatus.PARTIAL
        if modes
        else StandardScientificStatus.INSUFFICIENT_DATA
    )
    reason = (
        SatelliteCorrectionReasonCode.TRANSFERABLE_MODES_AVAILABLE
        if usable
        else SatelliteCorrectionReasonCode.NO_NAVIGATION_ELIGIBLE_MODE
        if modes
        else SatelliteCorrectionReasonCode.INSUFFICIENT_CALIBRATION_EVIDENCE
    )
    product_values = {
        "calibration_protocol_digest": calibration_protocol_digest,
        "calibration_evidence_digest": association.graph_digest,
        "source_fingerprint_authority_digest": spans[0].source_fingerprint_authority_digest,
        "calibration_source_spans": tuple(
            sorted(
                spans,
                key=lambda item: (
                    item.source_recording_fingerprint,
                    item.source_stream_index,
                    item.source_sample_start,
                    item.source_sample_stop,
                ),
            )
        ),
        "calibration_start_utc_ns": calibration_start_utc_ns,
        "calibration_end_utc_ns": calibration_end_utc_ns,
        "produced_utc_ns": produced_utc_ns,
        "tle_snapshot": prediction_bank.tle_snapshot,
        "tle_membership_authority_digest": prediction_bank.tle_membership_authority_digest,
        "verified_tle_members": tuple(
            VerifiedTleMemberV1(
                catalog_number=mode.catalog_number,
                selected_element_digest=mode.selected_element_digest,
                element_epoch_utc_ns=mode.element_epoch_utc_ns,
            )
            for mode in modes
        ),
        "downlink_frequency_hz": prediction_bank.nominal_rf_hz,
        "association_hypothesis_digest": association.content_digest,
        "modes": modes,
        "unassigned_probability": unassigned_probability,
        "status": status,
        "reason_code": reason,
    }
    product = _seal_product(product_values)
    receipt_values = {
        "calibration_site": calibration_site,
        "calibration_site_authority_digest": calibration_site_authority_digest,
        "full_joint_state_digest": full_joint_state_digest,
        "receiver_local_state_digest": receiver_local_state_digest,
        "correction_product": product,
        "sealed_utc_ns": sealed_utc_ns,
    }
    return _seal_receipt(receipt_values)


def replay_known_position_correction(
    *,
    graph: PhysicalEpisodeGraphV1,
    prediction_bank: CataloguePredictionBankV1,
    correction_product: SatelliteCorrectionProductV1,
    target_component_offset_prior_sigma_hz: float,
) -> KnownPositionCorrectionReplayResult:
    """Score frozen correction modes on later known-position observations.

    The product's equivalent epoch offset is linearly interpolated within the
    target bank's frozen tau grid.  Its variance is propagated with the local
    finite-difference Doppler derivative.  A fresh proper constant offset is
    marginalized independently for each target continuity component.
    """

    graph = PhysicalEpisodeGraphV1.model_validate(graph.model_dump(mode="json"))
    prediction_bank = CataloguePredictionBankV1.model_validate(
        prediction_bank.model_dump(mode="json")
    )
    correction_product = SatelliteCorrectionProductV1.model_validate(
        correction_product.model_dump(mode="json")
    )
    if (
        not math.isfinite(target_component_offset_prior_sigma_hz)
        or target_component_offset_prior_sigma_hz <= 0.0
    ):
        raise SatelliteCorrectionInputError("target component-offset prior must be positive")
    support = prediction_bank.support
    if support.content_digest != support.from_graph(graph).content_digest:
        raise SatelliteCorrectionInputError("prediction bank does not cover the replay graph")
    if prediction_bank.tle_snapshot.digest != correction_product.tle_snapshot.digest:
        raise SatelliteCorrectionInputError("replay must use the correction product's TLE snapshot")
    if prediction_bank.tle_membership_authority_digest != (
        correction_product.tle_membership_authority_digest
    ):
        raise SatelliteCorrectionInputError("replay TLE membership authority changed")
    if not math.isclose(
        prediction_bank.nominal_rf_hz,
        correction_product.downlink_frequency_hz,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise SatelliteCorrectionInputError("replay RF does not match the correction product")
    target_start = min(item.support_start_utc_ns for item in graph.observations)
    target_end = max(item.support_end_utc_ns for item in graph.observations)
    if target_start < correction_product.produced_utc_ns:
        raise SatelliteCorrectionInputError("replay observations predate correction production")

    candidate_by_number = {item.catalog_number: item for item in prediction_bank.candidates}
    observation_by_id = {item.observation_id: item for item in graph.observations}
    component_by_observation = {
        observation_id: episode.continuity_component_id
        for episode in graph.episodes
        for observation_id in episode.observation_ids
    }
    scores: list[CorrectionReplayModeScore] = []
    for mode in correction_product.modes:
        if not mode.navigation_eligible:
            continue
        if mode.valid_from_utc_ns > target_start or mode.valid_until_utc_ns < target_end:
            raise SatelliteCorrectionInputError("replay observations exceed correction validity")
        candidate = candidate_by_number.get(mode.catalog_number)
        if candidate is None:
            raise SatelliteCorrectionInputError("replay bank omits a correction catalogue mode")
        if (
            candidate.selected_element_digest != mode.selected_element_digest
            or candidate.element_epoch_utc_ns != mode.element_epoch_utc_ns
        ):
            raise SatelliteCorrectionInputError("replay candidate element changed")
        predicted_by_observation = _interpolated_corrected_predictions(candidate, mode)
        if set(predicted_by_observation) != set(observation_by_id):
            raise SatelliteCorrectionInputError(
                "replay candidate must predict the complete target observation inventory"
            )
        residuals_by_component: dict[str, list[tuple[float, float]]] = {}
        raw_residuals: list[float] = []
        for observation_id in sorted(observation_by_id):
            observation = observation_by_id[observation_id]
            predicted, prediction_variance = predicted_by_observation[observation_id]
            dt_s = (observation.support_center_utc_ns - mode.frequency.reference_utc_ns) / 1e9
            frequency_mean = mode.frequency.bias_hz + mode.frequency.drift_hz_s * dt_s
            frequency_variance = (
                mode.frequency.bias_variance_hz2
                + dt_s * dt_s * mode.frequency.drift_variance_hz2_s2
                + 2.0 * dt_s * mode.frequency.bias_drift_covariance_hz2_s
            )
            frequency_variance = _nonnegative_roundoff(
                frequency_variance,
                label="propagated satellite-frequency variance",
            )
            variance = (
                observation.standard_uncertainty_hz**2 + prediction_variance + frequency_variance
            )
            if not math.isfinite(variance) or variance <= 0.0:
                raise SatelliteCorrectionNumericalError(
                    "replay observation variance is not positive and finite"
                )
            residual = observation.measured_cfo_hz - predicted - frequency_mean
            if not math.isfinite(residual):
                raise SatelliteCorrectionNumericalError("replay residual is not finite")
            component_id = component_by_observation[observation_id]
            residuals_by_component.setdefault(component_id, []).append((residual, variance))
            raw_residuals.append(residual)

        component_estimates: list[ReplayComponentOffsetEstimate] = []
        negative_log_density = 0.0
        fitted_residual_squares: list[float] = []
        fitted_standardized_squares: list[float] = []
        for component_id in sorted(residuals_by_component):
            component_nll, mean_hz, variance_hz2 = _marginal_component_offset(
                residuals_by_component[component_id],
                prior_sigma_hz=target_component_offset_prior_sigma_hz,
            )
            negative_log_density = _checked_add(
                negative_log_density,
                component_nll,
                label="replay component evidence",
            )
            component_estimates.append(
                ReplayComponentOffsetEstimate(
                    continuity_component_id=component_id,
                    mean_hz=mean_hz,
                    standard_uncertainty_hz=math.sqrt(variance_hz2),
                )
            )
            fitted_residual_squares.extend(
                (residual - mean_hz) ** 2
                for residual, _variance in residuals_by_component[component_id]
            )
            fitted_standardized_squares.extend(
                (residual - mean_hz) ** 2 / variance
                for residual, variance in residuals_by_component[component_id]
            )
        count = len(raw_residuals)
        scores.append(
            CorrectionReplayModeScore(
                catalog_number=mode.catalog_number,
                correction_mode_digest=mode.mode_digest,
                observation_count=count,
                root_mean_square_residual_hz=math.sqrt(math.fsum(fitted_residual_squares) / count),
                standardized_root_mean_square=math.sqrt(
                    math.fsum(fitted_standardized_squares) / count
                ),
                negative_log_predictive_density=negative_log_density,
                target_component_offsets=tuple(component_estimates),
            )
        )
    if not scores:
        raise SatelliteCorrectionInputError("correction product has no replayable eligible modes")
    return KnownPositionCorrectionReplayResult(
        correction_product_digest=correction_product.content_digest,
        graph_digest=graph.content_digest,
        prediction_bank_digest=prediction_bank.content_digest,
        target_component_offset_prior_sigma_hz=target_component_offset_prior_sigma_hz,
        mode_scores=tuple(sorted(scores, key=lambda item: item.catalog_number)),
        null_model_scored=False,
        conditioned_on_assigned_correction_mode=True,
        receiver_local_state_exportable=False,
        identity_claimed=False,
        navigation_fix_claimed=False,
    )


def _revalidate_frequency_estimate(
    estimate: SatelliteFrequencyCalibrationEstimate,
) -> SatelliteFrequencyCalibrationEstimate:
    return SatelliteFrequencyCalibrationEstimate(
        catalog_number=estimate.catalog_number,
        activity_epoch_id=estimate.activity_epoch_id,
        scope=estimate.scope,
        beam_channel_id=estimate.beam_channel_id,
        reference_utc_ns=estimate.reference_utc_ns,
        bias_hz=estimate.bias_hz,
        drift_hz_s=estimate.drift_hz_s,
        bias_variance_hz2=estimate.bias_variance_hz2,
        drift_variance_hz2_s2=estimate.drift_variance_hz2_s2,
        bias_drift_covariance_hz2_s=estimate.bias_drift_covariance_hz2_s,
        calibration_evidence_eligible=estimate.calibration_evidence_eligible,
    )


def _validate_association_bank_join(
    association: CatalogueAssociationResultV1,
    bank: CataloguePredictionBankV1,
) -> None:
    if (
        association.prediction_bank_digest != bank.content_digest
        or association.candidate_universe_digest != bank.candidate_universe_digest
        or association.selection_protocol_digest != bank.selection_protocol_digest
        or association.tle_membership_authority_digest != bank.tle_membership_authority_digest
        or association.tau_search_policy != bank.tau_search_policy
    ):
        raise SatelliteCorrectionInputError("association and prediction bank do not bind exactly")
    if bank.truncated_candidate_count != 0:
        raise SatelliteCorrectionInputError("correction projection rejects a truncated catalogue")


def _conditional_tau_moments(
    association: CatalogueAssociationResultV1,
    *,
    catalog_number: int,
    expected_presence_probability: float,
) -> tuple[float, float, bool]:
    weighted: list[tuple[float, float, bool]] = []
    for mode in association.hypotheses:
        if catalog_number not in mode.active_catalog_numbers:
            continue
        tau_choice = next(
            item.tau_s for item in mode.tau_choices if item.catalog_number == catalog_number
        )
        weighted.append((mode.posterior_probability, tau_choice, mode.tau_boundary_hit))
    mass = math.fsum(item[0] for item in weighted)
    if not math.isclose(
        mass,
        expected_presence_probability,
        rel_tol=0.0,
        abs_tol=_PROBABILITY_TOLERANCE,
    ):
        raise SatelliteCorrectionInputError("catalogue presence does not match reported modes")
    if mass <= 0.0:
        raise SatelliteCorrectionInputError("cannot condition tau on zero catalogue mass")
    mean = math.fsum(probability * tau for probability, tau, _ in weighted) / mass
    variance = math.fsum(probability * (tau - mean) ** 2 for probability, tau, _ in weighted) / mass
    variance = _nonnegative_roundoff(variance, label="conditional tau variance")
    maximum_probability = max(probability for probability, _tau, _boundary in weighted)
    tie_tolerance = 8.0 * math.ulp(max(1.0, maximum_probability))
    map_boundary = any(
        is_boundary and maximum_probability - probability <= tie_tolerance
        for probability, _tau, is_boundary in weighted
    )
    return mean, variance, map_boundary


def _interpolated_corrected_predictions(
    candidate: CatalogueCandidatePredictionV1,
    mode: SatelliteCorrectionModeV1,
) -> dict[str, tuple[float, float]]:
    states = candidate.tau_states
    tau_values = tuple(item.tau_s for item in states)
    target_tau = mode.ephemeris.offset_s
    if target_tau < tau_values[0] - _TAU_TOLERANCE_S or target_tau > (
        tau_values[-1] + _TAU_TOLERANCE_S
    ):
        raise SatelliteCorrectionInputError("correction tau lies outside replay bank support")
    if len(states) == 1:
        if not math.isclose(target_tau, states[0].tau_s, rel_tol=0.0, abs_tol=_TAU_TOLERANCE_S):
            raise SatelliteCorrectionInputError("fixed-tau replay bank does not contain correction")
        if mode.ephemeris.variance_s2 != 0.0:
            raise SatelliteCorrectionInputError(
                "a one-state tau bank cannot propagate nonzero correction uncertainty"
            )
        return {
            item.observation_id: (item.predicted_cfo_hz, item.standard_uncertainty_hz**2)
            for item in states[0].predictions
        }

    right_index = bisect.bisect_left(tau_values, target_tau)
    exact_index = next(
        (
            index
            for index, tau_s in enumerate(tau_values)
            if math.isclose(target_tau, tau_s, rel_tol=0.0, abs_tol=_TAU_TOLERANCE_S)
        ),
        None,
    )
    if right_index == 0:
        left_index, right_index = 0, 1
    elif right_index == len(states):
        left_index, right_index = len(states) - 2, len(states) - 1
    else:
        left_index = right_index - 1
    left = states[left_index]
    right = states[right_index]
    width = right.tau_s - left.tau_s
    if not math.isfinite(width) or width <= 0.0:
        raise SatelliteCorrectionNumericalError("replay tau interpolation width is invalid")
    fraction = (target_tau - left.tau_s) / width
    left_predictions = {item.observation_id: item for item in left.predictions}
    right_predictions = {item.observation_id: item for item in right.predictions}
    if set(left_predictions) != set(right_predictions):
        raise SatelliteCorrectionInputError("replay tau states have different observations")
    result: dict[str, tuple[float, float]] = {}
    for observation_id in left_predictions:
        left_prediction = left_predictions[observation_id]
        right_prediction = right_predictions[observation_id]
        difference = right_prediction.predicted_cfo_hz - left_prediction.predicted_cfo_hz
        slope_hz_s = difference / width
        if exact_index is not None and 0 < exact_index < len(states) - 1:
            lower_prediction = {
                item.observation_id: item for item in states[exact_index - 1].predictions
            }[observation_id]
            upper_prediction = {
                item.observation_id: item for item in states[exact_index + 1].predictions
            }[observation_id]
            central_width = states[exact_index + 1].tau_s - states[exact_index - 1].tau_s
            slope_hz_s = (
                upper_prediction.predicted_cfo_hz - lower_prediction.predicted_cfo_hz
            ) / central_width
        predicted = left_prediction.predicted_cfo_hz + fraction * difference
        base_variance = (
            (1.0 - fraction) * left_prediction.standard_uncertainty_hz** 2
            + fraction * right_prediction.standard_uncertainty_hz** 2
        )
        variance = base_variance + slope_hz_s**2 * mode.ephemeris.variance_s2
        if not math.isfinite(predicted) or not math.isfinite(variance) or variance < 0.0:
            raise SatelliteCorrectionNumericalError("interpolated replay prediction is invalid")
        result[observation_id] = (predicted, variance)
    return result


def _marginal_component_offset(
    residual_variances: list[tuple[float, float]],
    *,
    prior_sigma_hz: float,
) -> tuple[float, float, float]:
    prior_variance = prior_sigma_hz * prior_sigma_hz
    if not math.isfinite(prior_variance) or prior_variance <= 0.0:
        raise SatelliteCorrectionNumericalError("component-offset prior variance overflowed")
    precisions = tuple(1.0 / variance for _residual, variance in residual_variances)
    total_precision = math.fsum(precisions)
    scaled = prior_variance * total_precision
    posterior_variance = (
        prior_variance / (1.0 + scaled) if math.isfinite(scaled) else 1.0 / total_precision
    )
    weighted_residual = math.fsum(residual / variance for residual, variance in residual_variances)
    posterior_mean = posterior_variance * weighted_residual
    if not all(math.isfinite(item) for item in (posterior_variance, posterior_mean)):
        raise SatelliteCorrectionNumericalError("component-offset posterior is not finite")
    quadratic = (
        math.fsum(
            (residual - posterior_mean) ** 2 / variance for residual, variance in residual_variances
        )
        + posterior_mean * posterior_mean / prior_variance
    )
    log_determinant = math.fsum(math.log(variance) for _residual, variance in residual_variances)
    log_determinant += (
        math.log1p(scaled)
        if math.isfinite(scaled)
        else math.log(prior_variance) + math.log(total_precision)
    )
    nll = 0.5 * (quadratic + log_determinant + len(residual_variances) * math.log(2.0 * math.pi))
    if not math.isfinite(nll):
        raise SatelliteCorrectionNumericalError("component-offset evidence is not finite")
    return nll, posterior_mean, posterior_variance


def _nonnegative_roundoff(value: float, *, label: str) -> float:
    if not math.isfinite(value):
        raise SatelliteCorrectionNumericalError(f"{label} is not finite")
    if value >= 0.0:
        return value
    if value >= -1e-12:
        return 0.0
    raise SatelliteCorrectionNumericalError(f"{label} is negative")


def _checked_add(left: float, right: float, *, label: str) -> float:
    result = left + right
    if not math.isfinite(result):
        raise SatelliteCorrectionNumericalError(f"{label} is not finite")
    if right != 0.0 and result == left:
        raise SatelliteCorrectionNumericalError(f"{label} increment is not representable")
    return result


def _seal_mode(values: Mapping[str, object]) -> SatelliteCorrectionModeV1:
    draft_values: dict[str, Any] = {
        **values,
        "mode_digest": canonical_digest({"draft": "satellite-correction-mode"}),
    }
    draft = SatelliteCorrectionModeV1.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"mode_digest"}, warnings=False)
    return SatelliteCorrectionModeV1.model_validate(
        {**payload, "mode_digest": canonical_digest(payload)}
    )


def _seal_product(values: Mapping[str, object]) -> SatelliteCorrectionProductV1:
    draft_values: dict[str, Any] = {
        **values,
        "content_digest": canonical_digest({"draft": "satellite-correction-product"}),
    }
    draft = SatelliteCorrectionProductV1.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"content_digest"}, warnings=False)
    return SatelliteCorrectionProductV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )


def _seal_receipt(values: Mapping[str, object]) -> KnownPositionCalibrationReceiptV1:
    draft_values: dict[str, Any] = {
        **values,
        "receipt_digest": canonical_digest({"draft": "known-position-calibration-receipt"}),
    }
    draft = KnownPositionCalibrationReceiptV1.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"receipt_digest"}, warnings=False)
    return KnownPositionCalibrationReceiptV1.model_validate(
        {**payload, "receipt_digest": canonical_digest(payload)}
    )
