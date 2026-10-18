"""Compare known-pilot window CFOs with unchanged original GLRT measurements."""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from dsx01_pilot_clock import FrameClock, WindowClock
from probe_dsx01_pilot_clock import write


def run(output):
    started = time.monotonic()
    data = json.loads((output / "selection.json").read_text())
    arrays = np.load(output / "selected_iq.npz")
    rate = data["sample_rate_hz"]
    rows = []
    for point in data["windows"]:
        if time.monotonic() - started > 180:
            raise TimeoutError("bounded window-clock experiment exceeded 180 seconds")
        iq = arrays[f"iq_{point['number']}"]
        candidate, probe = point["winner"], point["probe"]
        epoch = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
        acquired = candidate["fractional_tracking_cfo_hz"]
        models, controls = [], []
        for frame in range(14):
            origin = epoch + frame * rate / 750
            if origin + 302 * 4.4e-6 * rate > len(iq):
                continue
            models.append(FrameClock(iq, rate, origin, acquired, probe["edge"]))
            controls.append(FrameClock(iq, rate, origin, acquired, probe["edge"], roll=17))
        shared = WindowClock(models)
        common, joint = shared.fit(symbol_clock=False), shared.fit()
        control = WindowClock(controls).fit()
        halves = [
            WindowClock(models[: len(models) // 2]).fit(),
            WindowClock(models[len(models) // 2 :]).fit(),
        ]
        individual = [m.fit(symbol_clock=False) for m in models]
        row = dict(
            number=point["number"],
            track=point["track"],
            observation_id=point["observation_id"],
            receiver=point["receiver"],
            channel=probe["channel"],
            time_s=point["context_time_s"],
            original_cfo_hz=acquired,
            common=asdict(common),
            joint=asdict(joint),
            control=asdict(control),
            halves=[asdict(h) for h in halves],
            individual=[asdict(f) for f in individual],
            frame_frequency_mad_hz=float(
                1.4826
                * np.median(
                    abs(
                        np.array([f.residual_cfo_hz for f in individual])
                        - np.median([f.residual_cfo_hz for f in individual])
                    )
                )
            ),
            half_cfo_difference_hz=abs(halves[0].residual_cfo_hz - halves[1].residual_cfo_hz),
            half_ppm_difference=abs(halves[0].symbol_clock_ppm - halves[1].symbol_clock_ppm),
        )
        rows.append(row)
        print(
            json.dumps(
                {k: row[k] for k in ["number", "half_cfo_difference_hz", "half_ppm_difference"]}
            ),
            flush=True,
        )
        write(output / "window_progress.json", rows)
    write(
        output / "window_results.json",
        dict(
            rows=rows,
            elapsed_seconds=time.monotonic() - started,
            independent_frame_channels=True,
            shared_CFO_over_at_most_20ms=True,
            no_GPS_or_satellite_labels=True,
            frame_period_is_nominal_not_clock_measurement=True,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
