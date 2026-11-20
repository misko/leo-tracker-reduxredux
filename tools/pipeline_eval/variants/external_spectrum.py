"""Extract unlabeled Ku-band Doppler ridges from Kerberos power scans."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks

BIN_HZ = 1e6 / 1024
CENTER_HZ = 11_325_000_000
SCAN_FIELDS = ("541780000", "542780000", "976.56")
OFF_BAND_FIELDS = ("914500000", "915500000", "976.56")


@dataclass(frozen=True)
class Spectrum:
    utc: np.ndarray
    excess_db: np.ndarray


@dataclass(frozen=True)
class Ridge:
    utc: np.ndarray
    frequency_hz: np.ndarray
    power_db: float
    residual_hz: float


def read_spectrum(path: Path, first: int, duration: int, scan_fields=SCAN_FIELDS) -> Spectrum:
    times, powers = [], []
    with path.open() as incoming:
        for line in incoming:
            day, clock, low, high, step, sample_count, values = line.split(",", 6)
            stamp = datetime.fromisoformat(f"{day}T{clock.strip()}").replace(tzinfo=UTC)
            utc = int(stamp.timestamp())
            if utc >= first + duration:
                break
            if utc < first:
                continue
            if (
                tuple(field.strip() for field in (low, high, step)) != scan_fields
                or int(sample_count) <= 0
            ):
                raise ValueError("unexpected Kerberos IF grid")
            power = np.fromstring(values, sep=",", dtype=np.float64)
            if len(power) != 1025 or power[-1] != power[-2] or not np.isfinite(power).all():
                raise ValueError("invalid Kerberos powers or missing duplicated edge bin")
            times.append(utc)
            powers.append(power[:-1])
    if len(times) == 0 or np.any(np.diff(times) <= 0):
        raise ValueError("missing or unordered Kerberos UTC rows")
    excess = np.array(powers) - np.median(powers, axis=0)
    return Spectrum(np.array(times), excess - median_filter(excess, size=(1, 13)))


def extract_ridges(spectrum: Spectrum) -> tuple[Ridge, ...]:
    active, closed = [], []
    for utc, row in zip(spectrum.utc, spectrum.excess_db, strict=True):
        closed.extend(track for track in active if utc - track[-1][0] > 3)
        active = [track for track in active if utc - track[-1][0] <= 3]
        peaks = find_peaks(row, height=0.45, prominence=0.38, distance=3)[0]
        peaks = peaks[(peaks >= 8) & (peaks <= 1015)]
        if not len(peaks):
            continue
        choices = []
        for i, track in enumerate(active):
            last_utc, last_bin, _ = track[-1]
            elapsed = utc - last_utc
            rates = (peaks - last_bin) / elapsed
            if len(track) >= 4:
                old_utc, old_bin, _ = track[max(0, len(track) - 6)]
                rate = (last_bin - old_bin) / (last_utc - old_utc)
                departure = np.abs(rates - rate)
                allowed = departure <= 1.25 + 0.2 * (elapsed - 1)
            else:
                departure = abs(rates + 2.2) * 0.3
                allowed = (rates <= 0.15) & (rates >= -6.2)
            choices.extend(
                (float(departure[j] - 0.4 * row[peaks[j]]), i, j) for j in np.flatnonzero(allowed)
            )
        used_tracks, used_peaks = set(), set()
        for _, i, j in sorted(choices):
            if i not in used_tracks and j not in used_peaks:
                active[i].append((utc, peaks[j], row[peaks[j]]))
                used_tracks.add(i)
                used_peaks.add(j)
        active.extend(
            [(utc, peak, row[peak])] for j, peak in enumerate(peaks) if j not in used_peaks
        )

    accepted = []
    for track in closed + active:
        if len(track) < 18:
            continue
        utc, bins, power = np.transpose(track)
        elapsed = utc - utc[0]
        if elapsed[-1] + 1 > len(track) * 1.22 or bins[0] - bins[-1] < 12:
            continue
        fit = np.polynomial.Polynomial.fit(elapsed, bins, 2)
        residual = float(np.sqrt(np.mean((fit(elapsed) - bins) ** 2)))
        velocity = fit.deriv()(elapsed)
        if residual > 1.1 or not np.all((velocity >= -6.5) & (velocity <= -0.12)):
            continue
        central_power = float(np.median(power))
        if central_power < 0.63:
            continue
        accepted.append(
            Ridge(utc.astype(np.int64), (bins - 512) * BIN_HZ, central_power, residual * BIN_HZ)
        )

    distinct = []
    for ridge in sorted(accepted, key=lambda row: (-len(row.utc), row.residual_hz)):
        if not any(duplicates(ridge, earlier) for earlier in distinct):
            distinct.append(ridge)
    return tuple(sorted(distinct, key=lambda row: row.utc[0]))


def duplicates(a: Ridge, b: Ridge) -> bool:
    start, end = max(a.utc[0], b.utc[0]), min(a.utc[-1], b.utc[-1])
    if end - start < 8:
        return False
    grid = np.linspace(start, end, 10)
    difference = np.interp(grid, a.utc, a.frequency_hz) - np.interp(grid, b.utc, b.frequency_hz)
    center = np.median(difference)
    tone_spacing = 45 * BIN_HZ
    return (
        np.std(difference) < 1.4 * BIN_HZ
        and abs(center - round(center / tone_spacing) * tone_spacing) < 2.5 * BIN_HZ
    )
