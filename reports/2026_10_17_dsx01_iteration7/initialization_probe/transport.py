"""Exact same-observation state transport for a fixed-bank initialization assay.

Research helper only. No data loading, model search, reference coordinates or
candidate selection. Reject incompatible calibration frames instead of fitting
or silently approximating a carried correction.
"""
from __future__ import annotations

import numpy as np


def map_total_timing(source_numbers, source_total_s, target_numbers, source_common_s):
    source = np.asarray(source_numbers)
    target = np.asarray(target_numbers)
    total = np.asarray(source_total_s, float)
    if (source.ndim != 1 or target.ndim != 1 or not len(source) or not len(target)
            or total.shape != source.shape or not np.isfinite(total).all()
            or not np.isfinite(source_common_s)
            or len(set(map(int, source))) != len(source)
            or len(set(map(int, target))) != len(target)
            or np.any(source != source.astype(int)) or np.any(target != target.astype(int))
            or np.any(source <= 0) or np.any(target <= 0)):
        raise ValueError("Unique positive aligned candidate IDs and finite timings required")
    if not np.isclose(total.mean(), source_common_s, rtol=0, atol=1e-10):
        raise ValueError("Source common timing must equal the zero-sum gauge mean")
    lookup = dict(zip(map(int, source), total, strict=True))
    mapped = np.array([lookup.get(int(number), source_common_s) for number in target])
    common = float(mapped.mean())
    relative = mapped - common
    return mapped, common, relative


def calibration_arrays_equal(source_raw, target_raw):
    """Only an identical public calibration frame permits a coefficient copy."""
    for name in ("design", "clock_design"):
        before, after = np.asarray(getattr(source_raw, name)), np.asarray(getattr(target_raw, name))
        if before.shape != after.shape or not np.allclose(before, after, atol=1e-12, rtol=0):
            raise ValueError("Incompatible calibration frame: " + name)
    if source_raw.clock_count != target_raw.clock_count:
        raise ValueError("Identical residual-clock dimensions required")
    if source_raw.group_count or target_raw.group_count:
        raise ValueError("Original frozen-band calibration models required")


def seed_from_context(source_context, vector, nuisance, target_context, *, arm):
    """Carry complete physical/calibration state, use the same neutral q in both starts.

    The target must be the qualified JointBandObjective adapter. Source and target
    share observation metadata, measured values, regional frame and calibration
    basis. Different source orbit banks are allowed; only target-bank orbits will
    subsequently be evaluated. Missing target IDs receive the source common tau.
    """
    if arm not in ("fitted-c", "zero-c"):
        raise ValueError("Declared RF sensitivity arm required")
    source, target = source_context.model, target_context.model
    raw, target_raw = source.original, target.original
    if not hasattr(target, "band_design") or not hasattr(target, "original_nuisance_count"):
        raise ValueError("Qualified joint-band target required")
    calibration_arrays_equal(raw, target_raw)
    if source_context.prior != target_context.prior:
        raise ValueError("Same regional coordinate frame required")
    a, b = source_context.observations, target_context.observations
    if tuple(a.window_ids) != tuple(b.window_ids):
        raise ValueError("Identical ordered observation IDs required")
    for name in ("times_s", "measured_hz", "rf_hz", "receiver", "channel", "margin"):
        if not np.array_equal(getattr(a, name), getattr(b, name)):
            raise ValueError("Identical ordered observations required: " + name)
    sv, sn = np.asarray(vector, float).copy(), np.asarray(nuisance, float)
    if sv.shape != (source.size,) or sn.shape != source.initial_nuisance.shape:
        raise ValueError("Complete source vector and nuisance required")
    if not np.isfinite(sv).all() or not np.isfinite(sn).all():
        raise ValueError("Finite complete source state required")
    if arm == "zero-c":
        sv[6] = 0.0
    tau = sv[7] + source.basis @ sv[8:]
    mapped, common, relative = map_total_timing(source_context.bank.numbers, tau,
                                               target_context.bank.numbers, sv[7])
    tv = np.zeros(target.size)
    tv[:7], tv[7], tv[8:] = sv[:7], common, target.basis.T @ relative
    np.testing.assert_allclose(tv[7] + target.basis @ tv[8:], mapped, atol=1e-10, rtol=0)
    tn = np.zeros_like(target.initial_nuisance)
    tn[:target.clock_count] = sn[:source.clock_count]
    source_offsets = []
    for receiver in target.band_receivers:
        lane = (a.receiver == receiver) & (a.channel >= 5)
        if not lane.any():
            raise ValueError("Target band lacks donor support")
        values = raw.baseline[lane]
        if not np.allclose(values, values[0], atol=1e-10, rtol=0):
            raise ValueError("Donor high-band baseline is not a constant")
        source_offsets.append(values[0])
    source_offsets = np.asarray(source_offsets)
    if not np.allclose(raw.baseline, target.band_design @ source_offsets, atol=1e-10, rtol=0):
        raise ValueError("Donor baseline is not the declared physical band function")
    tn[target.original_nuisance_count:] = source_offsets
    source_correction = raw.correction(sv, sn[:source.base_nuisance_count])
    target_correction = target_raw.correction(tv, tn[:target.base_nuisance_count])
    target_correction += target.band_design @ (source_offsets - target.original_offsets_hz)
    error = float(np.max(abs(source_correction - target_correction)))
    if error > 1e-8:
        raise ValueError("Complete correction transport failed")
    tail = tn[target.base_nuisance_count:target.original_nuisance_count]
    if np.any(tail != 0):
        raise ValueError("Neutral target detection coordinates required")
    q = target.frozen_model.hyperparameters(tail)[2]
    np.testing.assert_allclose(q, np.full(len(q), target.score.detection_budget / len(q)),
                               atol=1e-12, rtol=0)
    before = set(map(int, source_context.bank.numbers))
    after = set(map(int, target_context.bank.numbers))
    return tv, tn, dict(arm=arm, overlap_candidates=len(before & after),
        added_target_candidates=sorted(after - before),
        dropped_source_candidates=sorted(before - after),
        source_common_timing_s=float(sv[7]), target_common_timing_s=common,
        maximum_correction_error_hz=error, absolute_band_offsets_hz=source_offsets.tolist(),
        detection_initialization="Identical neutral target q; donor q deliberately not carried",
        c0_semantics="Only donor RF coefficient zeroed before exact calibration transport",
        calibration_transport="Identical frame; exact coefficients, clock, absolute band function")
