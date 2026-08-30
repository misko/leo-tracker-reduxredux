"""Causal synthetic multi-dwell catalogue-mode filtering.

This module is a deliberately bounded Rao--Blackwellized HMM/filter core for
WP4/WP7 development.  It is a pure analyzer: callers provide ordered synthetic
CFO dwells and a complete, response-free bank of fixed catalogue predictions.
No storage, TLE propagation, HTTP, CLI, IQ, or real-corpus access occurs here.

Discrete NULL/NORAD paths remain separate.  There is exactly one source state
per dwell; ``K<=2`` in this slice means at most two distinct NORAD identities
across a path's history, not two simultaneous emitters in one dwell.
Conditional on each path, a scalar
hardware-drift error follows a Gaussian random walk only inside one declared
hardware epoch.  Every dwell receives the same proper zero-mean Gaussian local
CFO-offset prior.  That offset is analytically marginalized when the dwell is
scored and recovered only as a posterior diagnostic.  Consequently there is a
proper gauge and no candidate receives a hidden per-dwell slope or time shift.

For dwell ``d``, every child is scored from its parent's frozen posterior
before any response in ``d`` is assimilated.  Later response values are not
used for that score or update, although the whole caller-provided synthetic
input envelope is structurally validated before filtering.  This is not a
cryptographic data-opening or authority boundary.  Fixed-lag backward
smoothing, tau profiling, orbit-state updates, and ECM are intentionally not
implemented by this first synthetic core.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray

type CatalogueIdentity = int | None
type NuisanceResetReason = Literal[
    "initial-prior",
    "hardware-epoch-change",
    "validity-gap",
]
type AbstentionDiagnostic = Literal[
    "beam-pruned",
    "descriptive-close-mode-ambiguity",
    "exact-discrete-tie",
    "null-nearest",
]

_TIE_ULPS = 8.0
_ALGORITHM_VERSION = "causal-rb-multi-dwell-filter-v1"


class MultiDwellInputError(ValueError):
    """The frozen synthetic input family is incomplete or inconsistent."""


class MultiDwellNumericalError(ValueError):
    """A probability or Gaussian calculation is not numerically trustworthy."""


class MultiDwellWorkLimitError(ValueError):
    """The predeclared discrete-extension work bound would be exceeded."""


@dataclass(frozen=True, slots=True)
class SyntheticCfoDwell:
    """One chronological synthetic dwell with a response-free support grid.

    ``support_offsets_s`` are relative to ``center_utc_ns``.  Requiring them to
    be strictly ordered and centred defines the reported dwell-local offset at
    the support centre and avoids a silent offset/drift reparameterization.
    """

    dwell_id: str
    center_utc_ns: int
    hardware_epoch_id: str
    support_offsets_s: tuple[float, ...]
    measured_cfo_hz: tuple[float, ...]
    measurement_standard_uncertainties_hz: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.dwell_id:
            raise MultiDwellInputError("dwell_id cannot be empty")
        if isinstance(self.center_utc_ns, bool) or not isinstance(self.center_utc_ns, int):
            raise MultiDwellInputError("center_utc_ns must be an integer nanosecond time")
        if not 0 <= self.center_utc_ns <= 2**63 - 1:
            raise MultiDwellInputError("center_utc_ns must fit a nonnegative signed 64-bit UTC")
        if not self.hardware_epoch_id:
            raise MultiDwellInputError("hardware_epoch_id cannot be empty")
        count = len(self.support_offsets_s)
        if count < 2:
            raise MultiDwellInputError("each dwell requires at least two support rows")
        if (
            len(self.measured_cfo_hz) != count
            or len(self.measurement_standard_uncertainties_hz) != count
        ):
            raise MultiDwellInputError("dwell support, response, and uncertainty lengths differ")
        _require_all_finite("support_offsets_s", self.support_offsets_s)
        _require_all_finite("measured_cfo_hz", self.measured_cfo_hz)
        _require_all_positive(
            "measurement_standard_uncertainties_hz",
            self.measurement_standard_uncertainties_hz,
        )
        if any(
            right <= left
            for left, right in zip(
                self.support_offsets_s,
                self.support_offsets_s[1:],
                strict=False,
            )
        ):
            raise MultiDwellInputError("support_offsets_s must be strictly increasing")
        support_scale = max(1.0, *(abs(item) for item in self.support_offsets_s))
        centering_tolerance = 1e-12 * support_scale * count
        if not math.isfinite(centering_tolerance):
            raise MultiDwellInputError("support_offsets_s scale is not representable")
        try:
            support_sum = math.fsum(self.support_offsets_s)
        except OverflowError as error:
            raise MultiDwellInputError("support_offsets_s sum is not representable") from error
        if not math.isclose(
            support_sum,
            0.0,
            rel_tol=0.0,
            abs_tol=centering_tolerance,
        ):
            raise MultiDwellInputError(
                "support_offsets_s must be centred to define the local-offset gauge"
            )


@dataclass(frozen=True, slots=True)
class SyntheticCandidateDwellPrediction:
    """One candidate's precomputed response-free curve for one dwell."""

    dwell_id: str
    predicted_cfo_hz: tuple[float, ...]
    prediction_standard_uncertainties_hz: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.dwell_id:
            raise MultiDwellInputError("prediction dwell_id cannot be empty")
        if not self.predicted_cfo_hz:
            raise MultiDwellInputError("candidate dwell prediction cannot be empty")
        if len(self.prediction_standard_uncertainties_hz) != len(self.predicted_cfo_hz):
            raise MultiDwellInputError("candidate prediction and uncertainty lengths differ")
        _require_all_finite("predicted_cfo_hz", self.predicted_cfo_hz)
        _require_all_nonnegative(
            "prediction_standard_uncertainties_hz",
            self.prediction_standard_uncertainties_hz,
        )


@dataclass(frozen=True, slots=True)
class SyntheticCandidateTrajectory:
    """A complete fixed-tau prediction trajectory for one catalogue member."""

    catalog_number: int
    dwell_predictions: tuple[SyntheticCandidateDwellPrediction, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.catalog_number, bool)
            or not isinstance(self.catalog_number, int)
            or self.catalog_number <= 0
        ):
            raise MultiDwellInputError("catalog_number must be a positive integer")
        if not self.dwell_predictions:
            raise MultiDwellInputError("candidate trajectory cannot be empty")
        dwell_ids = tuple(item.dwell_id for item in self.dwell_predictions)
        if len(set(dwell_ids)) != len(dwell_ids):
            raise MultiDwellInputError("candidate trajectory repeats a dwell")


@dataclass(frozen=True, slots=True)
class SyntheticMultiDwellPredictionBank:
    """Complete, frozen response-free synthetic catalogue predictions."""

    dwell_ids: tuple[str, ...]
    candidates: tuple[SyntheticCandidateTrajectory, ...]
    source_candidate_count: int
    response_accessed: Literal[False] = field(default=False, init=False)
    tau_policy: Literal["fixed-precomputed-v1"] = field(default="fixed-precomputed-v1", init=False)

    def __post_init__(self) -> None:
        if not self.dwell_ids or any(not item for item in self.dwell_ids):
            raise MultiDwellInputError("prediction bank requires nonempty dwell identities")
        if len(set(self.dwell_ids)) != len(self.dwell_ids):
            raise MultiDwellInputError("prediction bank repeats a dwell identity")
        catalog_numbers = tuple(item.catalog_number for item in self.candidates)
        if not catalog_numbers:
            raise MultiDwellInputError("prediction bank requires at least one catalogue candidate")
        if catalog_numbers != tuple(sorted(catalog_numbers)) or len(set(catalog_numbers)) != len(
            catalog_numbers
        ):
            raise MultiDwellInputError(
                "candidate trajectories must be unique and ordered by catalog_number"
            )
        if (
            isinstance(self.source_candidate_count, bool)
            or not isinstance(self.source_candidate_count, int)
            or self.source_candidate_count != len(self.candidates)
        ):
            raise MultiDwellInputError(
                "synthetic filter rejects a truncated or inconsistent candidate bank"
            )
        for candidate in self.candidates:
            if tuple(item.dwell_id for item in candidate.dwell_predictions) != self.dwell_ids:
                raise MultiDwellInputError(
                    "every candidate must cover the exact ordered dwell inventory"
                )


@dataclass(frozen=True, slots=True)
class MultiDwellFilterConfig:
    """Bounded controls for the causal filter.

    Log weights are unnormalized *family* potentials.  Initial-candidate,
    NULL-to-candidate birth, and candidate-to-other-candidate handoff weights
    describe total family mass; that mass is divided uniformly over feasible
    members only after families are normalized.  Thus adding candidates does
    not accidentally multiply birth or handoff prior mass.

    The optional ambiguity margin is an explicitly descriptive synthetic
    diagnostic.  It is not calibrated, does not assert identity, and must not
    be promoted to an operational gate without a separate frozen calibration.
    """

    maximum_distinct_catalogues: int = 2
    retained_mode_limit: int = 64
    maximum_evaluated_extensions: int = 100_000
    maximum_support_rows_per_dwell: int = 512
    maximum_evaluated_support_rows: int = 2_000_000
    initial_drift_mean_hz_per_s: float = 0.0
    initial_drift_standard_uncertainty_hz_per_s: float = 2.0
    drift_random_walk_standard_uncertainty_hz_per_s_per_sqrt_s: float = 0.02
    dwell_offset_prior_standard_uncertainty_hz: float = 100.0
    maximum_nuisance_propagation_gap_s: float = 600.0
    null_prediction_cfo_hz: float = 0.0
    null_prediction_standard_uncertainty_hz: float = 1.0
    initial_null_log_weight: float = 0.0
    initial_candidate_log_weight: float = 0.0
    null_stay_log_weight: float = 0.0
    null_to_candidate_log_weight: float = -1.0
    candidate_to_null_log_weight: float = -1.0
    same_identity_log_weight: float = 0.0
    handoff_log_weight: float = -2.0
    descriptive_ambiguity_negative_log_joint_margin: float | None = None
    maximum_condition_number: float = 1e12

    def __post_init__(self) -> None:
        for integer_name, integer_value in (
            ("maximum_distinct_catalogues", self.maximum_distinct_catalogues),
            ("retained_mode_limit", self.retained_mode_limit),
            ("maximum_evaluated_extensions", self.maximum_evaluated_extensions),
            ("maximum_support_rows_per_dwell", self.maximum_support_rows_per_dwell),
            ("maximum_evaluated_support_rows", self.maximum_evaluated_support_rows),
        ):
            if (
                isinstance(integer_value, bool)
                or not isinstance(integer_value, int)
                or integer_value <= 0
            ):
                raise MultiDwellInputError(f"{integer_name} must be a positive integer")
        if self.maximum_distinct_catalogues > 2:
            raise MultiDwellInputError(
                "this bounded filter supports at most two distinct catalogue identities"
            )
        _require_finite("initial_drift_mean_hz_per_s", self.initial_drift_mean_hz_per_s)
        for positive_name, positive_value in (
            (
                "initial_drift_standard_uncertainty_hz_per_s",
                self.initial_drift_standard_uncertainty_hz_per_s,
            ),
            (
                "drift_random_walk_standard_uncertainty_hz_per_s_per_sqrt_s",
                self.drift_random_walk_standard_uncertainty_hz_per_s_per_sqrt_s,
            ),
            (
                "dwell_offset_prior_standard_uncertainty_hz",
                self.dwell_offset_prior_standard_uncertainty_hz,
            ),
            (
                "maximum_nuisance_propagation_gap_s",
                self.maximum_nuisance_propagation_gap_s,
            ),
            (
                "null_prediction_standard_uncertainty_hz",
                self.null_prediction_standard_uncertainty_hz,
            ),
            ("maximum_condition_number", self.maximum_condition_number),
        ):
            _require_positive(positive_name, positive_value)
        _require_finite("null_prediction_cfo_hz", self.null_prediction_cfo_hz)
        if self.null_prediction_cfo_hz != 0.0:
            raise MultiDwellInputError("restricted NULL prediction must equal exactly zero CFO")
        for weight_name, weight_value in (
            ("initial_null_log_weight", self.initial_null_log_weight),
            ("initial_candidate_log_weight", self.initial_candidate_log_weight),
            ("null_stay_log_weight", self.null_stay_log_weight),
            ("null_to_candidate_log_weight", self.null_to_candidate_log_weight),
            ("candidate_to_null_log_weight", self.candidate_to_null_log_weight),
            ("same_identity_log_weight", self.same_identity_log_weight),
            ("handoff_log_weight", self.handoff_log_weight),
        ):
            _require_finite(weight_name, weight_value)
        if self.descriptive_ambiguity_negative_log_joint_margin is not None:
            _require_nonnegative(
                "descriptive_ambiguity_negative_log_joint_margin",
                self.descriptive_ambiguity_negative_log_joint_margin,
            )


@dataclass(frozen=True, slots=True)
class DwellNuisanceUpdate:
    """One conditional nuisance prediction and post-assimilation estimate."""

    dwell_id: str
    hardware_epoch_id: str
    reset_reason: NuisanceResetReason | None
    predicted_drift_mean_hz_per_s: float
    predicted_drift_standard_uncertainty_hz_per_s: float
    filtered_drift_mean_hz_per_s: float
    filtered_drift_standard_uncertainty_hz_per_s: float
    dwell_offset_mean_hz: float
    dwell_offset_standard_uncertainty_hz: float
    drift_offset_covariance_hz2_per_s: float


@dataclass(frozen=True, slots=True)
class MultiDwellModeScore:
    """One retained discrete path after the named dwell is assimilated."""

    rank: int
    assignments: tuple[CatalogueIdentity, ...]
    active_catalog_numbers: tuple[int, ...]
    transition_negative_log_probability: float
    next_dwell_predictive_negative_log_likelihood: float
    cumulative_negative_log_joint: float
    posterior_probability_within_retained_beam: float
    nuisance: DwellNuisanceUpdate

    @property
    def current_identity(self) -> CatalogueIdentity:
        return self.assignments[-1]


@dataclass(frozen=True, slots=True)
class RollingDwellAssociation:
    """Causal ranking recorded after scoring and assimilating one dwell."""

    dwell_index: int
    dwell_id: str
    evaluated_extension_count: int
    evaluated_support_row_count: int
    retained_mode_count: int
    nominal_retained_mode_limit: int
    tie_expanded_retained_inventory: bool
    conditional_mass_retained_from_evaluated_extensions: float
    mixture_predictive_negative_log_likelihood: float
    mixture_predictive_conditioned_on_pruned_parent_beam: bool
    modes: tuple[MultiDwellModeScore, ...]
    nearest_identity: CatalogueIdentity
    identity_ambiguity_set: tuple[CatalogueIdentity, ...]
    exact_discrete_tie: bool
    exact_tie_tolerance: float | None
    descriptive_close_mode_ambiguity: bool
    current_step_beam_pruned: bool
    prior_or_current_beam_pruned: bool
    abstention_recommended: bool
    abstention_diagnostics: tuple[AbstentionDiagnostic, ...]
    score_before_assimilation: Literal[True] = field(default=True, init=False)
    later_response_used_for_current_score_or_assimilation: Literal[False] = field(
        default=False, init=False
    )
    whole_input_envelope_validated_before_filtering: Literal[True] = field(default=True, init=False)
    posterior_conditioned_on_retained_beam: Literal[True] = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class MultiDwellCatalogueFilterResult:
    """Synthetic causal-filter result; no satellite identity is claimed."""

    dwell_ids: tuple[str, ...]
    catalog_numbers: tuple[int, ...]
    rolling: tuple[RollingDwellAssociation, ...]
    final_modes: tuple[MultiDwellModeScore, ...]
    evaluated_extension_count: int
    evaluated_support_row_count: int
    any_pruning: bool
    final_abstention_recommended: bool
    final_abstention_diagnostics: tuple[AbstentionDiagnostic, ...]
    algorithm_version: Literal["causal-rb-multi-dwell-filter-v1"] = field(
        default="causal-rb-multi-dwell-filter-v1", init=False
    )
    nuisance_model: Literal[
        "epoch-scoped-scalar-drift-random-walk-plus-marginal-dwell-offset-v1"
    ] = field(
        default=("epoch-scoped-scalar-drift-random-walk-plus-marginal-dwell-offset-v1"),
        init=False,
    )
    tau_policy: Literal["fixed-precomputed-v1"] = field(default="fixed-precomputed-v1", init=False)
    discrete_modes_moment_matched: Literal[False] = field(default=False, init=False)
    fixed_lag_backward_smoothing_performed: Literal[False] = field(default=False, init=False)
    ecm_performed: Literal[False] = field(default=False, init=False)
    candidate_only: Literal[True] = field(default=True, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)
    thresholds_are_calibrated: Literal[False] = field(default=False, init=False)
    response_free_prediction_bank_required: Literal[True] = field(default=True, init=False)
    emitter_model: Literal["one-source-state-per-dwell-k02-distinct-history-v1"] = field(
        default="one-source-state-per-dwell-k02-distinct-history-v1", init=False
    )
    simultaneous_two_emitter_modelled: Literal[False] = field(default=False, init=False)
    nuisance_scope: Literal["receiver-local-nontransferable-v1"] = field(
        default="receiver-local-nontransferable-v1", init=False
    )
    nuisance_transferable_to_satellite_frequency_state_v1: Literal[False] = field(
        default=False, init=False
    )


@dataclass(frozen=True, slots=True)
class DwellMarginalScore:
    """Analytic Gaussian dwell score and conditional nuisance posterior."""

    observation_count: int
    predictive_negative_log_likelihood: float
    mahalanobis_squared: float
    log_determinant_covariance: float
    drift_posterior_mean_hz_per_s: float
    drift_posterior_standard_uncertainty_hz_per_s: float
    dwell_offset_posterior_mean_hz: float
    dwell_offset_posterior_standard_uncertainty_hz: float
    drift_offset_posterior_covariance_hz2_per_s: float


@dataclass(frozen=True, slots=True)
class _Path:
    assignments: tuple[CatalogueIdentity, ...]
    active_catalog_numbers: tuple[int, ...]
    cumulative_negative_log_joint: float
    drift_mean_hz_per_s: float
    drift_variance_hz2_per_s2: float
    hardware_epoch_id: str
    center_utc_ns: int
    last_transition_negative_log_probability: float
    last_predictive_negative_log_likelihood: float
    last_nuisance: DwellNuisanceUpdate


def filter_multi_dwell_catalogue_modes(
    dwells: tuple[SyntheticCfoDwell, ...],
    prediction_bank: SyntheticMultiDwellPredictionBank,
    *,
    config: MultiDwellFilterConfig,
) -> MultiDwellCatalogueFilterResult:
    """Run a bounded rolling NULL/NORAD filter over ordered synthetic dwells.

    Each rolling entry is causal: child likelihoods use only the frozen parent
    nuisance posterior.  Assimilation occurs only after that likelihood is
    computed.  The returned posterior probabilities are conditional on the
    retained beam; any pruning is explicit and recommends abstention.
    """

    config.__post_init__()
    _preflight_support_row_inventory(dwells=dwells, config=config)
    _validate_filter_inputs(dwells=dwells, prediction_bank=prediction_bank)
    candidate_numbers = tuple(item.catalog_number for item in prediction_bank.candidates)
    prediction_lookup = _prediction_lookup(prediction_bank)
    parents: tuple[_Path, ...] = ()
    rolling: list[RollingDwellAssociation] = []
    total_evaluated = 0
    total_evaluated_support_rows = 0
    any_pruning = False

    for dwell_index, dwell in enumerate(dwells):
        parent_beam_was_pruned = any_pruning
        if dwell_index == 0:
            extension_count = len(candidate_numbers) + 1
        else:
            extension_count = sum(
                len(
                    _feasible_next_identities(
                        parent=parent,
                        candidate_numbers=candidate_numbers,
                        maximum_distinct_catalogues=config.maximum_distinct_catalogues,
                    )
                )
                for parent in parents
            )
        if total_evaluated + extension_count > config.maximum_evaluated_extensions:
            raise MultiDwellWorkLimitError(
                "multi-dwell filter would exceed maximum_evaluated_extensions before "
                f"scoring dwell {dwell.dwell_id!r} "
                f"({total_evaluated + extension_count} > "
                f"{config.maximum_evaluated_extensions})"
            )
        evaluated_support_rows = extension_count * len(dwell.measured_cfo_hz)
        if (
            total_evaluated_support_rows + evaluated_support_rows
            > config.maximum_evaluated_support_rows
        ):
            raise MultiDwellWorkLimitError(
                "multi-dwell filter would exceed maximum_evaluated_support_rows before "
                f"scoring dwell {dwell.dwell_id!r} "
                f"({total_evaluated_support_rows + evaluated_support_rows} > "
                f"{config.maximum_evaluated_support_rows})"
            )
        extensions: list[_Path] = []
        if dwell_index == 0:
            choices = (None, *candidate_numbers)
            log_probabilities = _initial_log_probabilities(
                candidate_count=len(candidate_numbers),
                config=config,
            )
            for identity, log_probability in zip(choices, log_probabilities, strict=True):
                extensions.append(
                    _score_initial_path(
                        dwell=dwell,
                        identity=identity,
                        transition_negative_log_probability=-log_probability,
                        prediction_lookup=prediction_lookup,
                        config=config,
                    )
                )
        else:
            for parent in parents:
                choices = _feasible_next_identities(
                    parent=parent,
                    candidate_numbers=candidate_numbers,
                    maximum_distinct_catalogues=config.maximum_distinct_catalogues,
                )
                log_probabilities = _transition_log_probabilities(
                    previous=parent.assignments[-1],
                    choices=choices,
                    config=config,
                )
                for identity, log_probability in zip(choices, log_probabilities, strict=True):
                    extensions.append(
                        _score_extension(
                            parent=parent,
                            dwell=dwell,
                            identity=identity,
                            transition_negative_log_probability=-log_probability,
                            prediction_lookup=prediction_lookup,
                            config=config,
                        )
                    )
        if len(extensions) != extension_count:
            raise AssertionError("internal discrete-extension count changed during scoring")
        total_evaluated += extension_count
        total_evaluated_support_rows += evaluated_support_rows
        ordered = _order_paths(tuple(extensions))
        mixture_predictive_nll = _mixture_predictive_negative_log_likelihood(
            children=ordered,
            parents=parents,
        )
        retained, tie_expanded = _retain_top_modes(
            ordered,
            nominal_limit=config.retained_mode_limit,
        )
        conditional_mass = _conditional_retained_mass(ordered=ordered, retained=retained)
        current_step_pruned = len(retained) < len(ordered)
        any_pruning = parent_beam_was_pruned or current_step_pruned
        public_modes = _public_modes(retained)
        nearest = public_modes[0]
        exact_tied = _top_tied_paths(retained)
        exact_tie = len(exact_tied) > 1
        exact_tolerance = (
            None
            if not exact_tie
            else max(
                _score_tie_tolerance(
                    item.cumulative_negative_log_joint,
                    retained[0].cumulative_negative_log_joint,
                )
                for item in exact_tied
            )
        )
        ambiguity_paths = _ambiguity_paths(
            retained,
            margin=config.descriptive_ambiguity_negative_log_joint_margin,
        )
        ambiguity_set = _ordered_identities(tuple(item.assignments[-1] for item in ambiguity_paths))
        descriptive_close = (
            config.descriptive_ambiguity_negative_log_joint_margin is not None
            and len(ambiguity_set) > 1
        )
        diagnostics: list[AbstentionDiagnostic] = []
        if any_pruning:
            diagnostics.append("beam-pruned")
        if descriptive_close:
            diagnostics.append("descriptive-close-mode-ambiguity")
        if exact_tie:
            diagnostics.append("exact-discrete-tie")
        if nearest.current_identity is None:
            diagnostics.append("null-nearest")
        diagnostics.sort()
        rolling.append(
            RollingDwellAssociation(
                dwell_index=dwell_index,
                dwell_id=dwell.dwell_id,
                evaluated_extension_count=len(ordered),
                evaluated_support_row_count=evaluated_support_rows,
                retained_mode_count=len(retained),
                nominal_retained_mode_limit=config.retained_mode_limit,
                tie_expanded_retained_inventory=tie_expanded,
                conditional_mass_retained_from_evaluated_extensions=conditional_mass,
                mixture_predictive_negative_log_likelihood=mixture_predictive_nll,
                mixture_predictive_conditioned_on_pruned_parent_beam=(parent_beam_was_pruned),
                modes=public_modes,
                nearest_identity=nearest.current_identity,
                identity_ambiguity_set=ambiguity_set,
                exact_discrete_tie=exact_tie,
                exact_tie_tolerance=exact_tolerance,
                descriptive_close_mode_ambiguity=descriptive_close,
                current_step_beam_pruned=current_step_pruned,
                prior_or_current_beam_pruned=any_pruning,
                abstention_recommended=bool(diagnostics),
                abstention_diagnostics=tuple(diagnostics),
            )
        )
        parents = retained

    final = rolling[-1]
    final_diagnostics = set(final.abstention_diagnostics)
    if any_pruning:
        final_diagnostics.add("beam-pruned")
    ordered_final_diagnostics = tuple(sorted(final_diagnostics))
    return MultiDwellCatalogueFilterResult(
        dwell_ids=tuple(item.dwell_id for item in dwells),
        catalog_numbers=candidate_numbers,
        rolling=tuple(rolling),
        final_modes=final.modes,
        evaluated_extension_count=total_evaluated,
        evaluated_support_row_count=total_evaluated_support_rows,
        any_pruning=any_pruning,
        final_abstention_recommended=bool(ordered_final_diagnostics),
        final_abstention_diagnostics=ordered_final_diagnostics,
    )


def marginalize_dwell_nuisance(
    residual_cfo_hz: tuple[float, ...],
    support_offsets_s: tuple[float, ...],
    independent_standard_uncertainties_hz: tuple[float, ...],
    *,
    drift_prior_mean_hz_per_s: float,
    drift_prior_standard_uncertainty_hz_per_s: float,
    dwell_offset_prior_standard_uncertainty_hz: float,
    maximum_condition_number: float = 1e12,
) -> DwellMarginalScore:
    """Marginalize a proper scalar drift and dwell-local offset analytically."""

    count = len(residual_cfo_hz)
    if (
        count < 2
        or len(support_offsets_s) != count
        or len(independent_standard_uncertainties_hz) != count
    ):
        raise MultiDwellInputError("dwell nuisance score requires equal lengths >= 2")
    _require_all_finite("residual_cfo_hz", residual_cfo_hz)
    _require_all_finite("support_offsets_s", support_offsets_s)
    _require_all_positive(
        "independent_standard_uncertainties_hz",
        independent_standard_uncertainties_hz,
    )
    _require_finite("drift_prior_mean_hz_per_s", drift_prior_mean_hz_per_s)
    _require_positive(
        "drift_prior_standard_uncertainty_hz_per_s",
        drift_prior_standard_uncertainty_hz_per_s,
    )
    _require_positive(
        "dwell_offset_prior_standard_uncertainty_hz",
        dwell_offset_prior_standard_uncertainty_hz,
    )
    _require_positive("maximum_condition_number", maximum_condition_number)

    residual = np.asarray(residual_cfo_hz, dtype=np.float64)
    offsets = np.asarray(support_offsets_s, dtype=np.float64)
    diagonal_variance = np.asarray(
        tuple(
            _checked_square(item, name="independent standard uncertainty")
            for item in independent_standard_uncertainties_hz
        ),
        dtype=np.float64,
    )
    drift_variance = _checked_square(
        drift_prior_standard_uncertainty_hz_per_s,
        name="drift prior standard uncertainty",
    )
    offset_variance = _checked_square(
        dwell_offset_prior_standard_uncertainty_hz,
        name="dwell-offset prior standard uncertainty",
    )

    design = np.column_stack((offsets, np.ones(count, dtype=np.float64)))
    prior_mean = np.asarray((drift_prior_mean_hz_per_s, 0.0), dtype=np.float64)
    try:
        with np.errstate(over="raise", divide="raise", invalid="raise"):
            centered = residual - design @ prior_mean
            inverse_diagonal = 1.0 / diagonal_variance
            prior_precision = np.asarray((1.0 / drift_variance, 1.0 / offset_variance))
            posterior_normal = np.diag(prior_precision) + design.T @ (
                inverse_diagonal[:, np.newaxis] * design
            )
            posterior_cholesky = _checked_cholesky(
                posterior_normal,
                name="dwell nuisance information matrix",
                maximum_condition_number=maximum_condition_number,
            )
            delta_information = design.T @ (inverse_diagonal * centered)
            posterior_delta = np.linalg.solve(
                posterior_cholesky.T,
                np.linalg.solve(posterior_cholesky, delta_information),
            )
            posterior_mean = prior_mean + posterior_delta
            identity = np.eye(2, dtype=np.float64)
            posterior_covariance = np.linalg.solve(
                posterior_cholesky.T,
                np.linalg.solve(posterior_cholesky, identity),
            )
            posterior_residual = centered - design @ posterior_delta
            mahalanobis_squared = float(
                posterior_residual @ (inverse_diagonal * posterior_residual)
                + posterior_delta @ (prior_precision * posterior_delta)
            )
            log_determinant = float(
                math.fsum(math.log(item) for item in diagonal_variance)
                + math.log(drift_variance)
                + math.log(offset_variance)
                + 2.0 * np.sum(np.log(np.diag(posterior_cholesky)))
            )
            negative_log_likelihood = 0.5 * (
                mahalanobis_squared + log_determinant + count * math.log(2.0 * math.pi)
            )
    except (FloatingPointError, np.linalg.LinAlgError, OverflowError) as error:
        raise MultiDwellNumericalError(
            "dwell nuisance information calculation is not representable"
        ) from error
    if (
        not math.isfinite(mahalanobis_squared)
        or mahalanobis_squared < -1e-10
        or not math.isfinite(log_determinant)
        or not math.isfinite(negative_log_likelihood)
        or np.any(~np.isfinite(posterior_mean))
        or np.any(~np.isfinite(posterior_covariance))
        or np.any(np.diag(posterior_covariance) <= 0.0)
    ):
        raise MultiDwellNumericalError("dwell nuisance posterior is not finite and proper")
    return DwellMarginalScore(
        observation_count=count,
        predictive_negative_log_likelihood=negative_log_likelihood,
        mahalanobis_squared=max(0.0, mahalanobis_squared),
        log_determinant_covariance=log_determinant,
        drift_posterior_mean_hz_per_s=float(posterior_mean[0]),
        drift_posterior_standard_uncertainty_hz_per_s=math.sqrt(float(posterior_covariance[0, 0])),
        dwell_offset_posterior_mean_hz=float(posterior_mean[1]),
        dwell_offset_posterior_standard_uncertainty_hz=math.sqrt(float(posterior_covariance[1, 1])),
        drift_offset_posterior_covariance_hz2_per_s=float(posterior_covariance[0, 1]),
    )


def _score_initial_path(
    *,
    dwell: SyntheticCfoDwell,
    identity: CatalogueIdentity,
    transition_negative_log_probability: float,
    prediction_lookup: dict[tuple[int, str], SyntheticCandidateDwellPrediction],
    config: MultiDwellFilterConfig,
) -> _Path:
    return _score_path(
        assignments=(),
        active_catalog_numbers=(),
        parent_negative_log_joint=0.0,
        prior_drift_mean=config.initial_drift_mean_hz_per_s,
        prior_drift_variance=_checked_square(
            config.initial_drift_standard_uncertainty_hz_per_s,
            name="initial drift standard uncertainty",
        ),
        reset_reason="initial-prior",
        dwell=dwell,
        identity=identity,
        transition_negative_log_probability=transition_negative_log_probability,
        prediction_lookup=prediction_lookup,
        config=config,
    )


def _score_extension(
    *,
    parent: _Path,
    dwell: SyntheticCfoDwell,
    identity: CatalogueIdentity,
    transition_negative_log_probability: float,
    prediction_lookup: dict[tuple[int, str], SyntheticCandidateDwellPrediction],
    config: MultiDwellFilterConfig,
) -> _Path:
    prior_mean, prior_variance, reset_reason = _predict_drift(
        parent=parent,
        dwell=dwell,
        config=config,
    )
    return _score_path(
        assignments=parent.assignments,
        active_catalog_numbers=parent.active_catalog_numbers,
        parent_negative_log_joint=parent.cumulative_negative_log_joint,
        prior_drift_mean=prior_mean,
        prior_drift_variance=prior_variance,
        reset_reason=reset_reason,
        dwell=dwell,
        identity=identity,
        transition_negative_log_probability=transition_negative_log_probability,
        prediction_lookup=prediction_lookup,
        config=config,
    )


def _score_path(
    *,
    assignments: tuple[CatalogueIdentity, ...],
    active_catalog_numbers: tuple[int, ...],
    parent_negative_log_joint: float,
    prior_drift_mean: float,
    prior_drift_variance: float,
    reset_reason: NuisanceResetReason | None,
    dwell: SyntheticCfoDwell,
    identity: CatalogueIdentity,
    transition_negative_log_probability: float,
    prediction_lookup: dict[tuple[int, str], SyntheticCandidateDwellPrediction],
    config: MultiDwellFilterConfig,
) -> _Path:
    if identity is None:
        predictions = tuple(config.null_prediction_cfo_hz for _ in dwell.measured_cfo_hz)
        prediction_sigmas = tuple(
            config.null_prediction_standard_uncertainty_hz for _ in dwell.measured_cfo_hz
        )
    else:
        candidate_prediction = prediction_lookup[identity, dwell.dwell_id]
        predictions = candidate_prediction.predicted_cfo_hz
        prediction_sigmas = candidate_prediction.prediction_standard_uncertainties_hz
    residual = tuple(
        measured - predicted
        for measured, predicted in zip(dwell.measured_cfo_hz, predictions, strict=True)
    )
    independent_sigmas = tuple(
        math.hypot(measurement_sigma, prediction_sigma)
        for measurement_sigma, prediction_sigma in zip(
            dwell.measurement_standard_uncertainties_hz,
            prediction_sigmas,
            strict=True,
        )
    )
    marginal = marginalize_dwell_nuisance(
        residual,
        dwell.support_offsets_s,
        independent_sigmas,
        drift_prior_mean_hz_per_s=prior_drift_mean,
        drift_prior_standard_uncertainty_hz_per_s=math.sqrt(prior_drift_variance),
        dwell_offset_prior_standard_uncertainty_hz=(
            config.dwell_offset_prior_standard_uncertainty_hz
        ),
        maximum_condition_number=config.maximum_condition_number,
    )
    increment = _checked_score_sum(
        (
            transition_negative_log_probability,
            marginal.predictive_negative_log_likelihood,
        ),
        name="path transition and predictive increment",
    )
    total = _checked_score_sum(
        (parent_negative_log_joint, increment),
        name="cumulative path score",
    )
    new_active = (
        active_catalog_numbers
        if identity is None or identity in active_catalog_numbers
        else tuple(sorted((*active_catalog_numbers, identity)))
    )
    nuisance = DwellNuisanceUpdate(
        dwell_id=dwell.dwell_id,
        hardware_epoch_id=dwell.hardware_epoch_id,
        reset_reason=reset_reason,
        predicted_drift_mean_hz_per_s=prior_drift_mean,
        predicted_drift_standard_uncertainty_hz_per_s=math.sqrt(prior_drift_variance),
        filtered_drift_mean_hz_per_s=marginal.drift_posterior_mean_hz_per_s,
        filtered_drift_standard_uncertainty_hz_per_s=(
            marginal.drift_posterior_standard_uncertainty_hz_per_s
        ),
        dwell_offset_mean_hz=marginal.dwell_offset_posterior_mean_hz,
        dwell_offset_standard_uncertainty_hz=(
            marginal.dwell_offset_posterior_standard_uncertainty_hz
        ),
        drift_offset_covariance_hz2_per_s=(marginal.drift_offset_posterior_covariance_hz2_per_s),
    )
    return _Path(
        assignments=(*assignments, identity),
        active_catalog_numbers=new_active,
        cumulative_negative_log_joint=total,
        drift_mean_hz_per_s=marginal.drift_posterior_mean_hz_per_s,
        drift_variance_hz2_per_s2=(marginal.drift_posterior_standard_uncertainty_hz_per_s**2),
        hardware_epoch_id=dwell.hardware_epoch_id,
        center_utc_ns=dwell.center_utc_ns,
        last_transition_negative_log_probability=transition_negative_log_probability,
        last_predictive_negative_log_likelihood=marginal.predictive_negative_log_likelihood,
        last_nuisance=nuisance,
    )


def _predict_drift(
    *,
    parent: _Path,
    dwell: SyntheticCfoDwell,
    config: MultiDwellFilterConfig,
) -> tuple[float, float, NuisanceResetReason | None]:
    delta_s = _nanosecond_delta_s(dwell.center_utc_ns, parent.center_utc_ns)
    if not math.isfinite(delta_s) or delta_s <= 0.0:
        raise MultiDwellInputError("dwell chronology must advance by a representable interval")
    reset_reason: NuisanceResetReason | None = None
    if dwell.hardware_epoch_id != parent.hardware_epoch_id:
        reset_reason = "hardware-epoch-change"
    elif delta_s > config.maximum_nuisance_propagation_gap_s:
        reset_reason = "validity-gap"
    if reset_reason is not None:
        return (
            config.initial_drift_mean_hz_per_s,
            _checked_square(
                config.initial_drift_standard_uncertainty_hz_per_s,
                name="initial drift standard uncertainty",
            ),
            reset_reason,
        )
    process_variance = (
        _checked_square(
            config.drift_random_walk_standard_uncertainty_hz_per_s_per_sqrt_s,
            name="drift random-walk standard uncertainty",
        )
        * delta_s
    )
    variance = parent.drift_variance_hz2_per_s2 + process_variance
    if not math.isfinite(variance) or variance <= 0.0:
        raise MultiDwellNumericalError("predicted drift variance is not finite and positive")
    return parent.drift_mean_hz_per_s, variance, None


def _feasible_next_identities(
    *,
    parent: _Path,
    candidate_numbers: tuple[int, ...],
    maximum_distinct_catalogues: int,
) -> tuple[CatalogueIdentity, ...]:
    active = set(parent.active_catalog_numbers)
    return (
        None,
        *(
            item
            for item in candidate_numbers
            if item in active or len(active) < maximum_distinct_catalogues
        ),
    )


def _initial_log_probabilities(
    *,
    candidate_count: int,
    config: MultiDwellFilterConfig,
) -> tuple[float, ...]:
    null_family, candidate_family = _normalized_log_weights(
        (config.initial_null_log_weight, config.initial_candidate_log_weight)
    )
    candidate_state = candidate_family - math.log(candidate_count)
    return (null_family, *(candidate_state for _ in range(candidate_count)))


def _transition_log_probabilities(
    *,
    previous: CatalogueIdentity,
    choices: tuple[CatalogueIdentity, ...],
    config: MultiDwellFilterConfig,
) -> tuple[float, ...]:
    """Normalize state-family mass, then divide it over alternatives."""

    if previous is None:
        candidate_count = len(choices) - 1
        null_family, birth_family = _normalized_log_weights(
            (config.null_stay_log_weight, config.null_to_candidate_log_weight)
        )
        birth_state = birth_family - math.log(candidate_count)
        return (null_family, *(birth_state for _ in range(candidate_count)))

    handoff_count = sum(item is not None and item != previous for item in choices)
    family_names = ["null", "same"]
    family_weights = [config.candidate_to_null_log_weight, config.same_identity_log_weight]
    if handoff_count:
        family_names.append("handoff")
        family_weights.append(config.handoff_log_weight)
    normalized = dict(
        zip(
            family_names,
            _normalized_log_weights(tuple(family_weights)),
            strict=True,
        )
    )
    handoff_state = None if handoff_count == 0 else normalized["handoff"] - math.log(handoff_count)
    return tuple(
        normalized["null"]
        if item is None
        else normalized["same"]
        if item == previous
        else _require_handoff_probability(handoff_state)
        for item in choices
    )


def _require_handoff_probability(value: float | None) -> float:
    if value is None:
        raise AssertionError("handoff state exists without a handoff-family probability")
    return value


def _preflight_support_row_inventory(
    *,
    dwells: tuple[SyntheticCfoDwell, ...],
    config: MultiDwellFilterConfig,
) -> None:
    """Bound support inventory before any response value is inspected."""

    total_rows = 0
    for dwell in dwells:
        try:
            row_count = len(dwell.measured_cfo_hz)
        except (AttributeError, TypeError) as error:
            raise MultiDwellInputError("dwell support inventory is not sized") from error
        if row_count > config.maximum_support_rows_per_dwell:
            raise MultiDwellWorkLimitError(
                f"dwell {getattr(dwell, 'dwell_id', '<invalid>')!r} has {row_count} support "
                f"rows, exceeding maximum_support_rows_per_dwell "
                f"{config.maximum_support_rows_per_dwell}"
            )
        total_rows += row_count
        if total_rows > config.maximum_evaluated_support_rows:
            raise MultiDwellWorkLimitError(
                "input support inventory alone exceeds maximum_evaluated_support_rows"
            )


def _validate_filter_inputs(
    *,
    dwells: tuple[SyntheticCfoDwell, ...],
    prediction_bank: SyntheticMultiDwellPredictionBank,
) -> None:
    if prediction_bank.response_accessed:
        raise MultiDwellInputError("prediction bank must remain response-free")
    if prediction_bank.tau_policy != "fixed-precomputed-v1":
        raise MultiDwellInputError("prediction bank must use fixed precomputed tau")
    prediction_bank.__post_init__()
    if not dwells:
        raise MultiDwellInputError("at least one dwell is required")
    for dwell in dwells:
        dwell.__post_init__()
    for candidate in prediction_bank.candidates:
        candidate.__post_init__()
        for prediction in candidate.dwell_predictions:
            prediction.__post_init__()
    dwell_ids = tuple(item.dwell_id for item in dwells)
    if dwell_ids != prediction_bank.dwell_ids:
        raise MultiDwellInputError("prediction bank does not bind the exact ordered dwell input")
    if len(set(dwell_ids)) != len(dwell_ids):
        raise MultiDwellInputError("dwell identities must be unique")
    for left, right in zip(dwells, dwells[1:], strict=False):
        if right.center_utc_ns <= left.center_utc_ns:
            raise MultiDwellInputError("dwells must be supplied in strict chronological order")
        center_gap_s = _nanosecond_delta_s(right.center_utc_ns, left.center_utc_ns)
        support_gap_s = center_gap_s + min(right.support_offsets_s) - max(left.support_offsets_s)
        if not math.isfinite(support_gap_s) or support_gap_s < 0.0:
            raise MultiDwellInputError(
                "dwell support intervals must be nonoverlapping and chronological"
            )
    closed_epochs: set[str] = set()
    current_epoch = dwells[0].hardware_epoch_id
    for dwell in dwells[1:]:
        if dwell.hardware_epoch_id == current_epoch:
            continue
        closed_epochs.add(current_epoch)
        current_epoch = dwell.hardware_epoch_id
        if current_epoch in closed_epochs:
            raise MultiDwellInputError(
                "a hardware epoch cannot reappear after a declared reset boundary"
            )
    support_count_by_dwell = {item.dwell_id: len(item.measured_cfo_hz) for item in dwells}
    for candidate in prediction_bank.candidates:
        for prediction in candidate.dwell_predictions:
            if len(prediction.predicted_cfo_hz) != support_count_by_dwell[prediction.dwell_id]:
                raise MultiDwellInputError(
                    "candidate prediction does not cover the exact dwell support rows"
                )


def _prediction_lookup(
    bank: SyntheticMultiDwellPredictionBank,
) -> dict[tuple[int, str], SyntheticCandidateDwellPrediction]:
    return {
        (candidate.catalog_number, prediction.dwell_id): prediction
        for candidate in bank.candidates
        for prediction in candidate.dwell_predictions
    }


def _normalized_log_weights(values: tuple[float, ...]) -> tuple[float, ...]:
    if not values:
        raise MultiDwellNumericalError("cannot normalize an empty discrete prior")
    maximum = max(values)
    shifted = tuple(item - maximum for item in values)
    if any(not math.isfinite(item) for item in shifted):
        raise MultiDwellNumericalError("discrete log-weight range is not representable")
    mass = math.fsum(math.exp(item) for item in shifted)
    if not math.isfinite(mass) or mass <= 0.0:
        raise MultiDwellNumericalError("discrete shifted prior mass is not representable")
    normalizer = math.log(mass)
    normalized = tuple(item - normalizer for item in shifted)
    if any(not math.isfinite(item) or item > 1e-12 for item in normalized):
        raise MultiDwellNumericalError("normalized discrete log probabilities are invalid")
    return tuple(min(0.0, item) for item in normalized)


def _checked_cholesky(
    matrix: NDArray[np.float64],
    *,
    name: str,
    maximum_condition_number: float,
) -> NDArray[np.float64]:
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or np.any(~np.isfinite(matrix)):
        raise MultiDwellNumericalError(f"{name} is not a finite square matrix")
    condition_number = float(np.linalg.cond(matrix))
    if not math.isfinite(condition_number) or condition_number > maximum_condition_number:
        raise MultiDwellNumericalError(f"{name} exceeds the configured condition bound")
    try:
        return np.asarray(np.linalg.cholesky(matrix), dtype=np.float64)
    except np.linalg.LinAlgError as error:
        raise MultiDwellNumericalError(f"{name} is not positive definite") from error


def _retain_top_modes(
    ordered: tuple[_Path, ...],
    *,
    nominal_limit: int,
) -> tuple[tuple[_Path, ...], bool]:
    if len(ordered) <= nominal_limit:
        return ordered, False
    cutoff = ordered[nominal_limit - 1].cumulative_negative_log_joint
    retained = tuple(
        item
        for item in ordered
        if item.cumulative_negative_log_joint <= cutoff
        or abs(item.cumulative_negative_log_joint - cutoff)
        <= _score_tie_tolerance(item.cumulative_negative_log_joint, cutoff)
    )
    return retained, len(retained) > nominal_limit


def _order_paths(paths: tuple[_Path, ...]) -> tuple[_Path, ...]:
    """Order the best 8-ULP tie canonically, independent of float noise."""

    raw = tuple(sorted(paths, key=_path_sort_key))
    tied = _top_tied_paths(raw)
    tied_assignments = {item.assignments for item in tied}
    return tuple(sorted(tied, key=_path_tie_break_key)) + tuple(
        item for item in raw if item.assignments not in tied_assignments
    )


def _conditional_retained_mass(
    *,
    ordered: tuple[_Path, ...],
    retained: tuple[_Path, ...],
) -> float:
    minimum = ordered[0].cumulative_negative_log_joint
    total = math.fsum(math.exp(-(item.cumulative_negative_log_joint - minimum)) for item in ordered)
    kept = math.fsum(math.exp(-(item.cumulative_negative_log_joint - minimum)) for item in retained)
    if not math.isfinite(total) or total <= 0.0 or not math.isfinite(kept):
        raise MultiDwellNumericalError("retained-mode probability mass is not representable")
    return min(1.0, max(0.0, kept / total))


def _mixture_predictive_negative_log_likelihood(
    *,
    children: tuple[_Path, ...],
    parents: tuple[_Path, ...],
) -> float:
    """Score the new dwell under the normalized frozen parent mixture."""

    parent_negative_log_probabilities: dict[tuple[CatalogueIdentity, ...], float]
    if not parents:
        parent_negative_log_probabilities = {(): 0.0}
    else:
        parent_negative_log_probabilities = _normalized_negative_log_path_probabilities(parents)
    contributions = tuple(
        _checked_score_sum(
            (
                parent_negative_log_probabilities[item.assignments[:-1]],
                item.last_transition_negative_log_probability,
                item.last_predictive_negative_log_likelihood,
            ),
            name="mixture predictive contribution",
        )
        for item in children
    )
    return _negative_logsumexp_scores(contributions)


def _normalized_negative_log_path_probabilities(
    paths: tuple[_Path, ...],
) -> dict[tuple[CatalogueIdentity, ...], float]:
    minimum = min(item.cumulative_negative_log_joint for item in paths)
    distances = tuple(item.cumulative_negative_log_joint - minimum for item in paths)
    if any(not math.isfinite(item) or item < 0.0 for item in distances):
        raise MultiDwellNumericalError("parent path score range is not representable")
    shifted_mass = math.fsum(math.exp(-item) for item in distances)
    if not math.isfinite(shifted_mass) or shifted_mass <= 0.0:
        raise MultiDwellNumericalError("parent path probability mass is not representable")
    log_mass = math.log(shifted_mass)
    return {
        path.assignments: distance + log_mass
        for path, distance in zip(paths, distances, strict=True)
    }


def _negative_logsumexp_scores(scores: tuple[float, ...]) -> float:
    minimum = min(scores)
    distances = tuple(item - minimum for item in scores)
    if any(not math.isfinite(item) or item < 0.0 for item in distances):
        raise MultiDwellNumericalError("path score range is not representable")
    shifted_mass = math.fsum(math.exp(-item) for item in distances)
    if not math.isfinite(shifted_mass) or shifted_mass <= 0.0:
        raise MultiDwellNumericalError("path evidence mass is not representable")
    result = minimum - math.log(shifted_mass)
    if not math.isfinite(result):
        raise MultiDwellNumericalError("path evidence is not finite")
    return result


def _public_modes(paths: tuple[_Path, ...]) -> tuple[MultiDwellModeScore, ...]:
    minimum = paths[0].cumulative_negative_log_joint
    weights = tuple(math.exp(-(item.cumulative_negative_log_joint - minimum)) for item in paths)
    mass = math.fsum(weights)
    if not math.isfinite(mass) or mass <= 0.0:
        raise MultiDwellNumericalError("retained posterior mass is not representable")
    probabilities = [item / mass for item in weights]
    probabilities[0] += 1.0 - math.fsum(probabilities)
    return tuple(
        MultiDwellModeScore(
            rank=index + 1,
            assignments=path.assignments,
            active_catalog_numbers=path.active_catalog_numbers,
            transition_negative_log_probability=(path.last_transition_negative_log_probability),
            next_dwell_predictive_negative_log_likelihood=(
                path.last_predictive_negative_log_likelihood
            ),
            cumulative_negative_log_joint=path.cumulative_negative_log_joint,
            posterior_probability_within_retained_beam=probabilities[index],
            nuisance=path.last_nuisance,
        )
        for index, path in enumerate(paths)
    )


def _top_tied_paths(paths: tuple[_Path, ...]) -> tuple[_Path, ...]:
    best = paths[0].cumulative_negative_log_joint
    return tuple(
        item
        for item in paths
        if abs(item.cumulative_negative_log_joint - best)
        <= _score_tie_tolerance(item.cumulative_negative_log_joint, best)
    )


def _ambiguity_paths(
    paths: tuple[_Path, ...],
    *,
    margin: float | None,
) -> tuple[_Path, ...]:
    if margin is None:
        return _top_tied_paths(paths)
    best = paths[0].cumulative_negative_log_joint
    return tuple(
        item
        for item in paths
        if item.cumulative_negative_log_joint - best
        <= margin + _score_tie_tolerance(item.cumulative_negative_log_joint, best)
    )


def _ordered_identities(
    identities: tuple[CatalogueIdentity, ...],
) -> tuple[CatalogueIdentity, ...]:
    return tuple(sorted(set(identities), key=lambda item: -1 if item is None else item))


def _path_sort_key(path: _Path) -> tuple[object, ...]:
    return (
        path.cumulative_negative_log_joint,
        *_path_tie_break_key(path),
    )


def _path_tie_break_key(path: _Path) -> tuple[object, ...]:
    assignment_key = tuple(-1 if item is None else item for item in path.assignments)
    return (len(path.active_catalog_numbers), assignment_key)


def _score_tie_tolerance(left: float, right: float) -> float:
    return _TIE_ULPS * max(math.ulp(left), math.ulp(right), math.ulp(0.0))


def _checked_square(value: float, *, name: str) -> float:
    squared = value * value
    if not math.isfinite(squared) or squared <= 0.0:
        raise MultiDwellNumericalError(f"{name} variance is not representable")
    return squared


def _checked_score_sum(values: tuple[float, ...], *, name: str) -> float:
    if not values or any(not math.isfinite(item) for item in values):
        raise MultiDwellNumericalError(f"{name} inputs must be finite")
    try:
        result = math.fsum(values)
    except OverflowError as error:
        raise MultiDwellNumericalError(f"{name} is not representable") from error
    if not math.isfinite(result):
        raise MultiDwellNumericalError(f"{name} is not finite")
    for index, value in enumerate(values):
        if value == 0.0:
            continue
        try:
            without_value = math.fsum((*values[:index], *values[index + 1 :]))
        except OverflowError as error:
            raise MultiDwellNumericalError(f"{name} is not representable") from error
        if result == without_value:
            raise MultiDwellNumericalError(
                f"{name} loses a nonzero increment at floating-point precision"
            )
    return result


def _nanosecond_delta_s(later_utc_ns: int, earlier_utc_ns: int) -> float:
    delta_ns = later_utc_ns - earlier_utc_ns
    try:
        delta_s = float(delta_ns) / 1e9
    except OverflowError as error:
        raise MultiDwellInputError("dwell time difference is not representable") from error
    if not math.isfinite(delta_s):
        raise MultiDwellInputError("dwell time difference is not representable")
    return delta_s


def _require_finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise MultiDwellInputError(f"{name} must be finite")


def _require_positive(name: str, value: float) -> None:
    _require_finite(name, value)
    if value <= 0.0:
        raise MultiDwellInputError(f"{name} must be positive")


def _require_nonnegative(name: str, value: float) -> None:
    _require_finite(name, value)
    if value < 0.0:
        raise MultiDwellInputError(f"{name} must be nonnegative")


def _require_all_finite(name: str, values: tuple[float, ...]) -> None:
    if any(not math.isfinite(item) for item in values):
        raise MultiDwellInputError(f"{name} must contain only finite values")


def _require_all_positive(name: str, values: tuple[float, ...]) -> None:
    _require_all_finite(name, values)
    if any(item <= 0.0 for item in values):
        raise MultiDwellInputError(f"{name} must contain only positive values")


def _require_all_nonnegative(name: str, values: tuple[float, ...]) -> None:
    _require_all_finite(name, values)
    if any(item < 0.0 for item in values):
        raise MultiDwellInputError(f"{name} must contain only nonnegative values")


__all__ = [
    "DwellMarginalScore",
    "DwellNuisanceUpdate",
    "MultiDwellCatalogueFilterResult",
    "MultiDwellInputError",
    "MultiDwellModeScore",
    "MultiDwellNumericalError",
    "MultiDwellFilterConfig",
    "MultiDwellWorkLimitError",
    "RollingDwellAssociation",
    "SyntheticCandidateDwellPrediction",
    "SyntheticCandidateTrajectory",
    "SyntheticCfoDwell",
    "SyntheticMultiDwellPredictionBank",
    "filter_multi_dwell_catalogue_modes",
    "marginalize_dwell_nuisance",
]
