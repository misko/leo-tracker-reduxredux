"""Forecast the next periodic pilot start from two earlier points on one RF track."""

from dataclasses import dataclass
from math import isfinite

from .coherent_peak_filter import FRAME_RATE_HZ, MAX_GAP_S, Peak, wrapped


@dataclass(frozen=True)
class Forecast:
    linear_samples: float
    doppler_samples: float
    first_rate_ppm: float


def counter_phase(delta, rate):
    """Take the frame remainder in integer arithmetic before introducing a fraction."""
    return ((delta * FRAME_RATE_HZ) % rate) / FRAME_RATE_HZ


def predict(first: Peak, second: Peak, target_counter: int, rate: int, rf_hz: float):
    if rate <= 0 or not isfinite(rf_hz) or rf_hz <= 0:
        raise ValueError("pilot timing requires positive sampling and RF frequencies")
    first_delta = second.counter - first.counter
    second_delta = target_counter - second.counter
    dt1, dt2 = first_delta / rate, second_delta / rate
    if not (0 < dt1 <= MAX_GAP_S and 0 < dt2 <= MAX_GAP_S and 0.5 <= dt2 / dt1 <= 2):
        return None
    period = rate / FRAME_RATE_HZ
    advance = wrapped(counter_phase(first_delta, rate) + second.epoch - first.epoch, period)
    drift = advance / dt1
    linear = second.epoch + drift * dt2 - counter_phase(second_delta, rate)
    # A constant lifted CFO branch cancels between the two prior observations.
    frequency_slope = (second.cfo_hz - first.cfo_hz) / dt1
    midpoint_separation = (dt1 + dt2) * 0.5
    correction = rate * dt2 * frequency_slope * midpoint_separation / rf_hz
    return Forecast(linear % period, (linear - correction) % period, drift * 1e6 / rate)
