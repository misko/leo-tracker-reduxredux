"""Causal, source-isolated PSS timing and coarse carrier tracking.

Two constant-rate Kalman filters predict template-relative frame phase and CFO.
No satellite, absolute arrival time, or phase-coherent continuity is asserted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from leo.analysis.starlink.pss_bandwidth import PssBandSearch

PERIOD_S = 1 / 750


def circular_residual(observed: float, predicted: float) -> float:
    return (observed - predicted + PERIOD_S / 2) % PERIOD_S - PERIOD_S / 2


@dataclass(frozen=True)
class PssObservation:
    time_s: float
    frame_phase_s: float
    cfo_hz: float
    timing_sigma_s: float
    cfo_sigma_hz: float
    score: float

    def __post_init__(self) -> None:
        values = (
            self.time_s,
            self.frame_phase_s,
            self.cfo_hz,
            self.timing_sigma_s,
            self.cfo_sigma_hz,
            self.score,
        )
        if not all(math.isfinite(v) for v in values):
            raise ValueError("PSS observations must be finite")
        if min(self.timing_sigma_s, self.cfo_sigma_hz, self.score) <= 0:
            raise ValueError("PSS observation uncertainties and score must be positive")


def observations_from_search(search: PssBandSearch) -> tuple[PssObservation, ...]:
    """Keep every qualified timing mode; merge neighboring CFO-bank duplicates.

    Uncertainty is conservative: the timing floor is one sample, and carrier
    uncertainty is at least one bank step. Scores are diagnostics, not calibrated
    probabilities. Per-frame scatter is never divided by sqrt(frame count).
    """
    rate = search.band.sample_rate_hz
    time = (search.device_sample_start + search.sample_count / 2) / rate
    frequencies = sorted(r.nominal_frequency_offset_hz for r in search.hypotheses)
    rows = []
    for result in search.hypotheses:
        position = frequencies.index(result.nominal_frequency_offset_hz)
        gaps = []
        if position:
            gaps.append(frequencies[position] - frequencies[position - 1])
        if position + 1 < len(frequencies):
            gaps.append(frequencies[position + 1] - frequencies[position])
        step = max(gaps, default=rate / 2)
        for candidate in result.qualified_candidates:
            windows = [w for w in result.windows if w.candidate_index == candidate.candidate_index]
            if not windows:
                continue
            phases = np.asarray([w.frame_phase_samples / rate for w in windows])
            phases = np.unwrap(phases * 2 * np.pi / PERIOD_S) * PERIOD_S / (2 * np.pi)
            rows.append(
                PssObservation(
                    time,
                    float(np.median(phases)) % PERIOD_S,
                    candidate.frequency_offset_hz,
                    max(1 / rate, float(np.std(phases))),
                    max(1.0, float(step)),
                    candidate.robust_z,
                )
            )
    retained = []
    for row in sorted(rows, key=lambda x: (-x.score, x.frame_phase_s, x.cfo_hz)):
        if not any(
            abs(circular_residual(row.frame_phase_s, other.frame_phase_s)) <= 2e-6
            and abs(row.cfo_hz - other.cfo_hz)
            <= max(75_000.0, row.cfo_sigma_hz, other.cfo_sigma_hz)
            for other in retained
        ):
            retained.append(row)
    return tuple(retained)


@dataclass(frozen=True)
class PssTrackEstimate:
    state: str
    reason: str
    time_s: float
    frame_phase_s: float | None
    timing_rate_s_per_s: float | None
    timing_sigma_s: float | None
    cfo_hz: float | None
    cfo_rate_hz_per_s: float | None
    cfo_sigma_hz: float | None
    accepted_observations: int
    candidate_only: bool = field(default=True, init=False)


class PssTracker:
    """One receiver/channel/clock binding. Supply continuous blocks independently.

    The source key must include geometry, RX and clock generation. DSP history
    never crosses a block boundary. A gap may be bridged only by this statistical
    prediction, with growing uncertainty and an explicit maximum age.
    """

    def __init__(
        self,
        source_key: str,
        *,
        maximum_gap_s: float = 3.0,
        minimum_updates: int = 3,
        maximum_misses: int = 3,
    ):
        if not source_key or not math.isfinite(maximum_gap_s) or maximum_gap_s <= 0:
            raise ValueError("PSS source and maximum gap must be explicit")
        if minimum_updates < 2 or maximum_misses < 1:
            raise ValueError("PSS tracking counts are invalid")
        self.source_key = source_key
        self.maximum_gap_s = maximum_gap_s
        self.minimum_updates = minimum_updates
        self.maximum_misses = maximum_misses
        self._time: float | None = None
        self._last_accept: float | None = None
        self._x: np.ndarray | None = None
        self._p: np.ndarray | None = None
        self._accepted = 0
        self._misses = 0

    def frequency_bank(
        self, time_s: float, blind_bank_hz: tuple[float, ...], *, step_hz: float
    ) -> tuple[float, ...]:
        """Narrow a future search only after lock, within the declared blind domain.

        Returned hypotheses are an optimization suggestion; callers retain the
        full blind bank for periodic reacquisition and reference comparisons.
        """
        if (
            not math.isfinite(time_s)
            or not math.isfinite(step_hz)
            or step_hz <= 0
            or not blind_bank_hz
            or not all(math.isfinite(f) for f in blind_bank_hz)
        ):
            raise ValueError("PSS prediction bank must be finite and nonempty")
        if self._time is not None and time_s <= self._time:
            raise ValueError("PSS prediction time must be increasing")
        if (
            self._x is None
            or self._accepted < self.minimum_updates
            or self._misses
            or self._last_accept is None
            or time_s - self._last_accept > self.maximum_gap_s
        ):
            return blind_bank_hz
        assert self._p is not None and self._time is not None
        dt = time_s - self._time
        vector = np.array([1.0, dt])
        center = float(vector @ self._x[1])
        radius = max(step_hz, 4 * math.sqrt(float(vector @ self._p[1] @ vector) + 1e6 * dt**3 / 3))
        low = max(min(blind_bank_hz), center - radius)
        high = min(max(blind_bank_hz), center + radius)
        count = math.ceil((high - low) / step_hz) + 1
        if high <= low or count > 257:
            return blind_bank_hz
        return tuple(float(x) for x in np.linspace(low, high, count))

    def update(
        self, source_key: str, time_s: float, observations: tuple[PssObservation, ...]
    ) -> PssTrackEstimate:
        if source_key != self.source_key:
            raise ValueError("PSS tracker source binding changed")
        if not math.isfinite(time_s) or (self._time is not None and time_s <= self._time):
            raise ValueError("PSS tracker time must be finite and strictly increasing")
        if any(abs(o.time_s - time_s) > 1e-9 for o in observations):
            raise ValueError("PSS observations differ from update time")
        dt = 0.0 if self._time is None else time_s - self._time
        self._time = time_s
        expired = self._last_accept is not None and time_s - self._last_accept > self.maximum_gap_s
        if expired:
            self._x = self._p = None
            self._accepted = 0
        if self._x is not None:
            assert self._p is not None
            transition = np.array([[1.0, dt], [0.0, 1.0]])
            # Integrated random acceleration, separate physical units per filter.
            process = np.array([[dt**3 / 3, dt**2 / 2], [dt**2 / 2, dt]])
            for i, noise in enumerate((1e-14, 1e6)):
                self._x[i] = transition @ self._x[i]
                self._p[i] = transition @ self._p[i] @ transition.T + noise * process
        eligible = []
        for observation in observations:
            if self._x is not None:
                assert self._p is not None
                timing_error = circular_residual(observation.frame_phase_s, self._x[0, 0])
                cfo_error = observation.cfo_hz - self._x[1, 0]
                if abs(timing_error) > min(
                    PERIOD_S / 8,
                    max(2e-6, 4 * math.sqrt(self._p[0, 0, 0] + observation.timing_sigma_s**2)),
                ) or abs(cfo_error) > 4 * math.sqrt(self._p[1, 0, 0] + observation.cfo_sigma_hz**2):
                    continue
            eligible.append(observation)
        eligible.sort(key=lambda o: -o.score)
        ambiguous = len(eligible) > 1 and eligible[0].score < 1.2 * eligible[1].score
        if not eligible or ambiguous:
            self._misses += 1
            lost = expired or self._misses >= self.maximum_misses
            if lost:
                self._x = self._p = None
                self._accepted = 0
            reason = (
                "ambiguous timing modes" if ambiguous else "no observation inside prediction gate"
            )
            return self._estimate(
                "lost" if lost else ("coasting" if self._x is not None else "acquiring"), reason
            )
        selected = eligible[0]
        measurements = (selected.frame_phase_s, selected.cfo_hz)
        variances = (selected.timing_sigma_s**2, selected.cfo_sigma_hz**2)
        if self._x is None:
            self._x = np.array([[measurements[0], 0.0], [measurements[1], 0.0]])
            self._p = np.array([np.diag([variances[0], 1e-10]), np.diag([variances[1], 1e8])])
            self._accepted = 0
        else:
            assert self._p is not None
            for i in range(2):
                residual = (
                    circular_residual(measurements[i], self._x[i, 0])
                    if i == 0
                    else measurements[i] - self._x[i, 0]
                )
                gain = self._p[i, :, 0] / (self._p[i, 0, 0] + variances[i])
                self._x[i] += gain * residual
                transform = np.eye(2) - np.outer(gain, [1.0, 0.0])
                self._p[i] = (
                    transform @ self._p[i] @ transform.T + np.outer(gain, gain) * variances[i]
                )
        self._accepted += 1
        self._misses = 0
        self._last_accept = time_s
        return self._estimate(
            "tracking" if self._accepted >= self.minimum_updates else "acquiring",
            "accepted PSS observation",
        )

    def _estimate(self, state: str, reason: str) -> PssTrackEstimate:
        assert self._time is not None
        if self._x is None:
            return PssTrackEstimate(
                state, reason, self._time, None, None, None, None, None, None, self._accepted
            )
        assert self._p is not None
        return PssTrackEstimate(
            state,
            reason,
            self._time,
            float(self._x[0, 0] % PERIOD_S),
            float(self._x[0, 1]),
            math.sqrt(self._p[0, 0, 0]),
            float(self._x[1, 0]),
            float(self._x[1, 1]),
            math.sqrt(self._p[1, 0, 0]),
            self._accepted,
        )
