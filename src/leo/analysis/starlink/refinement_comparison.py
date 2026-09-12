"""Known-shift diagnostics on bounded independent scanner probes, with no IO."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Literal, cast

import numpy as np
import numpy.typing as npt

from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.glrt_refinement_prototype import continuous_glrt_score, joint_refine
from leo.analysis.starlink.pilot_methods import refine_glrt64_epochs
from leo.contracts.scanner_refinement import (
    PROFILES,
    Case,
    ComparisonCandidateV1,
    ComparisonMetricV1,
    ComparisonRowV1,
    Profile,
)


@dataclass(frozen=True)
class RefinementProbe:
    probe_id: str
    visit_index: int
    receiver_id: int
    target_index: int
    time_s: float
    sample_rate_hz: int
    edge: str
    samples: npt.NDArray[np.complex128]


def timing_difference(a: float, b: float) -> float:
    return (a - b + 1 / 1500) % (1 / 750) - 1 / 1500


def select_candidate(candidates: tuple[ComparisonCandidateV1, ...], phase: float | None):
    eligible = [
        c
        for c in candidates
        if c.epoch_s is not None
        and c.cfo_hz is not None
        and c.margin is not None
        and c.margin >= 0.025
        and (phase is None or abs(timing_difference(c.integer_epoch_s, phase)) <= 800e-9)
    ]
    return max(eligible, key=lambda c: (c.exact_score or 0, -c.rank)) if eligible else None


def score_profiles(samples: npt.NDArray[np.complex128], fs: int, edge: str):
    config = SymbolwiseAcquisitionConfig(
        maximum_probe_samples=len(samples),
        fine_cfo_step_hz=500,
        conditioned_cfo_step_hz=100,
        candidate_epoch_separation_samples=5,
        candidate_cfo_separation_hz=10000,
        retained_candidate_count=8,
    )
    started = time.perf_counter()
    acquisition = acquire_symbolwise(
        samples,
        fs,
        ReceiverFrequencyCalibration("comparison", 0, "0" * 64),
        edge=edge,
        config=config,
    )
    acquisition_seconds = time.perf_counter() - started
    results: dict[Profile, tuple[tuple[ComparisonCandidateV1, ...], float]] = {}
    for grid, profile in ((512, "grid512"), (8192, "grid8192")):
        started = time.perf_counter()
        refined = refine_glrt64_epochs(
            samples,
            fs,
            integer_epoch_samples=[c.refined_epoch_sample for c in acquisition.candidates],
            acquired_cfo_hz=[c.absolute_cfo_hz for c in acquisition.candidates],
            edge=edge,
            glrt_size=grid,
        )
        rows = tuple(
            ComparisonCandidateV1(
                rank=c.rank,
                integer_epoch_s=c.refined_epoch_sample / fs,
                epoch_s=(c.refined_epoch_sample + r.fractional_epoch_offset_samples) / fs
                if r.fractional_epoch_offset_samples is not None
                else None,
                cfo_hz=r.fractional_tracking_cfo_hz,
                exact_score=r.fractional_exact_score,
                margin=r.fractional_margin,
            )
            for c, r in zip(acquisition.candidates, refined, strict=True)
        )
        results[cast(Profile, profile)] = rows, time.perf_counter() - started
    local, joint = [], []
    local_seconds = joint_seconds = 0.0
    for c, base in zip(acquisition.candidates, results["grid512"][0], strict=True):
        if base.epoch_s is None:
            local.append(base)
            joint.append(base)
            continue
        offset = base.epoch_s * fs - c.refined_epoch_sample
        started = time.perf_counter()
        score, _ = continuous_glrt_score(
            samples,
            fs,
            anchor=c.refined_epoch_sample,
            offset=offset,
            conditioning_cfo_hz=c.absolute_cfo_hz,
            edge=edge,
        )
        local_seconds += time.perf_counter() - started
        local.append(
            base.model_copy(
                update={
                    "cfo_hz": score.tracking_cfo_hz,
                    "exact_score": score.exact_score,
                    "margin": score.margin,
                }
            )
        )
        started = time.perf_counter()
        refined_offset, score, _ = joint_refine(
            samples,
            fs,
            anchor=c.refined_epoch_sample,
            offset=offset,
            conditioning_cfo_hz=c.absolute_cfo_hz,
            edge=edge,
            initial_score=score,
        )
        joint_seconds += time.perf_counter() - started
        joint.append(
            base.model_copy(
                update={
                    "epoch_s": (c.refined_epoch_sample + refined_offset) / fs,
                    "cfo_hz": score.tracking_cfo_hz,
                    "exact_score": score.exact_score,
                    "margin": score.margin,
                }
            )
        )
    results["local512"] = tuple(local), results["grid512"][1] + local_seconds
    results["joint512"] = tuple(joint), results["local512"][1] + joint_seconds
    return results, acquisition_seconds


def compare_probe(probe: RefinementProbe) -> tuple[ComparisonRowV1, ...]:
    fs, samples = probe.sample_rate_hz, probe.samples
    if fs not in (2500000, 5000000, 10000000) or len(samples) != round(fs * 0.021):
        raise ValueError("comparison requires exactly 21 ms at a supported sample rate")
    seed = int(
        hashlib.sha256(("scanner-refinement-v1:" + probe.probe_id).encode()).hexdigest()[:16], 16
    )
    rng = np.random.default_rng(seed)
    frequency = float(rng.uniform(100, 2000) * rng.choice([-1, 1]))
    delay_ns = float(rng.uniform(30, 300) * rng.choice([-1, 1]))
    cases: tuple[tuple[Case, float], ...] = (
        ("baseline", 0),
        ("frequency", frequency),
        ("delay", delay_ns),
    )
    rows = []
    phase = None
    baseline_found = False
    for case, amount in cases:
        if case == "frequency":
            values = samples * np.exp(2j * np.pi * amount * np.arange(len(samples)) / fs)
        elif case == "delay":
            values = np.fft.ifft(
                np.fft.fft(samples)
                * np.exp(-2j * np.pi * np.fft.fftfreq(len(samples), 1 / fs) * amount * 1e-9)
            )
        else:
            values = samples
        crop = round(fs * 0.0005)
        profiles, acquisition_seconds = score_profiles(
            values[crop : crop + fs // 50], fs, probe.edge
        )
        if case == "baseline":
            baseline = select_candidate(profiles["grid512"][0], None)
            baseline_found = baseline is not None
            phase = baseline.integer_epoch_s if baseline is not None else None
        for profile in PROFILES:
            candidates, seconds = profiles[profile]
            selected = select_candidate(candidates, phase) if baseline_found else None
            rows.append(
                ComparisonRowV1(
                    probe_id=probe.probe_id,
                    visit_index=probe.visit_index,
                    receiver_id=cast(Literal[0, 1], probe.receiver_id),
                    target_index=probe.target_index,
                    time_s=probe.time_s,
                    profile=profile,
                    case=case,
                    amount=amount,
                    candidates=candidates,
                    selected_rank=selected.rank if selected else None,
                    acquisition_seconds=acquisition_seconds,
                    scoring_seconds=seconds,
                )
            )
    return tuple(rows)


def comparison_errors(rows: tuple[ComparisonRowV1, ...]):
    bases = {(r.probe_id, r.profile): r.selected for r in rows if r.case == "baseline"}
    errors = []
    for row in rows:
        if row.case == "baseline":
            continue
        base, selected = bases.get((row.probe_id, row.profile)), row.selected
        item = {
            "probe_id": row.probe_id,
            "profile": row.profile,
            "case": row.case,
            "time_s": row.time_s,
            "recovered": base is not None and selected is not None,
        }
        if base is not None and selected is not None:
            assert base.cfo_hz is not None and selected.cfo_hz is not None
            assert base.epoch_s is not None and selected.epoch_s is not None
            raw = selected.cfo_hz - base.cfo_hz - (row.amount if row.case == "frequency" else 0)
            folded = (raw + 1 / 8.8e-6) % (1 / 4.4e-6) - 1 / 8.8e-6
            dt = timing_difference(selected.epoch_s, base.epoch_s) * 1e9 - (
                row.amount if row.case == "delay" else 0
            )
            item.update(
                raw_cfo_hz=raw, cfo_hz=folded, delay_ns=dt, alias_changed=abs(raw - folded) > 1
            )
        errors.append(item)
    return errors


def comparison_metrics(rows: tuple[ComparisonRowV1, ...]) -> tuple[ComparisonMetricV1, ...]:
    errors = comparison_errors(rows)
    metrics = []
    for case in ("frequency", "delay"):
        common = set.intersection(
            *[
                {
                    e["probe_id"]
                    for e in errors
                    if e["case"] == case and e["profile"] == p and e["recovered"]
                }
                for p in PROFILES
            ]
        )
        for profile in PROFILES:
            group = [e for e in errors if e["case"] == case and e["profile"] == profile]
            good = [e for e in group if e["probe_id"] in common]

            def rms(key, selected=good):
                if not selected:
                    return None
                return float(np.sqrt(np.mean([e[key] ** 2 for e in selected])))

            metrics.append(
                ComparisonMetricV1(
                    profile=profile,
                    case=case,
                    attempted=len(group),
                    recovered=sum(e["recovered"] for e in group),
                    common=len(good),
                    cfo_rms_hz=rms("cfo_hz"),
                    raw_cfo_rms_hz=rms("raw_cfo_hz"),
                    delay_rms_ns=rms("delay_ns"),
                    alias_changes=sum(e.get("alias_changed", False) for e in group),
                )
            )
    return tuple(metrics)
