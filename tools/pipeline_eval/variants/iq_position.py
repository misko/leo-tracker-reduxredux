"""Replay bounded, original-rate IQ through GLRT and the regional receiver.

The receiver centers Doppler within each track. A constant RF-dependent
calibration term cancels exactly, so both arms use the same independently
computed result. No saved detector detections, tracks or assignments enter
this experiment.
"""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from contextlib import ExitStack
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from time import perf_counter

import numpy as np

from leo.analysis.starlink.native_short_window import NativeShortWindow
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
)
from leo.native_pipeline.projection import integer_support

BOUNDARY = (
    "Recorded CI16 decode, native GLRT, CFO/time track formation and causal regional position "
    "decision"
)
LIBRARY_ENV = "LEO_PIPELINE_EVAL_GLRT_LIBRARY"
LIBRARY = (
    Path(__file__).resolve().parents[3]
    / ".build-short-window-native-host"
    / "libleo-adaptive-detector.so"
)
SEQUENCES = tuple(64 * chunk + target for chunk in range(5) for target in range(8))
ALIAS_HZ = 1.0 / OFDM_SYMBOL_DURATION_S
FRAME_HZ = int(FRAME_RATE_HZ)
FRAME_US = 1e6 / FRAME_HZ
MIN_MARGIN = 0.025
MAX_REVISIT_S = 4.5
MIN_TRACK_S = 8.0
MIN_POINTS = 4


@dataclass(frozen=True)
class Detection:
    first_counter: int
    time_s: float
    cfo_hz: float
    phase_us: float
    margin: float


@dataclass(frozen=True)
class Clock:
    counter: int
    utc_ns: int
    cutoff_ns: int
    bracket_ns: int
    generation: int
    device_session: int
    sample_rate_hz: int


def _clock(window):
    acquisition = window.acquisition
    receipt = json.loads(acquisition["retune_receipt"])
    bracket = receipt["utc_clock_bracket"]
    before = int(bracket["before"]["realtime_ns"])
    after = int(bracket["after"]["realtime_ns"])
    counter = int(bracket["sample_counter"])
    if counter != acquisition["sample_start"] or not 0 <= after - before <= 2_000_000_000:
        raise ValueError("recorded window has an invalid initial UTC bracket")
    return Clock(
        counter,
        (before + after) // 2,
        before,
        after - before,
        acquisition["generation"],
        acquisition["device_session"],
        window.sample_rate_hz,
    )


def _supported(window, clock):
    acquisition = window.acquisition
    return (
        acquisition["generation"] == clock.generation
        and acquisition["device_session"] == clock.device_session
        and window.sample_rate_hz == clock.sample_rate_hz
        and acquisition["complete"] is True
        and not acquisition.get("quality_flags")
        and acquisition["counter_authority"] == "hardware"
        and acquisition["validity_authority"] == "provider_attested"
        and acquisition["sample_start"] >= clock.counter
        and acquisition["sample_end"] - acquisition["sample_start"] == len(window.samples)
        and len(window.samples) == window.sample_rate_hz // 50
    )


def _wrap(value, period):
    return (value + period / 2) % period - period / 2


def _detections(row, relative_counter, rate, count):
    points = []
    for candidate in row["candidates"]:
        fractional = candidate["fractional_epoch"]
        if fractional["status"] != "complete" or fractional["margin"] < MIN_MARGIN:
            continue
        epoch = candidate["epoch"]
        fraction = fractional["offset_samples"]
        cfo = fractional["tracking_cfo_hz"]
        margin = fractional["margin"]
        if not all(math.isfinite(value) for value in (fraction, cfo, margin)):
            continue
        support = integer_support(epoch, rate, count)
        time_s = (relative_counter + support.center + fraction) / rate
        phase_us = (
            ((relative_counter * FRAME_HZ) % rate) / rate * FRAME_US
            + (epoch + fraction) * 1e6 / rate
        ) % FRAME_US
        points.append(Detection(relative_counter, time_s, cfo, phase_us, margin))
    retained = []
    for point in sorted(points, key=lambda item: -item.margin):
        if not any(
            abs(_wrap(point.cfo_hz - peer.cfo_hz, ALIAS_HZ)) < 25
            and abs(_wrap(point.phase_us - peer.phase_us, FRAME_US)) < 0.3
            for peer in retained
        ):
            retained.append(point)
    return retained


def _link(revisits, max_revisit_s):
    """Extend tracks with exclusive matches and unwrap relative CFO and epoch."""
    active, complete = [], []
    for clock_time, points in revisits:
        stale = [track for track in active if clock_time - track[-1].time_s > max_revisit_s]
        complete.extend(stale)
        active = [track for track in active if clock_time - track[-1].time_s <= max_revisit_s]
        choices = []
        for i, track in enumerate(active):
            last = track[-1]
            for j, point in enumerate(points):
                dt = point.time_s - last.time_s
                if not 0 < dt <= max_revisit_s:
                    continue
                cfo, phase = last.cfo_hz, last.phase_us
                cfo_gate, phase_gate = 15_000 * dt, 12 + 33 * dt
                if len(track) > 1:
                    previous = track[-2]
                    weight = dt / (last.time_s - previous.time_s)
                    cfo += weight * (last.cfo_hz - previous.cfo_hz)
                    phase += weight * (last.phase_us - previous.phase_us)
                    cfo_gate, phase_gate = 650 + 300 * dt**2, 14 + 1.5 * dt**2
                dcfo = _wrap(point.cfo_hz - cfo, ALIAS_HZ)
                dphase = _wrap(point.phase_us - phase, FRAME_US)
                if abs(dcfo) <= cfo_gate and abs(dphase) <= phase_gate:
                    risk = (dcfo / cfo_gate) ** 2 + (dphase / phase_gate) ** 2
                    choices.append(
                        (-min(len(track), 2), risk, -point.margin, i, j, cfo + dcfo, phase + dphase)
                    )
        seen_tracks, seen_points = set(), set()
        for _, _, _, i, j, cfo, phase in sorted(choices):
            if i not in seen_tracks and j not in seen_points:
                point = points[j]
                active[i].append(
                    Detection(point.first_counter, point.time_s, cfo, phase, point.margin)
                )
                seen_tracks.add(i)
                seen_points.add(j)
        active.extend([point] for j, point in enumerate(points) if j not in seen_points)
    return [
        track
        for track in (*complete, *active)
        if len(track) >= MIN_POINTS and track[-1].time_s - track[0].time_s >= MIN_TRACK_S
    ]


def _distinct_tracks(tracks):
    """Count overlapping GLRT sidelobes with equivalent Doppler shape once."""
    retained = []
    for track in sorted(tracks, key=lambda item: (-len(item), -sum(p.margin for p in item))):
        by_visit = {point.first_counter: point.cfo_hz for point in track}
        for _, peer in retained:
            shared = by_visit.keys() & peer.keys()
            if len(shared) < max(MIN_POINTS, 0.7 * min(len(by_visit), len(peer))):
                continue
            differences = np.array([by_visit[visit] - peer[visit] for visit in sorted(shared)])
            residual = _wrap(differences - differences[0], ALIAS_HZ)
            if residual.std() < 600.0:
                break
        else:
            retained.append((track, by_visit))
    return [track for track, _ in retained]


def linked_tracks(lane_windows, max_revisit_s):
    """Build anonymous tracks from detections on the same receiver, channel, edge and RF."""
    linked = {lane: _link(revisits, max_revisit_s) for lane, revisits in lane_windows.items()}
    tracks = [
        dict(
            receiver=receiver,
            channel=channel,
            rf_hz=rf,
            times=[p.time_s for p in track],
            values=[p.cfo_hz for p in track],
        )
        for (receiver, channel, _, rf), lane_tracks in linked.items()
        for track in _distinct_tracks(lane_tracks)
    ]
    return tracks, sum(map(len, linked.values()))


def _arms(latlon=None, forced=None, rms=None):
    return {
        arm: dict(latlon=latlon, forced_latlon=forced, rf_rms_hz=rms) for arm in ("c0", "fitted_c")
    }


def _unavailable(reason, metrics=None):
    return dict(
        status="unavailable", reason=reason, boundary=BOUNDARY, arms=_arms(), metrics=metrics or {}
    )


def replay(
    windows,
    regions,
    catalogue,
    catalog_timestamp_ns,
    library,
    work_dir,
    metrics,
    *,
    max_revisit_s=MAX_REVISIT_S,
):
    """Consume verified CI16 windows, without any previously formed observations."""
    started = perf_counter()
    lane_windows = defaultdict(list)
    audit = []
    clock = None
    previous_counter = -1
    duration_s = 0.0
    with ExitStack() as contexts:
        detectors = {}
        for window in windows:
            if clock is None:
                clock = _clock(window)
            acquisition = window.acquisition
            counter = acquisition["sample_start"]
            if counter <= previous_counter:
                raise ValueError("replay sample counters are not increasing")
            previous_counter = counter
            metrics["windows_loaded"] += 1
            metrics["complex_samples_loaded"] += len(window.samples) * len(window.receiver_ids)
            row_audit = dict(
                sequence=window.sequence,
                global_visit=acquisition["global_visit"],
                iq_sha256=window.iq_sha256,
                sample_start=counter,
                sample_end=acquisition["sample_end"],
                analyzed=False,
                quality_flags=acquisition.get("quality_flags", []),
            )
            audit.append(row_audit)
            if not _supported(window, clock):
                metrics["windows_invalid_support"] += 1
                continue
            edge = window.target["edge"]
            channel = int(window.target["channel"])
            rf = int(window.target["lnb_lo_hz"]) + int(acquisition["actual_if_center_hz"])
            rate = window.sample_rate_hz
            relative = counter - clock.counter
            duration_s = (relative + len(window.samples)) / rate
            metrics["windows_analyzed"] += 1
            metrics["complex_samples_analyzed"] += len(window.samples) * len(window.receiver_ids)
            key = (edge, rate, len(window.receiver_ids))
            if key not in detectors:
                exact = np.asarray(qin_edge_pilot_frame(rate, edge), dtype="<c16")
                control = np.asarray(
                    qin_edge_pilot_frame(rate, edge, symbol_roll=CONTROL_SYMBOL_ROLL), dtype="<c16"
                )
                detectors[key] = contexts.enter_context(
                    NativeShortWindow(
                        str(library),
                        exact,
                        control,
                        sample_rate_hz=rate,
                        receiver_count=len(window.receiver_ids),
                        fractional_epoch=True,
                    )
                )
            mark = perf_counter()
            rows = detectors[key].analyze(window.samples)["rows"]
            metrics["glrt_s"] += perf_counter() - mark
            row_audit.update(analyzed=True, detector_candidates=0, projected_detections=0)
            for row in rows:
                receiver = window.receiver_ids[row["receiver_id"]]
                points = _detections(row, relative, rate, len(window.samples))
                lane_windows[(receiver, channel, edge, rf)].append((relative / rate, points))
                row_audit["detector_candidates"] += len(row["candidates"])
                row_audit["projected_detections"] += len(points)
            metrics["detector_candidates"] += row_audit["detector_candidates"]
            metrics["projected_detections"] += row_audit["projected_detections"]
    if clock is None:
        return _unavailable("raw recording has no selected windows", metrics)

    mark = perf_counter()
    tracks, linked_count = linked_tracks(lane_windows, max_revisit_s)
    metrics.update(
        tracks=len(tracks),
        linked_tracks=linked_count,
        track_points=sum(len(track["times"]) for track in tracks),
        track_spans_s=[track["times"][-1] - track["times"][0] for track in tracks],
        track_s=perf_counter() - mark,
        replay_span_s=duration_s,
        clock_bracket_ns=clock.bracket_ns,
        max_revisit_s=max_revisit_s,
    )
    observation = dict(
        anchor_utc_ns=clock.utc_ns,
        cutoff_utc_ns=clock.cutoff_ns,
        duration_s=duration_s,
        catalog_timestamp_ns=catalog_timestamp_ns,
        tracks=tracks,
    )
    from tools.pipeline_eval.reference import receiver as engine

    mark = perf_counter()
    solved = engine.solve(observation, regions, catalogue)
    diagnostics = solved["diagnostics"]
    work = diagnostics["work"]
    sky = diagnostics.get("sky", {})
    metrics.update(
        position_s=perf_counter() - mark,
        replay_s=perf_counter() - started,
        causal_satellites=sky.get("causal_satellites", 0),
        orbit_propagation_ran=bool(sky),
        association_ran=bool(work["grid_fits"]),
        grid_fits=work["grid_fits"],
        held_point_scores=work["point_scores"],
        time_shift_controls=work["null_schedules"],
    )
    metrics["native_library_sha256"] = sha256(Path(library).read_bytes()).hexdigest()
    (work_dir / "iq-replay.json").write_text(
        json.dumps(
            dict(windows=audit, observation=observation, receiver=solved),
            allow_nan=False,
        )
        + "\n"
    )
    pooled = diagnostics.get("position_evidence", {}).get("pooled")
    result = dict(
        boundary=BOUNDARY,
        metrics=metrics,
        arms=_arms(solved["latlon"], solved["best_latlon"], pooled and pooled["rms_hz"]),
    )
    if solved["status"] == "fix":
        return dict(result, status="ok")
    return dict(result, status="withheld", reason=solved["reason"])


def replay_metrics(selected):
    return dict(
        windows_selected=selected,
        windows_loaded=0,
        windows_analyzed=0,
        windows_invalid_support=0,
        complex_samples_loaded=0,
        complex_samples_analyzed=0,
        detector_candidates=0,
        projected_detections=0,
        glrt_s=0.0,
        calibration_invariant=True,
    )


def run(case: dict, work_dir: Path) -> dict:
    if case.get("panel") not in ("DS26", "DS29"):
        return _unavailable("this panel does not supply a pilot-compatible raw IQ recording")
    if not case.get("catalog_path"):
        return _unavailable("causal orbit catalogue absent")
    timestamp = case.get("catalog_timestamp_ns")
    if timestamp is None:
        return _unavailable("causal orbit catalogue timestamp absent")
    library = Path(os.environ.get(LIBRARY_ENV, LIBRARY))
    if not library.is_file():
        return _unavailable("build the host NativeShortWindow library or set " + LIBRARY_ENV)

    from tools.pipeline_eval.variants.iq_stream import (
        IQReadError,
        load_windows,
        recording_segments,
        recording_window_count,
    )

    metrics = replay_metrics(2 * len(SEQUENCES))
    try:
        segments = recording_segments(case)
        later = len(segments) - 2
        if later < 2:
            return _unavailable("recording lacks two separated replay strata")
        total_windows = recording_window_count(case)
        metrics.update(
            recording_segments=len(segments),
            selected_segments=[0, later],
            recording_windows=total_windows,
            recording_windows_outside_plan=total_windows - metrics["windows_selected"],
        )

        def windows():
            for segment in (0, later):
                yield from load_windows(case, SEQUENCES, segment_index=segment)

        return replay(
            windows(),
            case["regions"],
            Path(case["catalog_path"]).read_bytes(),
            int(timestamp),
            library,
            work_dir,
            metrics,
        )
    except (IQReadError, KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        return _unavailable(str(error), metrics)
