"""Deterministic circular line proposals; never assumes satellite identity."""

import numpy as np

PERIOD = 1 / 4.4e-6


def wrap(x):
    return (np.asarray(x) + PERIOD / 2) % PERIOD - PERIOD / 2


def propose(times, residual, count=2):
    times, residual = np.asarray(times), np.asarray(residual)
    candidates = []
    for slope in np.arange(-120, 121, dtype=float):
        phases = np.sort((residual - slope * times) % PERIOD)
        doubled = np.r_[phases, phases + PERIOD]
        ends = np.searchsorted(doubled, phases + 500, side="right")
        sizes = ends - np.arange(len(phases))
        start = int(np.argmax(sizes))
        intercept = float(wrap((doubled[start] + doubled[ends[start] - 1]) / 2))
        for _ in range(3):
            differences = wrap(residual - intercept - slope * times)
            mask = abs(differences) <= 250
            if mask.sum() < 4 or np.ptp(times[mask]) < 30:
                break
            delta = np.linalg.lstsq(
                np.column_stack([np.ones(mask.sum()), times[mask]]), differences[mask], rcond=None
            )[0]
            intercept = float(wrap(intercept + delta[0]))
            slope = float(np.clip(slope + delta[1], -120, 120))
        errors = wrap(residual - intercept - slope * times)
        mask = abs(errors) <= 250
        if mask.sum() < 4 or np.ptp(times[mask]) < 30:
            continue
        candidates.append(
            dict(
                intercept_hz=intercept,
                slope_hz_s=slope,
                support=int(mask.sum()),
                mask=mask,
                rms_hz=float(np.sqrt(np.mean(errors[mask] ** 2))),
            )
        )
    candidates.sort(key=lambda c: (-c["support"], c["rms_hz"], c["slope_hz_s"], c["intercept_hz"]))
    selected = []
    for candidate in candidates:
        if any(
            np.sum(candidate["mask"] & s["mask"]) / np.sum(candidate["mask"] | s["mask"]) >= 0.5
            for s in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) == count:
            break
    return [
        {k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in c.items()} for c in selected
    ]
