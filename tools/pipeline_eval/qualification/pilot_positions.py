"""Carry the bounded reader and both Python pilot banks through an actual position decision."""

import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.reference import receiver, waveform
from tools.pipeline_eval.variants import glrt_batch, glrt_cascade, iq_position, iq_stream

FRAME_STARTS = np.rint(np.arange(15) * waveform.RATE / 750).astype(int)
LAST_TAP = int(waveform.TAPS[-1, -1])
MEAN_TAP = float(waveform.TAPS.mean())


def _bank_peak(search):
    peak = search["winner"]
    if peak and peak["passed"]:
        return peak["epoch_sample"], peak["alias_cfo_hz"], peak["margin"]
    return None


def _cascade_peak(search):
    peak = search.winner
    if peak:
        return peak.epoch_sample, peak.absolute_cfo_hz, peak.margin
    return None


def _point(peak, counter, rate, samples):
    if peak is None:
        return []
    epoch, cfo, margin = peak
    # Both Python banks score complete 64-symbol frames and discard a partial last frame.
    starts = FRAME_STARTS[FRAME_STARTS + epoch + LAST_TAP < samples]
    if rate != waveform.RATE or len(starts) < 2:
        raise ValueError("a Python GLRT detection needs at least two complete 10 MHz frames")
    center = epoch + float(starts.mean()) + MEAN_TAP
    return [
        iq_position.Detection(
            counter,
            (counter + center) / rate,
            cfo,
            waveform.phase_at(epoch, counter),
            margin,
        )
    ]


def _decision(observation, regions, catalogue, boundary, metrics):
    solved = receiver.solve(observation, regions, catalogue)
    result = dict(
        status="ok" if solved["latlon"] is not None else "withheld",
        reason=solved["reason"],
        boundary=boundary,
        metrics=metrics,
        arms=iq_position._arms(solved["latlon"], solved["best_latlon"]),
    )
    return result


def frontends(case, four_regions, directory, check_controls=True):
    """All three candidate paths see the same verified 80 windows and fixed tracking rules."""
    modes = ("glrt_batch", "glrt_cascade")
    lanes = {m: defaultdict(list) for m in modes}
    counts = {m: {"positive": 0} for m in modes}
    if check_controls:
        for count in counts.values():
            count.update(control_positive=0, peak_disagreements=0)
    library = Path(os.environ.get(iq_position.LIBRARY_ENV, iq_position.LIBRARY))
    catalogue = Path(case["catalog_path"]).read_bytes()
    timestamp = case["catalog_timestamp_ns"]
    banks = {}
    window_hashes = []
    clock = None
    receiver_windows = 0
    duration = 0.0

    def windows():
        nonlocal clock, receiver_windows, duration
        later = len(iq_stream.recording_segments(case)) - 2
        if later < 2:
            raise ValueError("the bounded receiver needs two separated segments")
        for index in (0, later):
            plan = iq_stream._read_plan(case, iq_position.SEQUENCES, index)
            materialized, _ = iq_stream._decode(plan, materialize=True)
            streamed, _ = iq_stream._decode(plan, materialize=False)
            if not iq_stream._equal(materialized, streamed):
                raise ValueError("streamed IQ differs from the materialized reader")
            del materialized
            for win in streamed:
                if clock is None:
                    clock = iq_position._clock(win)
                window_hashes.append(win.iq_sha256)
                if iq_position._supported(win, clock):
                    rate, edge = win.sample_rate_hz, win.target["edge"]
                    if rate != waveform.RATE or len(win.samples) != waveform.PROBE_SAMPLES:
                        raise ValueError("Python GLRT requires 20 ms at 10 MHz")
                    counter = win.acquisition["sample_start"] - clock.counter
                    duration = (counter + len(win.samples)) / rate
                    if edge not in banks:
                        reference = waveform.PilotBank(edge)
                        banks[edge] = (
                            reference,
                            glrt_batch.BatchedPilotBank(reference, waveform),
                            glrt_cascade.PilotSearch(edge),
                        )
                    full, batched, cascade = banks[edge]
                    rf = int(win.target["lnb_lo_hz"]) + int(win.acquisition["actual_if_center_hz"])
                    for i, rx in enumerate(win.receiver_ids):
                        data = win.samples[:, i]
                        samples = data[:, 0].astype(float) + 1j * data[:, 1]
                        receiver_windows += 1
                        peaks = {
                            "glrt_batch": _bank_peak(batched.search(samples, counter)),
                            "glrt_cascade": _cascade_peak(cascade.search(samples, gated=True)),
                        }
                        if check_controls:
                            controls = {
                                "glrt_batch": _bank_peak(full.search(samples, counter)),
                                "glrt_cascade": _cascade_peak(cascade.search(samples, gated=False)),
                            }
                            for method, control in controls.items():
                                peak = peaks[method]
                                counts[method]["control_positive"] += control is not None
                                counts[method]["peak_disagreements"] += (
                                    peak[:2] if peak else None
                                ) != (control[:2] if control else None)
                        lane = (rx, int(win.target["channel"]), edge, rf)
                        for method, peak in peaks.items():
                            counts[method]["positive"] += peak is not None
                            points = _point(peak, counter, rate, len(samples))
                            lanes[method][lane].append((counter / rate, points))
                yield win

    native = iq_position.replay(
        windows(),
        case["regions"],
        catalogue,
        timestamp,
        library,
        directory,
        iq_position.replay_metrics(2 * len(iq_position.SEQUENCES)),
    )
    if native["status"] not in ("ok", "withheld"):
        raise ValueError(f"native position receiver did not run: {native.get('reason')}")
    native_observation = json.loads((directory / "iq-replay.json").read_bytes())["observation"]
    shared = dict(
        verified_windows=len(window_hashes),
        valid_receiver_windows=receiver_windows,
        ordered_iq_digest=hashlib.sha256(encoded(window_hashes)).hexdigest(),
        calibration_invariant=True,
    )
    offers = {"one": case["regions"], "four": four_regions}
    measured = []
    for method in (*modes, "iq_stream", "iq_position"):
        if method in modes:
            tracks, linked = iq_position.linked_tracks(lanes[method], iq_position.MAX_REVISIT_S)
            observation = dict(
                anchor_utc_ns=clock.utc_ns,
                cutoff_utc_ns=clock.cutoff_ns,
                duration_s=duration,
                catalog_timestamp_ns=timestamp,
                tracks=tracks,
            )
            metrics = dict(shared, **counts[method], tracks=len(tracks), linked_tracks=linked)
            boundary = (
                "80-window recorded IQ through the modified Python pilot bank, "
                "tracker and regional decision"
            )
        else:
            # The existing raw receiver uses the streamed reader. These labels identify the
            # same measured downstream run, including its input equivalence to the old reader.
            observation = native_observation
            metrics = dict(
                shared,
                tracks=len(observation["tracks"]),
                matched_reader_windows=len(window_hashes),
                native_library_sha256=native["metrics"]["native_library_sha256"],
            )
            boundary = "80-window bounded IQ reader, native GLRT, tracker and regional decision"
        metrics["observation_sha256"] = hashlib.sha256(encoded(observation)).hexdigest()
        for mode, regions in offers.items():
            outcome = _decision(observation, regions, catalogue, boundary, metrics)
            if method in ("iq_stream", "iq_position") and mode == "one":
                for key in ("latlon", "forced_latlon"):
                    if outcome["arms"]["c0"][key] != native["arms"]["c0"][key]:
                        raise ValueError("native replay and repeated regional decisions disagree")
            measured.append((method, mode, outcome))
    return measured
