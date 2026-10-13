"""Independent analytic OFDM injection checks the pilot's effective Doppler RF.

This is a noiseless scoring control, not an RF mapping or measurement calibration.
"""

import argparse
import hashlib
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S,
    OFDM_SYMBOL_DURATION_S,
    SUBCARRIER_SPACING_HZ,
    qin_edge_pilot_indices,
    qin_edge_pilot_symbols,
)
from leo.analysis.wrapped_glrt_likelihood import circular
from tools.evaluate_sparse_glrt import local_output, write_json


def injection(edge, speed_m_s, *, carrier_hz=10_825_000_000.0):
    """Transmit absolute subcarriers, time dilate, then mix at the nominal pilot RF."""
    rate, epoch = 2_500_000, 64
    nominal = -115_312_500.0 if edge == "lower" else 115_312_500.0
    indices = np.asarray(qin_edge_pilot_indices(edge))
    frequencies = np.where(indices < 512, indices, indices - 1024) * SUBCARRIER_SPACING_HZ
    symbols = qin_edge_pilot_symbols(edge)
    dilation = speed_m_s / 299_792_458.0
    time = (np.arange(2000) - epoch) / rate
    transmit_time = (1 - dilation) * time
    symbol = np.floor(transmit_time / OFDM_SYMBOL_DURATION_S).astype(int)
    keep = (symbol >= 2) & (symbol < 302)
    local = transmit_time[keep] - symbol[keep] * OFDM_SYMBOL_DURATION_S
    local -= CYCLIC_PREFIX_DURATION_S
    samples = np.zeros(len(time), complex)
    samples[keep] = np.sum(
        symbols[symbol[keep] - 2] * np.exp(2j * np.pi * local[:, None] * frequencies), axis=1
    ) / np.sqrt(8)
    samples *= np.exp(2j * np.pi * (-nominal - dilation * carrier_hz) * time)
    # Coarse acquisition uses channel-carrier Doppler, rounded to 10 kHz. It
    # deliberately does not provide the pilot RF correction to the fine scorer.
    acquired = float(
        np.round((frequencies.mean() - nominal - dilation * carrier_hz) / 10000) * 10000
    )
    score = conditioned_glrt64_score(
        samples,
        rate,
        epoch_sample=epoch,
        acquired_cfo_hz=acquired,
        edge=edge,
        glrt_size=131072,
    )
    return dict(
        edge=edge,
        speed_m_s=speed_m_s,
        carrier_hz=carrier_hz,
        nominal_pilot_rf_hz=carrier_hz + nominal,
        effective_pilot_rf_hz=float(carrier_hz + frequencies.mean()),
        expected_doppler_hz=float(-dilation * (carrier_hz + frequencies.mean())),
        acquisition_cfo_hz=acquired,
        score=asdict(score),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    local_output(args.output)
    rows = []
    for edge in ("lower", "upper"):
        base = injection(edge, 0)
        for speed in (0, 3000, -3000):
            row = base if speed == 0 else injection(edge, speed)
            row["circular_change_error_hz"] = float(
                circular(
                    row["score"]["tracking_cfo_hz"]
                    - base["score"]["tracking_cfo_hz"]
                    - row["expected_doppler_hz"]
                )
            )
            rows.append(row)
    write_json(
        args.output,
        dict(
            rows=rows,
            sample_rate_hz=2500000,
            fft_size=131072,
            acquisition_rounding_hz=10000,
            scope=(
                "Noiseless single-frame absolute-subcarrier injection; "
                "no front-end or RF LO authority"
            ),
            source_digests={
                str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (
                    Path(__file__),
                    Path("src/leo/analysis/starlink/templates.py"),
                    Path("src/leo/analysis/starlink/fast_scan_scores.py"),
                )
            },
        ),
    )


if __name__ == "__main__":
    main()
