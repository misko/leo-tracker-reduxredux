import csv
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter, maximum_filter1d
from scipy.optimize import linear_sum_assignment
from scipy.signal import find_peaks


DIRECTORY = Path(__file__).parent
BIN_HZ = 1_000_000 / 1_024
TONE_STEP = 45
N_ROWS = 3_600
CENTER = 512
TOOTH_INDICES = np.arange(-4, 5) * TONE_STEP


def load_hour(hour):
    path = DIRECTORY / f"Kerberos_230311_{hour:02d}00.csv"
    with path.open() as handle:
        rows = list(csv.reader(handle))
    times = [datetime.fromisoformat(f"{row[0]}T{row[1].strip()}").replace(tzinfo=timezone.utc) for row in rows]
    if len(rows) != N_ROWS or [(t - times[0]).total_seconds() for t in times] != list(range(N_ROWS)):
        raise ValueError(f"Unexpected timestamp sequence in {path.name}")
    if any(len(row) != 1_031 or tuple(s.strip() for s in row[2:5]) != ("541780000", "542780000", "976.56") for row in rows):
        raise ValueError(f"Unexpected FFT grid in {path.name}")
    spectra = np.array([row[6:] for row in rows], dtype=np.float64)
    if not np.isfinite(spectra).all() or not np.array_equal(spectra[:, -1], spectra[:, -2]):
        raise ValueError(f"Invalid data or missing duplicated edge bin in {path.name}")
    return times[0], spectra[:, :-1]


def excess_power(spectra, baseline):
    relative = spectra - baseline
    return relative - median_filter(relative, size=(1, 17))


def candidates(excess):
    peaks = maximum_filter1d(excess, size=3, axis=1)
    centers = np.arange(CENTER - 314, CENTER + 315)
    tooth_power = peaks[:, centers[:, None] + TOOTH_INDICES]
    # Limit any particularly strong tone to reduce responses of combs displaced by one tooth.
    score = np.clip(tooth_power - 0.36, 0.0, 1.8).sum(axis=2)
    points = []
    for draw in score:
        maxima = find_peaks(draw, height=2.6, prominence=0.7, distance=5)[0]
        points.append((centers[maxima], draw[maxima]))
    return points


def trajectory(points):
    open_tracks = []
    closed_tracks = []
    for time, (frequencies, scores) in enumerate(points):
        close = [track for track in open_tracks if time - track[-1][0] > 3]
        closed_tracks.extend(close)
        open_tracks = [track for track in open_tracks if time - track[-1][0] <= 3]
        used = set()
        if open_tracks and len(frequencies):
            cost = np.full((len(open_tracks), len(frequencies)), 1e6)
            for j, track in enumerate(open_tracks):
                elapsed = time - track[-1][0]
                rates = (frequencies - track[-1][1]) / elapsed
                if len(track) < 3:
                    deviation = np.abs(rates + 1.4)
                    valid = (rates > -8.5) & (rates < 1.5)
                else:
                    previous = np.array(track[-7:])
                    slope = np.polyfit(previous[:, 0] - time, previous[:, 1], 1)[0]
                    deviation = np.abs(rates - slope)
                    valid = deviation <= 1.55 + 0.06 * elapsed
                cost[j, valid] = deviation[valid] - 0.14 * scores[valid]
            matched_tracks, matched_points = linear_sum_assignment(cost)
            for j, k in zip(matched_tracks, matched_points, strict=True):
                if cost[j, k] < 1e5:
                    open_tracks[j].append((time, frequencies[k], scores[k]))
                    used.add(k)
        open_tracks.extend([(time, int(f), float(s))] for k, (f, s) in enumerate(zip(frequencies, scores, strict=True)) if k not in used)
    return closed_tracks + open_tracks


def accept_tracks(tracks, excess):
    accepted = []
    peak_power = maximum_filter1d(excess, size=5, axis=1)
    for current in tracks:
        points = np.array(current)
        times = points[:, 0].astype(int)
        freq = points[:, 1].astype(int)
        elapsed = int(times[-1] - times[0])
        if len(times) < 13 or elapsed > len(times) * 1.22 or freq[0] - freq[-1] < 6:
            continue
        p = np.polynomial.Polynomial.fit(times, freq, 2)
        rms = float(np.sqrt(np.mean((p(times) - freq) ** 2)))
        if rms > 1.0 or not np.all((-8.3 < p.deriv()(times)) & (p.deriv()(times) < -0.05)):
            continue
        lattice = np.arange(-5, 6) * TONE_STEP
        fit_centers = np.rint(p(times)).astype(int)
        tooth_bins = fit_centers[:, None] + lattice
        valid = (tooth_bins >= 3) & (tooth_bins < 1021)
        measured = peak_power[times[:, None], tooth_bins.clip(0, 1023)]
        measured[~valid] = 0
        support = np.median(measured, axis=0)
        # A nine-tooth comb contributes evidence at both extremes, and does not explain shifted aliases.
        if min(support[1], support[-2]) < 0.42 or (support[1:-1] > 0.49).sum() < 6:
            continue
        if max(support[0], support[-1]) > min(support[1], support[-2]) * 0.88:
            continue
        if np.median(points[:, 2]) < 4.0:
            continue
        accepted.append((points, p, rms, support))
    accepted.sort(key=lambda obj: (-len(obj[0]), obj[2]))
    distinct = []
    for obj in accepted:
        points, fit, _, _ = obj
        redundant = False
        for kept, kept_fit, _, _ in distinct:
            left = max(points[0, 0], kept[0, 0])
            right = min(points[-1, 0], kept[-1, 0])
            if right - left < -4:
                continue
            midpoint = (left + right) / 2
            difference = fit(midpoint) - kept_fit(midpoint)
            if abs(difference - np.rint(difference / TONE_STEP) * TONE_STEP) <= 2.5 and abs(fit.deriv()(midpoint) - kept_fit.deriv()(midpoint)) < 0.6:
                redundant = True
                break
        if not redundant:
            distinct.append(obj)
    return sorted(distinct, key=lambda obj: obj[0][0, 0])


if __name__ == "__main__":
    import sys

    stamp, preflight = load_hour(0)
    baseline = np.median(preflight, axis=0)
    for hour in map(int, sys.argv[1:]):
        stamp, powers = load_hour(hour) if hour else (stamp, preflight)
        excess = excess_power(powers, baseline)
        found = trajectory(candidates(excess))
        selected = accept_tracks(found, excess)
        print(hour, "candidates", len(found), "accepted", len(selected), "halves", sum(obj[0][-1, 0] < 1800 for obj in selected), sum(obj[0][0, 0] >= 1800 for obj in selected))
        serialized = []
        for points, p, rms, support in selected:
            print(f"{points[0, 0]:5.0f} {points[-1, 0]:5.0f} n={len(points):3d}  slope={p.deriv()(points[:,0].mean()):5.2f}  score={np.median(points[:,2]):5.2f} rms={rms:5.2f}  teeth={' '.join(f'{s:.1f}' for s in support)}")
            serialized.append({"times": points[:, 0].astype(int).tolist(), "values": ((points[:, 1] - CENTER) * BIN_HZ).tolist(), "rf_hz": 11325000000., "receiver": 1, "channel": 2})
        (DIRECTORY / f"tracks-{hour:02d}.json").write_text(json.dumps(serialized))
