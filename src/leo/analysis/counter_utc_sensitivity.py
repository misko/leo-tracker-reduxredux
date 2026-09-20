"""Finite-grid UTC sensitivity with one shared capture offset and frozen split.

This diagnoses candidate instability; it does not prove continuous-interval
stability or fit UTC against held-out observations. Orbital tau remains a
separate nuisance parameter of the existing matcher.
"""

from __future__ import annotations

from dataclasses import dataclass

from leo.analysis.persistent_hop_tle_match import (
    PersistentHopTleMatchResult,
    match_persistent_hop_track_to_tles,
)
from leo.contracts.catalogue_association import PhysicalEpisodeGraphV1
from leo.contracts.digests import canonical_digest


@dataclass(frozen=True)
class CounterUtcSensitivity:
    nominal: PersistentHopTleMatchResult
    offsets_ns: tuple[int, ...]
    leading_catalog_numbers: tuple[int | None, ...]
    abstention_reasons: tuple[str, ...]
    content_digest: str


def utc_offset_grid(maximum_error_ns: int) -> tuple[int, ...]:
    if type(maximum_error_ns) is not int or not 0 <= maximum_error_ns <= 100_000_000:
        raise ValueError("UTC sensitivity requires a qualified <=100 ms bound")
    if maximum_error_ns == 0:
        return (0,)
    steps = max(1, (maximum_error_ns + 24_999_999) // 25_000_000)
    return tuple(round(i * maximum_error_ns / steps) for i in range(-steps, steps + 1))


def match_counter_utc_sensitivity(
    graph,
    payload,
    *,
    maximum_error_ns,
    tle_snapshot,
    observer_site,
    config,
    matcher=match_persistent_hop_track_to_tles,
):
    offsets = utc_offset_grid(maximum_error_ns)
    # Identical observation IDs and split for every sensitivity point. Each
    # individual matcher still fits catalogue/tau/CFO only on training support.
    seed = canonical_digest(
        {
            "policy": "counter-utc-sensitivity-v1",
            "source_graph": graph.content_digest,
            "selection": config.selection_protocol_digest,
        }
    )
    results = []
    for offset in offsets:
        shifted = PhysicalEpisodeGraphV1.create(
            observations=tuple(
                row.model_copy(
                    update={
                        name: getattr(row, name) + offset
                        for name in (
                            "support_start_utc_ns",
                            "support_center_utc_ns",
                            "support_end_utc_ns",
                        )
                    }
                )
                for row in graph.observations
            ),
            episodes=graph.episodes,
        )
        results.append(
            matcher(
                shifted,
                payload,
                tle_snapshot=tle_snapshot,
                observer_site=observer_site,
                config=config,
                partition_seed=seed,
            )
        )
    nominal = results[offsets.index(0)]
    leaders = tuple(r.leading_catalog_number for r in results)
    reasons = []
    if len(set(leaders)) != 1 or leaders[0] is None:
        reasons.append("utc-offset-grid-leader-instability")
    if not all(r.leading_candidate_persisted_on_heldout for r in results):
        reasons.append("utc-offset-grid-heldout-instability")
    if any(r.abstention_recommended for r in results):
        reasons.append("utc-offset-grid-abstention")
    digest = canonical_digest(
        {
            "policy": "counter-utc-sensitivity-v1",
            "offsets_ns": offsets,
            "results": [r.content_digest for r in results],
            "partition_seed": seed,
        }
    )
    return CounterUtcSensitivity(nominal, offsets, leaders, tuple(reasons), digest)
