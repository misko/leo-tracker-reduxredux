"""Native GLRT factors to a guarded position using bounded causal Doppler tracks.

The frozen shape receiver removes a constant offset on each fixed-RF track.
Its published coordinate and withholding decisions are invariant to c.
The control is the archived alpha-beta linker, replayed on the same factors
and passed to the same receiver. The replay timers stop before position work.
"""

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from time import perf_counter

import numpy as np

from tools.pipeline_eval.reference import receiver
from tools.pipeline_eval.reference import tracker as legacy
from tools.pipeline_eval.reference.native_archive import NativeArchive

BOUNDARY = "saved native GLRT factors through causal track link and frozen shape position"
MAX_LANES = 16
MAX_LIVE_PER_LANE = 8
MAX_RETIRED = 64
MAX_SUPPORT = 128
MAX_LIFETIME_S = 180.0
MAX_RATE_HZ_S = 8_000.0
MAX_POSITIVE_RATE_HZ_S = 500.0
MEASUREMENT_VARIANCE = 150.0**2
ACCELERATION_VARIANCE = 55.0**2
PAIR_NOISE_MARGIN_HZ = 600.0
AMBIGUITY_MARGIN = 0.12
MIN_HITS = 6
MIN_CONFIRM_SPAN_S = 1.5

Lane = tuple[int, int, float]
Sample = tuple[float, float]


@dataclass(slots=True)
class Track:
    ordinal: int
    lane: Lane
    latest: Sample
    lane_probe: int
    support: list[Sample] = field(init=False)
    frequency: float = field(init=False)
    rate: float = -2_000.0
    ff: float = MEASUREMENT_VARIANCE
    fr: float = 0.0
    rr: float = 3_000.0**2
    hits: int = 1
    stride: int = 1

    def __post_init__(self):
        self.support = [self.latest]
        self.frequency = self.latest[1]

    @property
    def confirmed(self):
        return self.hits >= MIN_HITS and self.latest[0] - self.support[0][0] >= MIN_CONFIRM_SPAN_S

    def predict(self, dt):
        # Constant-velocity Doppler with an unobserved acceleration over this gap.
        qdt2 = ACCELERATION_VARIANCE * dt**2
        ff = self.ff + dt * (2 * self.fr + dt * (self.rr + qdt2 / 4))
        fr = self.fr + dt * (self.rr + qdt2 / 2)
        rr = self.rr + qdt2
        return self.frequency + self.rate * dt, ff, fr, rr

    def append(self, at, lane_probe, prediction, innovation):
        frequency, ff, fr, rr = prediction
        variance = ff + MEASUREMENT_VARIANCE
        self.frequency = frequency + ff / variance * innovation
        self.rate = min(
            MAX_POSITIVE_RATE_HZ_S, max(-MAX_RATE_HZ_S, self.rate + fr / variance * innovation)
        )
        self.ff = ff * MEASUREMENT_VARIANCE / variance
        self.fr = fr * MEASUREMENT_VARIANCE / variance
        self.rr = rr - fr * fr / variance
        self.latest = (at, frequency + innovation)
        self.lane_probe = lane_probe
        if self.hits % self.stride == 0:
            self.support.append(self.latest)
        self.hits += 1
        if len(self.support) == MAX_SUPPORT:
            del self.support[1::2]
            self.stride *= 2

    def descriptor(self):
        if self.latest[0] - self.support[0][0] < 20.0:
            return None
        support = self.support if self.latest is self.support[-1] else [*self.support, self.latest]
        if len(support) < 12:
            return None
        times, values = np.array(support).T
        centered_t = times - times.mean()
        centered_cfo = values - values.mean()
        slope = (centered_t @ centered_cfo) / (centered_t @ centered_t)
        deviation = np.linalg.norm(centered_cfo - slope * centered_t) / math.sqrt(len(support))
        if deviation < 250.0:
            return None
        rx, channel, rf_hz = self.lane
        return dict(times=times, values=values, receiver=rx, channel=channel, rf_hz=rf_hz)


@dataclass(slots=True)
class LaneState:
    probes: int = 0
    live: list[Track] = field(default_factory=list)


class Tracker:
    def __init__(self):
        self.lanes: dict[Lane, LaneState] = {}
        self.retired: list[tuple[int, int, dict]] = []
        self.latest = -math.inf
        self.stats = Counter()
        self.max_link_gap = 0.0

    def _expire(self, at, lane):
        live = []
        for track in lane.live:
            max_gap = 6.0 if track.hits >= 3 else 2.5
            if at - track.latest[0] <= max_gap and at - track.support[0][0] <= MAX_LIFETIME_S:
                live.append(track)
                continue
            self.stats["confirmed_expired"] += track.confirmed
            descriptor = track.descriptor()
            if descriptor is not None:
                self.retired.append((-track.hits, track.ordinal, descriptor))
                self.retired.sort()
                del self.retired[MAX_RETIRED:]
        lane.live = live

    def _birth(self, at, key, lane, measured):
        if len(lane.live) == MAX_LIVE_PER_LANE:
            tentative = [
                track for track in lane.live if not track.confirmed and track.latest[0] < at
            ]
            if not tentative:
                self.stats["birth_capacity_discards"] += 1
                return
            lane.live.remove(min(tentative, key=lambda t: (t.hits, t.latest[0], t.ordinal)))
            self.stats["tentative_evictions"] += 1
        lane.live.append(Track(self.stats["births"], key, (at, measured), lane.probes))
        self.stats["births"] += 1

    def ingest(self, at, key, peaks):
        if at < self.latest or len(peaks) > legacy.MAX_CANDIDATES:
            raise ValueError("out of order native factors or peak cap exceeded")
        self.latest = at
        if key not in self.lanes:
            if len(self.lanes) == MAX_LANES:
                raise ValueError("unsupported level of receiver/channel/RF lane diversity")
            self.lanes[key] = LaneState()
        lane = self.lanes[key]
        lane.probes += 1
        self._expire(at, lane)
        if not peaks:
            return

        edges = []
        explained = set()
        for track in lane.live:
            dt = at - track.latest[0]
            if dt == 0.0:
                explained.update(
                    i
                    for i, peak in enumerate(peaks)
                    if abs(legacy.wrap(peak - track.latest[1])) < legacy.DUPLICATE_HZ
                )
                continue
            prediction = track.predict(dt)
            frequency, variance, _, _ = prediction
            gate = 3.0 * math.sqrt(variance + MEASUREMENT_VARIANCE)
            penalty = 0.0 if track.confirmed else 0.33 / track.hits
            self.stats["continuation_tests"] += len(peaks)
            for i, peak in enumerate(peaks):
                innovation = legacy.wrap(peak - frequency)
                delta = frequency + innovation - track.latest[1]
                if (
                    abs(innovation) <= gate
                    and -MAX_RATE_HZ_S * dt - PAIR_NOISE_MARGIN_HZ
                    <= delta
                    <= MAX_POSITIVE_RATE_HZ_S * dt + PAIR_NOISE_MARGIN_HZ
                ):
                    edges.append(
                        (
                            abs(innovation) / gate + penalty,
                            i,
                            track.ordinal,
                            track,
                            prediction,
                            innovation,
                        )
                    )
                    explained.add(i)

        peak_costs = {}
        track_costs = {}
        edges.sort()
        for cost, i, ordinal, track, _, _ in edges:
            if track.confirmed:
                peak_costs.setdefault(i, []).append(cost)
                track_costs.setdefault(ordinal, []).append(cost)
        ambiguous_peaks = {
            i
            for i, options in peak_costs.items()
            if len(options) > 1 and options[1] - options[0] < AMBIGUITY_MARGIN
        }
        ambiguous_tracks = {
            i
            for i, options in track_costs.items()
            if len(options) > 1 and options[1] - options[0] < AMBIGUITY_MARGIN
        }
        self.stats["ambiguous_peaks"] += len(ambiguous_peaks)
        self.stats["ambiguous_tracks"] += len(ambiguous_tracks)
        used_peaks, used_tracks = set(), set()
        for _, i, ordinal, track, prediction, innovation in edges:
            if (
                i in ambiguous_peaks
                or ordinal in ambiguous_tracks
                or i in used_peaks
                or ordinal in used_tracks
            ):
                continue
            first_link = not track.confirmed
            skipped = lane.probes - track.lane_probe - 1
            gap = at - track.latest[0]
            track.append(at, lane.probes, prediction, innovation)
            self.stats["continuations"] += 1
            if track.confirmed:
                self.stats["confirmations"] += first_link
                self.stats["confirmed_coasted_links"] += skipped > 0
                self.stats["confirmed_missed_visits_bridged"] += skipped
                self.max_link_gap = max(self.max_link_gap, gap)
            used_peaks.add(i)
            used_tracks.add(ordinal)

        self.stats["unlinked_compatible_peaks"] += len(explained - used_peaks)
        for i, peak in enumerate(peaks):
            if i not in explained:
                self._birth(at, key, lane, peak)
        self.stats["peak_active_total"] = max(
            self.stats["peak_active_total"], sum(len(state.live) for state in self.lanes.values())
        )

    def document(self):
        segments = list(self.retired)
        for lane in self.lanes.values():
            for track in lane.live:
                descriptor = track.descriptor()
                if descriptor is not None:
                    segments.append((-track.hits, track.ordinal, descriptor))
        segments.sort()
        tracks = [desc for _, _, desc in segments[:MAX_RETIRED]]
        return {"tracks": tracks}, dict(self.stats, candidate_max_link_gap_s=self.max_link_gap)


def _replay(path, tracker):
    started = perf_counter()
    probes = passing_probes = peaks_seen = 0
    with path.open(encoding="utf-8") as source:
        archive = NativeArchive(source)
        half_probe = archive.probe_s / 2
        duration = archive.meta["duration_s"]
        for at, raw in archive:
            probe = json.loads(raw)
            peaks = legacy.distinct_candidates(probe["candidates"])
            lane = (1 + probe["receiver_id"], probe["channel"], probe["actual_rf_hz"])
            if at - half_probe < -1e-8 or at + half_probe > duration + 1e-8:
                raise ValueError("native factor outside recorded support")
            tracker.ingest(at, lane, peaks)
            probes += 1
            passing_probes += bool(peaks)
            peaks_seen += len(peaks)
    document, statistics = tracker.document()
    tracks = document["tracks"]
    observation = dict(
        tracks=tracks,
        duration_s=duration,
        anchor_utc_ns=archive.meta["anchor_utc_ns"],
        cutoff_utc_ns=archive.meta["causal_cutoff_utc_ns"],
    )
    counts = dict(
        native_probes=probes, probes_with_candidates=passing_probes, candidate_peaks=peaks_seen
    )
    elapsed = perf_counter() - started
    return observation, counts, statistics, elapsed


def _catalog_timestamp(case):
    if case.get("catalog_timestamp_ns") is not None:
        return int(case["catalog_timestamp_ns"])
    name = Path(case["catalog_path"]).name.split("-", 1)[0]
    if name.isdecimal():
        return int(name)
    with Path(case["observation_path"]).open(encoding="utf-8") as source:
        header = source.read(4096)
    match = re.search(r',\s*"tracks"\s*:', header)
    if match is None:
        raise ValueError("portable observation header must precede track records")
    return int(json.loads(header[: match.start()] + "}")["catalog_timestamp_ns"])


def _position(observation, regions, catalogue, timestamp):
    if timestamp > observation["cutoff_utc_ns"]:
        raise ValueError("TLE catalogue snapshot is later than native cutoff")
    started = perf_counter()
    result = receiver.solve(dict(observation, catalog_timestamp_ns=timestamp), regions, catalogue)
    return result, perf_counter() - started


def _arm(result=None):
    if result is None:
        return dict(latlon=None)
    return dict(
        latlon=result["latlon"],
        forced_latlon=result["best_latlon"],
        region_id=result["region_id"],
        reason=result["reason"],
    )


def run(case, work_dir):
    """Replay two linkers on identical archived factors and solve their own tracks."""
    try:
        if not case.get("native_path") or not case.get("catalog_path"):
            raise ValueError("native detector factors and a causal TLE catalogue are required")
        if not case.get("regions"):
            raise ValueError("at least one offered region is required")
        native = Path(case["native_path"])
        catalogue = Path(case["catalog_path"]).read_bytes()
        timestamp = _catalog_timestamp(case)
        linkers = {"candidate": Tracker(), "control": legacy.Tracker()}
        order = sorted(linkers, reverse=bool(sha256(case["id"].encode()).digest()[0] % 2))
        replays = {side: _replay(native, linkers[side]) for side in order}
        candidate, counts, stats, candidate_s = replays["candidate"]
        control, control_counts, control_stats, control_s = replays["control"]
        if counts != control_counts:
            raise ValueError("matched replay consumed different numbers of factors")
        outcomes = {
            side: _position(replays[side][0], case["regions"], catalogue, timestamp)
            for side in order
        }
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return dict(
            status="unavailable",
            boundary=BOUNDARY,
            reason=str(exc),
            metrics={},
            arms={name: _arm() for name in ("c0", "fitted_c")},
        )

    result, position_s = outcomes["candidate"]
    prior, prior_position_s = outcomes["control"]
    metrics = dict(
        counts,
        candidate_s=candidate_s,
        control_s=control_s,
        timing_scope="archive decode, deduplicate, link and emit tracks",
        calibration_invariant=True,
        timing_order=order,
        candidate_position_s=position_s,
        control_position_s=prior_position_s,
        candidate_tracks=len(candidate["tracks"]),
        control_tracks=len(control["tracks"]),
        candidate_support_points=sum(len(t["times"]) for t in candidate["tracks"]),
        control_support_points=sum(len(t["times"]) for t in control["tracks"]),
        candidate_peak_active=stats.get("peak_active_total", 0),
        control_peak_active=control_stats.get("peak_active_total", 0),
        candidate_links=stats.get("continuations", 0),
        control_links=control_stats.get("continuations_kept", 0),
        candidate_confirmed=stats.get("confirmations", 0),
        control_confirmed=control_stats.get("confirmations", 0),
        candidate_confirmed_coasted_links=stats.get("confirmed_coasted_links", 0),
        candidate_confirmed_missed_visits_bridged=stats.get("confirmed_missed_visits_bridged", 0),
        candidate_confirmed_expired=stats.get("confirmed_expired", 0),
        candidate_ambiguous_peaks=stats.get("ambiguous_peaks", 0),
        candidate_ambiguous_tracks=stats.get("ambiguous_tracks", 0),
        candidate_max_link_gap_s=stats["candidate_max_link_gap_s"],
        candidate_unlinked_compatible_peaks=stats.get("unlinked_compatible_peaks", 0),
        control_ambiguous_peaks=control_stats.get("ambiguous_candidates_skipped", 0),
        control_status=prior["status"],
        control_reason=prior["reason"],
        control_latlon=prior["latlon"] or [],
        control_forced_latlon=prior["best_latlon"] or [],
    )
    for side, (endpoint, _) in outcomes.items():
        diagnostics = endpoint["diagnostics"]
        fit_tracks = diagnostics.get("track_counts", {})
        for key in ("early", "late", "pooled"):
            metrics[f"{side}_{key}_tracks"] = fit_tracks.get(key, 0)
        metrics[f"{side}_grid_fits"] = diagnostics["work"]["grid_fits"]
        pooled = diagnostics.get("position_evidence", {}).get("pooled")
        if pooled is not None and pooled["rms_hz"] is not None:
            metrics[f"{side}_centered_rms_hz"] = pooled["rms_hz"]
    status = "ok" if result["status"] == "fix" else "withheld"
    return dict(
        status=status,
        reason=result["reason"],
        boundary=BOUNDARY,
        metrics=metrics,
        arms={name: _arm(result) for name in ("c0", "fitted_c")},
    )
