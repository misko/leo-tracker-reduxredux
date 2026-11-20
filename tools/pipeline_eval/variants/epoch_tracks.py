"""Causal Doppler track links with a simultaneous fractional pilot timing constraint."""

from collections import defaultdict
from dataclasses import dataclass, field
from hashlib import sha256
from statistics import median

from .coherent_peak_filter import FRAME_RATE_HZ, Peak, wrapped
from .track_epoch import counter_phase

MAX_LIVE = 12
PAIR_GAP_S = 2.6
DRIFT = 50e-6
TIE_SCORE = 0.25


@dataclass(slots=True)
class Chain:
    indices: list[int]
    frequencies: list[float]
    epoch_rates: list[float] = field(default_factory=list)


def links(peaks, rate, config):
    """Return disjoint forward chains with an explicit ambiguity and time gate."""
    frame = rate / FRAME_RATE_HZ
    period = config.alias_spacing_hz
    noise = config.association_sigma * config.noise_sigma_hz
    live, completed = [], []
    ambiguous = 0
    for index, peak in enumerate(peaks):
        if index and peak.counter <= peaks[index - 1].counter:
            raise ValueError("exact lane sample counters must be strictly increasing")
        contenders = []
        retained = []
        for chain in live:
            last = peaks[chain.indices[-1]]
            dt = (peak.counter - last.counter) / rate
            gap = config.max_gap_s if chain.epoch_rates else min(PAIR_GAP_S, config.max_gap_s)
            if dt > gap:
                completed.append(chain)
                continue
            retained.append(chain)
            if dt < 0.15:
                continue
            phase = counter_phase(peak.counter - last.counter, rate)
            advance = wrapped(phase + peak.epoch - last.epoch, frame)
            epoch_rate = advance / dt
            raw_cfo = wrapped(peak.cfo_hz - last.cfo_hz, period)
            cfo_bound = config.max_slope_hz_s * dt + noise
            if abs(epoch_rate) > rate * DRIFT or abs(raw_cfo) > cfo_bound:
                continue
            if chain.epoch_rates:
                prior = (last.counter - peaks[chain.indices[-2]].counter) / rate
                velocity = (chain.frequencies[-1] - chain.frequencies[-2]) / prior
                epoch_error = abs(wrapped(advance - median(chain.epoch_rates) * dt, frame))
                cfo_error = abs(wrapped(raw_cfo - velocity * dt, period))
                timing_allow = 4 + 2 * dt
                frequency_allow = noise + 100 * (dt + dt**2)
                if epoch_error > timing_allow or cfo_error > frequency_allow:
                    continue
                score = (epoch_error / timing_allow) ** 2 + (cfo_error / frequency_allow) ** 2
                priority = 0
            else:
                score = (epoch_rate / (rate * DRIFT)) ** 2 + (raw_cfo / cfo_bound) ** 2
                priority = 1
            contenders.append((priority, score, chain.indices[-1], chain, epoch_rate, raw_cfo))
        live = retained
        contenders.sort(key=lambda r: r[:3])
        uncertain = (
            len(contenders) > 1
            and contenders[0][0] == contenders[1][0]
            and contenders[1][1] - contenders[0][1] < TIE_SCORE
        )
        if contenders and not uncertain:
            _, _, _, chain, slope, increment = contenders[0]
            chain.indices.append(index)
            chain.frequencies.append(chain.frequencies[-1] + increment)
            chain.epoch_rates.append(slope)
            del chain.epoch_rates[:-3]
            continue
        ambiguous += uncertain
        if len(live) == MAX_LIVE:
            oldest = min(live, key=lambda c: (bool(c.epoch_rates), c.indices[-1]))
            live.remove(oldest)
            completed.append(oldest)
        live.append(Chain([index], [peak.cfo_hz]))
    return sorted(completed + live, key=lambda chain: chain.indices[0]), ambiguous


def _raw_peaks(document):
    session = document["source"]["session_id"]
    rows = {}
    for probe in document["source"]["probes"]:
        accepted = (c for c in probe["candidates"] if c["passed_fractional_margin_gate"] is True)
        peak = max(
            accepted, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]), default=None
        )
        if peak is None:
            continue
        counter = probe["valid_start_counter"]
        authority = f"{session}:{probe['receiver_id']}:{counter}".encode()
        key = "sha256:" + sha256(authority).hexdigest()
        if key in rows:
            raise ValueError("duplicate active native observation identity")
        rows[key] = (Peak.from_candidate(probe, counter, peak), probe["edge"])
    return rows


def prepare_tracks(document, config):
    """Build the released compact solver's original track and noise input shapes."""
    import numpy as np
    from leo.analysis.localization_v3.tracks import active_curvature, winning_observations

    from leo.analysis.polynomial_tracklets import _best_piece
    from leo.analysis.tracklet_fitting import finish_lane

    observations, metadata = winning_observations(document)
    peaks = _raw_peaks(document)
    if len(peaks) != len(observations):
        raise ValueError("fractional epoch authority differs from stock observation selection")
    lanes = defaultdict(list)
    for obs in observations:
        peak, edge = peaks[obs["observation_id"]]
        if peak.cfo_hz != obs["measured_cfo_hz"]:
            raise ValueError("fractional epoch side data refers to another winner")
        lanes[obs["actual_rf_hz"], obs["receiver"], obs["channel"], edge].append((obs, peak))
    tracks, raw_links, ambiguous = [], 0, 0
    for (rf, rx, channel, edge), entries in sorted(lanes.items()):
        rows, points = zip(*entries, strict=True)
        graphs, ties = links(points, document["source"]["sample_rate_hz"], config)
        raw_links += sum(len(chain.indices) - 1 for chain in graphs)
        ambiguous += ties
        ordinal = 0
        for chain in graphs:
            n = len(chain.indices)
            if n < config.min_points or ordinal >= config.max_tracks:
                continue
            support = [rows[i] for i in chain.indices]
            times = np.array([o["time_s"] for o in support])
            if times[-1] - times[0] < config.min_span_s:
                continue
            cfo = np.array([o["measured_cfo_hz"] for o in support])
            all_indices = np.arange(n)
            model = _best_piece(times, cfo, all_indices, np.array(chain.frequencies), config)
            if model is None:
                continue
            finished = finish_lane(
                times, cfo, all_indices, n, [model], config, method="causal_epoch_cfo"
            )
            for track in finished["tracks"]:
                if ordinal >= config.max_tracks:
                    break
                indices = np.asarray(track["indices"], int)
                indices = indices[np.argsort(times[indices], kind="stable")]
                for piece in track["pieces"]:
                    ix = piece["indices"]
                    piece.update(start_s=float(times[ix].min()), end_s=float(times[ix].max()))
                tracks.append(
                    dict(
                        track,
                        key=f"SCAN-RX{rx}-CH{channel}-T{ordinal:03}-RF{rf:.6f}-{edge}",
                        source_id="SCAN",
                        receiver=rx,
                        channel=channel,
                        rf_hz=rf,
                        bank="CH1-4" if channel <= 4 else "CH5-8",
                        observation_ids=[support[i]["observation_id"] for i in indices],
                        quality_status=track["diagnostics"]["quality_status"],
                        times=times[indices],
                        values=cfo[indices]
                        + config.alias_spacing_hz * finished["alias_lifts"][indices],
                    )
                )
                ordinal += 1
    ids = [oid for track in tracks for oid in track["observation_ids"]]
    if len(ids) != len(set(ids)):
        raise ValueError("causal track compression duplicated observation ownership")
    curved = [i for i, track in enumerate(tracks) if active_curvature(track)]
    return dict(
        observations=observations,
        metadata=metadata,
        tracks=tracks,
        graph_points=len(ids),
        curved_indices=curved,
        status="tracks_prepared" if curved else "no_active_curvature",
        epoch_track_receipt=dict(linked_edges=raw_links, ambiguous_probes=ambiguous),
    )
