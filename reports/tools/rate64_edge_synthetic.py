"""Bounded synthetic score/offset sanity checks, not receiver qualification."""

import argparse
import json
from pathlib import Path

import numpy as np

from leo.analysis.starlink.pilot_methods import conditioned_glrt64_scores
from leo.analysis.starlink.templates import qin_edge_pilot_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = []
    for fs in (2500000, 10000000):
        for edge in ("lower", "upper"):
            reference = qin_edge_pilot_frame(fs, edge).astype(complex)
            nominal = 0.0 if fs == 2500000 else (-312500.0 if edge == "lower" else 312500.0)
            for residual in (-200000.0, 0.0, 200000.0):
                frequency = nominal + residual
                signal = reference * np.exp(2j * np.pi * frequency * np.arange(len(reference)) / fs)
                for noise_db in (None, 0.0, 10.0, 15.0, 20.0, 25.0):
                    for seed in range(128 if noise_db is not None else 1):
                        rng = np.random.default_rng(20261006 + seed)
                        # Fixed noise PSD across rates; 10 MS/s admits 4x noise power.
                        variance = (
                            0.0 if noise_db is None else (fs / 2500000) * 10 ** (noise_db / 10)
                        )
                        noise = (
                            rng.normal(size=len(signal)) + 1j * rng.normal(size=len(signal))
                        ) * np.sqrt(variance / 2)
                        sample = signal + noise
                        score = conditioned_glrt64_scores(
                            sample, fs, epoch_samples=[0], acquired_cfo_hz=[frequency], edge=edge
                        )[0]
                        item = dict(
                            fs=fs,
                            edge=edge,
                            residual=residual,
                            noise_to_pilot_db_at_2p5=noise_db,
                            seed=seed,
                            exact=score.exact_score,
                            control=score.control_score,
                            margin=score.margin,
                            tracking_error_hz=score.tracking_cfo_hz - frequency,
                        )
                        if noise_db is None:
                            wrong = conditioned_glrt64_scores(
                                sample, fs, epoch_samples=[0], acquired_cfo_hz=[residual], edge=edge
                            )[0]
                            swapped = conditioned_glrt64_scores(
                                sample,
                                fs,
                                epoch_samples=[0],
                                acquired_cfo_hz=[frequency],
                                edge="upper" if edge == "lower" else "lower",
                            )[0]
                            item.update(
                                ignored_nominal_margin=wrong.margin,
                                wrong_edge_margin=swapped.margin,
                            )
                            assert abs(score.tracking_cfo_hz - frequency) < 1.0
                            assert score.exact_score > 0.999
                        results.append(item)
    args.output.write_text(json.dumps(results, indent=2))
    print("Synthetic cases:", len(results))


if __name__ == "__main__":
    main()
