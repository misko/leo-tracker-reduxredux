"""Independent continuous-mixer OFDM check of the edge CFO convention."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from leo.analysis.starlink import pilot_methods
from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S as TG,
)
from leo.analysis.starlink.templates import (
    OFDM_SYMBOL_DURATION_S as TS,
)
from leo.analysis.starlink.templates import (
    qin_edge_pilot_indices,
    qin_edge_pilot_symbols,
)


def center(edge):
    indexes = np.asarray(qin_edge_pilot_indices(edge))
    return float(np.mean(np.where(indexes < 512, indexes, indexes - 1024)) * 234375)


def bias(edge):
    return (-center(edge) + 0.5 / TS) % (1 / TS) - 0.5 / TS


def physical_frame(sample_rate_hz, edge, *, symbol_roll=0):
    """Eq. 14–16: full carrier OFDM first, continuous band-center mixer second.

    Evaluate analytically at output sample times (ideal band isolation). The
    only shared input with the production synthesizer is the published codes.
    """
    times = np.arange(round(sample_rate_hz / 750)) / sample_rate_hz
    indexes = np.asarray(qin_edge_pilot_indices(edge))
    frequencies = np.where(indexes < 512, indexes, indexes - 1024) * 234375
    codes = qin_edge_pilot_symbols(edge, symbol_roll=symbol_roll)
    output = np.zeros(len(times), complex)
    for symbol in range(2, 302):
        selected = np.flatnonzero(np.floor(times / TS).astype(int) == symbol)
        local = times[selected] - symbol * TS
        carriers = np.exp(2j * np.pi * (local[:, None] - TG) * frequencies)
        output[selected] = (carriers @ codes[symbol - 2]) / np.sqrt(8)
    return output * np.exp(-2j * np.pi * np.mean(frequencies) * times)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = []
    for fs in (2500000, 10000000):
        for edge in ("lower", "upper"):
            signal = physical_frame(fs, edge)
            for acquired in (0.0, bias(edge)):
                score = pilot_methods.conditioned_glrt64_scores(
                    signal, fs, epoch_samples=[0], acquired_cfo_hz=[acquired], edge=edge
                )[0]
                with patch.object(pilot_methods, "qin_edge_pilot_frame", physical_frame):
                    corrected = pilot_methods.conditioned_glrt64_scores(
                        signal, fs, epoch_samples=[0], acquired_cfo_hz=[0.0], edge=edge
                    )[0]
                assert corrected.exact_score > 0.999999
                assert abs(corrected.tracking_cfo_hz) < 1
                assert abs(score.tracking_cfo_hz - bias(edge)) < 100
                results.append(
                    dict(
                        rate=fs,
                        edge=edge,
                        physical_cfo_hz=0,
                        acquired_cfo_hz=acquired,
                        predicted_bias_hz=bias(edge),
                        measured_cfo_hz=score.tracking_cfo_hz,
                        legacy_exact=score.exact_score,
                        legacy_control=score.control_score,
                        legacy_margin=score.margin,
                        physical_exact=corrected.exact_score,
                        physical_margin=corrected.margin,
                    )
                )
    args.output.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
