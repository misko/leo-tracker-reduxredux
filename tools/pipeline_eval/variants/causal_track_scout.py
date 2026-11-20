"""Propose pilot starts from a small strictly causal set of receiver tracklets."""

from dataclasses import dataclass
from math import isfinite

from .coherent_peak_filter import FOLD_HZ, FRAME_RATE_HZ, MAX_GAP_S, Peak, wrapped
from .track_epoch import counter_phase

MAX_LANES = 64
MAX_TRACKLETS = 8
MAX_CENTERS = 4
DRIFT_FRACTION = 50e-6
TRACK_GATE_SAMPLES = 20.0
CFO_BASE_HZ = 1500
CFO_RATE_HZ_S = 6000


@dataclass(slots=True)
class Tracklet:
    latest: Peak
    serial: int
    previous: Peak | None = None
    observations: int = 1


class TrackScout:
    def __init__(self, rate):
        if type(rate) is not int or rate <= 0:
            raise ValueError("track scout requires a fixed integer sample rate")
        self.rate = rate
        self.frame = rate / FRAME_RATE_HZ
        self.centers_frame = round(self.frame)
        self.tracks = {}
        self.last_counter = {}
        self.pending = {}
        self.serial = 0

    def _drift(self, first, second):
        elapsed = (second.counter - first.counter) / self.rate
        phase = counter_phase(second.counter - first.counter, self.rate)
        return wrapped(phase + second.epoch - first.epoch, self.frame) / elapsed

    def _linear(self, track, counter):
        if track.previous is None:
            return None
        prior = track.latest.counter - track.previous.counter
        upcoming = counter - track.latest.counter
        if not prior <= 2 * upcoming <= 4 * prior:
            return None
        rate = self._drift(track.previous, track.latest)
        phase = counter_phase(upcoming, self.rate)
        return (track.latest.epoch + rate * upcoming / self.rate - phase) % self.frame

    def propose(self, lane, counter):
        """Begin a probe using only its known lane metadata and sample counter."""
        if type(counter) is not int or counter < 0:
            raise ValueError("sample counters must be exact nonnegative integers")
        if lane in self.pending or counter <= self.last_counter.get(lane, -1):
            raise ValueError("every lane must commit its prior probe before advancing")
        if lane not in self.tracks and len(self.tracks) >= MAX_LANES:
            raise ValueError("native RF lane inventory exceeds the fixed scout limit")
        retained = [
            track
            for track in self.tracks.get(lane, ())
            if (counter - track.latest.counter) / self.rate <= MAX_GAP_S
        ]
        self.tracks[lane] = retained
        self.pending[lane] = counter
        predictions = []
        ranked = sorted(retained, key=lambda t: (-t.observations, -t.latest.counter, t.serial))
        for track in ranked:
            epoch = self._linear(track, counter)
            if epoch is None:
                continue
            center = round(epoch) % self.centers_frame
            if any(
                abs(wrapped(center - prior, self.centers_frame)) <= 2 for prior, _ in predictions
            ):
                continue
            predictions.append((center, epoch))
            if len(predictions) == MAX_CENTERS:
                break
        return predictions

    def observe(self, lane, counter, winner):
        """Commit the new measurement only after the prospective proposal was emitted."""
        if self.pending.get(lane) != counter:
            raise ValueError("out-of-order detector feedback")
        if winner is not None and (
            winner.counter != counter or not all(map(isfinite, (winner.epoch, winner.cfo_hz)))
        ):
            raise ValueError("detector feedback changed the committed sample or is nonfinite")
        self.pending.pop(lane)
        self.last_counter[lane] = counter
        if winner is None:
            return
        candidates = self.tracks[lane]
        matched = []
        for track in candidates:
            dt = (counter - track.latest.counter) / self.rate
            cfo_innovation = abs(wrapped(winner.cfo_hz - track.latest.cfo_hz, FOLD_HZ))
            cfo_allow = CFO_BASE_HZ + CFO_RATE_HZ_S * dt
            if cfo_innovation > cfo_allow:
                continue
            rate_limit = self.rate * DRIFT_FRACTION
            drift = abs(self._drift(track.latest, winner))
            if drift > rate_limit:
                continue
            if track.previous is None:
                matched.append((1, drift / rate_limit + cfo_innovation / cfo_allow, track))
                continue
            expected = self._linear(track, counter)
            if expected is None:
                continue
            error = abs(wrapped(expected - winner.epoch, self.frame))
            if error <= TRACK_GATE_SAMPLES:
                matched.append((0, error / TRACK_GATE_SAMPLES + cfo_innovation / cfo_allow, track))
        if matched:
            _, _, chosen = min(matched, key=lambda r: (r[0], r[1], r[2].serial))
            chosen.previous = chosen.latest
            chosen.latest = winner
            chosen.observations += 1
        else:
            if len(candidates) == MAX_TRACKLETS:
                candidates.remove(min(candidates, key=lambda t: (t.latest.counter, t.serial)))
            candidates.append(Tracklet(winner, self.serial))
            self.serial += 1
