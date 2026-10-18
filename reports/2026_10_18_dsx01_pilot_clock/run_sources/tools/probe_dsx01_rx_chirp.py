"""Independent raw cross-IQ check for RX-dependent within-window frequency rate."""

import argparse
import json
from pathlib import Path

import numpy as np
from dsx01_pilot_clock import FrameClock, differential_chirp
from probe_dsx01_pilot_clock import write

from leo.analysis.starlink.fast_scan_fractional import fractional_take


def run(output):
    data = json.loads((output / "selection.json").read_text())
    arrays = np.load(output / "selected_iq.npz")
    fs = data["sample_rate_hz"]
    windows = data["windows"]
    rows = []
    for start in (0, 2):
        a, b = windows[start : start + 2]
        if a["probe"]["valid_start_counter"] != b["probe"]["valid_start_counter"]:
            raise ValueError("paired supports differ")
        za, zb = arrays[f"iq_{a['number']}"], arrays[f"iq_{b['number']}"]
        ea = a["winner"]["integer_epoch_sample"] + a["winner"]["fractional_epoch_offset_samples"]
        eb = b["winner"]["integer_epoch_sample"] + b["winner"]["fractional_epoch_offset_samples"]
        shift = eb - ea
        # Fix the delay using saved frame peaks, never tune it with CFO or GPS.
        indices = np.arange(
            max(20, int(np.ceil(-shift)) + 20),
            min(len(za) - 20, int(np.floor(len(zb) - shift)) - 20),
        )
        first = za[indices]
        second = fractional_take(zb, indices + shift)
        result = differential_chirp(first, second, fs, ea - indices[0])
        individual = []
        for point in (a, b):
            iq = arrays[f"iq_{point['number']}"]
            candidate, probe = point["winner"], point["probe"]
            epoch = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
            fits = [
                FrameClock(
                    iq,
                    fs,
                    epoch + f * fs / 750,
                    candidate["fractional_tracking_cfo_hz"],
                    probe["edge"],
                ).fit(symbol_clock=False)
                for f in range(14)
            ]
            frequency = np.array([v.residual_cfo_hz for v in fits])
            slope = np.polyfit(np.arange(14) / 750, frequency, 1)
            individual.append(
                dict(
                    receiver=point["receiver"],
                    line_rate_hz_s=float(slope[0]),
                    original_cfo_hz=candidate["fractional_tracking_cfo_hz"],
                    frame_fits=[v.__dict__ for v in fits],
                )
            )
        row = dict(
            time_s=a["context_time_s"],
            delay_samples=shift,
            observation_ids=[a["observation_id"], b["observation_id"]],
            template_free_cross_IQ=result,
            pilot_individual=individual,
            independent_pilot_rate_difference_hz_s=individual[0]["line_rate_hz_s"]
            - individual[1]["line_rate_hz_s"],
        )
        rows.append(row)
        print(json.dumps(row, default=str), flush=True)
    write(output / "differential_chirp.json", rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
