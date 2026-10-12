"""Reuse profiled shapes and retain original/intermediate clock incumbents."""

import time
from dataclasses import asdict, replace

import numpy as np

from leo.analysis.clock_conditioned_bootstrap import ClockConditioningConfiguration
from leo.analysis.continuous_merge_bootstrap import ContinuousBootstrapPolicy, choose_proposals
from leo.analysis.profiled_position_bootstrap import (
    bootstrap_coherence_cost,
    profile_bootstrap_shapes,
    seed_from_profiled_shapes,
)
from leo.analysis.regional_position_bootstrap import PositionBootstrap
from leo.analysis.regional_position_score import predict_orbits


def bootstrap_with_clock_incumbents(
    observations,
    bank,
    prior,
    point,
    tracks,
    *,
    merged_tracks,
    policy=None,
    configuration=None,
    selection="incumbent",
    maximum_seconds=5.0,
    samples_per_track=12,
    orbit_predictor=predict_orbits,
    audit=None,
):
    """Prioritize a complete original seed, then explore within the remaining bound.

    Incumbent selection includes the original unmerged seed and every completed
    pass. Final selection is an ablation using only completed final passes.
    Exact repeated conditioning slopes reuse the same pure forecast/profile
    result. A timed-out search may return an already complete incumbent; its
    execution history explicitly distinguishes that from a completed path.
    """
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1800:
        raise ValueError("invalid incumbent bootstrap time budget")
    if selection not in ("incumbent", "final"):
        raise ValueError("unknown clock incumbent selection")
    configuration = configuration or ClockConditioningConfiguration()
    policy = policy or ContinuousBootstrapPolicy()
    tracks = tuple(tuple(t) for t in tracks)
    pool = tuple(dict.fromkeys(tuple(t) for t in (*tracks, *merged_tracks)))
    begun = time.monotonic()
    centered = observations.times_s - observations.time_center_s
    candidates, events, cache, pass_costs = [], [], {}, {}
    original_reason = None
    timed_out = False
    profiles = 0

    def remaining():
        available = maximum_seconds - (time.monotonic() - begun)
        if available <= 0:
            raise TimeoutError("incumbent bootstrap total time budget")
        return available

    def remember(seed, source, cached_cost=None):
        remaining()
        cost = cached_cost
        if cost is None:
            cost = bootstrap_coherence_cost(
                observations, bank, prior, point, tracks, seed, orbit_predictor=orbit_predictor
            )
        if not np.isfinite(cost):
            raise ValueError("nonfinite clock coherence cost")
        remaining()
        candidates.append({"seed": seed, "source": source, "score": cost})
        return len(candidates) - 1

    initial_matches = profile_bootstrap_shapes(
        observations,
        bank,
        prior,
        point,
        pool,
        maximum_seconds=remaining(),
        samples_per_track=samples_per_track,
        orbit_predictor=orbit_predictor,
    )
    profiles += 1
    initial_by_rows = {m.rows: m for m in initial_matches}
    try:
        original = seed_from_profiled_shapes(
            observations,
            bank,
            prior,
            point,
            [initial_by_rows[t] for t in tracks if t in initial_by_rows],
            maximum_seconds=remaining(),
            orbit_predictor=orbit_predictor,
        )
        remember(original, {"kind": "original", "branch": None, "pass": None})
    except ValueError as error:
        original_reason = str(error)
    except TimeoutError:
        raise

    def one_pass(slopes):
        nonlocal profiles
        key = tuple(float(v) for v in slopes)
        if key in cache:
            return (*cache[key], True)
        derived = replace(
            observations,
            measured_hz=(observations.measured_hz - slopes[observations.receiver] * centered),
        )
        if key == (0.0, 0.0):
            matches = initial_matches
        else:
            matches = profile_bootstrap_shapes(
                derived,
                bank,
                prior,
                point,
                pool,
                maximum_seconds=remaining(),
                samples_per_track=samples_per_track,
                orbit_predictor=orbit_predictor,
            )
            profiles += 1
        selected, receipt = choose_proposals(
            tracks, merged_tracks, matches, observations.times_s, policy
        )
        by_rows = {m.rows: m for m in matches}
        qualified = tuple(by_rows[t] for t in selected if t in by_rows)
        if policy.mode == "consistent":
            before = {initial.satellite_index for initial in matches if initial.rows in set(tracks)}
            if before != {m.satellite_index for m in qualified}:
                raise ValueError("reused shapes changed original discovery bank")
        original_available = candidates and candidates[0]["source"]["kind"] == "original"
        if key == (0.0, 0.0) and original_available and qualified == candidates[0]["seed"].matches:
            result = candidates[0]["seed"]
            pass_costs[key] = candidates[0]["score"]
        else:
            result = seed_from_profiled_shapes(
                derived,
                bank,
                prior,
                point,
                qualified,
                maximum_seconds=remaining(),
                orbit_predictor=orbit_predictor,
            )
        vector = result.vector.copy()
        absolute = vector[[3, 5]] + slopes
        vector[[3, 5]] = np.clip(
            absolute, -configuration.maximum_slope_hz_per_s, configuration.maximum_slope_hz_per_s
        )
        restored = PositionBootstrap(result.satellite_indices, vector, result.matches)
        cache[key] = restored, receipt, (absolute != vector[[3, 5]]).tolist()
        return (*cache[key], False)

    for branch, start in enumerate(configuration.starts_hz_per_s):
        if timed_out:
            break
        slopes = (
            np.asarray(start, float) if configuration.conditioning == "alternating" else np.zeros(2)
        )
        for index in range(configuration.passes):
            event = {
                "branch": branch,
                "pass": index,
                "conditioning_slopes_hz_per_s": slopes.tolist(),
                "status": "failed",
            }
            try:
                remaining()
                seed, receipt, clipped, reused = one_pass(slopes)
                key = tuple(float(v) for v in slopes)
                candidate = remember(
                    seed,
                    {"kind": "pass", "branch": branch, "pass": index},
                    cached_cost=pass_costs.get(key),
                )
                pass_costs[key] = candidates[candidate]["score"]
                event.update(
                    status="complete",
                    candidate=candidate,
                    score=candidates[candidate]["score"],
                    reused=reused,
                    clipped=clipped,
                    selected_joins=sum(d["accepted"] for d in receipt["decisions"]),
                )
                if configuration.conditioning == "alternating":
                    slopes = (
                        1 - configuration.damping
                    ) * slopes + configuration.damping * seed.vector[[3, 5]]
            except ValueError as error:
                event["reason"] = str(error)
                events.append(event)
                break
            except TimeoutError as error:
                event["reason"] = str(error)
                timed_out = True
                events.append(event)
                break
            events.append(event)
    choices = list(range(len(candidates)))
    if selection == "final":
        choices = [
            i for i in choices if candidates[i]["source"]["pass"] == configuration.passes - 1
        ]
        if not choices:
            choices = [i for i, c in enumerate(candidates) if c["source"]["kind"] == "original"]
    if not choices:
        raise ValueError("no completed incumbent bootstrap seed")
    selected = choices[0]
    for index in choices[1:]:
        if candidates[index]["score"] < candidates[selected]["score"] - 1e-9:
            selected = index
    if audit is not None:
        audit(
            {
                "policy": "clock-incumbent-v2",
                "configuration": asdict(configuration),
                "merge_policy": asdict(policy),
                "selection": selection,
                "point": list(point),
                "complete_path": len(events)
                == len(configuration.starts_hz_per_s) * configuration.passes
                and all(e["status"] == "complete" for e in events),
                "timed_out": timed_out,
                "original_reason": original_reason,
                "events": events,
                "profiles": profiles,
                "selected": selected,
                "candidates": [{"source": c["source"], "score": c["score"]} for c in candidates],
                "candidate_packets": [c["seed"] for c in candidates],
                "seconds": time.monotonic() - begun,
            }
        )
    return candidates[selected]["seed"]
