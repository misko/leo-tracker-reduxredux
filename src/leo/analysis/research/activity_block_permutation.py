"""Deterministic constrained half-second prediction-time permutations.

This Research-only primitive replaces the affine v1 activity-block control for
new experiments.  It maps each observed half-second block to one prediction
block while preserving probe cadence inside a block.  The mapping is a perfect
matching selected by a digest-ranked, explicitly bounded search.

The constraints prevent a short-lag coherent subsequence from surviving the
control: directed displacements may not repeat at any forward lag covered by
the delay search, and no displacement may occur more than three times.  A plan
also requires at least half as many distinct directed displacements as blocks
and rejects every affine permutation.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from numbers import Integral, Real

from leo.analysis.research.satellite_activity import ActivityGrid, CfoProbe
from leo.contracts.digests import canonical_digest, sha256_digest

BLOCK_DURATION_S = 0.5
ALGORITHM_VERSION = "research-activity-block-permutation-v1"
_RANKING_VERSION = "research-activity-block-matching-ranking-v1"
_MAXIMUM_SEARCH_ATTEMPTS = 64
_MAXIMUM_SEARCH_STEPS_PER_ATTEMPT = 100_000
_MAXIMUM_DIRECTED_DISPLACEMENT_MULTIPLICITY = 3
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def _grid_payload(grid: ActivityGrid) -> dict[str, object]:
    return {
        "start_s": grid.start_s,
        "cell_duration_s": grid.cell_duration_s,
        "cell_count": int(grid.cell_count),
        "minimum_active_cells": int(grid.minimum_active_cells),
        "allow_left_censored": grid.allow_left_censored,
        "allow_right_censored": grid.allow_right_censored,
    }


def _block_geometry(grid: ActivityGrid) -> tuple[int, int]:
    ratio = BLOCK_DURATION_S / grid.cell_duration_s
    block_cells = round(ratio)
    if block_cells < 1 or not math.isclose(
        block_cells * grid.cell_duration_s,
        BLOCK_DURATION_S,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("block permutation requires cells that exactly tile a 0.5-second block")
    if grid.cell_count % block_cells:
        raise ValueError(
            "block permutation requires cell_count divisible by half-second block cells"
        )
    block_count = int(grid.cell_count) // block_cells
    if block_count < 2:
        raise ValueError("a block permutation requires at least two complete half-second blocks")
    return block_cells, block_count


def _validate_nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return int(value)


def _validate_control_geometry(
    block_count: int,
    maximum_delay_support_s: object,
) -> tuple[float, int, tuple[int, ...], int]:
    if (
        isinstance(maximum_delay_support_s, bool)
        or not isinstance(maximum_delay_support_s, Real)
        or not math.isfinite(maximum_delay_support_s)
        or maximum_delay_support_s < 0.0
    ):
        raise ValueError("maximum delay support must be finite and nonnegative")

    delay_support_s = float(maximum_delay_support_s)
    minimum_blocks = math.floor(delay_support_s / BLOCK_DURATION_S) + 1
    if minimum_blocks > block_count // 2:
        raise ValueError("displacement beyond maximum delay support is impossible on this circle")

    maximum_forbidden_lag = math.ceil(delay_support_s / BLOCK_DURATION_S)
    forbidden_lags = tuple(range(1, maximum_forbidden_lag + 1))
    required_distinct = math.ceil(block_count / 2)
    available_displacements = block_count - 2 * minimum_blocks + 1
    if available_displacements < required_distinct:
        raise ValueError("required directed-displacement diversity is impossible on this circle")

    if forbidden_lags:
        circular_spacing_capacity = block_count // (maximum_forbidden_lag + 1)
        per_displacement_capacity = min(
            _MAXIMUM_DIRECTED_DISPLACEMENT_MULTIPLICITY,
            circular_spacing_capacity,
        )
        if available_displacements * per_displacement_capacity < block_count:
            raise ValueError("forward-lag and displacement-multiplicity constraints are infeasible")

    return delay_support_s, minimum_blocks, forbidden_lags, required_distinct


def _circular_distance(left: int, right: int, count: int) -> int:
    direct = abs(left - right)
    return min(direct, count - direct)


def _is_affine_mapping(mapping: tuple[int, ...]) -> bool:
    count = len(mapping)
    offset = mapping[0]
    multiplier = (mapping[1] - offset) % count
    return all(
        predicted == (multiplier * observed + offset) % count
        for observed, predicted in enumerate(mapping)
    )


def _preserved_forward_lag_counts(
    mapping: tuple[int, ...], forbidden_lags: tuple[int, ...]
) -> tuple[tuple[int, int], ...]:
    count = len(mapping)
    return tuple(
        (
            lag,
            sum(
                mapping[(observed + lag) % count] == (predicted + lag) % count
                for observed, predicted in enumerate(mapping)
            ),
        )
        for lag in forbidden_lags
    )


@dataclass(frozen=True, slots=True)
class ActivityBlockPermutationDiagnostics:
    """Auditable measurements of the selected bounded-search result."""

    selection_attempt_count: int
    selected_attempt_search_step_count: int
    total_search_step_count: int
    forbidden_forward_lag_blocks: tuple[int, ...]
    preserved_forward_lag_counts: tuple[tuple[int, int], ...]
    directed_displacement_multiplicities: tuple[tuple[int, int], ...]
    distinct_directed_displacement_count: int
    required_distinct_directed_displacement_count: int
    maximum_directed_displacement_multiplicity: int
    allowed_maximum_directed_displacement_multiplicity: int
    realized_minimum_circular_displacement_blocks: int
    mapping_is_affine: bool

    def __post_init__(self) -> None:
        integer_fields = (
            self.selection_attempt_count,
            self.selected_attempt_search_step_count,
            self.total_search_step_count,
            self.distinct_directed_displacement_count,
            self.required_distinct_directed_displacement_count,
            self.maximum_directed_displacement_multiplicity,
            self.allowed_maximum_directed_displacement_multiplicity,
            self.realized_minimum_circular_displacement_blocks,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, Integral) for value in integer_fields
        ):
            raise ValueError("block-permutation diagnostics must use integer counts")
        if not 1 <= self.selection_attempt_count <= _MAXIMUM_SEARCH_ATTEMPTS:
            raise ValueError("selection attempt count lies outside the bounded search")
        if not (1 <= self.selected_attempt_search_step_count <= _MAXIMUM_SEARCH_STEPS_PER_ATTEMPT):
            raise ValueError("selected-attempt search step count lies outside the bounded search")
        if not (
            self.selected_attempt_search_step_count + self.selection_attempt_count - 1
            <= self.total_search_step_count
            <= self.selection_attempt_count * _MAXIMUM_SEARCH_STEPS_PER_ATTEMPT
        ):
            raise ValueError("total search step count lies outside the bounded search")
        if (
            self.selection_attempt_count == 1
            and self.total_search_step_count != self.selected_attempt_search_step_count
        ):
            raise ValueError("single-attempt search-step diagnostics disagree")
        if (
            self.distinct_directed_displacement_count < 1
            or self.required_distinct_directed_displacement_count < 1
            or self.maximum_directed_displacement_multiplicity < 1
            or self.realized_minimum_circular_displacement_blocks < 1
        ):
            raise ValueError("block-permutation diagnostic counts must be positive")
        if (
            self.allowed_maximum_directed_displacement_multiplicity
            != _MAXIMUM_DIRECTED_DISPLACEMENT_MULTIPLICITY
        ):
            raise ValueError("diagnostics disagree with the displacement-multiplicity limit")
        if not isinstance(self.mapping_is_affine, bool):
            raise ValueError("mapping affine diagnostic must be a boolean")

        if not isinstance(self.forbidden_forward_lag_blocks, tuple) or any(
            isinstance(lag, bool) or not isinstance(lag, Integral) or lag < 1
            for lag in self.forbidden_forward_lag_blocks
        ):
            raise ValueError("forbidden forward lags must be positive integer block counts")
        if self.forbidden_forward_lag_blocks != tuple(
            range(1, len(self.forbidden_forward_lag_blocks) + 1)
        ):
            raise ValueError("forbidden forward lags must be a contiguous prefix")

        if not isinstance(self.preserved_forward_lag_counts, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or isinstance(item[0], bool)
            or not isinstance(item[0], Integral)
            or isinstance(item[1], bool)
            or not isinstance(item[1], Integral)
            or item[1] < 0
            for item in self.preserved_forward_lag_counts
        ):
            raise ValueError("preserved forward-lag diagnostics must be integer pairs")
        if tuple(lag for lag, _count in self.preserved_forward_lag_counts) != (
            self.forbidden_forward_lag_blocks
        ):
            raise ValueError("preserved forward-lag diagnostics disagree with forbidden lags")

        if not isinstance(self.directed_displacement_multiplicities, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or isinstance(item[0], bool)
            or not isinstance(item[0], Integral)
            or item[0] < 0
            or isinstance(item[1], bool)
            or not isinstance(item[1], Integral)
            or item[1] < 1
            for item in self.directed_displacement_multiplicities
        ):
            raise ValueError("directed-displacement diagnostics must be integer pairs")
        if tuple(
            displacement for displacement, _count in self.directed_displacement_multiplicities
        ) != tuple(
            sorted(
                displacement for displacement, _count in self.directed_displacement_multiplicities
            )
        ):
            raise ValueError("directed-displacement diagnostics must be sorted")
        if len({item[0] for item in self.directed_displacement_multiplicities}) != len(
            self.directed_displacement_multiplicities
        ):
            raise ValueError("directed-displacement diagnostics must have unique keys")
        if self.distinct_directed_displacement_count != len(
            self.directed_displacement_multiplicities
        ):
            raise ValueError("distinct-displacement count disagrees with multiplicities")
        if self.maximum_directed_displacement_multiplicity != max(
            count for _displacement, count in self.directed_displacement_multiplicities
        ):
            raise ValueError("maximum displacement multiplicity disagrees with multiplicities")


def _diagnostics_for_mapping(
    mapping: tuple[int, ...],
    *,
    forbidden_lags: tuple[int, ...],
    required_distinct: int,
    selection_attempt_count: int,
    selected_attempt_search_step_count: int,
    total_search_step_count: int,
) -> ActivityBlockPermutationDiagnostics:
    block_count = len(mapping)
    displacement_counts = Counter(
        (predicted - observed) % block_count for observed, predicted in enumerate(mapping)
    )
    multiplicities = tuple(sorted(displacement_counts.items()))
    return ActivityBlockPermutationDiagnostics(
        selection_attempt_count=selection_attempt_count,
        selected_attempt_search_step_count=selected_attempt_search_step_count,
        total_search_step_count=total_search_step_count,
        forbidden_forward_lag_blocks=forbidden_lags,
        preserved_forward_lag_counts=_preserved_forward_lag_counts(mapping, forbidden_lags),
        directed_displacement_multiplicities=multiplicities,
        distinct_directed_displacement_count=len(multiplicities),
        required_distinct_directed_displacement_count=required_distinct,
        maximum_directed_displacement_multiplicity=max(multiplicities, key=lambda item: item[1])[1],
        allowed_maximum_directed_displacement_multiplicity=(
            _MAXIMUM_DIRECTED_DISPLACEMENT_MULTIPLICITY
        ),
        realized_minimum_circular_displacement_blocks=min(
            _circular_distance(observed, predicted, block_count)
            for observed, predicted in enumerate(mapping)
        ),
        mapping_is_affine=_is_affine_mapping(mapping),
    )


def _selection_context(
    *,
    grid: ActivityGrid,
    session_key_digest: str,
    control_index: int,
    maximum_delay_support_s: float,
    minimum_circular_displacement_blocks: int,
    forbidden_lags: tuple[int, ...],
    required_distinct: int,
    maximum_search_attempts: int,
    maximum_search_steps_per_attempt: int,
) -> dict[str, object]:
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "ranking_version": _RANKING_VERSION,
        "session_key_digest": session_key_digest,
        "control_index": control_index,
        "grid": _grid_payload(grid),
        "block_duration_s": BLOCK_DURATION_S,
        "maximum_delay_support_s": maximum_delay_support_s,
        "minimum_circular_displacement_blocks": minimum_circular_displacement_blocks,
        "forbidden_forward_lag_blocks": list(forbidden_lags),
        "required_distinct_directed_displacement_count": required_distinct,
        "allowed_maximum_directed_displacement_multiplicity": (
            _MAXIMUM_DIRECTED_DISPLACEMENT_MULTIPLICITY
        ),
        "maximum_search_attempts": maximum_search_attempts,
        "maximum_search_steps_per_attempt": maximum_search_steps_per_attempt,
    }


def _ranked_prediction_blocks(
    *,
    context_digest: str,
    attempt_index: int,
    observation_block: int,
    block_count: int,
    minimum_circular_displacement_blocks: int,
) -> tuple[int, ...]:
    attempt_seed = hashlib.sha256(f"{context_digest}:{attempt_index}".encode("ascii")).digest()
    candidates = (
        prediction_block
        for prediction_block in range(block_count)
        if _circular_distance(observation_block, prediction_block, block_count)
        >= minimum_circular_displacement_blocks
    )
    return tuple(
        sorted(
            candidates,
            key=lambda prediction_block: hashlib.sha256(
                attempt_seed + f":{observation_block}:{prediction_block}".encode("ascii")
            ).digest(),
        )
    )


def _search_one_attempt(
    *,
    context_digest: str,
    attempt_index: int,
    block_count: int,
    minimum_circular_displacement_blocks: int,
    maximum_forbidden_lag: int,
    required_distinct: int,
    maximum_search_steps: int,
) -> tuple[tuple[int, ...] | None, int]:
    candidate_orders = tuple(
        _ranked_prediction_blocks(
            context_digest=context_digest,
            attempt_index=attempt_index,
            observation_block=observation_block,
            block_count=block_count,
            minimum_circular_displacement_blocks=minimum_circular_displacement_blocks,
        )
        for observation_block in range(block_count)
    )
    mapping = [-1] * block_count
    used_prediction_blocks = [False] * block_count
    displacement_counts = [0] * block_count
    next_candidate = [0] * block_count
    distinct_displacements = 0
    search_steps = 0
    observation_block = 0

    while observation_block >= 0:
        if observation_block == block_count:
            candidate_mapping = tuple(mapping)
            if distinct_displacements >= required_distinct and not _is_affine_mapping(
                candidate_mapping
            ):
                return candidate_mapping, search_steps
            observation_block -= 1
            predicted = mapping[observation_block]
            displacement = (predicted - observation_block) % block_count
            displacement_counts[displacement] -= 1
            if displacement_counts[displacement] == 0:
                distinct_displacements -= 1
            used_prediction_blocks[predicted] = False
            mapping[observation_block] = -1
            continue

        no_diversity_capacity = (
            distinct_displacements + block_count - observation_block < required_distinct
        )
        exhausted_candidates = next_candidate[observation_block] >= len(
            candidate_orders[observation_block]
        )
        if no_diversity_capacity or exhausted_candidates:
            next_candidate[observation_block] = 0
            if observation_block == 0:
                break
            observation_block -= 1
            predicted = mapping[observation_block]
            displacement = (predicted - observation_block) % block_count
            displacement_counts[displacement] -= 1
            if displacement_counts[displacement] == 0:
                distinct_displacements -= 1
            used_prediction_blocks[predicted] = False
            mapping[observation_block] = -1
            continue

        if search_steps >= maximum_search_steps:
            break
        predicted = candidate_orders[observation_block][next_candidate[observation_block]]
        next_candidate[observation_block] += 1
        search_steps += 1
        if used_prediction_blocks[predicted]:
            continue

        displacement = (predicted - observation_block) % block_count
        if displacement_counts[displacement] >= _MAXIMUM_DIRECTED_DISPLACEMENT_MULTIPLICITY:
            continue
        preserves_forbidden_lag = any(
            (
                observation_block - earlier_block <= maximum_forbidden_lag
                or block_count - (observation_block - earlier_block) <= maximum_forbidden_lag
            )
            and (mapping[earlier_block] - earlier_block) % block_count == displacement
            for earlier_block in range(observation_block)
        )
        if preserves_forbidden_lag:
            continue

        is_new_displacement = displacement_counts[displacement] == 0
        mapping[observation_block] = predicted
        used_prediction_blocks[predicted] = True
        displacement_counts[displacement] += 1
        if is_new_displacement:
            distinct_displacements += 1
        observation_block += 1
        if observation_block < block_count:
            next_candidate[observation_block] = 0

    return None, search_steps


def _choose_block_permutation(
    *,
    grid: ActivityGrid,
    session_key_digest: str,
    control_index: int,
    maximum_delay_support_s: float,
    minimum_circular_displacement_blocks: int,
    forbidden_lags: tuple[int, ...],
    required_distinct: int,
    block_count: int,
    maximum_search_attempts: int,
    maximum_search_steps_per_attempt: int,
) -> tuple[tuple[int, ...], ActivityBlockPermutationDiagnostics]:
    context_digest = canonical_digest(
        _selection_context(
            grid=grid,
            session_key_digest=session_key_digest,
            control_index=control_index,
            maximum_delay_support_s=maximum_delay_support_s,
            minimum_circular_displacement_blocks=minimum_circular_displacement_blocks,
            forbidden_lags=forbidden_lags,
            required_distinct=required_distinct,
            maximum_search_attempts=maximum_search_attempts,
            maximum_search_steps_per_attempt=maximum_search_steps_per_attempt,
        )
    )
    total_search_steps = 0
    for attempt_index in range(maximum_search_attempts):
        mapping, search_steps = _search_one_attempt(
            context_digest=context_digest,
            attempt_index=attempt_index,
            block_count=block_count,
            minimum_circular_displacement_blocks=minimum_circular_displacement_blocks,
            maximum_forbidden_lag=len(forbidden_lags),
            required_distinct=required_distinct,
            maximum_search_steps=maximum_search_steps_per_attempt,
        )
        total_search_steps += search_steps
        if mapping is None:
            continue
        diagnostics = _diagnostics_for_mapping(
            mapping,
            forbidden_lags=forbidden_lags,
            required_distinct=required_distinct,
            selection_attempt_count=attempt_index + 1,
            selected_attempt_search_step_count=search_steps,
            total_search_step_count=total_search_steps,
        )
        return mapping, diagnostics
    raise ValueError(
        "no non-affine perfect block matching satisfies the constraints within bounded search"
    )


def _diagnostics_payload(
    diagnostics: ActivityBlockPermutationDiagnostics,
) -> dict[str, object]:
    return {
        "selection_attempt_count": diagnostics.selection_attempt_count,
        "selected_attempt_search_step_count": (diagnostics.selected_attempt_search_step_count),
        "total_search_step_count": diagnostics.total_search_step_count,
        "forbidden_forward_lag_blocks": list(diagnostics.forbidden_forward_lag_blocks),
        "preserved_forward_lag_counts": [
            [lag, count] for lag, count in diagnostics.preserved_forward_lag_counts
        ],
        "directed_displacement_multiplicities": [
            [displacement, count]
            for displacement, count in diagnostics.directed_displacement_multiplicities
        ],
        "distinct_directed_displacement_count": (diagnostics.distinct_directed_displacement_count),
        "required_distinct_directed_displacement_count": (
            diagnostics.required_distinct_directed_displacement_count
        ),
        "maximum_directed_displacement_multiplicity": (
            diagnostics.maximum_directed_displacement_multiplicity
        ),
        "allowed_maximum_directed_displacement_multiplicity": (
            diagnostics.allowed_maximum_directed_displacement_multiplicity
        ),
        "realized_minimum_circular_displacement_blocks": (
            diagnostics.realized_minimum_circular_displacement_blocks
        ),
        "mapping_is_affine": diagnostics.mapping_is_affine,
    }


def _plan_payload(
    *,
    grid: ActivityGrid,
    block_cells: int,
    block_count: int,
    maximum_delay_support_s: float,
    minimum_circular_displacement_blocks: int,
    session_key_digest: str,
    control_index: int,
    maximum_search_attempts: int,
    maximum_search_steps_per_attempt: int,
    prediction_block_by_observation_block: tuple[int, ...],
    diagnostics: ActivityBlockPermutationDiagnostics,
) -> dict[str, object]:
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "ranking_version": _RANKING_VERSION,
        "session_key_digest": session_key_digest,
        "control_index": control_index,
        "maximum_search_attempts": maximum_search_attempts,
        "maximum_search_steps_per_attempt": maximum_search_steps_per_attempt,
        "grid": _grid_payload(grid),
        "block_duration_s": BLOCK_DURATION_S,
        "block_cells": block_cells,
        "block_count": block_count,
        "maximum_delay_support_s": maximum_delay_support_s,
        "minimum_circular_displacement_blocks": minimum_circular_displacement_blocks,
        "prediction_block_by_observation_block": list(prediction_block_by_observation_block),
        "diagnostics": _diagnostics_payload(diagnostics),
    }


@dataclass(frozen=True, slots=True)
class ActivityBlockPermutation:
    """One validated general block permutation for one session control arm."""

    grid: ActivityGrid
    block_cells: int
    block_count: int
    maximum_delay_support_s: float
    minimum_circular_displacement_blocks: int
    session_key_digest: str
    control_index: int
    maximum_search_attempts: int
    maximum_search_steps_per_attempt: int
    prediction_block_by_observation_block: tuple[int, ...]
    diagnostics: ActivityBlockPermutationDiagnostics
    plan_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.grid, ActivityGrid):
            raise ValueError("block-permutation grid must be an ActivityGrid")
        if any(
            isinstance(value, bool) or not isinstance(value, Integral)
            for value in (self.block_cells, self.block_count)
        ):
            raise ValueError("block-permutation geometry must use integer counts")
        expected_block_cells, expected_block_count = _block_geometry(self.grid)
        if self.block_cells != expected_block_cells or self.block_count != expected_block_count:
            raise ValueError("block-permutation geometry disagrees with its activity grid")
        delay_support_s, minimum_blocks, forbidden_lags, required_distinct = (
            _validate_control_geometry(self.block_count, self.maximum_delay_support_s)
        )
        if self.minimum_circular_displacement_blocks != minimum_blocks:
            raise ValueError("minimum circular displacement is not derived from delay support")
        control_index = _validate_nonnegative_integer(self.control_index, "control index")
        if not isinstance(self.session_key_digest, str) or not _SHA256_PATTERN.fullmatch(
            self.session_key_digest
        ):
            raise ValueError("session key digest must be a tagged lowercase SHA-256")
        if not isinstance(self.plan_digest, str) or not _SHA256_PATTERN.fullmatch(self.plan_digest):
            raise ValueError("plan digest must be a tagged lowercase SHA-256")
        if not isinstance(self.diagnostics, ActivityBlockPermutationDiagnostics):
            raise ValueError("block-permutation diagnostics have the wrong type")
        if any(
            isinstance(value, bool) or not isinstance(value, Integral)
            for value in (
                self.maximum_search_attempts,
                self.maximum_search_steps_per_attempt,
            )
        ):
            raise ValueError("block-permutation search caps must be integer counts")
        if (
            self.maximum_search_attempts != _MAXIMUM_SEARCH_ATTEMPTS
            or self.maximum_search_steps_per_attempt != _MAXIMUM_SEARCH_STEPS_PER_ATTEMPT
        ):
            raise ValueError("block-permutation search caps disagree with the v1 algorithm")
        if (
            self.diagnostics.selection_attempt_count > self.maximum_search_attempts
            or self.diagnostics.selected_attempt_search_step_count
            > self.maximum_search_steps_per_attempt
            or self.diagnostics.total_search_step_count
            > self.diagnostics.selection_attempt_count * self.maximum_search_steps_per_attempt
        ):
            raise ValueError("block-permutation diagnostics exceed the declared search caps")

        if not isinstance(self.prediction_block_by_observation_block, tuple) or any(
            isinstance(value, bool) or not isinstance(value, Integral)
            for value in self.prediction_block_by_observation_block
        ):
            raise ValueError("block permutation must contain integer block indexes")
        mapping = tuple(int(value) for value in self.prediction_block_by_observation_block)
        if len(mapping) != self.block_count or sorted(mapping) != list(range(self.block_count)):
            raise ValueError("block permutation must be an exact perfect matching")

        measured_diagnostics = _diagnostics_for_mapping(
            mapping,
            forbidden_lags=forbidden_lags,
            required_distinct=required_distinct,
            selection_attempt_count=self.diagnostics.selection_attempt_count,
            selected_attempt_search_step_count=(
                self.diagnostics.selected_attempt_search_step_count
            ),
            total_search_step_count=self.diagnostics.total_search_step_count,
        )
        if measured_diagnostics != self.diagnostics:
            raise ValueError("block-permutation diagnostics disagree with the mapping")
        if (
            self.diagnostics.realized_minimum_circular_displacement_blocks
            < self.minimum_circular_displacement_blocks
        ):
            raise ValueError("block permutation violates minimum circular displacement")
        if any(count for _lag, count in self.diagnostics.preserved_forward_lag_counts):
            raise ValueError("block permutation preserves a forbidden forward lag")
        if (
            self.diagnostics.distinct_directed_displacement_count
            < self.diagnostics.required_distinct_directed_displacement_count
        ):
            raise ValueError("block permutation has insufficient directed-displacement diversity")
        if (
            self.diagnostics.maximum_directed_displacement_multiplicity
            > self.diagnostics.allowed_maximum_directed_displacement_multiplicity
        ):
            raise ValueError("block permutation exceeds the directed-displacement multiplicity cap")
        if self.diagnostics.mapping_is_affine:
            raise ValueError("block permutation must be non-affine")

        selected_mapping, selected_diagnostics = _choose_block_permutation(
            grid=self.grid,
            session_key_digest=self.session_key_digest,
            control_index=control_index,
            maximum_delay_support_s=delay_support_s,
            minimum_circular_displacement_blocks=minimum_blocks,
            forbidden_lags=forbidden_lags,
            required_distinct=required_distinct,
            block_count=self.block_count,
            maximum_search_attempts=self.maximum_search_attempts,
            maximum_search_steps_per_attempt=self.maximum_search_steps_per_attempt,
        )
        if mapping != selected_mapping or self.diagnostics != selected_diagnostics:
            raise ValueError("block permutation is not the digest-ranked bounded selection")

        expected_digest = canonical_digest(
            _plan_payload(
                grid=self.grid,
                block_cells=self.block_cells,
                block_count=self.block_count,
                maximum_delay_support_s=delay_support_s,
                minimum_circular_displacement_blocks=minimum_blocks,
                session_key_digest=self.session_key_digest,
                control_index=control_index,
                maximum_search_attempts=self.maximum_search_attempts,
                maximum_search_steps_per_attempt=self.maximum_search_steps_per_attempt,
                prediction_block_by_observation_block=mapping,
                diagnostics=self.diagnostics,
            )
        )
        if self.plan_digest != expected_digest:
            raise ValueError("plan digest does not bind the block permutation contents")

    @property
    def algorithm_version(self) -> str:
        return ALGORITHM_VERSION

    @property
    def ranking_version(self) -> str:
        return _RANKING_VERSION

    @property
    def block_duration_s(self) -> float:
        return BLOCK_DURATION_S

    @property
    def minimum_circular_displacement_s(self) -> float:
        return self.minimum_circular_displacement_blocks * BLOCK_DURATION_S

    @property
    def forbidden_forward_lag_blocks(self) -> tuple[int, ...]:
        return self.diagnostics.forbidden_forward_lag_blocks

    def prediction_cell_for_observation_cell(self, observation_cell_index: int) -> int:
        """Map a cell while preserving its position inside its half-second block."""

        if (
            isinstance(observation_cell_index, bool)
            or not isinstance(observation_cell_index, Integral)
            or not 0 <= observation_cell_index < self.grid.cell_count
        ):
            raise ValueError("observation cell index lies outside the block-permutation grid")
        observation_block, within_block = divmod(int(observation_cell_index), self.block_cells)
        prediction_block = self.prediction_block_by_observation_block[observation_block]
        return prediction_block * self.block_cells + within_block

    def prediction_time_for_probe(self, probe: CfoProbe) -> float:
        """Return the permuted TLE-evaluation time for one fixed RF probe.

        Translation can round a valid edge-adjacent offset onto the target
        cell boundary.  The result is adjusted inward by at most one ULP so it
        retains the source cell's strict half-open containment contract.
        """

        if probe.cell_index >= self.grid.cell_count:
            raise ValueError("probe cell index lies outside the block-permutation grid")
        observation_cell_start_s = self.grid.start_s + probe.cell_index * self.grid.cell_duration_s
        observation_cell_end_s = observation_cell_start_s + self.grid.cell_duration_s
        if not observation_cell_start_s <= probe.time_s < observation_cell_end_s:
            raise ValueError(
                "probe time lies outside its declared half-open block-permutation-grid cell"
            )

        within_cell_s = probe.time_s - observation_cell_start_s
        prediction_cell = self.prediction_cell_for_observation_cell(probe.cell_index)
        prediction_cell_start_s = self.grid.start_s + prediction_cell * self.grid.cell_duration_s
        prediction_cell_end_s = prediction_cell_start_s + self.grid.cell_duration_s
        prediction_time_s = float(prediction_cell_start_s + within_cell_s)
        if prediction_time_s < prediction_cell_start_s:
            if math.nextafter(prediction_time_s, math.inf) == prediction_cell_start_s:
                prediction_time_s = prediction_cell_start_s
        elif prediction_time_s == prediction_cell_end_s:
            prediction_time_s = math.nextafter(prediction_cell_end_s, prediction_cell_start_s)
        if not prediction_cell_start_s <= prediction_time_s < prediction_cell_end_s:
            raise ValueError("translated probe time cannot be represented inside its target cell")
        return prediction_time_s

    def prediction_times_for_probes(self, probes: tuple[CfoProbe, ...]) -> tuple[float, ...]:
        """Map probe times in caller order using this one shared control plan."""

        return tuple(self.prediction_time_for_probe(probe) for probe in probes)


def build_activity_block_permutation(
    grid: ActivityGrid,
    *,
    session_key: str,
    control_index: int,
    maximum_delay_support_s: float,
) -> ActivityBlockPermutation:
    """Build one canonical constrained permutation for a session control arm."""

    if not isinstance(grid, ActivityGrid):
        raise ValueError("block-permutation grid must be an ActivityGrid")
    if not isinstance(session_key, str) or not session_key:
        raise ValueError("block-permutation session key must be a nonempty string")
    normalized_control_index = _validate_nonnegative_integer(control_index, "control index")
    block_cells, block_count = _block_geometry(grid)
    delay_support_s, minimum_blocks, forbidden_lags, required_distinct = _validate_control_geometry(
        block_count, maximum_delay_support_s
    )
    session_key_digest = sha256_digest(session_key.encode("utf-8"))
    mapping, diagnostics = _choose_block_permutation(
        grid=grid,
        session_key_digest=session_key_digest,
        control_index=normalized_control_index,
        maximum_delay_support_s=delay_support_s,
        minimum_circular_displacement_blocks=minimum_blocks,
        forbidden_lags=forbidden_lags,
        required_distinct=required_distinct,
        block_count=block_count,
        maximum_search_attempts=_MAXIMUM_SEARCH_ATTEMPTS,
        maximum_search_steps_per_attempt=_MAXIMUM_SEARCH_STEPS_PER_ATTEMPT,
    )
    plan_digest = canonical_digest(
        _plan_payload(
            grid=grid,
            block_cells=block_cells,
            block_count=block_count,
            maximum_delay_support_s=delay_support_s,
            minimum_circular_displacement_blocks=minimum_blocks,
            session_key_digest=session_key_digest,
            control_index=normalized_control_index,
            maximum_search_attempts=_MAXIMUM_SEARCH_ATTEMPTS,
            maximum_search_steps_per_attempt=_MAXIMUM_SEARCH_STEPS_PER_ATTEMPT,
            prediction_block_by_observation_block=mapping,
            diagnostics=diagnostics,
        )
    )
    return ActivityBlockPermutation(
        grid=grid,
        block_cells=block_cells,
        block_count=block_count,
        maximum_delay_support_s=delay_support_s,
        minimum_circular_displacement_blocks=minimum_blocks,
        session_key_digest=session_key_digest,
        control_index=normalized_control_index,
        maximum_search_attempts=_MAXIMUM_SEARCH_ATTEMPTS,
        maximum_search_steps_per_attempt=_MAXIMUM_SEARCH_STEPS_PER_ATTEMPT,
        prediction_block_by_observation_block=mapping,
        diagnostics=diagnostics,
        plan_digest=plan_digest,
    )
