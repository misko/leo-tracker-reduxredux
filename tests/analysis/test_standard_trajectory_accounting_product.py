from __future__ import annotations

from leo.analysis.standard.codecs import decode_standard_product
from leo.analysis.standard.products import (
    TRAJECTORY_CONDITIONED_ACCOUNTING_PRODUCT,
    TRAJECTORY_CONDITIONED_ACCOUNTING_V1_PRODUCT,
)
from leo.analysis.standard.trajectory_accounting import (
    build_trajectory_conditioned_accounting_v1,
    build_trajectory_conditioned_accounting_v2,
    render_trajectory_conditioned_accounting_png,
    render_trajectory_conditioned_accounting_v2_png,
)
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodCandidate,
    PilotMethodScore,
    PilotProbeDetection,
)
from leo.analysis.starlink.trajectories import PolynomialTrajectory
from leo.contracts.digests import canonical_digest
from leo.contracts.trajectory_accounting import (
    TrajectoryAccountingConfigV1,
    TrajectoryAccountingConfigV2,
)


def _score(cfo_hz: float, margin: float) -> PilotMethodScore:
    return PilotMethodScore(PilotMethod.GLRT64, margin + 0.04, 0.04, margin, 0.0, cfo_hz)


def _candidate(rank: int, cfo_hz: float, margin: float) -> PilotMethodCandidate:
    return PilotMethodCandidate(rank, rank, cfo_hz, (_score(cfo_hz, margin),), None, None)


def _trajectory(label: str, cfo_hz: float) -> PolynomialTrajectory:
    trajectory_id = canonical_digest({"trajectory": label})
    return PolynomialTrajectory(
        trajectory_id,
        PilotMethod.GLRT64,
        1,
        0.0,
        (0.0, cfo_hz),
        0.0,
        1.0,
        (canonical_digest({"point": label, "number": 1}),),
        1,
        0.0,
        0.0,
        0.0,
        0,
    )


def test_accounting_product_is_strict_deterministic_and_preserves_overlap() -> None:
    primary = _trajectory("primary", -240_000.0)
    secondary = _trajectory("secondary", -130_000.0)
    detection = PilotProbeDetection(
        NumericalStatus.COMPLETE,
        0,
        0.0,
        0,
        -240_000.0,
        (_score(-240_000.0, 0.40),),
        None,
        None,
        "fixture",
        source_candidate_count=2,
        candidates=(
            _candidate(0, -240_000.0, 0.40),
            _candidate(1, -130_000.0, 0.30),
        ),
    )
    replay = (
        {
            "trajectory_id": primary.trajectory_id,
            "sample_start": 0,
            "time_s": 0.0,
            "detector_method": "glrt64",
            "corrected_margin": 0.41,
        },
        {
            "trajectory_id": secondary.trajectory_id,
            "sample_start": 0,
            "time_s": 0.0,
            "detector_method": "glrt64",
            "corrected_margin": 0.32,
        },
    )
    digest = canonical_digest({"fixture": "trajectory-accounting"})
    product = build_trajectory_conditioned_accounting_v1(
        (detection,),
        (("family-primary", primary), ("family-secondary", secondary)),
        replay,
        frequency_offsets_hz={primary.trajectory_id: 0.0, secondary.trajectory_id: 0.0},
        pilot_scan_digest=digest,
        trajectory_bank_digest=digest,
        trajectory_feedback_digest=digest,
        config=TrajectoryAccountingConfigV1(),
    )

    assert product.evaluation_count == 2
    assert product.associated_evaluation_count == 2
    assert {item.baseline_candidate_rank for item in product.evaluations} == {0, 1}
    assert product.associated_transitions.positive_to_positive == 2
    assert product.unique_probe_transitions.positive_to_positive == 1
    document = product.model_dump(mode="json")
    assert (
        decode_standard_product(TRAJECTORY_CONDITIONED_ACCOUNTING_V1_PRODUCT, document) == document
    )

    first = render_trajectory_conditioned_accounting_png(
        (("stream-0 · radio-0 · RX1", document),), session_id="cap-fixture"
    )
    second = render_trajectory_conditioned_accounting_png(
        (("stream-0 · radio-0 · RX1", document),), session_id="cap-fixture"
    )
    assert first.startswith(b"\x89PNG\r\n\x1a\n")
    assert first == second


def test_v2_compares_independent_winner_with_transported_epoch() -> None:
    primary = _trajectory("primary-v2", -240_000.0)
    secondary = _trajectory("secondary-v2", -130_000.0)
    detection = PilotProbeDetection(
        NumericalStatus.COMPLETE,
        0,
        0.0,
        0,
        -240_000.0,
        (_score(-240_000.0, 0.40),),
        None,
        None,
        "fixture",
        source_candidate_count=2,
        candidates=(
            _candidate(0, -240_000.0, 0.40),
            _candidate(1, -130_000.0, 0.30),
        ),
    )
    replay = tuple(
        {
            "trajectory_id": trajectory.trajectory_id,
            "sample_start": 0,
            "time_s": 0.0,
            "detector_method": "glrt64",
            "corrected_margin": reacquired,
            "corrected_residual_cfo_hz": 50_000.0,
            "conditioned_corrected_margin": conditioned,
            "conditioned_tracking_cfo_hz": 50.0,
            "conditioned_epoch_sample": rank,
            "conditioned_seed_cfo_hz": 0.0,
        }
        for trajectory, rank, reacquired, conditioned in (
            (primary, 0, 0.01, 0.41),
            (secondary, 1, 0.02, 0.32),
        )
    )
    digest = canonical_digest({"fixture": "trajectory-accounting-v2"})
    product = build_trajectory_conditioned_accounting_v2(
        (detection,),
        (("family-primary", primary), ("family-secondary", secondary)),
        replay,
        frequency_offsets_hz={primary.trajectory_id: 0.0, secondary.trajectory_id: 0.0},
        pilot_scan_digest=digest,
        trajectory_bank_digest=digest,
        trajectory_feedback_digest=digest,
        config=TrajectoryAccountingConfigV2(),
    )

    assert product.reacquired_associated_transitions.positive_to_negative == 2
    assert product.conditioned_associated_transitions.positive_to_positive == 2
    assert product.reacquired_unique_probe_transitions.positive_to_negative == 1
    assert product.conditioned_unique_probe_transitions.positive_to_positive == 1
    assert {item.baseline_candidate_epoch_sample for item in product.evaluations} == {0, 1}
    document = product.model_dump(mode="json")
    assert decode_standard_product(TRAJECTORY_CONDITIONED_ACCOUNTING_PRODUCT, document) == document
    first = render_trajectory_conditioned_accounting_v2_png(
        (("stream-0 · radio-0 · RX1", document),), session_id="cap-fixture-v2"
    )
    second = render_trajectory_conditioned_accounting_v2_png(
        (("stream-0 · radio-0 · RX1", document),), session_id="cap-fixture-v2"
    )
    assert first.startswith(b"\x89PNG\r\n\x1a\n")
    assert first == second
