from __future__ import annotations

import math
from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

import leo.analysis.starlink.seeded_acquisition as seeded
from leo.analysis.starlink.acquisition import (
    DEFAULT_ACQUIRE_SYMBOLS,
    DEFAULT_ANCHOR_SYMBOLS,
    DEFAULT_VERIFY_SYMBOLS,
    NumericalStatus,
)
from leo.analysis.starlink.seeded_acquisition import (
    CFO_ALIAS_SPACING_HZ,
    KnownPilotModeSeed,
    PilotModeProposalOrigin,
    ResearchDisposition,
    ResearchEvidenceDecision,
    SeededPilotAcquisitionConfig,
    TemplateEvidenceRole,
    acquire_seeded_known_pilot_modes,
    canonicalize_cfo_alias,
)
from leo.analysis.starlink.templates import (
    FRAME_RATE_HZ,
    qin_edge_pilot_frame,
    template_sha256,
)
from leo.contracts.states import StarlinkEdge

RATE = 250_000.0
WINDOW_SAMPLES = round(0.075 * RATE)
PROVENANCE = "a" * 64


def _capture(
    *,
    epoch_sample: int,
    absolute_cfo_hz: float = 0.0,
    doppler_rate_hz_s: float = 0.0,
    amplitude: float = 1.0,
    symbol_roll: int = 0,
    timing_rate_samples_s: float = 0.0,
    sample_rate_hz: float = RATE,
) -> np.ndarray:
    template = qin_edge_pilot_frame(
        sample_rate_hz,
        StarlinkEdge.LOWER,
        symbol_roll=symbol_roll,
    )
    output = np.zeros(round(0.075 * sample_rate_hz), dtype=np.complex128)
    indexes = np.arange(template.size)
    frame = 0
    while True:
        nominal_start = epoch_sample + round(frame * sample_rate_hz / FRAME_RATE_HZ)
        start = epoch_sample + round(
            frame * sample_rate_hz / FRAME_RATE_HZ
            + timing_rate_samples_s * nominal_start / sample_rate_hz
        )
        if start + template.size > output.size:
            break
        absolute = start + indexes
        time_s = absolute / sample_rate_hz
        output[start : start + template.size] += (
            amplitude
            * template
            * np.exp(2j * np.pi * (absolute_cfo_hz * time_s + 0.5 * doppler_rate_hz_s * time_s**2))
        )
        frame += 1
    return output


def _seed(epoch_sample: int, cfo_hz: float = 0.0) -> KnownPilotModeSeed:
    return KnownPilotModeSeed(
        nominal_epoch_sample=epoch_sample,
        nominal_absolute_cfo_hz=cfo_hz,
        branch_id="trajectory-0",
        provenance_sha256=PROVENANCE,
    )


def _named_seed(
    epoch_sample: int,
    cfo_hz: float,
    branch_id: str,
    digest_character: str,
    *,
    rate_hz_s: float = 0.0,
) -> KnownPilotModeSeed:
    return KnownPilotModeSeed(
        nominal_epoch_sample=epoch_sample,
        nominal_absolute_cfo_hz=cfo_hz,
        branch_id=branch_id,
        provenance_sha256=digest_character * 64,
        nominal_doppler_rate_hz_s=rate_hz_s,
    )


def test_seed_and_configuration_contracts_are_frozen_and_fail_closed() -> None:
    seed = _seed(7)

    with pytest.raises(ValueError, match="seed epoch"):
        KnownPilotModeSeed(-1, 0.0, "branch", PROVENANCE)
    with pytest.raises(ValueError, match="provenance"):
        KnownPilotModeSeed(0, 0.0, "branch", "not-a-digest")
    with pytest.raises(ValueError, match="explicitly uncalibrated"):
        SeededPilotAcquisitionConfig(thresholds_calibrated=True)
    with pytest.raises(ValueError, match="unique modulo 300"):
        SeededPilotAcquisitionConfig(control_symbol_rolls=(17, 317))
    with pytest.raises(ValueError, match="trajectory epoch radius"):
        SeededPilotAcquisitionConfig(trajectory_epoch_radius_samples=-1)
    with pytest.raises(ValueError, match="maximum trajectory epoch span"):
        SeededPilotAcquisitionConfig(maximum_trajectory_epoch_span_samples=-1)
    with pytest.raises(ValueError, match="maximum adjacent trajectory epoch step"):
        SeededPilotAcquisitionConfig(maximum_adjacent_trajectory_epoch_step_samples=-1)
    with pytest.raises(ValueError, match="maximum trajectory epoch fit RMS"):
        SeededPilotAcquisitionConfig(maximum_trajectory_epoch_fit_rms_samples=-0.01)
    with pytest.raises(ValueError, match="maximum trajectory CFO span"):
        SeededPilotAcquisitionConfig(maximum_trajectory_cfo_span_hz=-0.01)
    with pytest.raises(ValueError, match="proposal block index"):
        SeededPilotAcquisitionConfig(global_proposal_block_index=1)
    with pytest.raises(ValueError, match="unique even acquisition symbols"):
        SeededPilotAcquisitionConfig(global_proposal_symbols=())
    with pytest.raises(ValueError, match="unique even acquisition symbols"):
        SeededPilotAcquisitionConfig(global_proposal_symbols=(2, 2))
    with pytest.raises(ValueError, match="unique even acquisition symbols"):
        SeededPilotAcquisitionConfig(global_proposal_symbols=(2, 3))
    with pytest.raises(FrozenInstanceError):
        seed.nominal_epoch_sample = 8  # type: ignore[misc]


def test_boundary_seed_is_retained_and_scored_on_the_exact_frame_lattice() -> None:
    epoch = math.floor(RATE / FRAME_RATE_HZ)
    cfo_hz = 1_200.0
    result = acquire_seeded_known_pilot_modes(
        _capture(epoch_sample=epoch, absolute_cfo_hz=cfo_hz),
        RATE,
        seed=_seed(epoch, cfo_hz),
        edge=StarlinkEdge.LOWER,
        config=SeededPilotAcquisitionConfig(retained_candidate_count=1),
    )

    assert result.status is NumericalStatus.COMPLETE
    assert len(result.accepted_modes) == 1
    assert result.block_starts == (0, 4_583, 9_167, 13_750)
    assert result.winner is not None
    assert result.winner.proposal_origin is PilotModeProposalOrigin.PROTECTED_SEED
    assert result.winner.epoch_sample == epoch
    assert result.winner.absolute_cfo_hz == cfo_hz
    assert result.winner.passing_block_count == 4
    assert result.winner.median_verify_score == pytest.approx(1.0)
    assert result.winner.median_exact_minus_control_margin > 0.5
    for block in result.winner.blocks:
        frame_index = round((block.first_frame_start_sample - epoch) / result.frame_period_samples)
        assert block.first_frame_start_sample == epoch + round(
            frame_index * result.frame_period_samples
        )
        assert block.projected_epoch_sample == block.first_frame_start_sample - block.start_sample
        assert block.verify_score == pytest.approx(1.0)


def test_stronger_local_mode_does_not_remove_the_protected_seed() -> None:
    result = acquire_seeded_known_pilot_modes(
        _capture(epoch_sample=42),
        RATE,
        seed=_seed(40),
        edge=StarlinkEdge.LOWER,
        config=SeededPilotAcquisitionConfig(
            local_cfo_radius_hz=0.0,
            retained_candidate_count=2,
            candidate_epoch_separation_samples=2,
        ),
    )

    assert result.winner is not None
    assert result.winner.epoch_sample == 42
    protected = tuple(
        mode
        for mode in result.retained_modes
        if mode.proposal_origin is PilotModeProposalOrigin.PROTECTED_SEED
    )
    assert len(protected) == 1
    assert protected[0].proposal_epoch_sample == 40
    assert protected[0].source_nominal_epoch_sample == 40
    assert protected[0].epoch_sample == 42


def test_controls_use_the_exact_candidates_coordinates_and_absolute_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[int, float, tuple[int, ...], int, int]] = []
    original = seeded._normalized_absolute_block_score

    def recording_score(
        values: np.ndarray,
        template: np.ndarray,
        sample_rate_hz: float,
        epoch_sample: int,
        absolute_cfo_hz: float,
        symbols: tuple[int, ...],
        block_start_sample: int,
        block_stop_sample: int,
    ) -> tuple[float, int]:
        observed.append(
            (
                epoch_sample,
                absolute_cfo_hz,
                symbols,
                block_start_sample,
                block_stop_sample,
            )
        )
        return original(
            values,
            template,
            sample_rate_hz,
            epoch_sample,
            absolute_cfo_hz,
            symbols,
            block_start_sample,
            block_stop_sample,
        )

    monkeypatch.setattr(seeded, "_normalized_absolute_block_score", recording_score)
    result = acquire_seeded_known_pilot_modes(
        _capture(epoch_sample=23, absolute_cfo_hz=250.0),
        RATE,
        seed=_seed(23, 250.0),
        edge=StarlinkEdge.LOWER,
        config=SeededPilotAcquisitionConfig(
            local_epoch_radius_samples=0,
            local_cfo_radius_hz=0.0,
            retained_candidate_count=1,
        ),
    )

    assert result.winner is not None
    for start in result.block_starts:
        held_out = [row for row in observed if row[2] == DEFAULT_VERIFY_SYMBOLS and row[3] == start]
        assert len(held_out) == 6  # exact, three conditional, and two orbit-breaking controls
        assert len({(row[0], row[1], row[3], row[4]) for row in held_out}) == 1
    assert sum(row[2] == DEFAULT_ACQUIRE_SYMBOLS for row in observed) == 4
    assert all(
        not identity.independently_reacquired
        for identity in (
            *result.conditional_control_template_identities,
            *result.diagnostic_control_template_identities,
        )
    )


def test_candidate_bound_and_discard_accounting_are_complete_and_deterministic() -> None:
    config = SeededPilotAcquisitionConfig(
        local_epoch_radius_samples=1,
        local_cfo_radius_hz=100.0,
        local_cfo_step_hz=100.0,
        retained_candidate_count=2,
    )
    first = acquire_seeded_known_pilot_modes(
        np.zeros(WINDOW_SAMPLES, dtype=np.complex128),
        RATE,
        seed=_seed(10),
        edge=StarlinkEdge.LOWER,
        config=config,
    )
    second = acquire_seeded_known_pilot_modes(
        np.zeros(WINDOW_SAMPLES, dtype=np.complex128),
        RATE,
        seed=_seed(10),
        edge=StarlinkEdge.LOWER,
        config=config,
    )

    assert first == second
    assert first.evaluated_grid_point_count == 9
    assert first.evaluated_block_score_count == 36
    assert (
        len(first.retained_modes)
        + first.separation_suppressed_count
        + first.candidate_limit_truncated_count
        == first.evaluated_grid_point_count
    )
    assert len(first.retained_modes) <= config.retained_candidate_count
    assert first.winner is None
    assert not first.thresholds_calibrated
    assert not first.specificity_claimed
    assert first.candidate_only


def test_tiny_path_reductions_are_bit_exact_with_numpy() -> None:
    values = (
        0.08561427421923362,
        0.7410712840746775,
        0.3972266495505785,
        0.623412746363287,
        0.19371826661787406,
    )

    for length in range(1, len(values) + 1):
        selected = values[:length]
        assert seeded._small_median(selected).hex() == float(np.median(selected)).hex()
        assert seeded._small_mean(selected).hex() == float(np.mean(selected)).hex()

    generator = np.random.default_rng(0x5A11)
    for length in range(1, 5):
        for row in generator.uniform(-1.0, 1.0, size=(250, length)):
            selected = tuple(float(value) for value in row)
            assert seeded._small_mean(selected).hex() == float(np.mean(selected)).hex()


def test_repeated_trajectory_geometry_is_scored_once_per_unique_epoch_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0
    original = seeded._linear_fit_residual_metrics

    def recording_fit(
        x_values: tuple[float, ...],
        y_values: tuple[float, ...],
    ) -> tuple[float, float]:
        nonlocal call_count
        call_count += 1
        return original(x_values, y_values)

    monkeypatch.setattr(seeded, "_linear_fit_residual_metrics", recording_fit)
    result = acquire_seeded_known_pilot_modes(
        _capture(epoch_sample=23, absolute_cfo_hz=250.0),
        RATE,
        seed=_seed(23, 250.0),
        edge=StarlinkEdge.LOWER,
    )

    assert result.trajectory_path_evaluated_count == 26_880
    assert call_count < result.trajectory_path_evaluated_count // 10
    assert result.winner is not None
    assert result.winner.epoch_sample == 23
    assert result.winner.absolute_cfo_hz == 250.0


def test_explicit_refinement_pairs_preserve_legacy_cartesian_anchor_winners() -> None:
    epoch_count = math.ceil(RATE / FRAME_RATE_HZ)
    anchors = ((23, 0.0), (200, 1_000.0))
    settings = SeededPilotAcquisitionConfig(global_fallback_enabled=False)
    epochs = tuple(
        sorted({(epoch + offset) % epoch_count for epoch, _ in anchors for offset in range(-2, 3)})
    )
    explicit_coordinates = tuple(
        sorted(
            {
                ((epoch + offset) % epoch_count, cfo_hz)
                for epoch, cfo_hz in anchors
                for offset in range(-2, 3)
            }
        )
    )
    legacy_cartesian_coordinates = tuple(
        (epoch, cfo_hz) for epoch in epochs for cfo_hz in (0.0, 1_000.0)
    )
    block_length = round(settings.block_duration_s * RATE)
    blocks = tuple(
        (start, start + block_length)
        for start in seeded._evenly_spaced_block_starts(
            WINDOW_SAMPLES,
            block_length,
            settings.block_count,
        )
    )
    values = _capture(epoch_sample=23)
    template = np.asarray(
        qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER),
        dtype=np.complex128,
    )

    explicit = seeded._score_proposals(
        values,
        template,
        RATE,
        anchors,
        explicit_coordinates,
        0.0,
        blocks,
        settings.minimum_frame_support_per_block,
        epoch_count,
        settings,
    )
    legacy = seeded._score_proposals(
        values,
        template,
        RATE,
        anchors,
        legacy_cartesian_coordinates,
        0.0,
        blocks,
        settings.minimum_frame_support_per_block,
        epoch_count,
        settings,
    )

    assert explicit[0] == legacy[0]
    assert explicit[1] == len(explicit_coordinates) * settings.block_count
    assert legacy[1] == len(legacy_cartesian_coordinates) * settings.block_count
    assert explicit[2:] == legacy[2:]


def test_cfo_alias_canonicalization_collapses_one_symbol_rate_lift() -> None:
    canonical, lift = canonicalize_cfo_alias(85_000.0)
    shifted, shifted_lift = canonicalize_cfo_alias(85_000.0 + CFO_ALIAS_SPACING_HZ)

    assert shifted == pytest.approx(canonical, abs=1e-9)
    assert shifted_lift == lift + 1


def test_short_window_is_numerically_insufficient_without_partial_candidates() -> None:
    result = acquire_seeded_known_pilot_modes(
        np.zeros(round(0.010 * RATE), dtype=np.complex128),
        RATE,
        seed=_seed(0),
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.INSUFFICIENT
    assert result.retained_modes == ()
    assert result.evaluated_grid_point_count == 0
    assert result.winner is None
    assert result.presence_disposition is ResearchDisposition.INSUFFICIENT
    assert result.code_specificity_disposition is ResearchDisposition.INSUFFICIENT
    assert result.cfo_alias_resolution_disposition is ResearchDisposition.INSUFFICIENT
    assert result.uniqueness_disposition is ResearchDisposition.INSUFFICIENT


def test_expected_pilot_cannot_also_be_a_conditional_control() -> None:
    with pytest.raises(ValueError, match="expected pilot"):
        acquire_seeded_known_pilot_modes(
            np.zeros(WINDOW_SAMPLES, dtype=np.complex128),
            RATE,
            seed=_seed(0),
            edge=StarlinkEdge.LOWER,
            expected_symbol_roll=17,
        )


def test_global_fallback_recovers_a_large_epoch_seed_error_and_preserves_seed() -> None:
    actual_epoch = 210
    nominal_epoch = 20
    config = SeededPilotAcquisitionConfig(
        local_cfo_radius_hz=0.0,
        minimum_exact_score=0.5,
        minimum_exact_minus_control_margin=0.2,
        global_cfo_radius_hz=0.0,
        global_retained_candidate_count=4,
    )
    result = acquire_seeded_known_pilot_modes(
        _capture(epoch_sample=actual_epoch),
        RATE,
        seed=_seed(nominal_epoch),
        edge=StarlinkEdge.LOWER,
        config=config,
    )

    assert result.global_fallback_attempted
    assert result.global_proposal_block_index == 0
    assert result.global_proposal_block_start_sample == 0
    assert result.global_proposal_block_stop_sample == round(config.block_duration_s * RATE)
    assert result.global_proposal_sample_count == round(config.block_duration_s * RATE)
    assert result.global_proposal_symbol_count == len(DEFAULT_ANCHOR_SYMBOLS)
    assert result.global_proposal_frame_offset_count == 15
    assert result.global_searched_epoch_count == math.ceil(RATE / FRAME_RATE_HZ)
    assert result.global_searched_cfo_count == 1
    assert result.global_evaluated_grid_point_count == math.ceil(RATE / FRAME_RATE_HZ)
    assert result.winner is not None
    assert result.winner.proposal_origin is PilotModeProposalOrigin.GLOBAL_FALLBACK
    assert result.winner.epoch_sample == actual_epoch
    assert len(result.accepted_modes) == 1
    assert any(
        mode.proposal_origin is PilotModeProposalOrigin.PROTECTED_SEED
        and mode.epoch_sample == nominal_epoch
        for mode in result.retained_modes
    )
    global_rows = tuple(
        mode
        for mode in result.retained_modes
        if mode.proposal_origin is PilotModeProposalOrigin.GLOBAL_FALLBACK
    )
    assert len(global_rows) <= config.global_retained_candidate_count
    assert result.global_evaluated_block_score_count >= len(global_rows) * config.block_count
    assert result.global_evaluated_block_score_count <= (
        len(global_rows) * (2 * config.trajectory_epoch_radius_samples + 1) * config.block_count
    )
    assert result.global_trajectory_path_evaluated_count > 0
    assert all(len(mode.blocks) == config.block_count for mode in global_rows)
    assert (
        len(global_rows)
        + result.global_separation_suppressed_count
        + result.global_candidate_limit_truncated_count
        == result.global_peak_count
    )


def test_global_proposal_search_uses_only_declared_block_and_anchor_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[int, tuple[int, ...], int, int]] = []
    original = seeded._folded_anchor_score_grid

    def recording_grid(
        values: np.ndarray,
        template: np.ndarray,
        sample_rate_hz: float,
        absolute_cfo_hz: tuple[float, ...],
        symbols: tuple[int, ...],
        epoch_count: int,
    ) -> tuple[np.ndarray, ...]:
        observed.append((values.size, symbols, len(absolute_cfo_hz), epoch_count))
        return original(
            values,
            template,
            sample_rate_hz,
            absolute_cfo_hz,
            symbols,
            epoch_count,
        )

    monkeypatch.setattr(seeded, "_folded_anchor_score_grid", recording_grid)
    config = SeededPilotAcquisitionConfig(
        local_cfo_radius_hz=0.0,
        minimum_exact_score=0.5,
        minimum_exact_minus_control_margin=0.2,
        global_cfo_radius_hz=250.0,
        global_cfo_step_hz=250.0,
    )
    result = acquire_seeded_known_pilot_modes(
        _capture(epoch_sample=210),
        RATE,
        seed=_seed(20),
        edge=StarlinkEdge.LOWER,
        config=config,
    )

    assert observed == [
        (
            round(config.block_duration_s * RATE),
            DEFAULT_ANCHOR_SYMBOLS,
            3,
            math.ceil(RATE / FRAME_RATE_HZ),
        )
    ]
    assert result.global_evaluated_grid_point_count == (math.ceil(RATE / FRAME_RATE_HZ) * 3)
    assert result.winner is not None
    assert len(result.winner.blocks) == config.block_count


def test_global_proposal_recovers_deterministic_noisy_wrap_cfo_and_rate() -> None:
    proposal_rate_hz = 2_500_000.0
    epoch_count = math.ceil(proposal_rate_hz / FRAME_RATE_HZ)
    actual_epoch = epoch_count - 4
    actual_cfo_hz = 1_300.0
    rate_hz_s = 600.0
    generator = np.random.default_rng(0xC0F0)
    samples = _capture(
        epoch_sample=actual_epoch,
        absolute_cfo_hz=actual_cfo_hz,
        doppler_rate_hz_s=rate_hz_s,
        sample_rate_hz=proposal_rate_hz,
    )
    samples += 0.02 * (
        generator.normal(size=samples.size) + 1j * generator.normal(size=samples.size)
    )
    seed = _named_seed(
        100,
        1_050.0,
        "noisy-wrap-rate",
        "c",
        rate_hz_s=rate_hz_s,
    )
    config = SeededPilotAcquisitionConfig(
        local_cfo_radius_hz=0.0,
        minimum_exact_score=0.3,
        minimum_exact_minus_control_margin=0.1,
        global_cfo_radius_hz=500.0,
        global_cfo_step_hz=250.0,
        global_retained_candidate_count=4,
    )

    first = acquire_seeded_known_pilot_modes(
        samples,
        proposal_rate_hz,
        seed=seed,
        edge=StarlinkEdge.LOWER,
        config=config,
    )
    second = acquire_seeded_known_pilot_modes(
        samples,
        proposal_rate_hz,
        seed=seed,
        edge=StarlinkEdge.LOWER,
        config=config,
    )

    assert first == second
    assert first.global_fallback_attempted
    assert first.winner is not None
    assert first.winner.proposal_origin is PilotModeProposalOrigin.GLOBAL_FALLBACK
    assert first.winner.epoch_sample == actual_epoch
    assert first.winner.absolute_cfo_hz == actual_cfo_hz
    assert first.winner.doppler_rate_hz_s == rate_hz_s
    assert first.winner.passing_block_count == config.block_count


def test_global_proposal_block_dropout_makes_no_absence_claim() -> None:
    config = SeededPilotAcquisitionConfig(
        local_cfo_radius_hz=0.0,
        minimum_exact_score=0.5,
        minimum_exact_minus_control_margin=0.2,
        global_cfo_radius_hz=0.0,
    )
    samples = _capture(epoch_sample=210)
    samples[: round(config.block_duration_s * RATE)] = 0.0

    result = acquire_seeded_known_pilot_modes(
        samples,
        RATE,
        seed=_seed(20),
        edge=StarlinkEdge.LOWER,
        config=config,
    )

    assert result.global_fallback_attempted
    assert result.global_peak_count == 0
    assert result.accepted_modes == ()
    assert result.presence_disposition is ResearchDisposition.NO_RESEARCH_CANDIDATE
    assert not result.specificity_claimed
    assert result.candidate_only


def test_global_fallback_null_is_rejected_with_explicit_candidate_cap_accounting() -> None:
    generator = np.random.default_rng(0xF411)
    samples = (
        generator.normal(size=WINDOW_SAMPLES) + 1j * generator.normal(size=WINDOW_SAMPLES)
    ) / np.sqrt(2)
    config = SeededPilotAcquisitionConfig(
        local_epoch_radius_samples=0,
        local_cfo_radius_hz=0.0,
        retained_candidate_count=1,
        minimum_exact_score=0.5,
        global_cfo_radius_hz=0.0,
        global_retained_candidate_count=2,
        global_candidate_epoch_separation_samples=1,
    )
    result = acquire_seeded_known_pilot_modes(
        samples,
        RATE,
        seed=_seed(10),
        edge=StarlinkEdge.LOWER,
        config=config,
    )

    global_rows = tuple(
        mode
        for mode in result.retained_modes
        if mode.proposal_origin is PilotModeProposalOrigin.GLOBAL_FALLBACK
    )
    assert result.status is NumericalStatus.COMPLETE
    assert result.global_fallback_attempted
    assert result.global_evaluated_grid_point_count == math.ceil(RATE / FRAME_RATE_HZ)
    assert len(global_rows) == config.global_retained_candidate_count
    assert result.global_candidate_limit_truncated_count > 0
    assert result.global_peak_count == (
        len(global_rows)
        + result.global_separation_suppressed_count
        + result.global_candidate_limit_truncated_count
    )
    assert result.global_evaluated_block_score_count >= len(global_rows) * config.block_count
    assert result.global_trajectory_path_evaluated_count > 0
    assert result.accepted_modes == ()


def test_configuration_and_template_identities_are_deterministic_and_content_addressed() -> None:
    config = SeededPilotAcquisitionConfig(
        local_epoch_radius_samples=0,
        local_cfo_radius_hz=0.0,
        retained_candidate_count=1,
        global_fallback_enabled=False,
    )
    samples = _capture(epoch_sample=23, absolute_cfo_hz=250.0)
    first = acquire_seeded_known_pilot_modes(
        samples,
        RATE,
        seed=_seed(23, 250.0),
        edge=StarlinkEdge.LOWER,
        config=config,
    )
    second = acquire_seeded_known_pilot_modes(
        samples,
        RATE,
        seed=_seed(23, 250.0),
        edge=StarlinkEdge.LOWER,
        config=config,
    )

    assert first == second
    assert first.config_digest == config.digest
    assert first.config_digest.startswith("sha256:")
    assert (
        config.digest
        != SeededPilotAcquisitionConfig(
            local_epoch_radius_samples=1,
            local_cfo_radius_hz=0.0,
            retained_candidate_count=1,
            global_fallback_enabled=False,
        ).digest
    )
    assert first.exact_template_identity.template_sha256 == template_sha256(
        qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)
    )
    assert first.exact_template_identity.role is TemplateEvidenceRole.EXPECTED
    assert first.exact_template_identity.independently_reacquired
    assert len(first.conditional_control_template_identities) == 3
    assert all(
        identity.role is TemplateEvidenceRole.CONDITIONAL_GATE
        and identity.gates_research_decision
        and not identity.independently_reacquired
        for identity in first.conditional_control_template_identities
    )
    assert len(first.diagnostic_control_template_identities) == 2
    assert all(
        identity.role is TemplateEvidenceRole.ORBIT_BREAKING_DIAGNOSTIC
        and not identity.gates_research_decision
        and not identity.independently_reacquired
        for identity in first.diagnostic_control_template_identities
    )
    identities = (
        first.exact_template_identity,
        *first.conditional_control_template_identities,
        *first.diagnostic_control_template_identities,
    )
    assert len({identity.label for identity in identities}) == len(identities)
    assert len({identity.template_sha256 for identity in identities}) == len(identities)
    assert first.winner is not None
    assert second.winner is not None
    assert len(first.winner.median_diagnostic_control_scores) == 2
    assert all(len(block.diagnostic_control_scores) == 2 for block in first.winner.blocks)
    assert len(first.winner.trajectory_path_sha256) == 64
    assert first.winner.trajectory_path_sha256 == second.winner.trajectory_path_sha256


def test_orbit_breaking_controls_are_not_scalar_rolls_and_transplant_opposite_code() -> None:
    deranged, transplanted = seeded._orbit_breaking_control_payloads(
        RATE,
        StarlinkEdge.LOWER,
    )
    scalar_digests = {
        template_sha256(qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER, symbol_roll=roll))
        for roll in (0, 17, 53, 101)
    }

    assert template_sha256(deranged) not in scalar_digests
    assert template_sha256(transplanted) not in scalar_digests
    # Both edge banks have the same center-relative tone geometry.  Equality
    # therefore confirms that the opposite-edge states were transplanted onto
    # the tested baseband tones rather than frequency-shifted out of band.
    assert template_sha256(transplanted) == template_sha256(
        qin_edge_pilot_frame(RATE, StarlinkEdge.UPPER)
    )


def test_claim_dispositions_remain_separate_and_explicitly_uncalibrated() -> None:
    config = SeededPilotAcquisitionConfig(
        local_epoch_radius_samples=0,
        local_cfo_radius_hz=0.0,
        retained_candidate_count=1,
        global_fallback_enabled=False,
    )
    candidate = acquire_seeded_known_pilot_modes(
        _capture(epoch_sample=23),
        RATE,
        seed=_seed(23),
        edge=StarlinkEdge.LOWER,
        config=config,
    )
    rejected = acquire_seeded_known_pilot_modes(
        np.zeros(WINDOW_SAMPLES, dtype=np.complex128),
        RATE,
        seed=_seed(23),
        edge=StarlinkEdge.LOWER,
        config=config,
    )

    assert candidate.presence_disposition is ResearchDisposition.UNCALIBRATED_CANDIDATE
    assert candidate.code_specificity_disposition is ResearchDisposition.AMBIGUOUS
    assert candidate.cfo_alias_resolution_disposition is ResearchDisposition.UNRESOLVED
    assert candidate.uniqueness_disposition is ResearchDisposition.UNRESOLVED
    assert not candidate.thresholds_calibrated
    assert not candidate.specificity_claimed
    assert rejected.presence_disposition is ResearchDisposition.NO_RESEARCH_CANDIDATE
    assert rejected.code_specificity_disposition is ResearchDisposition.UNASSESSED
    assert rejected.cfo_alias_resolution_disposition is ResearchDisposition.UNASSESSED
    assert rejected.uniqueness_disposition is ResearchDisposition.UNASSESSED


def test_two_prequalified_non_alias_families_remain_separate_components() -> None:
    epoch = 23
    second_cfo_hz = 85_000.0
    samples = _capture(epoch_sample=epoch) + _capture(
        epoch_sample=epoch,
        absolute_cfo_hz=second_cfo_hz,
    )
    primary = _named_seed(epoch, 0.0, "family-a", "a")
    secondary = _named_seed(epoch, second_cfo_hz, "family-b", "b")
    config = SeededPilotAcquisitionConfig(
        local_epoch_radius_samples=0,
        local_cfo_radius_hz=0.0,
        retained_candidate_count=1,
        global_fallback_enabled=False,
    )
    result = acquire_seeded_known_pilot_modes(
        samples,
        RATE,
        seed=primary,
        additional_seeds=(secondary,),
        edge=StarlinkEdge.LOWER,
        config=config,
    )

    assert result.seed is primary
    assert result.additional_seeds == (secondary,)
    assert result.evaluated_seed_count == 2
    assert len(result.accepted_modes) == 2
    assert {mode.source_branch_id for mode in result.accepted_modes} == {
        "family-a",
        "family-b",
    }
    assert {mode.source_provenance_sha256 for mode in result.accepted_modes} == {
        "a" * 64,
        "b" * 64,
    }
    assert abs(
        result.accepted_modes[0].canonical_cfo_hz - result.accepted_modes[1].canonical_cfo_hz
    ) == pytest.approx(second_cfo_hz)
    assert result.uniqueness_disposition is ResearchDisposition.AMBIGUOUS
    assert result.whole_window_rescore_candidate_count == 2
    assert result.whole_window_rescore_template_score_count == 12


def test_same_epoch_one_symbol_rate_lift_is_retained_as_an_alias_duplicate() -> None:
    epoch = 23
    alias_cfo_hz = CFO_ALIAS_SPACING_HZ
    samples = _capture(epoch_sample=epoch) + _capture(
        epoch_sample=epoch,
        absolute_cfo_hz=alias_cfo_hz,
    )
    primary = _named_seed(epoch, 0.0, "alias-zero", "a")
    lifted = _named_seed(epoch, alias_cfo_hz, "alias-plus-one", "b")
    result = acquire_seeded_known_pilot_modes(
        samples,
        RATE,
        seed=primary,
        additional_seeds=(lifted,),
        edge=StarlinkEdge.LOWER,
        config=SeededPilotAcquisitionConfig(
            local_epoch_radius_samples=0,
            local_cfo_radius_hz=0.0,
            retained_candidate_count=1,
            global_fallback_enabled=False,
        ),
    )

    assert len(result.accepted_modes) == 1
    duplicates = tuple(
        mode
        for mode in result.retained_modes
        if mode.decision is ResearchEvidenceDecision.ALIAS_DUPLICATE
    )
    assert len(duplicates) == 1
    assert duplicates[0].epoch_sample == result.accepted_modes[0].epoch_sample
    assert duplicates[0].canonical_cfo_hz == pytest.approx(
        result.accepted_modes[0].canonical_cfo_hz,
        abs=1e-9,
    )
    assert result.cfo_alias_resolution_disposition is ResearchDisposition.AMBIGUOUS


def test_rate_aware_whole_window_rescore_is_required_and_fully_accounted() -> None:
    epoch = 23
    cfo_hz = 1_200.0
    rate_hz_s = -3_000.0
    seed = _named_seed(epoch, cfo_hz, "rate-aware", "c", rate_hz_s=rate_hz_s)
    result = acquire_seeded_known_pilot_modes(
        _capture(
            epoch_sample=epoch,
            absolute_cfo_hz=cfo_hz,
            doppler_rate_hz_s=rate_hz_s,
        ),
        RATE,
        seed=seed,
        edge=StarlinkEdge.LOWER,
        config=SeededPilotAcquisitionConfig(
            local_epoch_radius_samples=0,
            local_cfo_radius_hz=0.0,
            retained_candidate_count=1,
            global_fallback_enabled=False,
        ),
    )

    assert result.winner is not None
    assert result.winner.whole_window_verify_score == pytest.approx(1.0)
    assert result.winner.whole_window_exact_minus_control_margin is not None
    assert result.winner.whole_window_exact_minus_control_margin > 0.5
    assert result.winner.whole_window_frame_support > 40
    assert result.winner.whole_window_consistent_with_blocks
    assert len(result.winner.whole_window_control_scores) == 3
    assert len(result.winner.whole_window_diagnostic_control_scores) == 2
    assert result.whole_window_rescore_candidate_count == 1
    assert result.whole_window_rescore_template_score_count == 6


def test_protected_seed_survives_more_than_eight_stronger_or_equal_grid_decoys() -> None:
    config = SeededPilotAcquisitionConfig(
        local_epoch_radius_samples=2,
        local_cfo_radius_hz=500.0,
        local_cfo_step_hz=50.0,
        retained_candidate_count=8,
        global_fallback_enabled=False,
    )
    result = acquire_seeded_known_pilot_modes(
        np.zeros(WINDOW_SAMPLES, dtype=np.complex128),
        RATE,
        seed=_seed(23),
        edge=StarlinkEdge.LOWER,
        config=config,
    )

    assert result.evaluated_grid_point_count > 8
    assert result.candidate_limit_truncated_count > 8
    protected = tuple(
        mode
        for mode in result.retained_modes
        if mode.proposal_origin is PilotModeProposalOrigin.PROTECTED_SEED
    )
    assert len(protected) == 1
    assert protected[0].epoch_sample == 23
    assert protected[0].source_branch_id == "trajectory-0"
    assert protected[0].source_provenance_sha256 == PROVENANCE


def test_even_only_block_lattice_path_tracks_bounded_epoch_drift() -> None:
    result = acquire_seeded_known_pilot_modes(
        _capture(epoch_sample=23, timing_rate_samples_s=30.0),
        RATE,
        seed=_seed(23),
        edge=StarlinkEdge.LOWER,
        config=SeededPilotAcquisitionConfig(
            local_cfo_radius_hz=0.0,
            retained_candidate_count=1,
            global_fallback_enabled=False,
        ),
    )

    assert result.winner is not None
    assert result.winner.trajectory_block_epoch_samples == (23, 24, 24, 25)
    assert result.winner.epoch_sample == 24
    assert result.winner.trajectory_block_epoch_residual_samples == (-1, 0, 0, 1)
    assert result.winner.trajectory_epoch_span_samples == 2
    assert result.winner.trajectory_max_adjacent_epoch_step_samples == 1
    assert result.winner.trajectory_timing_rate_samples_s == pytest.approx(32.7, abs=1.0)
    assert result.winner.trajectory_epoch_fit_rms_samples < 0.3
    assert result.winner.trajectory_admissible
    assert result.winner.whole_window_consistent_with_blocks
    assert result.winner.whole_window_verify_score is not None
    assert result.winner.whole_window_verify_score > 0.8
    assert all(block.passed_research_gate for block in result.winner.blocks)
    assert all(
        block.trajectory_epoch_sample == epoch
        for block, epoch in zip(
            result.winner.blocks,
            result.winner.trajectory_block_epoch_samples,
            strict=True,
        )
    )
    assert result.evaluated_block_score_count == (
        result.evaluated_grid_point_count * SeededPilotAcquisitionConfig().block_count
    )
    assert result.trajectory_path_evaluated_count > result.evaluated_grid_point_count
    assert result.trajectory_path_limit_truncated_count == 0


def test_abrupt_epoch_step_is_not_smoothed_into_one_contiguous_arc() -> None:
    template = qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)
    samples = np.zeros(WINDOW_SAMPLES, dtype=np.complex128)
    frame_index = 0
    while True:
        nominal_start = 23 + round(frame_index * RATE / FRAME_RATE_HZ)
        frame_start = nominal_start + (2 if nominal_start / RATE >= 0.040 else 0)
        if frame_start + template.size > samples.size:
            break
        samples[frame_start : frame_start + template.size] += template
        frame_index += 1

    result = acquire_seeded_known_pilot_modes(
        samples,
        RATE,
        seed=_seed(23),
        edge=StarlinkEdge.LOWER,
        config=SeededPilotAcquisitionConfig(
            local_cfo_radius_hz=0.0,
            retained_candidate_count=1,
            global_fallback_enabled=False,
        ),
    )

    assert result.accepted_modes == ()
    assert result.whole_window_rescore_candidate_count == 0
    assert len(result.retained_modes) == 1
    mode = result.retained_modes[0]
    assert mode.trajectory_block_epoch_samples == (23, 23, 25, 25)
    assert mode.trajectory_epoch_span_samples == 2
    assert mode.trajectory_max_adjacent_epoch_step_samples == 2
    assert mode.trajectory_epoch_fit_rms_samples < 0.75
    assert not mode.trajectory_admissible
    assert mode.passing_block_count == 4
    assert mode.decision is ResearchEvidenceDecision.REJECTED


def test_abrupt_cfo_residual_path_exceeding_frozen_span_is_not_admitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def discontinuous_cfo_score(
        values: np.ndarray,
        template: np.ndarray,
        sample_rate_hz: float,
        epoch_sample: int,
        absolute_cfo_hz: float,
        symbols: tuple[int, ...],
        block_start_sample: int,
        block_stop_sample: int,
    ) -> tuple[float, int]:
        del values, template, sample_rate_hz, epoch_sample, block_stop_sample
        if symbols != DEFAULT_ACQUIRE_SYMBOLS:
            return 0.5, 4
        target_cfo_hz = -100.0 if block_start_sample < 7_500 else 100.0
        return (1.0 if absolute_cfo_hz == target_cfo_hz else 0.1), 4

    monkeypatch.setattr(
        seeded,
        "_normalized_absolute_block_score",
        discontinuous_cfo_score,
    )
    result = acquire_seeded_known_pilot_modes(
        np.ones(WINDOW_SAMPLES, dtype=np.complex128),
        RATE,
        seed=_seed(23),
        edge=StarlinkEdge.LOWER,
        config=SeededPilotAcquisitionConfig(
            local_epoch_radius_samples=0,
            local_cfo_radius_hz=100.0,
            local_cfo_step_hz=100.0,
            retained_candidate_count=1,
            global_fallback_enabled=False,
        ),
    )

    assert result.accepted_modes == ()
    mode = result.retained_modes[0]
    assert mode.trajectory_block_absolute_cfo_hz == (
        -100.0,
        -100.0,
        100.0,
        100.0,
    )
    assert mode.trajectory_block_cfo_residual_hz == (0.0, 0.0, 200.0, 200.0)
    assert mode.trajectory_cfo_span_hz == 200.0
    assert not mode.trajectory_admissible


def test_all_block_admitted_rows_are_rescored_before_local_component_collapse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_candidate_count = 0

    def controlled_rescore(
        modes: tuple[seeded.KnownPilotModeCandidate, ...],
        values: np.ndarray,
        exact_template: np.ndarray,
        control_templates: tuple[np.ndarray, ...],
        diagnostic_control_templates: tuple[np.ndarray, ...],
        sample_rate_hz: float,
        settings: SeededPilotAcquisitionConfig,
    ) -> tuple[tuple[seeded.KnownPilotModeCandidate, ...], int, int]:
        del values, exact_template, sample_rate_hz, settings
        nonlocal observed_candidate_count
        observed_candidate_count = sum(
            mode.decision is ResearchEvidenceDecision.CANDIDATE for mode in modes
        )
        rescored = tuple(
            replace(
                mode,
                whole_window_verify_score=(
                    0.95
                    if mode.proposal_origin is not PilotModeProposalOrigin.PROTECTED_SEED
                    else 0.01
                ),
                whole_window_exact_minus_control_margin=(
                    0.5
                    if mode.proposal_origin is not PilotModeProposalOrigin.PROTECTED_SEED
                    else -0.1
                ),
                whole_window_consistent_with_blocks=(
                    mode.proposal_origin is not PilotModeProposalOrigin.PROTECTED_SEED
                ),
                decision=(
                    ResearchEvidenceDecision.CANDIDATE
                    if mode.proposal_origin is not PilotModeProposalOrigin.PROTECTED_SEED
                    else ResearchEvidenceDecision.WHOLE_WINDOW_INCONSISTENT
                ),
            )
            if mode.decision is ResearchEvidenceDecision.CANDIDATE
            else mode
            for mode in modes
        )
        template_count = 1 + len(control_templates) + len(diagnostic_control_templates)
        return rescored, observed_candidate_count, observed_candidate_count * template_count

    monkeypatch.setattr(
        seeded,
        "_rescore_candidate_modes_on_whole_window",
        controlled_rescore,
    )
    result = acquire_seeded_known_pilot_modes(
        _capture(epoch_sample=42),
        RATE,
        seed=_seed(40),
        edge=StarlinkEdge.LOWER,
        config=SeededPilotAcquisitionConfig(
            local_cfo_radius_hz=0.0,
            retained_candidate_count=2,
            candidate_epoch_separation_samples=2,
            global_fallback_enabled=False,
        ),
    )

    assert observed_candidate_count == 2
    assert len(result.accepted_modes) == 1
    assert result.winner is not None
    assert result.winner.proposal_origin is PilotModeProposalOrigin.LOCAL_SEARCH
    protected = next(
        mode
        for mode in result.retained_modes
        if mode.proposal_origin is PilotModeProposalOrigin.PROTECTED_SEED
    )
    assert protected.decision is ResearchEvidenceDecision.WHOLE_WINDOW_INCONSISTENT


def test_presence_is_reported_when_same_coordinate_controls_make_code_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def ambiguous_score(
        values: np.ndarray,
        template: np.ndarray,
        sample_rate_hz: float,
        epoch_sample: int,
        absolute_cfo_hz: float,
        symbols: tuple[int, ...],
        block_start_sample: int,
        block_stop_sample: int,
    ) -> tuple[float, int]:
        del (
            values,
            template,
            sample_rate_hz,
            epoch_sample,
            absolute_cfo_hz,
            symbols,
            block_start_sample,
            block_stop_sample,
        )
        return 0.5, 4

    monkeypatch.setattr(seeded, "_normalized_absolute_block_score", ambiguous_score)
    result = acquire_seeded_known_pilot_modes(
        np.ones(WINDOW_SAMPLES, dtype=np.complex128),
        RATE,
        seed=_seed(23),
        edge=StarlinkEdge.LOWER,
        config=SeededPilotAcquisitionConfig(
            local_epoch_radius_samples=0,
            local_cfo_radius_hz=0.0,
            retained_candidate_count=1,
            global_fallback_enabled=False,
        ),
    )

    assert result.accepted_modes == ()
    assert result.whole_window_rescore_candidate_count == 0
    assert result.presence_disposition is ResearchDisposition.UNCALIBRATED_CANDIDATE
    assert result.code_specificity_disposition is ResearchDisposition.AMBIGUOUS
    assert result.cfo_alias_resolution_disposition is ResearchDisposition.UNASSESSED
    assert result.uniqueness_disposition is ResearchDisposition.UNASSESSED
    assert result.retained_modes[0].median_verify_score == pytest.approx(0.5)
    assert result.retained_modes[0].median_exact_minus_control_margin == pytest.approx(0.0)
    assert result.retained_modes[0].decision is ResearchEvidenceDecision.REJECTED


def test_unequal_rate_alias_lifts_remain_distinct_trajectory_components() -> None:
    epoch = 23
    primary_rate_hz_s = -5_000.0
    lifted_rate_hz_s = 5_000.0
    primary = _named_seed(
        epoch,
        0.0,
        "alias-negative-rate",
        "a",
        rate_hz_s=primary_rate_hz_s,
    )
    lifted = _named_seed(
        epoch,
        CFO_ALIAS_SPACING_HZ,
        "alias-positive-rate",
        "b",
        rate_hz_s=lifted_rate_hz_s,
    )
    samples = _capture(
        epoch_sample=epoch,
        doppler_rate_hz_s=primary_rate_hz_s,
    ) + _capture(
        epoch_sample=epoch,
        absolute_cfo_hz=CFO_ALIAS_SPACING_HZ,
        doppler_rate_hz_s=lifted_rate_hz_s,
    )
    result = acquire_seeded_known_pilot_modes(
        samples,
        RATE,
        seed=primary,
        additional_seeds=(lifted,),
        edge=StarlinkEdge.LOWER,
        config=SeededPilotAcquisitionConfig(
            local_epoch_radius_samples=0,
            local_cfo_radius_hz=0.0,
            retained_candidate_count=1,
            global_fallback_enabled=False,
        ),
    )

    assert len(result.accepted_modes) == 2
    assert {mode.doppler_rate_hz_s for mode in result.accepted_modes} == {
        primary_rate_hz_s,
        lifted_rate_hz_s,
    }
    assert not any(
        mode.decision is ResearchEvidenceDecision.ALIAS_DUPLICATE for mode in result.retained_modes
    )
    assert result.uniqueness_disposition is ResearchDisposition.AMBIGUOUS
