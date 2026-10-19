"""Literal positive-arrival phase arithmetic from the surviving generator."""
import math
from numbers import Integral
import numpy as np

FRAME_RATE_HZ = 750


def relative_counter(valid_start_counter, session_start_counter, probe_start_ms, sample_rate_hz):
    values = [valid_start_counter, session_start_counter, probe_start_ms, sample_rate_hz]
    if any(isinstance(x, bool) or not isinstance(x, Integral) for x in values):
        raise ValueError('Exact integer device counters, milliseconds and sample rate required')
    if sample_rate_hz <= 0 or probe_start_ms < 0:
        raise ValueError('Positive sample rate and nonnegative probe offset required')
    # Never cast absolute hardware counters to float, or multiply in int64.
    return int(valid_start_counter)-int(session_start_counter)+int(probe_start_ms)*int(sample_rate_hz)//1000


def arrival_phase_samples(counter, integer_epoch_sample, fractional_offset_samples, sample_rate_hz):
    if not isinstance(counter, Integral) or not isinstance(integer_epoch_sample, Integral):
        raise ValueError('Integer relative counter and epoch required')
    if not isinstance(sample_rate_hz, Integral) or sample_rate_hz <= 0 or not math.isfinite(fractional_offset_samples):
        raise ValueError('Positive integer sample rate and finite epoch offset required')
    period = sample_rate_hz/FRAME_RATE_HZ
    return (((int(counter)*FRAME_RATE_HZ)%int(sample_rate_hz))/FRAME_RATE_HZ
        +int(integer_epoch_sample)+fractional_offset_samples)%period


def first_frame_time_s(counter, integer_epoch_sample, fractional_offset_samples, sample_rate_hz):
    return counter/sample_rate_hz+(integer_epoch_sample+fractional_offset_samples)/sample_rate_hz


def unwrap_phase_samples(phase, sample_rate_hz):
    period = sample_rate_hz/FRAME_RATE_HZ
    return np.unwrap(np.asarray(phase)*2*np.pi/period)*period/(2*np.pi)


def linear_detrend(times, values):
    """Replay the generator's existing descriptive constant/linear removal."""
    times, values = np.asarray(times), np.asarray(values)
    design = np.column_stack([np.ones(len(times)), times-times.mean()])
    return values-design@np.linalg.lstsq(design, values, rcond=None)[0]
