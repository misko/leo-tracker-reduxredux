"""Bounded chronological linking on saved native pilot candidates."""

from collections import Counter
from dataclasses import dataclass, field
import math

import numpy as np


PERIOD = 1 / 4.4e-6
MAX_LANES = 16
TRACKS_PER_LANE = 8
MAX_CANDIDATES = 4
DUPLICATE_HZ = 350.
MAX_SUPPORT = 128
MAX_SEGMENTS = 64
MAX_LIFETIME_S = 180.
MAX_RATE_HZ_S = 8_000.
MIN_HITS = 6
MIN_CONFIRM_SPAN_S = 1.5
AMBIGUITY_MARGIN = .12


def wrap(hz):
    return hz - PERIOD * round(hz / PERIOD)


def distinct_candidates(candidates):
    peaks = []
    for candidate in sorted(candidates, key=lambda p: (-p['fractional_margin'], p['candidate_rank'])):
        if candidate['passed_fractional_margin_gate'] is not True:
            continue
        hz = wrap(candidate['fractional_tracking_cfo_hz'])
        if all(abs(wrap(hz - earlier)) >= DUPLICATE_HZ for earlier in peaks):
            peaks.append(hz)
            if len(peaks) == MAX_CANDIDATES:
                break
    return peaks


@dataclass(slots=True)
class Track:
    ordinal: int
    lane: tuple
    last: tuple
    frequency: float
    rate: float = 0.
    hits: int = 1
    stride: int = 1
    samples: list = field(default_factory=list)

    @property
    def confirmed(self):
        return self.hits >= MIN_HITS and self.last[0] - self.samples[0][0] >= MIN_CONFIRM_SPAN_S

    def append(self, now, innovation, dt):
        alpha, beta = (1., 1.) if self.hits == 1 else (.8, .35)
        prediction = self.frequency + self.rate * dt
        self.frequency = prediction + alpha * innovation
        self.rate = max(-MAX_RATE_HZ_S, min(MAX_RATE_HZ_S, self.rate + beta * innovation / dt))
        self.last = (now, prediction + innovation)
        if self.hits % self.stride == 0:
            self.samples.append(self.last)
        self.hits += 1
        if len(self.samples) >= MAX_SUPPORT:
            del self.samples[1::2]
            self.stride *= 2

    def descriptor(self):
        if not self.confirmed or self.last[0] - self.samples[0][0] < 20.:
            return None
        points = self.samples if self.samples[-1] is self.last else [*self.samples, self.last]
        if len(points) < 12:
            return None
        times, cfo = np.array(points).T
        centered_t = times - times.mean()
        centered_cfo = cfo - cfo.mean()
        straight = centered_t * (centered_t @ centered_cfo / (centered_t @ centered_t))
        if np.linalg.norm(centered_cfo - straight) / math.sqrt(len(cfo)) < 250.:
            return None
        rx, channel, rf = self.lane
        return dict(times=times, values=cfo, receiver=rx, channel=channel, rf_hz=rf)


class Tracker:
    def __init__(self):
        self.lanes = {}
        self.retired = []
        self.stats = Counter()
        self.latest = -math.inf
        self.first_confirmed = None

    def retire(self, track):
        descriptor = track.descriptor()
        if descriptor is not None:
            self.stats['curved_tracks_retired'] += 1
            self.retired.append((track.hits, track.ordinal, descriptor))
            self.retired.sort(key=lambda item: (-item[0], item[1]))
            if len(self.retired) > MAX_SEGMENTS:
                self.retired.pop()
                self.stats['curved_archive_discards'] += 1

    def ingest(self, now, lane_key, peaks):
        if now < self.latest:
            raise ValueError('native probe timestamps must be nondecreasing')
        if len(peaks) > MAX_CANDIDATES:
            raise ValueError('candidate cap exceeded')
        self.latest = now
        if lane_key not in self.lanes:
            if len(self.lanes) == MAX_LANES:
                raise ValueError('unexpected number of receiver/channel/RF lanes')
            self.lanes[lane_key] = []
        lane = self.lanes[lane_key]
        self.stats['probes'] += 1
        self.stats['probes_with_candidates'] += bool(peaks)
        self.stats['distinct_candidates'] += len(peaks)
        for track in lane[:]:
            if (now - track.last[0] > (6. if track.hits >= 3 else 2.5)
                    or now - track.samples[0][0] > MAX_LIFETIME_S):
                lane.remove(track)
                self.retire(track)
        edges, unexplained = [], []
        for i, measured in enumerate(peaks):
            options = []
            for track in lane:
                dt = now - track.last[0]
                if dt <= 0:
                    continue
                innovation = wrap(measured - track.frequency - track.rate * dt)
                self.stats['continuation_tests'] += 1
                if track.hits == 1:
                    gate = 450 + MAX_RATE_HZ_S * dt
                elif track.hits == 2:
                    gate = 600 + 500 * dt + 35 * dt * dt
                else:
                    gate = 450 + 100 * dt + 35 * dt * dt
                if abs(innovation) <= gate:
                    cost = abs(innovation) / gate + (.5 if track.hits == 1 else 0.) + .03 * i
                    options.append((cost, i, track.ordinal, track, dt, innovation))
            mature = sorted(edge[0] for edge in options if edge[3].confirmed)
            if len(mature) >= 2 and mature[1] - mature[0] < AMBIGUITY_MARGIN:
                self.stats['ambiguous_candidates_skipped'] += 1
            else:
                edges.extend(options)
            if not options and not any(track.last[0] == now and abs(wrap(measured - track.frequency))
                                       < DUPLICATE_HZ for track in lane):
                unexplained.append(measured)
        used_peaks, used_tracks = set(), set()
        for _, i, ordinal, track, dt, innovation in sorted(edges):
            if i in used_peaks or ordinal in used_tracks:
                continue
            was_confirmed = track.confirmed
            track.append(now, innovation, dt)
            used_peaks.add(i)
            used_tracks.add(ordinal)
            self.stats['continuations_kept'] += 1
            if not was_confirmed and track.confirmed:
                self.stats['confirmations'] += 1
                if self.first_confirmed is None:
                    self.first_confirmed = now
        for measured in unexplained:
            self.birth(now, lane_key, lane, measured)
        self.stats['peak_active_per_lane'] = max(self.stats['peak_active_per_lane'], len(lane))
        self.stats['peak_active_total'] = max(self.stats['peak_active_total'], sum(map(len, self.lanes.values())))

    def birth(self, now, lane_key, lane, measured):
        if len(lane) == TRACKS_PER_LANE:
            # An unexplained peak may replace a tentative segment only.
            tentative = [track for track in lane if not track.confirmed and track.last[0] < now]
            if not tentative:
                self.stats['birth_capacity_discards'] += 1
                return
            lane.remove(min(tentative, key=lambda track: (track.hits, track.last[0], track.ordinal)))
            self.stats['tentative_evictions'] += 1
        ordinal = self.stats['births']
        self.stats['births'] += 1
        sample = (now, measured)
        lane.append(Track(ordinal, lane_key, sample, measured, samples=[sample]))

    def document(self):
        segments = list(self.retired)
        for lane in self.lanes.values():
            for track in lane:
                descriptor = track.descriptor()
                if descriptor is not None:
                    segments.append((track.hits, track.ordinal, descriptor))
        segments.sort(key=lambda item: (-item[0], item[1]))
        tracks = [descriptor for _, _, descriptor in segments[:MAX_SEGMENTS]]
        info = dict(self.stats, eligible_segments_before_cap=len(segments), solver_segments=len(tracks),
                    first_track_confirmed_midpoint_air_s=self.first_confirmed,
                    solver_support_points=sum(len(track['times']) for track in tracks))
        return dict(tracks=tracks, curved_indices=list(range(len(tracks)))), info
