"""Use spread measured knots for proposal work and exact observations for fitting."""

from pathlib import Path
from runpy import run_path
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from blind_joint_finish import build_at, digest, elapsed, propose as blind_propose
from tools.pipeline_eval.variants import v5_core


SAMPLER = Path(__file__).resolve().parents[3] / "tools/pipeline_eval/variants/algo08_sampled_initial.py"


def sample_tracks(tracks, select):
    result = []
    for track in tracks:
        times = np.asarray(track["times"])
        if not len(times) or np.any(np.diff(times) <= 0):
            raise ValueError("Expected chronological distinct original timestamps")
        knots = select(times)
        result.append(dict(track, times=times[knots], values=np.asarray(track["values"])[knots],
                           observation_ids=[track["observation_ids"][i] for i in knots]))
    return result


def expand_track(full, sampled, active):
    """Recover every point between the retained knot endpoints of an accepted trim."""
    times = np.asarray(full["times"])
    knots = np.searchsorted(times, sampled["times"])
    if (np.any(knots >= len(times)) or not np.array_equal(times[knots], sampled["times"])
            or [full["observation_ids"][i] for i in knots] != list(sampled["observation_ids"])
            or not np.array_equal(np.asarray(full["values"])[knots], sampled["values"])):
        raise ValueError("Proposal knots differ from the original measured track")
    interval = np.flatnonzero(active)
    restored = np.zeros(len(times), bool)
    if interval.size:
        if np.any(np.diff(interval) != 1):
            raise ValueError("Expected a contiguous interval from the original salvage rule")
        restored[knots[interval[0]]:knots[interval[-1]] + 1] = True
    return restored


def expand_support(full, sample, node, keep, basis, entries):
    if not np.array_equal(full.norads, sample.norads):
        raise ValueError("The sample and full contexts use different orbit labels")
    groups, masks = {}, []
    for row, i, section in zip(basis.rows, basis.members, basis.slices, strict=True):
        track = full.tracks[i]
        if track["key"] != row["component"] or sample.tracks[i]["key"] != track["key"]:
            raise ValueError("A curved track moved between proposal and full contexts")
        restored = expand_track(track, sample.tracks[i], keep[section])
        if restored.any():
            groups.setdefault(row["candidate_index"], set()).add(track["receiver"])
        masks.append(restored)
    rebuilt = []
    for e in entries:
        index = e["track_index"]
        track = full.tracks[index]
        label = e["candidate_index"]
        if (track["key"] != e["component"] or index in full.curved or label not in groups
                or int(full.norads[label]) != e["norad"]):
            raise ValueError("A predictive label lost its original track or curved calibration support")
        rebuilt.append(dict(e, points=len(track["times"]), observation_ids=track["observation_ids"],
                            cross_receiver_curved_support=len(groups[label]) == 2))
    if [r["component"] for r in node["seed"]["rows"]] != [r["component"] for r in basis.rows]:
        raise ValueError("Curved membership order changed before expansion")
    return np.concatenate(masks), rebuilt


def propose(prepared, region, bound, measured, *, repair):
    if prepared["status"] != "inputs_prepared":
        return None, prepared["status"]
    cpu, wall = process_time(), perf_counter()
    sampler = run_path(str(SAMPLER))
    original = prepared["tracks"]["tracks"]
    curved = prepared["tracks"]["curved_indices"]
    compact = sample_tracks(original, sampler["spread"])
    reduced = dict(prepared, tracks=dict(prepared["tracks"], tracks=compact))
    context = v5_core.scan_context

    def sample_context(inputs, *args, **kwargs):
        scan = context(inputs, *args, **kwargs)
        scan.curved = list(curved)
        scan.groups = [(scan.tracks[i]["key"], [scan.tracks[i]]) for i in curved]
        return scan

    def expand(sample, node, keep, basis, entries, point, model):
        full = context(prepared, region, digest(prepared["noise"]), bound, "genuine_previous")
        restored_node = sampler["restore_node"](full, node)
        restored, predictive = expand_support(full, sample, node, keep, basis, entries)
        detail.update(compact_curved_selected=int(keep.sum()), full_curved_selected=int(restored.sum()),
                      compact_predictive_selected=sum(e["points"] for e in entries),
                      full_predictive_selected=sum(e["points"] for e in predictive))
        references = dict(zip(basis.labels, basis.reference, strict=True))
        exact, powers, means = build_at(full, restored_node, restored, point, references, model)
        return full, restored_node, restored, exact, powers, means, predictive

    detail = dict(limit=sampler["TRACK_SAMPLES"], tracks=len(original), curved_tracks=len(curved),
                  full_track_points=sum(len(t["times"]) for t in original),
                  compact_track_points=sum(len(t["times"]) for t in compact),
                  full_curved_points=sum(len(original[i]["times"]) for i in curved),
                  compact_curved_points=sum(len(compact[i]["times"]) for i in curved))
    measured.update(quadrature=detail, knot_clocks=elapsed(cpu, wall))
    with patch.object(v5_core, "scan_context", sample_context):
        return blind_propose(reduced, region, bound, measured, repair=repair, expand=expand)
