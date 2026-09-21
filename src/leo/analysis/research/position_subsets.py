"""Truth-blind, deterministic subset design for receiver-position benchmarks.

Membership depends only on stable RF metadata.  Frequency values, residuals,
catalogue identities, fitted parameters, and evaluation truth are deliberately
absent from this module's input contract.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

SAMPLER_VERSION = "position-subsets-v2-global-floor-sha256-order"
FRACTIONS = (0.25, 0.5, 1.0)


@dataclass(frozen=True)
class Observation:
    observation_id: str
    track_id: str
    pass_group_id: str
    timestamp_ns: int
    fitting: bool
    channel: str
    sample_rate_hz: int


@dataclass(frozen=True)
class PositionSubset:
    method: Literal["density", "pass", "duration"]
    fraction: float | None
    seed: int | None
    fitting_ids: tuple[str, ...]
    evaluation_ids: tuple[str, ...]
    unsupported_evaluation_ids: tuple[str, ...]
    unusable_track_ids: tuple[str, ...]
    rounding: str
    sampler_version: str = SAMPLER_VERSION
    window_start_ns: int | None = None
    window_end_ns: int | None = None

    @property
    def subset_id(self) -> str:
        return canonical_hash(asdict(self))


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def canonical_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def _hash_order(seed: int, namespace: str, stable_id: str) -> bytes:
    return hashlib.sha256(f"{SAMPLER_VERSION}\0{seed}\0{namespace}\0{stable_id}".encode()).digest()


def _validate(rows: Sequence[Observation], seeds: Sequence[int]) -> tuple[Observation, ...]:
    ordered = tuple(sorted(rows, key=lambda x: x.observation_id))
    ids = [x.observation_id for x in ordered]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate observation_id")
    if any(not x.observation_id or not x.track_id or not x.pass_group_id for x in ordered):
        raise ValueError("stable IDs must be non-empty")
    if any(x.timestamp_ns < 0 or x.sample_rate_hz <= 0 for x in ordered):
        raise ValueError("timestamps and sample rates must be valid")
    if any(seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be unique non-negative integers")
    return ordered


def _support(
    rows: Sequence[Observation], selected: set[str]
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    fitted_tracks = {x.track_id for x in rows if x.observation_id in selected}
    all_tracks = {x.track_id for x in rows if x.fitting}
    evaluation = tuple(sorted(x.observation_id for x in rows if not x.fitting))
    unsupported = tuple(
        sorted(x.observation_id for x in rows if not x.fitting and x.track_id not in fitted_tracks)
    )
    return evaluation, unsupported, tuple(sorted(all_tracks - fitted_tracks))


def _density(rows: Sequence[Observation], seed: int, bins: int, fraction: float) -> PositionSubset:
    by_track: dict[str, list[Observation]] = {}
    for row in rows:
        if row.fitting:
            by_track.setdefault(row.track_id, []).append(row)
    strata: dict[tuple[str, int], list[Observation]] = {}
    for track, track_rows in by_track.items():
        chronological = sorted(track_rows, key=lambda x: (x.timestamp_ns, x.observation_id))
        # Equal-index temporal bins keep support across the track without using responses.
        for bin_index in range(bins):
            stratum = chronological[
                math.floor(bin_index * len(chronological) / bins) : math.floor(
                    (bin_index + 1) * len(chronological) / bins
                )
            ]
            strata[(track, bin_index)] = sorted(
                stratum,
                key=lambda x: (
                    _hash_order(seed, f"density:{track}:{bin_index}", x.observation_id),
                    x.observation_id,
                ),
            )
    stratum_order = sorted(
        strata,
        key=lambda key: (_hash_order(seed, "density-strata", f"{key[0]}:{key[1]}"), key),
    )
    ordered = []
    for index in range(max((len(x) for x in strata.values()), default=0)):
        for key in stratum_order:
            if index < len(strata[key]):
                ordered.append(strata[key][index])
    target = math.floor(fraction * sum(len(x) for x in strata.values()))
    selected = {x.observation_id for x in ordered[:target]}
    evaluation, unsupported, unusable = _support(rows, selected)
    return PositionSubset(
        "density",
        fraction,
        seed,
        tuple(sorted(selected)),
        evaluation,
        unsupported,
        unusable,
        "floor-global-stratified-round-robin",
    )


def _passes(rows: Sequence[Observation], seed: int, fraction: float) -> PositionSubset:
    groups: dict[str, list[Observation]] = {}
    for row in rows:
        if row.fitting:
            groups.setdefault(row.pass_group_id, []).append(row)
    # Group selection uses RF/time strata and never an inferred catalogue identity.
    starts = {group: min(x.timestamp_ns for x in members) for group, members in groups.items()}
    lo, hi = min(starts.values(), default=0), max(starts.values(), default=0)
    strata: dict[tuple[str, int, int], list[str]] = {}
    for group, members in groups.items():
        time_bin = min(3, math.floor(4 * (starts[group] - lo) / max(1, hi - lo + 1)))
        key = (members[0].channel, members[0].sample_rate_hz, time_bin)
        strata.setdefault(key, []).append(group)
    for key, values in strata.items():
        values.sort(key=lambda group: (_hash_order(seed, f"pass:{key}", group), group))
    # Round-robin across channel/rate/time strata balances the global prefix
    # while retaining an exact floor of the requested number of whole groups.
    ordered = []
    for index in range(max((len(x) for x in strata.values()), default=0)):
        for key in sorted(strata):
            if index < len(strata[key]):
                ordered.append(strata[key][index])
    keep = set(ordered[: math.floor(fraction * len(ordered))])
    selected = {x.observation_id for group in keep for x in groups[group]}
    evaluation, unsupported, unusable = _support(rows, selected)
    return PositionSubset(
        "pass",
        fraction,
        seed,
        tuple(sorted(selected)),
        evaluation,
        unsupported,
        unusable,
        "floor-whole-pass-groups",
    )


def build_subset_matrix(
    observations: Iterable[Observation],
    *,
    seeds: Sequence[int] = tuple(range(20)),
    temporal_bins: int = 4,
    durations_s: Sequence[int] = (1800, 3600, 7200, 14400, 28800),
    fractions: Sequence[float] = FRACTIONS,
) -> tuple[PositionSubset, ...]:
    """Create nested 25/50/100% density/pass subsets and primary duration windows.

    The identical full subsets are emitted once with ``seed=None``.  Counts use
    floor, including zero; no hidden per-track or per-stratum minimum is imposed.
    """
    if temporal_bins <= 0:
        raise ValueError("temporal_bins must be positive")
    if (
        not fractions
        or tuple(sorted(set(fractions))) != tuple(fractions)
        or fractions[-1] != 1.0
        or any(not 0 < f <= 1 for f in fractions)
    ):
        raise ValueError("fractions must be increasing, unique, in (0, 1], and end at 1")
    rows = _validate(tuple(observations), seeds)
    full_ids = tuple(sorted(x.observation_id for x in rows if x.fitting))
    evaluation, unsupported, unusable = _support(rows, set(full_ids))
    output: list[PositionSubset] = []
    for method in ("density", "pass"):
        for seed in seeds:
            output.extend(
                (
                    _density(rows, seed, temporal_bins, fraction)
                    if method == "density"
                    else _passes(rows, seed, fraction)
                )
                for fraction in fractions[:-1]
            )
        output.append(
            PositionSubset(
                method,
                1.0,
                None,
                full_ids,
                evaluation,
                unsupported,
                unusable,
                "complete-fitting-pool",
            )
        )
    fitting_rows = [x for x in rows if x.fitting]
    if fitting_rows:
        start = min(x.timestamp_ns for x in fitting_rows)
        campaign_end = max(x.timestamp_ns for x in fitting_rows) + 1
        campaign_duration = campaign_end - start
        for fraction in fractions:
            end = (
                campaign_end
                if fraction == 1.0
                else start + math.floor(fraction * campaign_duration)
            )
            selected = {x.observation_id for x in fitting_rows if start <= x.timestamp_ns < end}
            eval_ids, unsupported_ids, unusable_ids = _support(rows, selected)
            output.append(
                PositionSubset(
                    "duration",
                    fraction,
                    None,
                    tuple(sorted(selected)),
                    eval_ids,
                    unsupported_ids,
                    unusable_ids,
                    "floor-campaign-prefix",
                    window_start_ns=start,
                    window_end_ns=end,
                )
            )
        for seconds in durations_s:
            if seconds <= 0:
                raise ValueError("durations must be positive")
            end = start + int(seconds) * 1_000_000_000
            selected = {x.observation_id for x in fitting_rows if start <= x.timestamp_ns < end}
            eval_ids, unsupported_ids, unusable_ids = _support(rows, selected)
            output.append(
                PositionSubset(
                    "duration",
                    None,
                    None,
                    tuple(sorted(selected)),
                    eval_ids,
                    unsupported_ids,
                    unusable_ids,
                    "primary-campaign-prefix",
                    window_start_ns=start,
                    window_end_ns=end,
                )
            )
    return tuple(output)
