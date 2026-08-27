"""Block-prequential evidence for frozen linear-Gaussian hypothesis families.

This pure analyzer is the numerical core for a later calibrated catalogue-
versus-radio comparison.  Every discrete state supplies a response-free base
curve, a linear nuisance design, and a proper Gaussian parameter prior on the
same observation inventory.  The analyzer:

* applies one shared measurement covariance policy to every state;
* scores each future calendar block before assimilating that block;
* marginalizes parameter and block-common uncertainty analytically;
* normalizes priors hierarchically from family to discrete state; and
* retains explicitly supplied missing opportunities and abstains when coverage
  is inadequate or the caller cannot attest a complete opportunity universe.

The returned normalized masses are conditional on the declared, currently
uncalibrated model and prior inventory.  They are not calibrated satellite-
identity probabilities, a model-selection gate, or an authorization to score
opened observations.  Execution authority and empirical-rank calibration are
separate layers.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Literal

from leo.contracts.digests import canonical_digest

type PredictiveFamily = Literal["null", "catalogue-orbit", "radio-polynomial"]
type ObservationStatus = Literal["usable", "missing"]
type CoverageAbstentionDiagnostic = Literal[
    "incomplete-opportunity-inventory",
    "insufficient-evaluation-block-coverage",
    "insufficient-evaluation-observation-coverage",
    "insufficient-usable-evaluation-blocks",
    "insufficient-usable-evaluation-observations",
]

_FAMILIES: tuple[PredictiveFamily, ...] = (
    "null",
    "catalogue-orbit",
    "radio-polynomial",
)
_ALGORITHM_VERSION = "block-prequential-hierarchical-linear-gaussian-v1"
_SHA256_PREFIX = "sha256:"
_SHA256_HEX_LENGTH = 64


class BlockPredictiveInputError(ValueError):
    """The frozen inventory, partition, covariance, or work bounds are invalid."""


class BlockPredictiveWorkLimitError(ValueError):
    """The declared response-free work inventory exceeds a frozen cap."""


class BlockPredictiveNumericalError(ValueError):
    """A proper Gaussian update or normalized mixture is not representable."""


@dataclass(frozen=True, slots=True)
class BlockPredictiveObservation:
    """One expected CFO opportunity; missing rows remain explicit."""

    observation_id: str
    support_start_utc_ns: int
    support_center_utc_ns: int
    support_end_utc_ns: int
    status: ObservationStatus
    measured_cfo_hz: float | None
    standard_uncertainty_hz: float | None
    missing_reason: str | None = None

    def __post_init__(self) -> None:
        if not _is_digest(self.observation_id):
            raise BlockPredictiveInputError("observation identity must be a tagged SHA-256 digest")
        if (
            isinstance(self.support_start_utc_ns, bool)
            or isinstance(self.support_center_utc_ns, bool)
            or isinstance(self.support_end_utc_ns, bool)
            or not isinstance(self.support_start_utc_ns, int)
            or not isinstance(self.support_center_utc_ns, int)
            or not isinstance(self.support_end_utc_ns, int)
            or self.support_start_utc_ns <= 0
            or not self.support_start_utc_ns <= self.support_center_utc_ns < self.support_end_utc_ns
        ):
            raise BlockPredictiveInputError("observation UTC support is invalid")
        if self.status == "usable":
            if (
                self.measured_cfo_hz is None
                or self.standard_uncertainty_hz is None
                or not math.isfinite(self.measured_cfo_hz)
                or not math.isfinite(self.standard_uncertainty_hz)
                or self.standard_uncertainty_hz <= 0.0
                or self.missing_reason is not None
            ):
                raise BlockPredictiveInputError(
                    "usable observations need finite response and positive uncertainty"
                )
        elif self.status == "missing":
            if (
                self.measured_cfo_hz is not None
                or self.standard_uncertainty_hz is not None
                or self.missing_reason is None
                or not self.missing_reason.strip()
            ):
                raise BlockPredictiveInputError(
                    "missing observations need no response and an explicit reason"
                )
        else:
            raise BlockPredictiveInputError("observation status is invalid")


@dataclass(frozen=True, slots=True)
class FrozenStateObservationModel:
    """One state's response-free prediction and nuisance design for one row."""

    observation_id: str
    base_prediction_hz: float
    design_row: tuple[float, ...]
    prediction_standard_uncertainty_hz: float = 0.0

    def __post_init__(self) -> None:
        if not _is_digest(self.observation_id):
            raise BlockPredictiveInputError("state-row identity must be a tagged SHA-256 digest")
        if (
            not math.isfinite(self.base_prediction_hz)
            or not math.isfinite(self.prediction_standard_uncertainty_hz)
            or self.prediction_standard_uncertainty_hz < 0.0
            or not self.design_row
            or any(not math.isfinite(item) for item in self.design_row)
        ):
            raise BlockPredictiveInputError("state prediction row is invalid")


@dataclass(frozen=True, slots=True)
class FrozenLinearGaussianState:
    """One persistent discrete state with a proper continuous nuisance prior."""

    state_id: str
    family: PredictiveFamily
    model_authority_digest: str
    log_prior_weight_within_family: float
    parameter_prior_mean: tuple[float, ...]
    parameter_prior_covariance: tuple[tuple[float, ...], ...]
    observation_models: tuple[FrozenStateObservationModel, ...]
    prediction_inventory_reference_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.state_id.strip():
            raise BlockPredictiveInputError("state identity cannot be empty")
        if self.family not in _FAMILIES:
            raise BlockPredictiveInputError("state family is invalid")
        if not _is_digest(self.model_authority_digest):
            raise BlockPredictiveInputError("state model authority must be digest-bound")
        if not math.isfinite(self.log_prior_weight_within_family):
            raise BlockPredictiveInputError("state prior weight must be finite")
        parameter_count = len(self.parameter_prior_mean)
        if parameter_count < 1 or any(
            not math.isfinite(item) for item in self.parameter_prior_mean
        ):
            raise BlockPredictiveInputError("every state needs a finite, nonempty proper prior")
        covariance = _validated_square_matrix(
            self.parameter_prior_covariance,
            dimension=parameter_count,
            name="state parameter prior covariance",
        )
        _cholesky(covariance, "state parameter prior covariance")
        if not self.observation_models:
            if not _is_digest(self.prediction_inventory_reference_digest):
                raise BlockPredictiveInputError(
                    "external state predictions require a digest-bound inventory reference"
                )
            return
        if self.prediction_inventory_reference_digest is not None:
            raise BlockPredictiveInputError(
                "inline state predictions cannot also claim an external inventory"
            )
        if len({item.observation_id for item in self.observation_models}) != len(
            self.observation_models
        ):
            raise BlockPredictiveInputError("state observation identities must be unique")
        if any(len(item.design_row) != parameter_count for item in self.observation_models):
            raise BlockPredictiveInputError("state design dimension differs from its prior")


type StateObservationModelProvider = Callable[
    [str, tuple[str, ...]],
    tuple[FrozenStateObservationModel, ...],
]


@dataclass(frozen=True, slots=True)
class FamilyPriorWeight:
    family: PredictiveFamily
    log_weight: float

    def __post_init__(self) -> None:
        if self.family not in _FAMILIES or not math.isfinite(self.log_weight):
            raise BlockPredictiveInputError("family prior weight is invalid")


@dataclass(frozen=True, slots=True)
class CalendarBlockCovariance:
    """Shared measurement covariance applied identically to every family.

    For usable rows in one calendar block, conditional measurement covariance
    is ``scale * diag(sigma**2) + floor * I + common * 11'``.  State-specific
    prediction variance is then added to the diagonal, while nuisance-parameter
    covariance is marginalized as a separate low-rank term.
    """

    measurement_variance_scale: float
    independent_variance_floor_hz2: float
    block_common_variance_hz2: float
    calibration_authority_digest: str
    calibrated: bool = False

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.measurement_variance_scale)
            or self.measurement_variance_scale <= 0.0
            or not math.isfinite(self.independent_variance_floor_hz2)
            or self.independent_variance_floor_hz2 < 0.0
            or not math.isfinite(self.block_common_variance_hz2)
            or self.block_common_variance_hz2 < 0.0
            or not _is_digest(self.calibration_authority_digest)
        ):
            raise BlockPredictiveInputError("calendar-block covariance policy is invalid")

    @property
    def content_digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class BlockPredictiveEvidenceConfig:
    training_observation_ids: tuple[str, ...]
    evaluation_observation_ids: tuple[str, ...]
    expected_observation_inventory_digest: str
    expected_hypothesis_inventory_digest: str
    family_prior_weights: tuple[FamilyPriorWeight, ...]
    covariance: CalendarBlockCovariance
    calendar_block_duration_ns: int
    minimum_usable_evaluation_observations: int
    minimum_usable_evaluation_blocks: int
    minimum_evaluation_observation_coverage: float
    minimum_evaluation_block_coverage: float
    opportunity_inventory_complete: bool = True
    maximum_observation_count: int = 4_096
    maximum_hypothesis_count: int = 25_000
    maximum_parameter_count: int = 8
    maximum_rows_per_calendar_block: int = 2_048
    maximum_state_observation_evaluations: int = 30_000_000

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_inventory_complete, bool):
            raise BlockPredictiveInputError(
                "opportunity-inventory completeness must be explicitly boolean"
            )
        for label, values in (
            ("training", self.training_observation_ids),
            ("evaluation", self.evaluation_observation_ids),
        ):
            if (
                not values
                or len(set(values)) != len(values)
                or any(not _is_digest(item) for item in values)
            ):
                raise BlockPredictiveInputError(
                    f"{label} observation inventory must be nonempty, unique digests"
                )
        if set(self.training_observation_ids) & set(self.evaluation_observation_ids):
            raise BlockPredictiveInputError("training and evaluation inventories must be disjoint")
        if not _is_digest(self.expected_observation_inventory_digest) or not _is_digest(
            self.expected_hypothesis_inventory_digest
        ):
            raise BlockPredictiveInputError("expected inventories must be digest-bound")
        if tuple(item.family for item in self.family_prior_weights) != _FAMILIES:
            raise BlockPredictiveInputError(
                "family priors must contain null, catalogue, and radio exactly once in order"
            )
        if (
            isinstance(self.calendar_block_duration_ns, bool)
            or not isinstance(self.calendar_block_duration_ns, int)
            or self.calendar_block_duration_ns <= 0
        ):
            raise BlockPredictiveInputError("calendar block duration must be positive UTC ns")
        integer_controls = (
            self.minimum_usable_evaluation_observations,
            self.minimum_usable_evaluation_blocks,
            self.maximum_observation_count,
            self.maximum_hypothesis_count,
            self.maximum_parameter_count,
            self.maximum_rows_per_calendar_block,
            self.maximum_state_observation_evaluations,
        )
        if any(
            isinstance(item, bool) or not isinstance(item, int) or item < 1
            for item in integer_controls
        ):
            raise BlockPredictiveInputError(
                "coverage minima and work caps must be positive integers"
            )
        for value in (
            self.minimum_evaluation_observation_coverage,
            self.minimum_evaluation_block_coverage,
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise BlockPredictiveInputError("coverage ratios must lie in [0, 1]")

    @property
    def content_digest(self) -> str:
        return canonical_digest(
            {
                **asdict(self),
                "covariance_policy_digest": self.covariance.content_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class StateBlockPredictiveScore:
    state_id: str
    family: PredictiveFamily
    usable_observation_count: int
    predictive_negative_log_likelihood: float
    predictive_mahalanobis_squared: float
    predictive_log_determinant_hz2: float
    mean_normalized_innovation_squared: float | None
    scored_before_assimilation: Literal[True] = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class FamilyBlockPredictiveScore:
    family: PredictiveFamily
    state_count: int
    normalized_model_mass_before_block: float
    conditional_predictive_negative_log_likelihood: float
    normalized_model_mass_after_block: float


@dataclass(frozen=True, slots=True)
class CalendarBlockPredictiveScore:
    block_index: int
    block_start_utc_ns: int
    block_end_utc_ns: int
    observation_ids: tuple[str, ...]
    opportunity_count: int
    usable_observation_count: int
    usable_observation_fraction: float
    scored: bool
    mixture_predictive_negative_log_likelihood: float
    state_scores: tuple[StateBlockPredictiveScore, ...]
    family_scores: tuple[FamilyBlockPredictiveScore, ...]


@dataclass(frozen=True, slots=True)
class StatePredictiveSummary:
    state_id: str
    family: PredictiveFamily
    normalized_log_prior_within_family: float
    normalized_log_model_mass_after_training: float
    normalized_model_mass_after_training: float
    normalized_log_model_mass_final: float
    normalized_model_mass_final: float
    training_predictive_negative_log_likelihood: float
    evaluation_predictive_negative_log_likelihood: float
    training_parameter_posterior_mean: tuple[float, ...]
    training_parameter_posterior_covariance: tuple[tuple[float, ...], ...]
    final_parameter_posterior_mean: tuple[float, ...]
    final_parameter_posterior_covariance: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class FamilyPredictiveSummary:
    family: PredictiveFamily
    state_count: int
    normalized_log_prior: float
    normalized_model_mass_after_training: float
    normalized_model_mass_final: float
    evaluation_prequential_negative_log_likelihood: float


@dataclass(frozen=True, slots=True)
class BlockPredictiveEvidenceResult:
    observation_inventory_digest: str
    hypothesis_inventory_digest: str
    observation_partition_digest: str
    covariance_policy_digest: str
    covariance_parameters_calibrated: bool
    config_digest: str
    training_observation_count: int
    training_usable_observation_count: int
    training_calendar_block_count: int
    evaluation_observation_count: int
    evaluation_usable_observation_count: int
    evaluation_calendar_block_count: int
    evaluation_usable_calendar_block_count: int
    evaluation_observation_coverage: float | None
    evaluation_block_coverage: float | None
    opportunity_inventory_complete: bool
    missing_opportunities_retained: bool
    coverage_conditioned_on_observed_rows: bool
    evaluation_mixture_prequential_negative_log_likelihood: float
    blocks: tuple[CalendarBlockPredictiveScore, ...]
    states: tuple[StatePredictiveSummary, ...]
    families: tuple[FamilyPredictiveSummary, ...]
    abstention_recommended: bool
    abstention_diagnostics: tuple[CoverageAbstentionDiagnostic, ...]
    result_digest: str
    algorithm_version: Literal["block-prequential-hierarchical-linear-gaussian-v1"] = field(
        default="block-prequential-hierarchical-linear-gaussian-v1", init=False
    )
    exact_common_observation_inventory: Literal[True] = field(default=True, init=False)
    shared_measurement_covariance_across_families: Literal[True] = field(default=True, init=False)
    score_before_assimilate: Literal[True] = field(default=True, init=False)
    hierarchical_family_state_priors_normalized: Literal[True] = field(default=True, init=False)
    empirical_rank_calibration_applied: Literal[False] = field(default=False, init=False)
    identity_probability_calibrated: Literal[False] = field(default=False, init=False)
    model_selection_gate_produced: Literal[False] = field(default=False, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)


@dataclass(slots=True)
class _StateRuntime:
    state: FrozenLinearGaussianState
    normalized_log_prior_within_family: float
    parameter_mean: tuple[float, ...]
    parameter_covariance: tuple[tuple[float, ...], ...]
    cumulative_log_joint: float
    training_negative_log_likelihood: float = 0.0
    evaluation_negative_log_likelihood: float = 0.0
    training_parameter_mean: tuple[float, ...] = ()
    training_parameter_covariance: tuple[tuple[float, ...], ...] = ()
    training_log_mass: float = 0.0


@dataclass(frozen=True, slots=True)
class _GaussianUpdate:
    negative_log_likelihood: float
    mahalanobis_squared: float
    log_determinant: float
    posterior_mean: tuple[float, ...]
    posterior_covariance: tuple[tuple[float, ...], ...]


def observation_inventory_digest(
    observations: tuple[BlockPredictiveObservation, ...],
) -> str:
    """Digest the declared ledger, including response and explicit missingness."""

    return canonical_digest(
        {
            "schema": "org.leo.research.block-predictive-observation-inventory/v1",
            "observations": [asdict(item) for item in observations],
        }
    )


def hypothesis_inventory_digest(states: tuple[FrozenLinearGaussianState, ...]) -> str:
    """Digest a canonical state inventory independent of caller tuple ordering."""

    ordered = sorted(states, key=_state_sort_key)
    return canonical_digest(
        {
            "schema": "org.leo.research.block-predictive-hypothesis-inventory/v1",
            "states": [asdict(item) for item in ordered],
        }
    )


def score_block_predictive_evidence(
    observations: tuple[BlockPredictiveObservation, ...],
    states: tuple[FrozenLinearGaussianState, ...],
    *,
    config: BlockPredictiveEvidenceConfig,
    external_model_provider: StateObservationModelProvider | None = None,
) -> BlockPredictiveEvidenceResult:
    """Score a frozen hierarchical state inventory one future block at a time.

    Large response-free prediction banks may keep state rows in digest-bound
    read-only storage. Such states declare an external prediction-inventory
    digest and the provider supplies only the current block's rows; rows are
    validated and discarded after that block rather than retained in memory.
    """

    config = _revalidate_config(config)
    _preflight_work_bounds(observations, states, config=config)
    observations = _revalidate_observations(observations)
    states = _revalidate_states(states)
    has_external_states = any(not item.observation_models for item in states)
    if has_external_states != (external_model_provider is not None):
        raise BlockPredictiveInputError(
            "an external model provider is required exactly for external state predictions"
        )
    observed_digest = observation_inventory_digest(observations)
    state_digest = hypothesis_inventory_digest(states)
    if observed_digest != config.expected_observation_inventory_digest:
        raise BlockPredictiveInputError("observation inventory digest differs")
    if state_digest != config.expected_hypothesis_inventory_digest:
        raise BlockPredictiveInputError("hypothesis inventory digest differs")
    _validate_common_inventory(observations, states, config=config)

    observation_by_id = {item.observation_id: item for item in observations}
    training = tuple(observation_by_id[item] for item in config.training_observation_ids)
    evaluation = tuple(observation_by_id[item] for item in config.evaluation_observation_ids)
    training_blocks = _calendar_blocks(training, config.calendar_block_duration_ns)
    evaluation_blocks = _calendar_blocks(evaluation, config.calendar_block_duration_ns)
    if set(training_blocks) & set(evaluation_blocks):
        raise BlockPredictiveInputError(
            "one calendar block cannot be split between training and evaluation"
        )

    normalized_family_priors = dict(
        zip(
            _FAMILIES,
            _normalized_log_weights(tuple(item.log_weight for item in config.family_prior_weights)),
            strict=True,
        )
    )
    states_by_family = {
        family: tuple(item for item in states if item.family == family) for family in _FAMILIES
    }
    if any(not family_states for family_states in states_by_family.values()):
        raise BlockPredictiveInputError("null, catalogue, and radio families must all be present")
    normalized_state_priors: dict[str, float] = {}
    for _family, family_states in states_by_family.items():
        normalized = _normalized_log_weights(
            tuple(item.log_prior_weight_within_family for item in family_states)
        )
        normalized_state_priors.update(
            {item.state_id: value for item, value in zip(family_states, normalized, strict=True)}
        )

    model_by_state = {
        state.state_id: {item.observation_id: item for item in state.observation_models}
        for state in states
        if state.observation_models
    }
    runtimes = [
        _StateRuntime(
            state=state,
            normalized_log_prior_within_family=normalized_state_priors[state.state_id],
            parameter_mean=state.parameter_prior_mean,
            parameter_covariance=state.parameter_prior_covariance,
            cumulative_log_joint=(
                normalized_family_priors[state.family] + normalized_state_priors[state.state_id]
            ),
        )
        for state in states
    ]

    for block in training_blocks.values():
        for runtime in runtimes:
            update = _score_and_update(
                block,
                _models_for_block(
                    runtime.state,
                    block,
                    inline_models_by_state=model_by_state,
                    external_model_provider=external_model_provider,
                ),
                parameter_mean=runtime.parameter_mean,
                parameter_covariance=runtime.parameter_covariance,
                covariance=config.covariance,
            )
            runtime.training_negative_log_likelihood += update.negative_log_likelihood
            runtime.cumulative_log_joint -= update.negative_log_likelihood
            runtime.parameter_mean = update.posterior_mean
            runtime.parameter_covariance = update.posterior_covariance
    training_log_masses = _normalized_log_runtime_masses(runtimes)
    for runtime in runtimes:
        runtime.training_parameter_mean = runtime.parameter_mean
        runtime.training_parameter_covariance = runtime.parameter_covariance
        runtime.training_log_mass = training_log_masses[runtime.state.state_id]

    block_results: list[CalendarBlockPredictiveScore] = []
    family_evaluation_nll = {family: 0.0 for family in _FAMILIES}
    total_evaluation_nll = 0.0
    for block_index, block in evaluation_blocks.items():
        log_masses_before = _normalized_log_runtime_masses(runtimes)
        family_log_masses_before = _family_log_masses(runtimes, log_masses_before)
        updates: dict[str, _GaussianUpdate] = {}
        state_scores: list[StateBlockPredictiveScore] = []
        for runtime in runtimes:
            update = _score_and_update(
                block,
                _models_for_block(
                    runtime.state,
                    block,
                    inline_models_by_state=model_by_state,
                    external_model_provider=external_model_provider,
                ),
                parameter_mean=runtime.parameter_mean,
                parameter_covariance=runtime.parameter_covariance,
                covariance=config.covariance,
            )
            updates[runtime.state.state_id] = update
            usable_count = sum(item.status == "usable" for item in block)
            state_scores.append(
                StateBlockPredictiveScore(
                    state_id=runtime.state.state_id,
                    family=runtime.state.family,
                    usable_observation_count=usable_count,
                    predictive_negative_log_likelihood=update.negative_log_likelihood,
                    predictive_mahalanobis_squared=update.mahalanobis_squared,
                    predictive_log_determinant_hz2=update.log_determinant,
                    mean_normalized_innovation_squared=(
                        None if usable_count == 0 else update.mahalanobis_squared / usable_count
                    ),
                )
            )

        mixture_nll = -_logsumexp(
            tuple(
                log_masses_before[runtime.state.state_id]
                - updates[runtime.state.state_id].negative_log_likelihood
                for runtime in runtimes
            )
        )
        if not math.isfinite(mixture_nll):
            raise BlockPredictiveNumericalError("mixture predictive score is not finite")
        total_evaluation_nll += mixture_nll
        family_block_nll: dict[PredictiveFamily, float] = {}
        for family in _FAMILIES:
            family_runtimes = tuple(item for item in runtimes if item.state.family == family)
            family_block_nll[family] = -_logsumexp(
                tuple(
                    log_masses_before[item.state.state_id]
                    - family_log_masses_before[family]
                    - updates[item.state.state_id].negative_log_likelihood
                    for item in family_runtimes
                )
            )
            family_evaluation_nll[family] += family_block_nll[family]

        # Assimilation happens only after every state and family score for this
        # block has been computed from the frozen pre-block posterior.
        for runtime in runtimes:
            update = updates[runtime.state.state_id]
            runtime.evaluation_negative_log_likelihood += update.negative_log_likelihood
            runtime.cumulative_log_joint -= update.negative_log_likelihood
            runtime.parameter_mean = update.posterior_mean
            runtime.parameter_covariance = update.posterior_covariance
        log_masses_after = _normalized_log_runtime_masses(runtimes)
        family_log_masses_after = _family_log_masses(runtimes, log_masses_after)
        block_start = block_index * config.calendar_block_duration_ns
        usable_count = sum(item.status == "usable" for item in block)
        block_results.append(
            CalendarBlockPredictiveScore(
                block_index=block_index,
                block_start_utc_ns=block_start,
                block_end_utc_ns=block_start + config.calendar_block_duration_ns,
                observation_ids=tuple(item.observation_id for item in block),
                opportunity_count=len(block),
                usable_observation_count=usable_count,
                usable_observation_fraction=usable_count / len(block),
                scored=usable_count > 0,
                mixture_predictive_negative_log_likelihood=mixture_nll,
                state_scores=tuple(state_scores),
                family_scores=tuple(
                    FamilyBlockPredictiveScore(
                        family=family,
                        state_count=len(states_by_family[family]),
                        normalized_model_mass_before_block=math.exp(
                            family_log_masses_before[family]
                        ),
                        conditional_predictive_negative_log_likelihood=(family_block_nll[family]),
                        normalized_model_mass_after_block=math.exp(family_log_masses_after[family]),
                    )
                    for family in _FAMILIES
                ),
            )
        )

    final_log_masses = _normalized_log_runtime_masses(runtimes)
    final_family_log_masses = _family_log_masses(runtimes, final_log_masses)
    training_family_log_masses = _family_log_masses(runtimes, training_log_masses)
    state_summaries = tuple(
        StatePredictiveSummary(
            state_id=runtime.state.state_id,
            family=runtime.state.family,
            normalized_log_prior_within_family=runtime.normalized_log_prior_within_family,
            normalized_log_model_mass_after_training=runtime.training_log_mass,
            normalized_model_mass_after_training=math.exp(runtime.training_log_mass),
            normalized_log_model_mass_final=final_log_masses[runtime.state.state_id],
            normalized_model_mass_final=math.exp(final_log_masses[runtime.state.state_id]),
            training_predictive_negative_log_likelihood=(runtime.training_negative_log_likelihood),
            evaluation_predictive_negative_log_likelihood=(
                runtime.evaluation_negative_log_likelihood
            ),
            training_parameter_posterior_mean=runtime.training_parameter_mean,
            training_parameter_posterior_covariance=(runtime.training_parameter_covariance),
            final_parameter_posterior_mean=runtime.parameter_mean,
            final_parameter_posterior_covariance=runtime.parameter_covariance,
        )
        for runtime in runtimes
    )
    family_summaries = tuple(
        FamilyPredictiveSummary(
            family=family,
            state_count=len(states_by_family[family]),
            normalized_log_prior=normalized_family_priors[family],
            normalized_model_mass_after_training=math.exp(training_family_log_masses[family]),
            normalized_model_mass_final=math.exp(final_family_log_masses[family]),
            evaluation_prequential_negative_log_likelihood=family_evaluation_nll[family],
        )
        for family in _FAMILIES
    )

    training_usable = sum(item.status == "usable" for item in training)
    evaluation_usable = sum(item.status == "usable" for item in evaluation)
    evaluation_usable_blocks = sum(
        any(item.status == "usable" for item in block) for block in evaluation_blocks.values()
    )
    observation_coverage = (
        evaluation_usable / len(evaluation) if config.opportunity_inventory_complete else None
    )
    block_coverage = (
        evaluation_usable_blocks / len(evaluation_blocks)
        if config.opportunity_inventory_complete
        else None
    )
    diagnostics: list[CoverageAbstentionDiagnostic] = []
    if not config.opportunity_inventory_complete:
        diagnostics.append("incomplete-opportunity-inventory")
    if evaluation_usable < config.minimum_usable_evaluation_observations:
        diagnostics.append("insufficient-usable-evaluation-observations")
    if evaluation_usable_blocks < config.minimum_usable_evaluation_blocks:
        diagnostics.append("insufficient-usable-evaluation-blocks")
    if (
        observation_coverage is not None
        and observation_coverage < config.minimum_evaluation_observation_coverage
    ):
        diagnostics.append("insufficient-evaluation-observation-coverage")
    if block_coverage is not None and block_coverage < config.minimum_evaluation_block_coverage:
        diagnostics.append("insufficient-evaluation-block-coverage")
    diagnostics.sort()
    partition_digest = canonical_digest(
        {
            "algorithm_version": _ALGORITHM_VERSION,
            "observation_inventory_digest": observed_digest,
            "training_observation_ids": config.training_observation_ids,
            "evaluation_observation_ids": config.evaluation_observation_ids,
            "calendar_block_duration_ns": config.calendar_block_duration_ns,
        }
    )
    payload = {
        "observation_inventory_digest": observed_digest,
        "hypothesis_inventory_digest": state_digest,
        "observation_partition_digest": partition_digest,
        "covariance_policy_digest": config.covariance.content_digest,
        "covariance_parameters_calibrated": config.covariance.calibrated,
        "config_digest": config.content_digest,
        "training_observation_count": len(training),
        "training_usable_observation_count": training_usable,
        "training_calendar_block_count": len(training_blocks),
        "evaluation_observation_count": len(evaluation),
        "evaluation_usable_observation_count": evaluation_usable,
        "evaluation_calendar_block_count": len(evaluation_blocks),
        "evaluation_usable_calendar_block_count": evaluation_usable_blocks,
        "evaluation_observation_coverage": observation_coverage,
        "evaluation_block_coverage": block_coverage,
        "opportunity_inventory_complete": config.opportunity_inventory_complete,
        "missing_opportunities_retained": config.opportunity_inventory_complete,
        "coverage_conditioned_on_observed_rows": (not config.opportunity_inventory_complete),
        "evaluation_mixture_prequential_negative_log_likelihood": total_evaluation_nll,
        "blocks": [asdict(item) for item in block_results],
        "states": [asdict(item) for item in state_summaries],
        "families": [asdict(item) for item in family_summaries],
        "abstention_recommended": bool(diagnostics),
        "abstention_diagnostics": diagnostics,
        "algorithm_version": _ALGORITHM_VERSION,
        "exact_common_observation_inventory": True,
        "shared_measurement_covariance_across_families": True,
        "score_before_assimilate": True,
        "hierarchical_family_state_priors_normalized": True,
        "empirical_rank_calibration_applied": False,
        "identity_probability_calibrated": False,
        "model_selection_gate_produced": False,
        "identity_claimed": False,
    }
    result_digest = canonical_digest(payload)
    return BlockPredictiveEvidenceResult(
        observation_inventory_digest=observed_digest,
        hypothesis_inventory_digest=state_digest,
        observation_partition_digest=partition_digest,
        covariance_policy_digest=config.covariance.content_digest,
        covariance_parameters_calibrated=config.covariance.calibrated,
        config_digest=config.content_digest,
        training_observation_count=len(training),
        training_usable_observation_count=training_usable,
        training_calendar_block_count=len(training_blocks),
        evaluation_observation_count=len(evaluation),
        evaluation_usable_observation_count=evaluation_usable,
        evaluation_calendar_block_count=len(evaluation_blocks),
        evaluation_usable_calendar_block_count=evaluation_usable_blocks,
        evaluation_observation_coverage=observation_coverage,
        evaluation_block_coverage=block_coverage,
        opportunity_inventory_complete=config.opportunity_inventory_complete,
        missing_opportunities_retained=config.opportunity_inventory_complete,
        coverage_conditioned_on_observed_rows=(not config.opportunity_inventory_complete),
        evaluation_mixture_prequential_negative_log_likelihood=total_evaluation_nll,
        blocks=tuple(block_results),
        states=state_summaries,
        families=family_summaries,
        abstention_recommended=bool(diagnostics),
        abstention_diagnostics=tuple(diagnostics),
        result_digest=result_digest,
    )


def block_predictive_evidence_result_payload(
    result: BlockPredictiveEvidenceResult,
) -> dict[str, object]:
    """Return a JSON-compatible result after verifying complete digest closure."""

    document = asdict(result)
    claimed = document.pop("result_digest")
    if claimed != canonical_digest(document):
        raise BlockPredictiveInputError("block-predictive result digest does not close")
    return {**document, "result_digest": claimed}


def _models_for_block(
    state: FrozenLinearGaussianState,
    block: tuple[BlockPredictiveObservation, ...],
    *,
    inline_models_by_state: dict[str, dict[str, FrozenStateObservationModel]],
    external_model_provider: StateObservationModelProvider | None,
) -> dict[str, FrozenStateObservationModel]:
    inline = inline_models_by_state.get(state.state_id)
    if inline is not None:
        return inline
    if external_model_provider is None:
        raise BlockPredictiveInputError("external state prediction provider is absent")
    observation_ids = tuple(item.observation_id for item in block)
    try:
        rows = external_model_provider(state.state_id, observation_ids)
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise BlockPredictiveInputError("external state prediction provider failed") from error
    if tuple(item.observation_id for item in rows) != observation_ids:
        raise BlockPredictiveInputError(
            "external state predictions differ from the exact chronological block inventory"
        )
    if any(len(item.design_row) != len(state.parameter_prior_mean) for item in rows):
        raise BlockPredictiveInputError("external state design dimension differs from its prior")
    return {item.observation_id: item for item in rows}


def _score_and_update(
    block: tuple[BlockPredictiveObservation, ...],
    model_by_id: dict[str, FrozenStateObservationModel],
    *,
    parameter_mean: tuple[float, ...],
    parameter_covariance: tuple[tuple[float, ...], ...],
    covariance: CalendarBlockCovariance,
) -> _GaussianUpdate:
    usable = tuple(item for item in block if item.status == "usable")
    if not usable:
        return _GaussianUpdate(
            negative_log_likelihood=0.0,
            mahalanobis_squared=0.0,
            log_determinant=0.0,
            posterior_mean=parameter_mean,
            posterior_covariance=parameter_covariance,
        )
    parameter_count = len(parameter_mean)
    prior_cholesky = _cholesky(parameter_covariance, "parameter posterior covariance")
    residuals: list[float] = []
    independent_variances: list[float] = []
    whitened_design: list[tuple[float, ...]] = []
    common_sigma = math.sqrt(covariance.block_common_variance_hz2)
    for observation in usable:
        model = model_by_id[observation.observation_id]
        if observation.measured_cfo_hz is None or observation.standard_uncertainty_hz is None:
            raise AssertionError("validated usable observation lost its response")
        fitted_nuisance = math.fsum(
            value * coefficient
            for value, coefficient in zip(model.design_row, parameter_mean, strict=True)
        )
        residual = observation.measured_cfo_hz - model.base_prediction_hz - fitted_nuisance
        diagonal_variance = (
            covariance.measurement_variance_scale * observation.standard_uncertainty_hz**2
            + covariance.independent_variance_floor_hz2
            + model.prediction_standard_uncertainty_hz**2
        )
        if (
            not math.isfinite(residual)
            or not math.isfinite(diagonal_variance)
            or (diagonal_variance <= 0.0)
        ):
            raise BlockPredictiveNumericalError(
                "block residual variance is not positive and finite"
            )
        parameter_row = tuple(
            math.fsum(
                model.design_row[index] * prior_cholesky[index][column]
                for index in range(column, parameter_count)
            )
            for column in range(parameter_count)
        )
        whitened_design.append(
            (*parameter_row, common_sigma) if common_sigma > 0.0 else parameter_row
        )
        residuals.append(residual)
        independent_variances.append(diagonal_variance)

    latent_count = len(whitened_design[0])
    information = tuple(
        tuple(
            (1.0 if left == right else 0.0)
            + math.fsum(
                row[left] * row[right] / variance
                for row, variance in zip(
                    whitened_design,
                    independent_variances,
                    strict=True,
                )
            )
            for right in range(latent_count)
        )
        for left in range(latent_count)
    )
    projected = tuple(
        math.fsum(
            row[column] * residual / variance
            for row, residual, variance in zip(
                whitened_design,
                residuals,
                independent_variances,
                strict=True,
            )
        )
        for column in range(latent_count)
    )
    information_cholesky = _cholesky(information, "block predictive information")
    latent_posterior_mean = _solve_cholesky(information_cholesky, projected)
    conditional_residuals = tuple(
        residual
        - math.fsum(
            value * coefficient
            for value, coefficient in zip(row, latent_posterior_mean, strict=True)
        )
        for row, residual in zip(whitened_design, residuals, strict=True)
    )
    mahalanobis = math.fsum(
        residual * residual / variance
        for residual, variance in zip(
            conditional_residuals,
            independent_variances,
            strict=True,
        )
    ) + math.fsum(value * value for value in latent_posterior_mean)
    log_determinant = math.fsum(math.log(item) for item in independent_variances) + 2.0 * math.fsum(
        math.log(information_cholesky[index][index]) for index in range(latent_count)
    )
    nll = 0.5 * math.fsum((mahalanobis, log_determinant, len(usable) * math.log(2.0 * math.pi)))
    if any(not math.isfinite(item) for item in (mahalanobis, log_determinant, nll)) or (
        mahalanobis < 0.0
    ):
        raise BlockPredictiveNumericalError("block predictive density is not representable")

    inverse_columns = tuple(
        _solve_cholesky(
            information_cholesky,
            tuple(1.0 if row == column else 0.0 for row in range(latent_count)),
        )
        for column in range(parameter_count)
    )
    latent_parameter_covariance = tuple(
        tuple(inverse_columns[column][row] for column in range(parameter_count))
        for row in range(parameter_count)
    )
    parameter_shift = tuple(
        math.fsum(
            prior_cholesky[row][column] * latent_posterior_mean[column] for column in range(row + 1)
        )
        for row in range(parameter_count)
    )
    posterior_mean = tuple(
        mean + shift for mean, shift in zip(parameter_mean, parameter_shift, strict=True)
    )
    left_product = tuple(
        tuple(
            math.fsum(
                prior_cholesky[row][index] * latent_parameter_covariance[index][column]
                for index in range(row + 1)
            )
            for column in range(parameter_count)
        )
        for row in range(parameter_count)
    )
    posterior_covariance = tuple(
        tuple(
            math.fsum(
                left_product[row][index] * prior_cholesky[column][index]
                for index in range(column + 1)
            )
            for column in range(parameter_count)
        )
        for row in range(parameter_count)
    )
    posterior_covariance = _symmetrize(posterior_covariance)
    _cholesky(posterior_covariance, "updated parameter covariance")
    if any(not math.isfinite(item) for item in posterior_mean):
        raise BlockPredictiveNumericalError("updated parameter mean is not finite")
    return _GaussianUpdate(
        negative_log_likelihood=nll,
        mahalanobis_squared=mahalanobis,
        log_determinant=log_determinant,
        posterior_mean=posterior_mean,
        posterior_covariance=posterior_covariance,
    )


def _calendar_blocks(
    observations: tuple[BlockPredictiveObservation, ...],
    duration_ns: int,
) -> dict[int, tuple[BlockPredictiveObservation, ...]]:
    grouped: dict[int, list[BlockPredictiveObservation]] = {}
    for item in observations:
        grouped.setdefault(item.support_center_utc_ns // duration_ns, []).append(item)
    return {index: tuple(values) for index, values in sorted(grouped.items())}


def _validate_common_inventory(
    observations: tuple[BlockPredictiveObservation, ...],
    states: tuple[FrozenLinearGaussianState, ...],
    *,
    config: BlockPredictiveEvidenceConfig,
) -> None:
    ids = tuple(item.observation_id for item in observations)
    partition = config.training_observation_ids + config.evaluation_observation_ids
    if set(partition) != set(ids) or len(partition) != len(ids):
        raise BlockPredictiveInputError("training and evaluation must exhaust observations")
    id_positions = {item: index for index, item in enumerate(ids)}
    if tuple(sorted(config.training_observation_ids, key=id_positions.__getitem__)) != (
        config.training_observation_ids
    ) or tuple(sorted(config.evaluation_observation_ids, key=id_positions.__getitem__)) != (
        config.evaluation_observation_ids
    ):
        raise BlockPredictiveInputError("partitions must preserve chronological inventory order")
    observation_by_id = {item.observation_id: item for item in observations}
    if max(
        observation_by_id[item].support_end_utc_ns for item in config.training_observation_ids
    ) > min(
        observation_by_id[item].support_start_utc_ns for item in config.evaluation_observation_ids
    ):
        raise BlockPredictiveInputError("training support must end before evaluation support")
    for state in states:
        if not state.observation_models:
            continue
        state_ids = tuple(item.observation_id for item in state.observation_models)
        if state_ids != ids:
            raise BlockPredictiveInputError(
                "every state must model the exact common chronological observation inventory"
            )
    training_usable = sum(
        observation_by_id[item].status == "usable" for item in config.training_observation_ids
    )
    if training_usable < 1:
        raise BlockPredictiveInputError("at least one usable training observation is required")


def _preflight_work_bounds(
    observations: tuple[BlockPredictiveObservation, ...],
    states: tuple[FrozenLinearGaussianState, ...],
    *,
    config: BlockPredictiveEvidenceConfig,
) -> None:
    """Reject conservative metadata-sized work before response values are inspected."""

    try:
        observation_count = len(observations)
        state_count = len(states)
    except TypeError as error:
        raise BlockPredictiveInputError(
            "observation and state inventories must be sized"
        ) from error
    if observation_count > config.maximum_observation_count:
        raise BlockPredictiveWorkLimitError("observation inventory exceeds its work cap")
    if state_count > config.maximum_hypothesis_count:
        raise BlockPredictiveWorkLimitError("hypothesis inventory exceeds its work cap")
    if observation_count < 2 or state_count < 3:
        raise BlockPredictiveInputError("block evidence needs observations and all three families")
    if state_count * observation_count > config.maximum_state_observation_evaluations:
        raise BlockPredictiveWorkLimitError("state-row inventory exceeds its work cap")
    for state in states:
        try:
            parameter_count = len(state.parameter_prior_mean)
            model_count = len(state.observation_models)
        except (AttributeError, TypeError) as error:
            raise BlockPredictiveInputError("state inventory is malformed") from error
        if parameter_count > config.maximum_parameter_count:
            raise BlockPredictiveWorkLimitError("state parameter dimension exceeds its work cap")
        if model_count > config.maximum_observation_count:
            raise BlockPredictiveWorkLimitError("state-row inventory exceeds its work cap")
    try:
        block_counts: dict[int, int] = {}
        for item in observations:
            block = item.support_center_utc_ns // config.calendar_block_duration_ns
            block_counts[block] = block_counts.get(block, 0) + 1
    except (AttributeError, TypeError, ZeroDivisionError) as error:
        raise BlockPredictiveInputError("observation support metadata is malformed") from error
    if block_counts and max(block_counts.values()) > config.maximum_rows_per_calendar_block:
        raise BlockPredictiveWorkLimitError("calendar block exceeds its row-work cap")


def _revalidate_observations(
    values: tuple[BlockPredictiveObservation, ...],
) -> tuple[BlockPredictiveObservation, ...]:
    try:
        copied = tuple(BlockPredictiveObservation(**asdict(item)) for item in values)
    except (AttributeError, TypeError, ValueError) as error:
        raise BlockPredictiveInputError("observation inventory is invalid") from error
    if len({item.observation_id for item in copied}) != len(copied):
        raise BlockPredictiveInputError("observation identities must be unique")
    if copied != tuple(
        sorted(copied, key=lambda item: (item.support_center_utc_ns, item.observation_id))
    ):
        raise BlockPredictiveInputError("observation inventory must be chronological")
    return copied


def _revalidate_states(
    values: tuple[FrozenLinearGaussianState, ...],
) -> tuple[FrozenLinearGaussianState, ...]:
    try:
        copied = tuple(
            FrozenLinearGaussianState(
                state_id=item.state_id,
                family=item.family,
                model_authority_digest=item.model_authority_digest,
                log_prior_weight_within_family=item.log_prior_weight_within_family,
                parameter_prior_mean=tuple(item.parameter_prior_mean),
                parameter_prior_covariance=tuple(
                    tuple(row) for row in item.parameter_prior_covariance
                ),
                observation_models=tuple(
                    FrozenStateObservationModel(**asdict(row)) for row in item.observation_models
                ),
                prediction_inventory_reference_digest=(item.prediction_inventory_reference_digest),
            )
            for item in values
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise BlockPredictiveInputError("hypothesis inventory is invalid") from error
    if len({item.state_id for item in copied}) != len(copied):
        raise BlockPredictiveInputError("state identities must be unique")
    return tuple(sorted(copied, key=_state_sort_key))


def _revalidate_config(value: BlockPredictiveEvidenceConfig) -> BlockPredictiveEvidenceConfig:
    try:
        return BlockPredictiveEvidenceConfig(
            training_observation_ids=tuple(value.training_observation_ids),
            evaluation_observation_ids=tuple(value.evaluation_observation_ids),
            expected_observation_inventory_digest=value.expected_observation_inventory_digest,
            expected_hypothesis_inventory_digest=value.expected_hypothesis_inventory_digest,
            family_prior_weights=tuple(
                FamilyPriorWeight(item.family, item.log_weight)
                for item in value.family_prior_weights
            ),
            covariance=CalendarBlockCovariance(**asdict(value.covariance)),
            calendar_block_duration_ns=value.calendar_block_duration_ns,
            minimum_usable_evaluation_observations=(value.minimum_usable_evaluation_observations),
            minimum_usable_evaluation_blocks=value.minimum_usable_evaluation_blocks,
            minimum_evaluation_observation_coverage=(value.minimum_evaluation_observation_coverage),
            minimum_evaluation_block_coverage=value.minimum_evaluation_block_coverage,
            opportunity_inventory_complete=value.opportunity_inventory_complete,
            maximum_observation_count=value.maximum_observation_count,
            maximum_hypothesis_count=value.maximum_hypothesis_count,
            maximum_parameter_count=value.maximum_parameter_count,
            maximum_rows_per_calendar_block=value.maximum_rows_per_calendar_block,
            maximum_state_observation_evaluations=(value.maximum_state_observation_evaluations),
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise BlockPredictiveInputError("block-predictive config is invalid") from error


def _normalized_log_runtime_masses(runtimes: list[_StateRuntime]) -> dict[str, float]:
    normalizer = _logsumexp(tuple(item.cumulative_log_joint for item in runtimes))
    return {item.state.state_id: item.cumulative_log_joint - normalizer for item in runtimes}


def _family_log_masses(
    runtimes: list[_StateRuntime],
    state_log_masses: dict[str, float],
) -> dict[PredictiveFamily, float]:
    return {
        family: _logsumexp(
            tuple(
                state_log_masses[item.state.state_id]
                for item in runtimes
                if item.state.family == family
            )
        )
        for family in _FAMILIES
    }


def _normalized_log_weights(values: tuple[float, ...]) -> tuple[float, ...]:
    if not values or any(not math.isfinite(item) for item in values):
        raise BlockPredictiveInputError("prior weights must be finite and nonempty")
    normalizer = _logsumexp(values)
    return tuple(item - normalizer for item in values)


def _logsumexp(values: tuple[float, ...]) -> float:
    if not values or any(not math.isfinite(item) for item in values):
        raise BlockPredictiveNumericalError("log-sum-exp inputs must be finite and nonempty")
    maximum = max(values)
    shifted = math.fsum(math.exp(item - maximum) for item in values)
    result = maximum + math.log(shifted)
    if not math.isfinite(result):
        raise BlockPredictiveNumericalError("log-sum-exp is not representable")
    return result


def _validated_square_matrix(
    value: tuple[tuple[float, ...], ...],
    *,
    dimension: int,
    name: str,
) -> tuple[tuple[float, ...], ...]:
    if len(value) != dimension or any(len(row) != dimension for row in value):
        raise BlockPredictiveInputError(f"{name} dimension is invalid")
    copied = tuple(tuple(float(item) for item in row) for row in value)
    if any(not math.isfinite(item) for row in copied for item in row):
        raise BlockPredictiveInputError(f"{name} must be finite")
    tolerance = 64.0 * math.ulp(max(1.0, *(abs(item) for row in copied for item in row)))
    if any(
        abs(copied[row][column] - copied[column][row]) > tolerance
        for row in range(dimension)
        for column in range(row)
    ):
        raise BlockPredictiveInputError(f"{name} must be symmetric")
    return _symmetrize(copied)


def _cholesky(
    matrix: tuple[tuple[float, ...], ...],
    name: str,
) -> tuple[tuple[float, ...], ...]:
    dimension = len(matrix)
    if dimension < 1 or any(len(row) != dimension for row in matrix):
        raise BlockPredictiveNumericalError(f"{name} is not square")
    lower = [[0.0 for _ in range(dimension)] for _ in range(dimension)]
    for row in range(dimension):
        for column in range(row + 1):
            reduced = matrix[row][column] - math.fsum(
                lower[row][index] * lower[column][index] for index in range(column)
            )
            if row == column:
                if not math.isfinite(reduced) or reduced <= 0.0:
                    raise BlockPredictiveNumericalError(f"{name} is not positive definite")
                lower[row][column] = math.sqrt(reduced)
            else:
                value = reduced / lower[column][column]
                if not math.isfinite(value):
                    raise BlockPredictiveNumericalError(f"{name} factor is not finite")
                lower[row][column] = value
    return tuple(tuple(row) for row in lower)


def _solve_cholesky(
    lower: tuple[tuple[float, ...], ...],
    rhs: tuple[float, ...],
) -> tuple[float, ...]:
    dimension = len(lower)
    if len(rhs) != dimension:
        raise BlockPredictiveNumericalError("Cholesky solve dimension differs")
    forward: list[float] = []
    for row in range(dimension):
        value = (rhs[row] - math.fsum(lower[row][i] * forward[i] for i in range(row))) / (
            lower[row][row]
        )
        if not math.isfinite(value):
            raise BlockPredictiveNumericalError("Cholesky forward solve is not finite")
        forward.append(value)
    result = [0.0 for _ in range(dimension)]
    for row in reversed(range(dimension)):
        value = (
            forward[row]
            - math.fsum(lower[index][row] * result[index] for index in range(row + 1, dimension))
        ) / lower[row][row]
        if not math.isfinite(value):
            raise BlockPredictiveNumericalError("Cholesky backward solve is not finite")
        result[row] = value
    return tuple(result)


def _symmetrize(
    matrix: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple((matrix[row][column] + matrix[column][row]) / 2.0 for column in range(len(matrix)))
        for row in range(len(matrix))
    )


def _state_sort_key(state: FrozenLinearGaussianState) -> tuple[int, str]:
    return (_FAMILIES.index(state.family), state.state_id)


def _is_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith(_SHA256_PREFIX):
        return False
    hexadecimal = value[len(_SHA256_PREFIX) :]
    return len(hexadecimal) == _SHA256_HEX_LENGTH and all(
        item in "0123456789abcdef" for item in hexadecimal
    )


__all__ = [
    "BlockPredictiveEvidenceConfig",
    "BlockPredictiveEvidenceResult",
    "BlockPredictiveInputError",
    "BlockPredictiveNumericalError",
    "BlockPredictiveObservation",
    "BlockPredictiveWorkLimitError",
    "CalendarBlockCovariance",
    "CalendarBlockPredictiveScore",
    "FamilyBlockPredictiveScore",
    "FamilyPredictiveSummary",
    "FamilyPriorWeight",
    "FrozenLinearGaussianState",
    "FrozenStateObservationModel",
    "StateBlockPredictiveScore",
    "StateObservationModelProvider",
    "StatePredictiveSummary",
    "block_predictive_evidence_result_payload",
    "hypothesis_inventory_digest",
    "observation_inventory_digest",
    "score_block_predictive_evidence",
]
