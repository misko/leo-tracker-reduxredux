from __future__ import annotations

import ast
import inspect
import math
from dataclasses import replace
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from leo.analysis import blinded_doppler_position as base_solver_module
from leo.analysis import blinded_doppler_position_particles as particle_solver_module
from leo.analysis.blinded_doppler_position import (
    BlindedDopplerPositionEvidence,
    BlindedDopplerPositionInputError,
    FrozenDopplerPositionHypothesis,
)
from leo.analysis.blinded_doppler_position_particles import (
    BlindedDopplerParticleConfig,
    solve_blinded_geodetic_particle_doppler_position,
)
from leo.analysis.blinded_position_evaluation import evaluate_blinded_position_reveal
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import (
    BlindedPositionRevealReceiptV1,
    BoundedGeodeticPriorV1,
    NavigationLane,
)
from leo.contracts.satellite_pnt_particles import (
    GeodeticPositionParticleV1,
    ResponseFreeGeodeticParticleBankV1,
)
from leo.contracts.sky import ObserverSiteV1
from leo.contracts.standard_pipeline import StandardScientificStatus
from tests.analysis.test_blinded_doppler_position import (
    _TARGET_END,
    _TARGET_START,
    _TRUTH_ECEF_M,
    _challenge,
    _digest,
    _oracle_evidence,
    _product,
    _seal,
)
from tests.analysis.test_blinded_position_evaluation import _truth


def _broad_prior() -> BoundedGeodeticPriorV1:
    return BoundedGeodeticPriorV1(
        prior_provenance_digest=_digest("continental-position-prior"),
        latitude_lower_deg=30.0,
        latitude_upper_deg=45.0,
        longitude_lower_deg=-130.0,
        longitude_upper_deg=-110.0,
        altitude_lower_m=-100.0,
        altitude_upper_m=1_000.0,
    )


def _particle_bank(
    prior: BoundedGeodeticPriorV1,
    *,
    produced_utc_ns: int = _TARGET_START - 1,
    generation_protocol_digest: str | None = None,
) -> ResponseFreeGeodeticParticleBankV1:
    coordinates = (
        (37.0, -122.0, 10.0),
        (37.002, -122.0, 10.0),
        (36.998, -122.0, 10.0),
        (37.0, -121.998, 10.0),
        (37.0, -122.002, 10.0),
    )
    covariance = (
        (2_500.0, 0.0, 0.0),
        (0.0, 2_500.0, 0.0),
        (0.0, 0.0, 2_500.0),
    )
    particles = tuple(
        sorted(
            (
                GeodeticPositionParticleV1(
                    particle_id=_digest(f"particle-{index}"),
                    position=ObserverSiteV1(
                        latitude_deg=latitude,
                        longitude_deg=longitude,
                        altitude_m=altitude,
                        label=f"response-free-particle-{index}",
                    ),
                    prior_probability=1.0 / len(coordinates),
                    local_covariance_ecef_m2=covariance,
                )
                for index, (latitude, longitude, altitude) in enumerate(coordinates)
            ),
            key=lambda item: item.particle_id,
        )
    )
    return _seal(
        ResponseFreeGeodeticParticleBankV1,
        {
            "prior_provenance_digest": prior.prior_provenance_digest,
            "generation_protocol_digest": (
                _digest("particle-generation-protocol")
                if generation_protocol_digest is None
                else generation_protocol_digest
            ),
            "produced_utc_ns": produced_utc_ns,
            "particles": particles,
        },
    )


def _solve() -> tuple[Any, Any, Any, Any]:
    prior = _broad_prior()
    product = _product()
    challenge = _challenge(product, observation_count=16, oracle=True, prior=prior)
    evidence = _oracle_evidence(challenge)
    bank = _particle_bank(prior)
    estimate = solve_blinded_geodetic_particle_doppler_position(
        challenge=challenge,
        evidence=evidence,
        particle_bank=bank,
        config=BlindedDopplerParticleConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )
    return challenge, evidence, bank, estimate


def test_broad_prior_particle_lane_ranks_truth_without_truth_port() -> None:
    _challenge_value, _evidence, bank, estimate = _solve()

    assert estimate.status is StandardScientificStatus.PARTIAL
    assert estimate.lane is NavigationLane.ORACLE_IDENTITY_FROZEN_CORRECTION
    assert estimate.truth_accessed is False
    assert estimate.truth_metrics_included is False
    assert estimate.source_mode_count == len(bank.particles)
    assert estimate.returned_mode_count + estimate.truncated_mode_count == len(bank.particles)
    error_m = math.dist(estimate.modes[0].mean_ecef_m, _TRUTH_ECEF_M)
    assert error_m < 0.01
    assert estimate.modes[0].receiver_clock is not None


def test_particle_gaussian_marginal_matches_dense_covariance_oracle() -> None:
    prior = _broad_prior()
    product = _product()
    challenge = _challenge(product, observation_count=16, oracle=True, prior=prior)
    evidence = _oracle_evidence(challenge)
    hypothesis = evidence.hypotheses[0]
    correction_by_digest = {item.mode_digest: item for item in product.modes}
    noise = base_solver_module._build_observation_noise_model(
        hypothesis=hypothesis,
        correction_by_digest=correction_by_digest,
        maximum_condition=1e14,
    )
    bank = _particle_bank(prior)
    particle = next(
        item
        for item in bank.particles
        if item.position.latitude_deg == 37.0 and item.position.longitude_deg == -122.0
    )
    receiver_sigma_hz = 1_000.0
    score = particle_solver_module._score_particle(
        particle_id=particle.particle_id,
        mean_ecef_m=_TRUTH_ECEF_M,
        covariance_ecef_m2=particle.local_covariance_ecef_m2,
        prior_probability=particle.prior_probability,
        hypothesis=hypothesis,
        correction_by_digest=correction_by_digest,
        downlink_frequency_hz=product.downlink_frequency_hz,
        observed=np.asarray(
            [item.measured_cfo_hz for item in hypothesis.observations], dtype=np.float64
        ),
        precision=noise.precision,
        log_determinant=noise.log_determinant,
        receiver_variance_hz2=receiver_sigma_hz**2,
    )
    predictions = np.asarray(
        [
            base_solver_module._predict_and_jacobian(
                receiver_ecef_m=np.asarray(_TRUTH_ECEF_M),
                receiver_frequency_bias_hz=0.0,
                observation=observation,
                correction=correction_by_digest[observation.correction_mode_digest],
                downlink_frequency_hz=product.downlink_frequency_hz,
            )[0]
            for observation in hypothesis.observations
        ]
    )
    residual = np.asarray([item.measured_cfo_hz for item in hypothesis.observations]) - predictions
    covariance = np.linalg.inv(noise.precision) + receiver_sigma_hz**2 * np.ones(
        (len(residual), len(residual))
    )
    sign, log_determinant = np.linalg.slogdet(covariance)
    assert sign > 0.0
    dense_negative_log_joint = 0.5 * (
        float(residual @ np.linalg.solve(covariance, residual))
        + float(log_determinant)
        + len(residual) * math.log(2.0 * math.pi)
    ) - math.log(particle.prior_probability)

    assert score.negative_log_joint == pytest.approx(dense_negative_log_joint, rel=2e-8, abs=2e-7)


def test_particle_estimate_can_only_be_evaluated_after_reveal() -> None:
    truth = _truth(16)
    prior = _broad_prior()
    product = _product()
    challenge = _challenge(
        product,
        observation_count=16,
        oracle=True,
        prior=prior,
        truth_commitment_digest=truth.content_digest,
    )
    estimate = solve_blinded_geodetic_particle_doppler_position(
        challenge=challenge,
        evidence=_oracle_evidence(challenge),
        particle_bank=_particle_bank(prior),
        config=BlindedDopplerParticleConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )
    receipt = _seal(
        BlindedPositionRevealReceiptV1,
        {
            "challenge": challenge,
            "estimate": estimate,
            "truth": truth,
            "revealed_utc_ns": _TARGET_END + 3,
        },
        "receipt_digest",
    )

    evaluation = evaluate_blinded_position_reveal(receipt)

    assert evaluation.reported_mode.three_dimensional_error_m < 0.01
    assert evaluation.estimate_content_digest == estimate.content_digest


def test_particle_bank_must_precede_target_and_match_prior() -> None:
    prior = _broad_prior()
    product = _product()
    challenge = _challenge(product, observation_count=16, oracle=True, prior=prior)
    evidence = _oracle_evidence(challenge)

    with pytest.raises(BlindedDopplerPositionInputError, match="before target response"):
        solve_blinded_geodetic_particle_doppler_position(
            challenge=challenge,
            evidence=evidence,
            particle_bank=_particle_bank(prior, produced_utc_ns=_TARGET_START),
            config=BlindedDopplerParticleConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )

    wrong_prior = _broad_prior().model_copy(
        update={"prior_provenance_digest": _digest("other-prior")}
    )
    wrong_bank = _particle_bank(wrong_prior)
    with pytest.raises(BlindedDopplerPositionInputError, match="another position prior"):
        solve_blinded_geodetic_particle_doppler_position(
            challenge=challenge,
            evidence=evidence,
            particle_bank=wrong_bank,
            config=BlindedDopplerParticleConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )


def test_particle_bank_is_revalidated_before_scoring() -> None:
    prior = _broad_prior()
    product = _product()
    challenge = _challenge(product, observation_count=16, oracle=True, prior=prior)
    bank = _particle_bank(prior)
    poisoned = bank.model_copy(update={"content_digest": _digest("stale-particle-bank")})

    with pytest.raises(ValidationError, match="digest"):
        solve_blinded_geodetic_particle_doppler_position(
            challenge=challenge,
            evidence=_oracle_evidence(challenge),
            particle_bank=poisoned,
            config=BlindedDopplerParticleConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )


def test_target_response_changes_scores_but_not_frozen_particle_bank() -> None:
    challenge, evidence, bank, estimate = _solve()
    hypothesis = evidence.hypotheses[0]
    first = hypothesis.observations[0]
    mutated_rows = (
        replace(first, measured_cfo_hz=first.measured_cfo_hz + 5.0),
        *hypothesis.observations[1:],
    )
    mutated = BlindedDopplerPositionEvidence(
        challenge_content_digest=challenge.content_digest,
        state_provider_digest=evidence.state_provider_digest,
        hypotheses=(
            FrozenDopplerPositionHypothesis(
                correction_mode_digests=hypothesis.correction_mode_digests,
                observations=tuple(
                    sorted(
                        mutated_rows,
                        key=lambda item: (
                            item.observation_product_digest,
                            item.observation_id,
                        ),
                    )
                ),
            ),
        ),
    )

    changed = solve_blinded_geodetic_particle_doppler_position(
        challenge=challenge,
        evidence=mutated,
        particle_bank=bank,
        config=BlindedDopplerParticleConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )

    assert bank == ResponseFreeGeodeticParticleBankV1.model_validate(bank.model_dump(mode="json"))
    assert changed.solver_execution_digest != estimate.solver_execution_digest


def test_particle_work_bound_fails_before_scoring() -> None:
    challenge, evidence, bank, _estimate = _solve()

    with pytest.raises(BlindedDopplerPositionInputError, match="work bound"):
        solve_blinded_geodetic_particle_doppler_position(
            challenge=challenge,
            evidence=evidence,
            particle_bank=bank,
            config=BlindedDopplerParticleConfig(maximum_particles=2),
            sealed_utc_ns=_TARGET_END + 2,
        )


def test_particle_solver_has_no_truth_or_reveal_import() -> None:
    tree = ast.parse(inspect.getsource(particle_solver_module))
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert "BlindedPositionTruthV1" not in imported_names
    assert "BlindedPositionRevealReceiptV1" not in imported_names


def test_particle_generation_digest_cannot_alias_response_evidence() -> None:
    prior = _broad_prior()
    product = _product()
    challenge = _challenge(product, observation_count=16, oracle=True, prior=prior)

    with pytest.raises(BlindedDopplerPositionInputError, match="response-isolated"):
        solve_blinded_geodetic_particle_doppler_position(
            challenge=challenge,
            evidence=_oracle_evidence(challenge),
            particle_bank=_particle_bank(
                prior,
                generation_protocol_digest=challenge.target_evidence_digest,
            ),
            config=BlindedDopplerParticleConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )


def test_particle_contract_rejects_probability_and_covariance_poison() -> None:
    prior = _broad_prior()
    bank = _particle_bank(prior)
    particle = bank.particles[0]
    payload = particle.model_dump(mode="json")
    payload["local_covariance_ecef_m2"] = (
        (1.0, 2.0, 0.0),
        (2.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )

    with pytest.raises(ValidationError):
        GeodeticPositionParticleV1.model_validate(payload)

    bank_payload = bank.model_dump(mode="json", exclude={"content_digest"})
    bank_payload["particles"][0]["prior_probability"] = 0.5
    with pytest.raises(ValidationError, match="sum to one"):
        ResponseFreeGeodeticParticleBankV1.model_validate(
            {**bank_payload, "content_digest": canonical_digest(bank_payload)}
        )


@pytest.mark.parametrize("sigma", [1e-200, 1e200])
def test_particle_prior_variance_must_be_representable(sigma: float) -> None:
    with pytest.raises(BlindedDopplerPositionInputError, match="representable"):
        BlindedDopplerParticleConfig(receiver_frequency_bias_prior_sigma_hz=sigma)
