"""Pure known-pilot CFO refinements with the original acquisition held fixed."""

from functools import lru_cache

import numpy as np

from leo.analysis.starlink.fast_scan_fractional import fractional_take
from leo.analysis.starlink.templates import qin_edge_pilot_frame


@lru_cache(maxsize=4)
def templates(edge):
    return tuple(qin_edge_pilot_frame(2_500_000, edge, symbol_roll=roll) for roll in (0, 17))


def symbol_correlations(iq, integer_epoch, fraction, cfo, edge):
    """At 2.5 MS/s exactly eleven samples cover each 4.4-us symbol."""
    values = np.asarray(iq, dtype=np.complex128)
    relative = np.arange(2, 302)[:, None] * 11 + np.arange(11)
    periods = np.rint(np.arange(16) * 2_500_000 / 750).astype(int)
    starts = integer_epoch + periods
    valid = starts[:, None] + fraction + relative[:, -1] < len(values) - 8
    valid &= starts[:, None] + fraction + relative[:, 0] >= 8
    active = np.any(valid, axis=1)
    starts, valid = starts[active], valid[active]
    absolute = starts[:, None, None] + relative[None, :, :] + fraction
    received = np.zeros_like(absolute, dtype=np.complex128)
    received[valid] = fractional_take(values, absolute[valid])
    corrected = received * np.exp(-2j * np.pi * cfo * absolute / 2_500_000)
    exact, control = [
        np.sum(corrected * np.conj(t[relative])[None, :, :], axis=2) for t in templates(edge)
    ]
    return exact, control, valid, starts


def maximize(correlations, *, size=16384, limit=1000):
    spectrum = abs(np.fft.fft(correlations, n=size, axis=1)) ** 2
    grid = np.fft.fftfreq(size, 4.4e-6)
    keep = np.flatnonzero(abs(grid) <= limit)
    ceiling = np.sum(abs(correlations), axis=1) ** 2
    summed = np.sum(spectrum, axis=0)
    index = keep[np.argmax(summed[keep])]
    individual = keep[np.argmax(spectrum[:, keep], axis=1)]
    return dict(
        residual_cfo_hz=float(grid[index]),
        score=float(summed[index] / max(np.sum(ceiling), 1e-20)),
        individual_cfo_hz=grid[individual],
        individual_score=spectrum[np.arange(len(correlations)), individual]
        / np.maximum(ceiling, 1e-20),
    )


def evaluate(iq, integer_epoch, fraction, cfo, edge, *, size=16384, limit=1000):
    exact, control, valid, starts = symbol_correlations(iq, integer_epoch, fraction, cfo, edge)
    result = {}
    for count in (64, 300):
        mask = np.all(valid[:, :count], axis=1)
        a, b = [maximize(c[mask, :count], size=size, limit=limit) for c in (exact, control)]
        entry = dict(
            residual_cfo_hz=a["residual_cfo_hz"],
            exact_score=a["score"],
            control_score=b["score"],
            margin=a["score"] - b["score"],
            frames=int(mask.sum()),
            frequency_grid_spacing_hz=1 / (4.4e-6 * size),
        )
        entry["accepted"] = bool(entry["margin"] >= 0.02 and abs(entry["residual_cfo_hz"]) <= 750)
        result[f"glrt{count}"] = entry
        if count != 300:
            continue
        times = (starts[mask] + fraction + (2 + 150) * 11) / 2_500_000 - 0.010
        frequencies = a["individual_cfo_hz"]
        margins = a["individual_score"] - b["individual_score"]
        good = (margins >= 0.02) & (abs(frequencies) <= 750)
        line = dict(
            accepted=False,
            valid_frames=int(good.sum()),
            frame_time_from_midpoint_s=times,
            frame_frequencies_hz=frequencies,
            frame_margins=margins,
        )
        if good.sum() >= 6 and np.ptp(times[good]) >= 0.007:
            x = np.column_stack((np.ones(good.sum()), times[good]))
            y = frequencies[good]
            weights = margins[good] ** 2
            weights = np.minimum(weights, 4 * np.median(weights))
            for _ in range(8):
                coefficient = np.linalg.lstsq(
                    x * np.sqrt(weights[:, None]), y * np.sqrt(weights), rcond=None
                )[0]
                residual = y - x @ coefficient
                scale = max(20.0, 1.4826 * np.median(abs(residual - np.median(residual))))
                weights = np.minimum(margins[good] ** 2, 4 * np.median(margins[good] ** 2))
                weights *= np.minimum(1, 2.5 * scale / np.maximum(abs(residual), 1e-9))
            line.update(
                residual_cfo_hz=float(coefficient[0]),
                rate_hz_s=float(coefficient[1]),
                frame_line_rms_hz=float(np.sqrt(np.mean(residual**2))),
                accepted=bool(abs(coefficient[0]) <= 750 and abs(coefficient[1]) <= 100000),
            )
        result["midpoint300"] = line
    return result
