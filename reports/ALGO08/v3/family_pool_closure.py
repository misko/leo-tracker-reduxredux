"""Admit compatible outside families while keeping the original full measurement set."""

from collections import Counter
from functools import partial
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import discovery, position, scan as scan_kernel
from tools.pipeline_eval.variants import v5_core, v5_tiled_salvage

from blind_joint_finish import digest, elapsed, propose as joint_propose
from representative_family_pool import MARGIN, compact_catalogue, family_pool, fine_pool, restore, zero_reference_objective


ROUND_LIMIT = 3
FAMILY_LIMIT = 8
CACHE_BYTES = 64 * 1024**2


class AnchorPlanes:
    """Reuse row-independent nominal projections for exact repeated regional anchors."""

    def __init__(self, full, project, byte_limit=CACHE_BYTES):
        self.full = full
        self.project = project
        self.byte_limit = byte_limit
        self.by_anchor = {}
        self.retained = 0
        self.counts = Counter()

    def scoped(self, compact, labels):
        def evaluate(geometry, latitude, longitude, **kwargs):
            if geometry is not compact.geometry or kwargs:
                return self.project(geometry, latitude, longitude, **kwargs)
            key = float(latitude), float(longitude)
            previous = self.by_anchor.get(key)
            if previous is None:
                self.counts["projected_family_rows"] += len(labels)
                self.counts["projection_calls"] += 1
                result = self.project(geometry, *key)
                old_bytes = 0
            else:
                old, planes, old_bytes = previous
                old_positions = np.searchsorted(labels, old)
                if np.any(old_positions >= len(labels)) or not np.array_equal(labels[old_positions], old):
                    raise ValueError("Nominal anchor reuse requires monotone causal catalogue admission")
                self.counts["reused_family_rows"] += len(old)
                if len(old) == len(labels):
                    self.counts["exact_plane_hits"] += 1
                    return planes
                missing = np.ones(len(labels), bool)
                missing[old_positions] = False
                added = labels[missing]
                sky = {name: (array if name == "time_s" else array[added]) for name, array in self.full.sky.items()}
                new_geometry = scan_kernel.prepare_phase_geometry(sky, self.full.times)
                self.counts["projected_family_rows"] += len(added)
                self.counts["projection_calls"] += 1
                self.counts["incremental_projection_calls"] += 1
                added_planes = self.project(new_geometry, *key)
                result = tuple(np.empty((len(labels), len(self.full.times)), dtype=plane.dtype) for plane in planes)
                for value, kept, new in zip(result, planes, added_planes, strict=True):
                    value[old_positions], value[missing] = kept, new
            size = sum(value.nbytes for value in result)
            remaining = self.retained - old_bytes + size
            if remaining <= self.byte_limit:
                for value in result:
                    value.setflags(write=False)
                self.by_anchor[key] = labels.copy(), result, size
                self.retained = remaining
                self.counts["peak_bytes"] = max(self.counts["peak_bytes"], remaining)
            else:
                self.counts["over_budget"] += 1
            return result

        return evaluate


def next_additions(outside, labels, *, round_number, previously_added):
    added = {int(row["candidate_index"]) for row in outside} - labels
    if added and (round_number == ROUND_LIMIT or previously_added + len(added) > FAMILY_LIMIT):
        raise ValueError("Full-catalogue compatible winners remain beyond the family or round cap")
    return added


def refine(full, node):
    model, fit, trace = position.refreshed(full, full.radio_sigma_hz, node, "c0", rounds=2, iterations=48)
    point = np.asarray(fit["parameters"])
    if not np.isfinite(fit["score"]) or not np.isfinite(point).all():
        raise ValueError("The exact cold finalist was nonfinite")
    phases = dict(zip(model.labels, np.clip(trace[-1]["posterior_phase_s"], -15., 15.), strict=True))
    return point, model.state(point), phases, float(fit["score"])


def choose_cold(prepared, region, bound, measured, labels_used):
    clocks = (process_time(), perf_counter())
    full = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "previous")
    measured["full_context_clocks"] = elapsed(*clocks)
    clocks = (process_time(), perf_counter())
    labels, anchors, times = family_pool(full, prepared["tracks"]["metadata"]["duration_s"])
    anchor_cache = AnchorPlanes(full, discovery.phase_linear_frequency)
    attempts = []
    measured.update(family_pool=dict(full_candidates=len(full.norads), initial_pool_candidates=len(labels),
                                     representative_tracks=len(anchors), total_curved_tracks=len(full.curved),
                                     representative_times=times, full_times=len(full.times),
                                     original_curved_points=sum(len(full.tracks[i]["times"]) for i in full.curved),
                                     initial_pool_norads=[int(full.norads[j]) for j in labels]),
                    pool_closure=dict(rounds=attempts, cache=anchor_cache.counts,
                                      cap=dict(rounds=ROUND_LIMIT, added_families=FAMILY_LIMIT, bytes=CACHE_BYTES)),
                    pool_clocks=elapsed(*clocks))
    if not len(labels) or len(labels) == len(full.norads):
        raise ValueError("No smaller causal catalogue was nominated")
    labels_used.update(map(int, labels))
    initially = labels_used.copy()
    zero_cache, fit_cache, previous_ranks = {}, {}, []

    for round_number in range(1, ROUND_LIMIT + 1):
        clocks = (process_time(), perf_counter())
        labels = np.array(sorted(labels_used), dtype=np.intp)
        compact = compact_catalogue(full, labels)
        with patch.object(discovery, "phase_linear_frequency", anchor_cache.scoped(compact, labels)):
            ranked = v5_core.ranked_initial_nodes(compact)
        restored = [restore(full, node, labels) for node in ranked]
        signatures = [discovery.signature(node) for node in restored]
        scores, reused = [], 0
        for node, key in zip(restored[:2], signatures[:2], strict=True):
            if key in zero_cache:
                reused += 1
            else:
                zero_cache[key] = zero_reference_objective(full, node)
            scores.append(zero_cache[key])
        prefix = 0
        for a, b in zip(previous_ranks, signatures):
            if a != b:
                break
            prefix += 1
        detail = dict(round=round_number, roster=len(labels), ranked_count=len(ranked), exact_branch_scores=scores,
                      repeated_ranks=len(set(previous_ranks) & set(signatures)), repeated_leading_ranks=prefix,
                      ranked_signatures=[digest(key) for key in signatures], cached_zero_scores=reused,
                      rank_clocks=elapsed(*clocks))
        attempts.append(detail)
        if not scores or not all(np.isfinite(scores)) or (len(scores) > 1 and scores[1] - scores[0] <= MARGIN):
            raise ValueError("Ambiguous reduced-catalogue cold branches")
        previous_ranks = signatures
        clocks = (process_time(), perf_counter())
        node, signature = restored[0], signatures[0]
        reused = signature in fit_cache
        if not reused:
            fit_cache[signature] = refine(full, node)
        point, state, phases, score = fit_cache[signature]
        chosen_labels = Counter(row["candidate_index"] for row in node["seed"]["rows"])
        detail.update(refined_score=score, refined_east_north_km=point, reused_exact_fit=reused,
                      refined_norads=[int(full.norads[j]) for j in sorted(chosen_labels)],
                      newly_admitted_winner_tracks={int(full.norads[j]): chosen_labels[j]
                                                   for j in sorted(labels_used - initially) if chosen_labels[j]},
                      refinement_clocks=elapsed(*clocks))
        clocks = (process_time(), perf_counter())
        base = discovery.phase_linear_frequency(full.geometry, *region.latlon(point))
        _, rows, _, _ = full.association(state, base, region.native_point(full, point), "receiver_smooth")
        outside = [row for row in rows if row["compatible"] and row["candidate_index"] not in labels_used]
        detail.update(outside=[dict(component=row["component"], norad=row["candidate_norad"]) for row in outside],
                      full_guard_clocks=elapsed(*clocks))
        extra = next_additions(outside, labels_used, round_number=round_number, previously_added=len(labels_used - initially))
        detail["admitted_norads"] = [int(full.norads[j]) for j in sorted(extra)]
        if not extra:
            return node, point, phases, dict(scores=[score], branch=1, east_north_km=point,
                                            latlon=region.latlon(point), catalogue=len(full.norads))
        labels_used.update(extra)
    raise AssertionError("A bounded family closure must either return or request checked fallback")


def propose(prepared, region, bound, measured, *, repair):
    labels, salvage = set(), Counter()
    measured["pooled_salvage"] = salvage
    cold = partial(choose_cold, measured=measured, labels_used=labels)
    fine = partial(fine_pool, v5_tiled_salvage.fine_alternatives, labels, salvage)
    with patch.object(v5_tiled_salvage, "fine_alternatives", fine):
        return joint_propose(prepared, region, bound, measured, repair=repair, cold_start=cold)
