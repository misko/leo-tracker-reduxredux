"""Deterministic half-second prediction-time controls for satellite activity.

This Research-only primitive breaks the relationship between an observed RF
timeline and catalogue prediction time without modifying the observation
inventory.  One session-level plan maps every observed half-second block to a
different prediction-time block.  Cells and probe offsets retain their order
inside each block, so the control preserves the native cadence that a
half-second activity episode can exploit.

The control tests catalogue/time specificity conditional on the observed RF
activity.  It is not a signal-absence control and cannot estimate the raw
detector's false-presence rate.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from numbers import Integral, Real

from leo.analysis.research.satellite_activity import ActivityGrid, CfoProbe
from leo.contracts.digests import canonical_digest, sha256_digest

BLOCK_DURATION_S = 0.5
ALGORITHM_VERSION = "research-activity-block-derangement-v1"
_RANKING_VERSION = "research-activity-block-affine-ranking-v2"
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
        raise ValueError("v1 derangement requires cells that exactly tile a 0.5-second block")
    if grid.cell_count % block_cells:
        raise ValueError("v1 derangement requires cell_count divisible by half-second block cells")
    block_count = int(grid.cell_count) // block_cells
    if block_count < 2:
        raise ValueError("a block derangement requires at least two complete half-second blocks")
    return block_cells, block_count


def _validate_control_geometry(
    block_count: int,
    maximum_delay_support_s: object,
    minimum_circular_displacement_blocks: object,
) -> tuple[float, int]:
    if (
        isinstance(maximum_delay_support_s, bool)
        or not isinstance(maximum_delay_support_s, Real)
        or not math.isfinite(maximum_delay_support_s)
        or maximum_delay_support_s < 0.0
    ):
        raise ValueError("maximum delay support must be finite and nonnegative")
    if (
        isinstance(minimum_circular_displacement_blocks, bool)
        or not isinstance(minimum_circular_displacement_blocks, Integral)
        or minimum_circular_displacement_blocks < 1
    ):
        raise ValueError("minimum circular displacement must be a positive integer block count")

    delay_support_s = float(maximum_delay_support_s)
    minimum_blocks = int(minimum_circular_displacement_blocks)
    minimum_displacement_s = minimum_blocks * BLOCK_DURATION_S
    if minimum_displacement_s <= delay_support_s:
        raise ValueError("minimum circular displacement must lie beyond maximum delay support")
    if minimum_blocks > block_count // 2:
        raise ValueError("minimum circular displacement is impossible on this block circle")
    return delay_support_s, minimum_blocks


def _circular_distance(left: int, right: int, count: int) -> int:
    direct = abs(left - right)
    return min(direct, count - direct)


def _affine_mapping(block_count: int, multiplier: int, offset: int) -> tuple[int, ...]:
    return tuple((multiplier * index + offset) % block_count for index in range(block_count))


def _forward_block_adjacency_broken(mapping: tuple[int, ...]) -> bool:
    count = len(mapping)
    return all(
        mapping[(observed + 1) % count] != (predicted + 1) % count
        for observed, predicted in enumerate(mapping)
    )


def _selection_context(
    *,
    grid: ActivityGrid,
    session_key_digest: str,
    maximum_delay_support_s: float,
    minimum_circular_displacement_blocks: int,
) -> dict[str, object]:
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "ranking_version": _RANKING_VERSION,
        "session_key_digest": session_key_digest,
        "grid": _grid_payload(grid),
        "block_duration_s": BLOCK_DURATION_S,
        "maximum_delay_support_s": maximum_delay_support_s,
        "minimum_circular_displacement_blocks": minimum_circular_displacement_blocks,
        "forward_block_adjacency_broken": True,
    }


def _choose_affine_derangement(
    *,
    grid: ActivityGrid,
    session_key_digest: str,
    maximum_delay_support_s: float,
    minimum_circular_displacement_blocks: int,
    block_count: int,
) -> tuple[int, int, tuple[int, ...]]:
    context = _selection_context(
        grid=grid,
        session_key_digest=session_key_digest,
        maximum_delay_support_s=maximum_delay_support_s,
        minimum_circular_displacement_blocks=minimum_circular_displacement_blocks,
    )
    best: tuple[str, int, int, tuple[int, ...]] | None = None
    for multiplier in range(1, block_count):
        # A multiplier of one is only a circular time shift: every block keeps
        # its forward successor, so an allowed offset can preserve almost the
        # entire CFO curve.  Reverse order remains admissible.  Because time
        # still runs forward inside each block, multiplier B-1 creates a
        # backward discontinuity at every boundary rather than a smooth global
        # time reversal; it is also the sole order-breaking affine unit for
        # feasible block counts 4 and 6.
        if multiplier == 1:
            continue
        if math.gcd(multiplier, block_count) != 1:
            continue
        for offset in range(block_count):
            mapping = _affine_mapping(block_count, multiplier, offset)
            if any(
                _circular_distance(observed, predicted, block_count)
                < minimum_circular_displacement_blocks
                for observed, predicted in enumerate(mapping)
            ):
                continue
            if not _forward_block_adjacency_broken(mapping):
                continue
            rank_digest = canonical_digest(
                {
                    "ranking_version": _RANKING_VERSION,
                    "context": context,
                    "affine_multiplier": multiplier,
                    "affine_offset": offset,
                }
            )
            candidate = (rank_digest, multiplier, offset, mapping)
            if best is None or candidate[:3] < best[:3]:
                best = candidate
    if best is None:
        raise ValueError(
            "no order-breaking affine block derangement satisfies the requested displacement"
        )
    return best[1], best[2], best[3]


def _plan_payload(
    *,
    grid: ActivityGrid,
    block_cells: int,
    block_count: int,
    maximum_delay_support_s: float,
    minimum_circular_displacement_blocks: int,
    session_key_digest: str,
    affine_multiplier: int,
    affine_offset: int,
    prediction_block_by_observation_block: tuple[int, ...],
) -> dict[str, object]:
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "ranking_version": _RANKING_VERSION,
        "session_key_digest": session_key_digest,
        "grid": _grid_payload(grid),
        "block_duration_s": BLOCK_DURATION_S,
        "block_cells": block_cells,
        "block_count": block_count,
        "maximum_delay_support_s": maximum_delay_support_s,
        "minimum_circular_displacement_blocks": minimum_circular_displacement_blocks,
        "affine_multiplier": affine_multiplier,
        "affine_offset": affine_offset,
        "forward_block_adjacency_broken": _forward_block_adjacency_broken(
            prediction_block_by_observation_block
        ),
        "prediction_block_by_observation_block": list(prediction_block_by_observation_block),
    }


@dataclass(frozen=True, slots=True)
class ActivityBlockDerangement:
    """One exact affine permutation shared by a session's prediction lanes.

    ``prediction_block_by_observation_block[b]`` identifies the block of TLE
    prediction times used while scoring RF observations in block ``b``.  The
    RF probe timestamps, candidate bundles, and usability masks remain fixed.
    """

    grid: ActivityGrid
    block_cells: int
    block_count: int
    maximum_delay_support_s: float
    minimum_circular_displacement_blocks: int
    session_key_digest: str
    affine_multiplier: int
    affine_offset: int
    prediction_block_by_observation_block: tuple[int, ...]
    plan_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.grid, ActivityGrid):
            raise ValueError("derangement grid must be an ActivityGrid")
        if any(
            isinstance(value, bool) or not isinstance(value, Integral)
            for value in (self.block_cells, self.block_count)
        ):
            raise ValueError("derangement block geometry must use integer counts")
        expected_block_cells, expected_block_count = _block_geometry(self.grid)
        if self.block_cells != expected_block_cells or self.block_count != expected_block_count:
            raise ValueError("derangement block geometry disagrees with its activity grid")
        delay_support_s, minimum_blocks = _validate_control_geometry(
            self.block_count,
            self.maximum_delay_support_s,
            self.minimum_circular_displacement_blocks,
        )
        if not isinstance(self.session_key_digest, str) or not _SHA256_PATTERN.fullmatch(
            self.session_key_digest
        ):
            raise ValueError("session key digest must be a tagged lowercase SHA-256")
        if not isinstance(self.plan_digest, str) or not _SHA256_PATTERN.fullmatch(self.plan_digest):
            raise ValueError("plan digest must be a tagged lowercase SHA-256")
        if (
            isinstance(self.affine_multiplier, bool)
            or not isinstance(self.affine_multiplier, Integral)
            or not 1 <= self.affine_multiplier < self.block_count
            or self.affine_multiplier == 1
            or math.gcd(int(self.affine_multiplier), self.block_count) != 1
        ):
            raise ValueError("affine multiplier must be invertible and break forward block order")
        if (
            isinstance(self.affine_offset, bool)
            or not isinstance(self.affine_offset, Integral)
            or not 0 <= self.affine_offset < self.block_count
        ):
            raise ValueError("affine offset lies outside the block circle")

        if not isinstance(self.prediction_block_by_observation_block, tuple) or any(
            isinstance(value, bool) or not isinstance(value, Integral)
            for value in self.prediction_block_by_observation_block
        ):
            raise ValueError("derangement mapping must contain integer block indexes")
        mapping = tuple(int(value) for value in self.prediction_block_by_observation_block)
        if len(mapping) != self.block_count or sorted(mapping) != list(range(self.block_count)):
            raise ValueError("derangement mapping must be an exact block permutation")
        expected_mapping = _affine_mapping(
            self.block_count,
            int(self.affine_multiplier),
            int(self.affine_offset),
        )
        if mapping != expected_mapping:
            raise ValueError("derangement mapping disagrees with its affine parameters")
        if any(
            _circular_distance(observed, predicted, self.block_count) < minimum_blocks
            for observed, predicted in enumerate(mapping)
        ):
            raise ValueError("derangement mapping violates its circular displacement")
        if not _forward_block_adjacency_broken(mapping):
            raise ValueError("derangement mapping preserves forward block adjacency")

        selected_multiplier, selected_offset, _selected_mapping = _choose_affine_derangement(
            grid=self.grid,
            session_key_digest=self.session_key_digest,
            maximum_delay_support_s=delay_support_s,
            minimum_circular_displacement_blocks=minimum_blocks,
            block_count=self.block_count,
        )
        if (int(self.affine_multiplier), int(self.affine_offset)) != (
            selected_multiplier,
            selected_offset,
        ):
            raise ValueError("affine parameters are not the digest-ranked session selection")

        expected_digest = canonical_digest(
            _plan_payload(
                grid=self.grid,
                block_cells=self.block_cells,
                block_count=self.block_count,
                maximum_delay_support_s=delay_support_s,
                minimum_circular_displacement_blocks=minimum_blocks,
                session_key_digest=self.session_key_digest,
                affine_multiplier=int(self.affine_multiplier),
                affine_offset=int(self.affine_offset),
                prediction_block_by_observation_block=mapping,
            )
        )
        if self.plan_digest != expected_digest:
            raise ValueError("plan digest does not bind the derangement contents")

    @property
    def algorithm_version(self) -> str:
        return ALGORITHM_VERSION

    @property
    def ranking_version(self) -> str:
        """Digest-ranking rule used to choose this session's affine map."""

        return _RANKING_VERSION

    @property
    def block_duration_s(self) -> float:
        return BLOCK_DURATION_S

    @property
    def minimum_circular_displacement_s(self) -> float:
        return self.minimum_circular_displacement_blocks * BLOCK_DURATION_S

    @property
    def forward_block_adjacency_broken(self) -> bool:
        """Whether every forward-adjacent observed pair is separated in prediction order."""

        return _forward_block_adjacency_broken(self.prediction_block_by_observation_block)

    @property
    def realized_minimum_circular_displacement_blocks(self) -> int:
        return min(
            _circular_distance(observed, predicted, self.block_count)
            for observed, predicted in enumerate(self.prediction_block_by_observation_block)
        )

    def prediction_cell_for_observation_cell(self, observation_cell_index: int) -> int:
        """Map one observed cell to a prediction cell at the same within-block index."""

        if (
            isinstance(observation_cell_index, bool)
            or not isinstance(observation_cell_index, Integral)
            or not 0 <= observation_cell_index < self.grid.cell_count
        ):
            raise ValueError("observation cell index lies outside the derangement grid")
        observation_block, within_block = divmod(int(observation_cell_index), self.block_cells)
        prediction_block = self.prediction_block_by_observation_block[observation_block]
        return prediction_block * self.block_cells + within_block

    def prediction_time_for_probe(self, probe: CfoProbe) -> float:
        """Return the displaced TLE-evaluation time for one fixed RF probe."""

        if probe.cell_index >= self.grid.cell_count:
            raise ValueError("probe cell index lies outside the derangement grid")
        observation_cell_start_s = self.grid.start_s + probe.cell_index * self.grid.cell_duration_s
        observation_cell_end_s = observation_cell_start_s + self.grid.cell_duration_s
        tolerance_s = 8.0 * max(
            math.ulp(observation_cell_start_s),
            math.ulp(observation_cell_end_s),
            math.ulp(probe.time_s),
        )
        if (
            probe.time_s < observation_cell_start_s - tolerance_s
            or probe.time_s >= observation_cell_end_s - tolerance_s
        ):
            raise ValueError("probe time lies outside its declared derangement-grid cell")

        within_cell_s = probe.time_s - observation_cell_start_s
        prediction_cell = self.prediction_cell_for_observation_cell(probe.cell_index)
        prediction_cell_start_s = self.grid.start_s + prediction_cell * self.grid.cell_duration_s
        return float(prediction_cell_start_s + within_cell_s)

    def prediction_times_for_probes(self, probes: tuple[CfoProbe, ...]) -> tuple[float, ...]:
        """Map probe times in caller order using this one shared session plan."""

        return tuple(self.prediction_time_for_probe(probe) for probe in probes)


def build_activity_block_derangement(
    grid: ActivityGrid,
    *,
    session_key: str,
    maximum_delay_support_s: float,
    minimum_circular_displacement_blocks: int,
) -> ActivityBlockDerangement:
    """Build the canonical digest-ranked affine derangement for one session.

    ``maximum_delay_support_s`` is the greatest absolute orbital-time shift
    available to the evaluated hypothesis family.  The requested block
    displacement must be strictly larger so that this control cannot be undone
    by an allowed delay state.
    """

    if not isinstance(grid, ActivityGrid):
        raise ValueError("derangement grid must be an ActivityGrid")
    if not isinstance(session_key, str) or not session_key:
        raise ValueError("derangement session key must be a nonempty string")
    block_cells, block_count = _block_geometry(grid)
    delay_support_s, minimum_blocks = _validate_control_geometry(
        block_count,
        maximum_delay_support_s,
        minimum_circular_displacement_blocks,
    )
    session_key_digest = sha256_digest(session_key.encode("utf-8"))
    multiplier, offset, mapping = _choose_affine_derangement(
        grid=grid,
        session_key_digest=session_key_digest,
        maximum_delay_support_s=delay_support_s,
        minimum_circular_displacement_blocks=minimum_blocks,
        block_count=block_count,
    )
    plan_digest = canonical_digest(
        _plan_payload(
            grid=grid,
            block_cells=block_cells,
            block_count=block_count,
            maximum_delay_support_s=delay_support_s,
            minimum_circular_displacement_blocks=minimum_blocks,
            session_key_digest=session_key_digest,
            affine_multiplier=multiplier,
            affine_offset=offset,
            prediction_block_by_observation_block=mapping,
        )
    )
    return ActivityBlockDerangement(
        grid=grid,
        block_cells=block_cells,
        block_count=block_count,
        maximum_delay_support_s=delay_support_s,
        minimum_circular_displacement_blocks=minimum_blocks,
        session_key_digest=session_key_digest,
        affine_multiplier=multiplier,
        affine_offset=offset,
        prediction_block_by_observation_block=mapping,
        plan_digest=plan_digest,
    )
