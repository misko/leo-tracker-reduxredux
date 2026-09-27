"""Causal known-channel state and replay decisions; independent of native DSP.

The reference detector is deliberately absent from this API. Only observations
produced by this strategy update its state. No phase coherence through a retune
is assumed: a pilot timing lattice and CFO are predicted independently.
"""
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Key:
    session: str
    receiver: int
    channel: int
    edge: str
    rate_hz: int


@dataclass(frozen=True)
class Observation:
    window: int
    epoch_samples: float
    cfo_hz: float
    exact: float
    control: float
    supported: bool = True
    timing_kind: str = 'fitted'
    scoring_cfo_hz: float | None = None

    def __post_init__(self):
        if not 0 <= self.window < 6:
            raise ValueError('observation must belong to a recorded 20-ms window')
        if not all(math.isfinite(v) for v in
                   (self.epoch_samples, self.cfo_hz, self.exact, self.control)):
            raise ValueError('nonfinite observation')
        if self.scoring_cfo_hz is not None and not math.isfinite(self.scoring_cfo_hz):
            raise ValueError('nonfinite scoring CFO')

    @property
    def margin(self):
        return self.exact - self.control

    @property
    def positive(self):
        return self.supported and self.margin > .025


@dataclass(frozen=True)
class Policy:
    max_age_seconds: float = 2.0
    discovery_interval: int = 32
    maximum_cfo_innovation_hz: float = 8000.0
    maximum_cfo_rate_hz_per_s: float = 5000.0
    maximum_timing_innovation_seconds: float = 4e-6
    use_cfo_rate: bool = True
    maximum_clock_error_ppm: float = 50.0
    learning_cfo_slack_hz: float = 2000.0

    def __post_init__(self):
        values = (self.max_age_seconds, self.maximum_cfo_innovation_hz,
                  self.maximum_cfo_rate_hz_per_s, self.maximum_timing_innovation_seconds,
                  self.maximum_clock_error_ppm, self.learning_cfo_slack_hz)
        if (not all(math.isfinite(v) and v >= 0 for v in values)
                or self.max_age_seconds <= 0 or self.discovery_interval < 1):
            raise ValueError('invalid cache expiry/discovery policy')


@dataclass
class State:
    anchor_counter: int
    anchor_fraction: float
    last_visit_start: int
    last_visit_index: int
    cfo_hz: float
    cfo_rate_hz_per_s: float = 0.0
    accepted_since_discovery: int = 0
    preferred_window: int = 0
    timing_rate_samples_per_s: float = 0.0
    fit_anchor_counter: int | None = None
    fit_anchor_fraction: float = 0.0
    scoring_cfo_hz: float | None = None


@dataclass(frozen=True)
class Prediction:
    window: int
    epoch_samples: float
    cfo_hz: float
    age_seconds: float
    scoring_cfo_hz: float | None = None


def circular_samples(delta, rate):
    period = rate / 750
    return (delta + period / 2) % period - period / 2


class Tracker:
    def __init__(self, policy=None):
        self.policy = policy or Policy()
        self.states = {}
        self.last_inputs = {}

    def begin(self, key, start_counter, visit_index):
        """Register each visit once, rejecting replay/lookahead/counter resets."""
        previous = self.last_inputs.get(key)
        if previous is not None and (start_counter <= previous[0] or visit_index <= previous[1]):
            raise ValueError('visits must advance in source time and visit index')
        self.last_inputs[key] = (start_counter, visit_index)
        state = self.states.get(key)
        if state is None:
            return None, 'cold'
        age = (start_counter - state.last_visit_start) / key.rate_hz
        if age > self.policy.max_age_seconds:
            return None, 'expired'
        if state.accepted_since_discovery >= self.policy.discovery_interval - 1:
            return None, 'periodic_discovery'
        window = state.preferred_window
        window_start = start_counter + window * (key.rate_hz // 50)
        # Integer modulo first preserves sub-sample precision at huge counters
        # and the noninteger rate/750 frame period.
        epoch = ((state.anchor_counter - window_start) * 750 % key.rate_hz) / 750
        epoch = (epoch + state.anchor_fraction
                 + state.timing_rate_samples_per_s * age) % (key.rate_hz / 750)
        cfo_rate = state.cfo_rate_hz_per_s if self.policy.use_cfo_rate else 0.0
        predicted_cfo = state.cfo_hz + cfo_rate * age
        scoring_cfo = (state.cfo_hz if state.scoring_cfo_hz is None
                       else state.scoring_cfo_hz) + cfo_rate * age
        if abs(scoring_cfo) > 400000:
            return None, 'cfo_outside_supported_band'
        return Prediction(window, epoch, predicted_cfo, age, scoring_cfo), 'predicted'

    def accepts(self, key, prediction, observation):
        if not observation.positive or prediction.window != observation.window:
            return False
        timing_error = abs(circular_samples(
            observation.epoch_samples - prediction.epoch_samples, key.rate_hz)) / key.rate_hz
        return (timing_error <= self.policy.maximum_timing_innovation_seconds
                and abs(observation.cfo_hz - prediction.cfo_hz)
                <= self.policy.maximum_cfo_innovation_hz)

    def update(self, key, start_counter, visit_index, observation, *, discovery):
        if self.last_inputs.get(key) != (start_counter, visit_index):
            raise ValueError('update must belong to the current registered visit')
        if not observation.positive:
            return False
        previous = self.states.get(key)
        if previous is not None and previous.last_visit_start >= start_counter:
            raise ValueError('state may advance only once per visit')
        cfo_rate = 0.0
        timing_rate = 0.0
        count = 0
        whole = math.floor(observation.epoch_samples)
        anchor = start_counter + observation.window * (key.rate_hz // 50) + whole
        fraction = observation.epoch_samples - whole
        fit_anchor = anchor if observation.timing_kind != 'predicted_verified' else None
        fit_fraction = fraction if fit_anchor is not None else 0.0
        if previous is not None:
            if observation.timing_kind == 'predicted_verified':
                # A CFO innovation cannot erase the independent timing fit.
                fit_anchor = previous.fit_anchor_counter
                fit_fraction = previous.fit_anchor_fraction
                timing_rate = previous.timing_rate_samples_per_s
            elapsed_samples = anchor - previous.anchor_counter
            elapsed_samples += fraction - previous.anchor_fraction
            dt = elapsed_samples / key.rate_hz
            residual = circular_samples(elapsed_samples, key.rate_hz)
            cfo_delta = observation.cfo_hz - previous.cfo_hz
            clock_bound = self.policy.maximum_clock_error_ppm * 1e-6 * key.rate_hz
            compatible = (0 < dt <= self.policy.max_age_seconds + .12
                          and abs(residual) <= clock_bound * dt + key.rate_hz * 2e-6
                          and abs(cfo_delta) <= self.policy.maximum_cfo_rate_hz_per_s * dt
                          + self.policy.learning_cfo_slack_hz)
            if compatible:
                measured_rate = cfo_delta / dt
                # A fitted derivative outside the bound is not a trustworthy
                # saturated estimate. Preserve the preceding causal slope.
                cfo_rate = (measured_rate if abs(measured_rate)
                            <= self.policy.maximum_cfo_rate_hz_per_s
                            else previous.cfo_rate_hz_per_s)
                # Point verification does not fit fresh timing. Keep the
                # learned drift until an independent fitted timing arrives.
                timing_rate = previous.timing_rate_samples_per_s
                if (observation.timing_kind != 'predicted_verified'
                        and previous.fit_anchor_counter is not None):
                    fit_elapsed = anchor - previous.fit_anchor_counter
                    fit_elapsed += fraction - previous.fit_anchor_fraction
                    fit_dt = fit_elapsed / key.rate_hz
                    # Never estimate from a model-generated point anchor.
                    # Bound age to prevent circular timing-rate ambiguity.
                    if 0 < fit_dt <= 5.0:
                        fit_residual = circular_samples(fit_elapsed, key.rate_hz)
                        measured_timing_rate = fit_residual / fit_dt
                        if abs(measured_timing_rate) <= clock_bound:
                            timing_rate = measured_timing_rate
            if not discovery:
                count = previous.accepted_since_discovery + 1
        self.states[key] = State(
            anchor, fraction, start_counter, visit_index,
            observation.cfo_hz, cfo_rate, count, observation.window, timing_rate,
            fit_anchor, fit_fraction, observation.scoring_cfo_hz)
        return True


def reference_match(reference, proposed, rate_hz):
    """Within-visit trajectory-compatible association, frozen before scoring.

Unlike the earlier fixed-window experiment, a tracked measurement may select
a different observed window in the same visit. The frame lattice and CFO must
still agree. This is reference association, not proof of satellite identity.
    """
    if not reference.positive or not proposed.positive:
        return False
    delta = (reference.window - proposed.window) * (rate_hz // 50)
    delta += reference.epoch_samples - proposed.epoch_samples
    return (abs(circular_samples(delta, rate_hz)) / rate_hz <= 2e-6
            and abs(reference.cfo_hz - proposed.cfo_hz) <= 8000)
