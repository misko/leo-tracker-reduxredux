"""Thin broad catalogue candidates while keeping the full measured track geometry."""

from collections import Counter
from copy import copy
from functools import partial
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import discovery, position, scan as scan_kernel
from tools.pipeline_eval.variants import v5_core, v5_tiled_salvage

from blind_joint_finish import digest, elapsed, propose as joint_propose


MARGIN = 1.
PER_TRACK = 4


def representatives(scan, duration):
    groups = {}
    for i in scan.curved:
        t = scan.tracks[i]
        times = t["times"]
        middle = .5 * (times[0] + times[-1])
        key = t["receiver"], t["rf_hz"], min(2, int(3 * middle / duration))
        rank = -len(times), t["key"]
        if key not in groups or rank < groups[key][0]:
            groups[key] = rank, i
    return [i for _, i in sorted(groups.values())]


def phase_shape(y, frequency, derivative, elevation, times, widths, sigma):
    """Proposal-only profile with a bounded orbit phase and a free RF intercept."""
    x = times - times.mean()
    xx = x @ x
    z = y - frequency
    output_slope = z @ x / xx
    phase_slope = derivative @ x / xx
    raw = z - z.mean(axis=1)[:, None] - output_slope[:, None] * x
    phase_shape = derivative - derivative.mean(axis=1)[:, None] - phase_slope[:, None] * x
    stiffness = (sigma / widths) ** 2
    information = np.einsum("ij,ij->i", phase_shape, phase_shape) + stiffness
    phase = np.clip(np.einsum("ij,ij->i", raw, phase_shape) / information, -15., 15.)
    residual = raw - phase[:, None] * phase_shape
    score = (np.einsum("ij,ij->i", residual, residual) + stiffness * phase**2) / len(times)
    possible = (elevation.min(axis=1) >= 0) & (np.abs(output_slope - phase * phase_slope) <= 30. + 450. / np.ptp(times))
    return np.where(possible, score, np.inf)


def family_pool(scan, duration):
    anchors = representatives(scan, duration)
    times = np.unique(np.concatenate([scan.tracks[i]["times"] for i in anchors]))
    nominal = scan_kernel.prepare_phase_geometry(scan.sky, times)
    f, e, d = discovery.phase_linear_frequency(nominal, *scan.search_region.center)
    offered = set()
    for i in anchors:
        t = scan.tracks[i]
        columns = np.searchsorted(times, t["times"])
        rf = t["rf_hz"] / discovery.REFERENCE_RF
        score = phase_shape(t["values"], rf * f[:, columns], rf * d[:, columns], e[:, columns],
                            t["times"], np.maximum(1., scan.sigma), scan.radio_sigma_hz)
        order = np.argsort(score, kind="stable")[:PER_TRACK]
        offered.update(int(j) for j in order if np.isfinite(score[j]))
    return np.array(sorted(offered), dtype=np.intp), anchors, len(times)


def compact_catalogue(full, labels):
    compact = copy(full)
    compact.sky = {key: (value if key == "time_s" else value[labels]) for key, value in full.sky.items()}
    compact.norads, compact.sigma = compact.sky["norad"], compact.sky["phase_sigma_s"]
    compact.elements = {str(int(n)): full.elements[str(int(n))] for n in compact.norads}
    compact.geometry = scan_kernel.prepare_phase_geometry(compact.sky, compact.times)
    compact.element_derivatives, compact.reference = {}, {}
    for key in ("previous_shape_cache", "causal_uncertainty_modes", "reference_motion_derivatives"):
        setattr(compact, key, {})
    return compact


def restore(full, node, labels):
    rows = [dict(row, candidate_index=int(labels[row["candidate_index"]])) for row in node["seed"]["rows"]]
    if any(int(full.norads[r["candidate_index"]]) != r["candidate_norad"] for r in rows):
        raise ValueError("Compact candidates do not map to the original causal identities")
    return dict(seed=dict(rows=rows, state=discovery.zero_state(full)), aliases=list(node["aliases"]))


def zero_reference_objective(scan, node):
    labels = {r["candidate_index"] for r in node["seed"]["rows"]}
    model = position.NormalPosition(scan, node, scan.radio_sigma_hz, False, reference=np.zeros(len(labels)))
    residual = model.residual(np.zeros(2))
    return float(residual @ residual)


def choose_cold(prepared, region, bound, measured, labels_used):
    clocks = (process_time(), perf_counter())
    full = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "previous")
    measured["full_context_clocks"] = elapsed(*clocks)
    clocks = (process_time(), perf_counter())
    labels, anchors, times = family_pool(full, prepared["tracks"]["metadata"]["duration_s"])
    detail = dict(full_candidates=len(full.norads), pool_candidates=len(labels), representative_tracks=len(anchors),
                  total_curved_tracks=len(full.curved), representative_times=times, original_times=len(full.times),
                  original_curved_points=sum(len(full.tracks[i]["times"]) for i in full.curved),
                  pool_norads=[int(full.norads[j]) for j in labels])
    measured.update(family_pool=detail, pool_clocks=elapsed(*clocks))
    if not len(labels) or len(labels) == len(full.norads):
        raise ValueError("No smaller causal catalogue was nominated")
    labels_used.update(map(int, labels))
    clocks = (process_time(), perf_counter())
    ranked = v5_core.ranked_initial_nodes(compact_catalogue(full, labels))
    best = [restore(full, node, labels) for node in ranked[:2]]
    scores = [zero_reference_objective(full, node) for node in best]
    detail.update(zero_reference_scores=scores, distinct_ranked_nodes=len(ranked))
    measured["pooled_rank_clocks"] = elapsed(*clocks)
    if not scores or not all(np.isfinite(scores)) or (len(scores) > 1 and scores[1] - scores[0] <= MARGIN):
        raise ValueError("Ambiguous reduced-catalogue cold branches")
    clocks = (process_time(), perf_counter())
    node = best[0]
    model, fit, trace = position.refreshed(full, full.radio_sigma_hz, node, "c0", rounds=2, iterations=48)
    point = np.asarray(fit["parameters"])
    state = model.state(point)
    measured["cold_refinement_clocks"] = elapsed(*clocks)
    if not np.isfinite(fit["score"]) or not np.isfinite(point).all():
        raise ValueError("The exact cold finalist was nonfinite")
    clocks = (process_time(), perf_counter())
    base = discovery.phase_linear_frequency(full.geometry, *region.latlon(point))
    _, rows, _, _ = full.association(state, base, region.native_point(full, point), "receiver_smooth")
    outside = [(row["component"], row["candidate_norad"]) for row in rows
               if row["compatible"] and row["candidate_index"] not in labels_used]
    detail["compatible_outside_winners"] = outside
    measured["outside_check_clocks"] = elapsed(*clocks)
    if outside:
        raise ValueError("Compatible full-catalogue cold nomination lies outside the pool")
    phases = dict(zip(model.labels, np.clip(trace[-1]["posterior_phase_s"], -15., 15.), strict=True))
    return node, point, phases, dict(scores=[float(fit["score"])], branch=1, east_north_km=point,
                                    latlon=region.latlon(point), catalogue=len(full.norads))


def fine_pool(original, labels, counters, kernel, scan, track, y, noise, rf, shortlist, coordinates):
    inside = set(shortlist) & labels
    outside = set(shortlist) - inside
    start = process_time()
    found, supports = original(kernel, scan, track, y, noise, rf, inside, coordinates) if inside else ([], 0)
    counters["inside_cpu_s"] += process_time() - start
    counters["fine_tracks"] += 1
    counters["fine_inside_candidates"] += len(inside)
    ambiguous = (not found or found[0]["points"] != len(track["times"]) or
                 (len(found) > 1 and found[1]["points"] == found[0]["points"]
                  and found[1]["cost"] - found[0]["cost"] <= MARGIN))
    if ambiguous and outside:
        start = process_time()
        remaining, outside_supports = original(kernel, scan, track, y, noise, rf, outside, coordinates)
        counters["outside_cpu_s"] += process_time() - start
        counters["fine_outside_candidates"] += len(outside)
        counters["rescanned_tracks"] += 1
        supports = max(supports, outside_supports)
        found = sorted(found + remaining, key=lambda r: (-r["points"], r["cost"], r["candidate_index"]))[:5]
    else:
        counters["fine_outside_candidates_skipped"] += len(outside)
    return found, supports


def propose(prepared, region, bound, measured, *, repair):
    labels, salvage = set(), Counter()
    measured["pooled_salvage"] = salvage
    cold = partial(choose_cold, measured=measured, labels_used=labels)
    fine = partial(fine_pool, v5_tiled_salvage.fine_alternatives, labels, salvage)
    with patch.object(v5_tiled_salvage, "fine_alternatives", fine):
        return joint_propose(prepared, region, bound, measured, repair=repair, cold_start=cold)
