from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.qam import (
    PilotFrameCfoConfig,
    PilotFrameCfoEstimate,
    PilotFrameCfoSplitValidation,
)
from leo.analysis.qam.pilot import _estimate_edge_pilot_frame_cfo_split_from_cube
from leo.analysis.research.frame_cfo_dwell_prototype import (
    SYMBOL_CFO_ALIAS_SPACING_HZ,
    FrameCfoPrototypeRow,
    PrototypeProbe,
    PrototypeRegion,
    PrototypeRegionRole,
    TrajectoryHypothesis,
    analyze_region_hypothesis,
    frame_opportunities,
    select_prototype_regions,
    source_bound_seed_hz,
    summarize_hypothesis,
)
from leo.analysis.starlink import NumericalStatus, qin_edge_pilot_frame
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    qin_edge_pilot_symbols,
)

RATE = 2_500_000


def _probe(
    index: int,
    *,
    sample_start: int | None = None,
    time_s: float | None = None,
    margin: float = 0.20,
    exact_score: float = 0.50,
    raw_cfo_hz: float = 100_000.0,
    alias_index: int = 0,
) -> PrototypeProbe:
    start = 100 + 100 * index if sample_start is None else sample_start
    return PrototypeProbe(
        probe_index=index,
        canonical_observation_id=f"canonical-{index}",
        source_observation_id=f"source-{index}",
        detection_time_s=index / 10 if time_s is None else time_s,
        detection_sample_start=start,
        local_epoch_sample=1,
        raw_source_cfo_hz=raw_cfo_hz,
        observation_alias_index=alias_index,
        exact_score=exact_score,
        control_score=0.01,
        margin=margin,
    )


def _hypothesis(
    *,
    trajectory_id: str = "trajectory",
    alias_index: int = 0,
    coefficients_hz: tuple[float, ...] = (100_000.0,),
) -> TrajectoryHypothesis:
    return TrajectoryHypothesis(
        trajectory_id=trajectory_id,
        branch_id="branch",
        alias_index=alias_index,
        reference_time_s=0.0,
        absolute_coefficients_hz=coefficients_hz,
        automatic_correction_eligible=False,
    )


def _point_estimate(
    index: int,
    *,
    supported: bool,
    diagnostic_value: float | None,
    status: NumericalStatus = NumericalStatus.COMPLETE,
    search_boundary: bool = False,
) -> PilotFrameCfoEstimate:
    complete = status is NumericalStatus.COMPLETE
    residual = float(index) if complete else None
    return PilotFrameCfoEstimate(
        status=status,
        measurement_supported=supported,
        rejection_reasons=(
            ()
            if supported
            else ("search_boundary",)
            if search_boundary
            else ("synthetic_rejection",)
        ),
        frame_start_sample=10_000 + index,
        reference_sample=10_100.0 + index,
        residual_cfo_hz=residual,
        absolute_cfo_hz=None if residual is None else 100_000.0 + residual,
        frequency_uncertainty_hz=1.0 if complete else None,
        exact_coherence=0.5 if complete else None,
        control_coherence=0.01 if complete else None,
        coherence_margin=0.49 if complete else None,
        even_residual_cfo_hz=residual,
        odd_residual_cfo_hz=residual,
        even_odd_disagreement_hz=diagnostic_value if complete else None,
        timing_spread_hz=diagnostic_value if complete else None,
        half_frame_difference_z=diagnostic_value if complete else None,
        tone_deletion_spread_hz=diagnostic_value if complete else None,
        search_boundary=search_boundary,
    )


def _row(
    index: int,
    hypothesis: TrajectoryHypothesis,
    *,
    primary: PilotFrameCfoEstimate | None,
    strong: bool,
    crosses_refill: bool = False,
    sensitivity: PilotFrameCfoEstimate | None = None,
    split: PilotFrameCfoSplitValidation | None = None,
) -> FrameCfoPrototypeRow:
    time_s = 1.0 + index / 750.0
    return FrameCfoPrototypeRow(
        row_id=f"row-{index}",
        region_id=f"region-{index // 8}",
        region_role=(
            PrototypeRegionRole.HIGH_MARGIN if strong else PrototypeRegionRole.LOW_POSITIVE_MARGIN
        ),
        strong_interior_opportunity=strong,
        trajectory_id=hypothesis.trajectory_id,
        branch_id=hypothesis.branch_id,
        trajectory_alias_index=hypothesis.alias_index,
        canonical_observation_id="canonical",
        source_observation_id="source",
        observation_alias_index=0,
        frame_index=index,
        frame_start_sample=10_000 + index,
        frame_time_s=time_s,
        continuity_segment=int(crosses_refill),
        crosses_refill_boundary=crosses_refill,
        raw_source_cfo_hz=100_000.0,
        source_bound_seed_hz=100_000.0,
        trajectory_model_cfo_hz=float(hypothesis.model_cfo_hz(time_s)),
        primary=primary,
        sensitivity=sensitivity,
        split_validation=split,
    )


def test_six_disjoint_region_roles_are_deterministic_under_probe_permutation() -> None:
    def candidate(index: int) -> PrototypeProbe:
        margin = 0.06 + ((index * 7) % 13) / 100
        if index == 5:
            margin = 0.90
        elif index == 25:
            margin = 0.001
        return _probe(index, margin=margin)

    probes = tuple(candidate(index) for index in range(30))
    refill_boundaries = tuple(100 + 100 * index + 1 + 37 for index in (8, 14, 22, 28))
    generator = np.random.default_rng(0xCF0)
    permutations = (
        probes,
        tuple(reversed(probes)),
        tuple(probes[int(index)] for index in generator.permutation(len(probes))),
    )

    selections = tuple(
        select_prototype_regions(
            values,
            refill_boundaries=refill_boundaries,
            sample_rate_hz=1_000,
            recording_sample_count=4_000,
        )
        for values in permutations
    )
    identities = tuple(
        tuple(
            (item.role, item.probe.probe_index, item.sample_start, item.refill_boundary_sample)
            for item in selection
        )
        for selection in selections
    )

    assert identities[0] == identities[1] == identities[2]
    selected = selections[0]
    assert tuple(item.role for item in selected) == tuple(PrototypeRegionRole)
    assert len({item.region_id for item in selected}) == 6
    by_start = sorted(selected, key=lambda item: item.sample_start)
    assert all(
        left.sample_stop <= right.sample_start
        for left, right in zip(by_start, by_start[1:], strict=False)
    )
    boundary = selected[-1]
    assert boundary.role is PrototypeRegionRole.REFILL_BOUNDARY
    assert boundary.refill_boundary_sample is not None
    assert boundary.sample_start < boundary.refill_boundary_sample < boundary.sample_stop


def test_fractional_lattice_is_exact_and_refill_detection_includes_both_guards() -> None:
    sample_start = 1_000_001
    sample_count = round(0.075 * RATE)
    region = PrototypeRegion(
        region_id="region",
        role=PrototypeRegionRole.HIGH_MARGIN,
        probe=_probe(0, sample_start=sample_start - 1, time_s=0.4),
        sample_start=sample_start,
        sample_count=sample_count,
        strong_glrt_region=True,
        refill_boundary_sample=None,
    )
    expected_local = tuple(round(index * RATE / 750.0) for index in range(56))
    target_start = sample_start + expected_local[10]
    boundary = target_start + 1_000

    opportunities = frame_opportunities(
        region,
        sample_rate_hz=RATE,
        refill_boundaries=(boundary,),
    )

    assert len(opportunities) == 56
    assert tuple(item.local_frame_start for item in opportunities) == expected_local
    assert tuple(np.diff(expected_local[:10])) == (
        3333,
        3334,
        3333,
        3333,
        3334,
        3333,
        3333,
        3334,
        3333,
    )
    frame_content = round(302 * RATE * OFDM_SYMBOL_DURATION_S)
    assert opportunities[-1].local_frame_start + frame_content <= sample_count
    assert round(56 * RATE / 750.0) + frame_content > sample_count
    assert tuple(item.frame_index for item in opportunities if item.crosses_refill_boundary) == (
        10,
    )
    assert not opportunities[10].strong_interior_opportunity
    assert opportunities[11].continuity_segment == 1

    guard_cases = (
        (target_start - 1, False),
        (target_start, True),
        (target_start + frame_content, True),
        (target_start + frame_content + 1, False),
    )
    for refill_sample, expected_crossing in guard_cases:
        tested = frame_opportunities(
            region,
            sample_rate_hz=RATE,
            refill_boundaries=(refill_sample,),
        )[10]
        assert tested.crosses_refill_boundary is expected_crossing


def test_source_bound_seed_preserves_explicit_alias_hypotheses() -> None:
    probe = _probe(0, raw_cfo_hz=-17_250.0, alias_index=-2)
    raw_alias = _hypothesis(trajectory_id="raw-alias", alias_index=-2)
    lifted_alias = _hypothesis(trajectory_id="lifted-alias", alias_index=-1)

    raw_seed = source_bound_seed_hz(probe, raw_alias)
    lifted_seed = source_bound_seed_hz(probe, lifted_alias)

    assert raw_seed == probe.raw_source_cfo_hz
    assert lifted_seed - raw_seed == pytest.approx(SYMBOL_CFO_ALIAS_SPACING_HZ)
    assert raw_alias.trajectory_id != lifted_alias.trajectory_id
    assert raw_alias.alias_index != lifted_alias.alias_index


def test_split_validation_membership_is_unchanged_by_corrupted_odd_qin() -> None:
    expected = qin_edge_pilot_symbols(StarlinkEdge.LOWER)
    control = qin_edge_pilot_symbols(
        StarlinkEdge.LOWER,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )
    times_s = (np.arange(300, dtype=float) - 149.5) * OFDM_SYMBOL_DURATION_S
    channel = np.linspace(0.5, 1.5, 8) * np.exp(0.2j * np.arange(8))

    def cube(odd_cfo_hz: float) -> np.ndarray:
        matched = np.empty((300, 8), dtype=np.complex128)
        matched[::2] = channel * np.exp(2j * np.pi * 300.0 * times_s[::2, None])
        matched[1::2] = channel * np.exp(2j * np.pi * odd_cfo_hz * times_s[1::2, None])
        return matched * expected

    arguments = {
        "expected": expected,
        "control": control,
        "frame_start_sample": 1,
        "reference_sample": 100.0,
        "acquisition_absolute_cfo_hz": 0.0,
        "config": PilotFrameCfoConfig(),
    }
    clean = _estimate_edge_pilot_frame_cfo_split_from_cube(cube(300.0), **arguments)
    corrupted = _estimate_edge_pilot_frame_cfo_split_from_cube(cube(2_500.0), **arguments)

    assert clean.training_supported
    assert corrupted.training_supported
    assert clean.training_rejection_reasons == corrupted.training_rejection_reasons == ()
    assert clean.even_residual_cfo_hz == corrupted.even_residual_cfo_hz
    assert clean.even_exact_coherence == corrupted.even_exact_coherence
    assert clean.even_control_coherence == corrupted.even_control_coherence
    assert clean.even_search_boundary == corrupted.even_search_boundary is False
    assert clean.odd_residual_cfo_hz == pytest.approx(300.0, abs=0.1)
    assert corrupted.odd_search_boundary
    assert corrupted.odd_residual_cfo_hz == pytest.approx(2_000.0, abs=0.1)


def test_wide_sensitivity_success_never_substitutes_for_primary_boundary_failure() -> None:
    frame_content = round(302 * RATE * OFDM_SYMBOL_DURATION_S)
    frame_start = 1_234_567
    acquisition_cfo_hz = 200_000.0
    residual_cfo_hz = 2_500.0
    template = np.asarray(qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER), np.complex128)
    samples = np.zeros(frame_content + 2, dtype=np.complex128)
    indexes = np.arange(frame_content)
    samples[1 + indexes] = template[:frame_content] * np.exp(
        2j * np.pi * (acquisition_cfo_hz + residual_cfo_hz) * (frame_start + indexes) / RATE
    )
    probe = _probe(
        0,
        sample_start=frame_start - 1,
        time_s=frame_start / RATE,
        raw_cfo_hz=acquisition_cfo_hz,
    )
    region = PrototypeRegion(
        region_id="one-frame-region",
        role=PrototypeRegionRole.HIGH_MARGIN,
        probe=probe,
        sample_start=frame_start,
        sample_count=frame_content,
        strong_glrt_region=True,
        refill_boundary_sample=None,
    )
    hypothesis = _hypothesis(coefficients_hz=(acquisition_cfo_hz + residual_cfo_hz,))

    row = analyze_region_hypothesis(
        samples,
        region=region,
        hypothesis=hypothesis,
        edge=StarlinkEdge.LOWER,
        sample_rate_hz=RATE,
        refill_boundaries=(),
    )[0]

    assert row.primary is not None and row.sensitivity is not None
    assert not row.primary.measurement_supported
    assert row.primary.search_boundary
    assert row.primary.residual_cfo_hz == pytest.approx(2_000.0, abs=0.1)
    assert row.sensitivity.measurement_supported
    assert row.sensitivity.residual_cfo_hz == pytest.approx(residual_cfo_hz, abs=0.5)
    assert not row.sensitivity_substituted
    assert row.document()["primary"] != row.document()["sensitivity"]

    summary = summarize_hypothesis((row,), hypothesis)
    assert summary["wide_supported_primary_unsupported_count"] == 1
    assert summary["sensitivity_substitution_count"] == 0
    assert summary["strong_interior_supported_count"] == 0


def test_summary_accounting_uses_all_opportunities_and_pre_rejection_diagnostics() -> None:
    hypothesis = _hypothesis()
    rows: list[FrameCfoPrototypeRow] = []
    diagnostic_values = [float(index) for index in range(7)]
    for index, value in enumerate(diagnostic_values):
        rows.append(
            _row(
                index,
                hypothesis,
                primary=_point_estimate(index, supported=True, diagnostic_value=value),
                strong=True,
            )
        )
    rows.append(
        _row(
            7,
            hypothesis,
            primary=_point_estimate(
                7,
                supported=False,
                diagnostic_value=200.0,
                search_boundary=True,
            ),
            strong=True,
        )
    )
    rows.append(_row(8, hypothesis, primary=None, strong=True))
    rows.append(
        _row(
            9,
            hypothesis,
            primary=_point_estimate(
                9,
                supported=False,
                diagnostic_value=None,
                status=NumericalStatus.NO_RESULT,
            ),
            strong=True,
        )
    )
    for index, value in ((10, 300.0), (11, 400.0)):
        rows.append(
            _row(
                index,
                hypothesis,
                primary=_point_estimate(index, supported=False, diagnostic_value=value),
                strong=False,
            )
        )
    rows.append(
        _row(
            12,
            hypothesis,
            primary=None,
            strong=False,
            crosses_refill=True,
        )
    )

    summary = summarize_hypothesis(tuple(rows), hypothesis)
    expected_diagnostic = np.asarray([*diagnostic_values, 200.0, 300.0, 400.0])

    assert summary["frame_opportunity_count"] == 13
    assert summary["refill_crossing_frame_count"] == 1
    assert summary["numerically_complete_frame_count"] == 10
    assert summary["supported_frame_count"] == 7
    assert summary["strong_interior_opportunity_count"] == 10
    assert summary["strong_interior_supported_count"] == 7
    assert summary["strong_interior_retention_fraction"] == pytest.approx(0.7)
    assert summary["strong_search_boundary_fraction"] == pytest.approx(1 / 8)
    assert summary["even_odd_p95_hz"] == pytest.approx(np.percentile(expected_diagnostic, 95))
    assert summary["timing_spread_p95_hz"] == summary["even_odd_p95_hz"]
    assert summary["tone_deletion_spread_p95_hz"] == summary["even_odd_p95_hz"]
    population = str(summary["diagnostics_population"])
    assert "numerically complete continuity-safe frames" in population
    assert "no reported diagnostic selects its own population" in population
    assert summary["heldout_validation"]["status"] == "insufficient"
