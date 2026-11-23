"""Price fixed time arithmetic while retaining the original quadratic least-squares gate."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import sys
from time import process_time_ns

import numpy as np

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from named_roster_0402 import PINS, SETTINGS, STAGE, pinned


class PreparedNoiseScreen:
    """Keep time-only inputs to the original noise formulas for one row set."""

    def __init__(self, times):
        t = np.asarray(times, float)
        if t.ndim != 1 or len(t) < 4 or not np.isfinite(t).all() or np.ptp(t) <= 0:
            raise ValueError("finite samples and positive time span required")
        self.n = len(t)
        self.x = t - t.mean()
        self.x_norm = np.sqrt(self.x @ self.x)
        tx = self.x / max(float(np.ptp(t)) / 2, 1.0)
        self.design = np.stack([np.ones(self.n), tx, tx * tx], axis=1)
        self.sqrt_n, self.log_n = np.sqrt(self.n), np.log(self.n)
        self.noise_floor = self.n * 75.0**2
        self.splits = np.arange(4, self.n - 3)
        self.later = self.n - self.splits
        self.jump_scale = np.sqrt(1 / self.splits + 1 / self.later)

    def __call__(self, residual):
        r = np.asarray(residual, float)
        if r.ndim != 2 or r.shape[1] != self.n or not np.isfinite(r).all():
            raise ValueError("matching finite residual/time samples required")
        mean = r.mean(axis=1)
        sigma = np.maximum(np.std(r, axis=1, ddof=1, mean=mean[:, None]), 75.0)
        mean_z = np.abs(mean) * self.sqrt_n / sigma
        slope_z = np.abs(r @ self.x) / np.maximum(sigma * self.x_norm, 1e-12)
        fitted = (self.design @ np.linalg.lstsq(self.design, r.T, rcond=None)[0]).T
        rss0 = np.maximum(np.sum(r * r, axis=1), self.noise_floor)
        rss1 = np.maximum(np.sum((r - fitted) ** 2, axis=1), self.noise_floor)
        bic = self.n * np.log(rss0 / rss1) - 3 * self.log_n
        if len(self.splits):
            sums = np.cumsum(r, axis=1)[:, self.splits - 1]
            jump = sums / self.splits - (r.sum(axis=1)[:, None] - sums) / self.later
            step_z = np.max(np.abs(jump) / (sigma[:, None] * self.jump_scale), axis=1)
        else:
            step_z = np.zeros(len(r))
        centered = r - mean[:, None]
        acf = np.sum(centered[:, :-1] * centered[:, 1:], axis=1) / np.maximum(
            np.sum(centered * centered, axis=1), 1e-12
        )
        passed = (mean_z <= 3) & (slope_z <= 3) & (bic <= 10) & (step_z <= 4)
        passed &= np.abs(acf) <= 4 / self.sqrt_n
        return dict(noise_screen_pass=passed, mean_z=mean_z, slope_z=slope_z,
                    quadratic_bic_gain=bic, maximum_step_z=step_z, lag1_acf=acf)


def parity(actual, expected):
    if actual.keys() != expected.keys() or any(actual[key].tobytes() != expected[key].tobytes() for key in expected):
        raise ValueError("A prepared screen changed the original scalar bits")


def sample_tracks(prepared, selected):
    eligible = []
    for t in prepared["tracks"]:
        active = np.asarray([oid in selected for oid in t["observation_ids"]])
        if int(active.sum()) < 12:
            continue
        times, values = np.asarray(t["times"])[active], np.asarray(t["values"])[active]
        x = (times - times.mean()) / max(float(np.ptp(times)), 1.0)
        design = np.stack((np.ones(len(x)), x, x * x), axis=1)
        residual = values - design @ np.linalg.lstsq(design, values, rcond=None)[0]
        eligible.append((len(times), t["key"], times, residual[None, :]))
    eligible.sort(key=lambda item: item[:2])
    if len(eligible) < 12:
        raise ValueError("Expected at least 12 original named owned track supports")
    return [eligible[i] for i in np.linspace(0, len(eligible) - 1, 12, dtype=int)]


def run(output):
    import empty_bootstrap as boot
    from dense_geographic_trial import host

    machine = host()
    if output.absolute() != output.resolve() or not output.is_relative_to("/dev/shm"):
        raise ValueError("Expected new tmpfs output")
    boot.load_runtime()
    from aperture_trial import RELEASE, write
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

    native = pinned(STAGE / "named-detections.json", SETTINGS["native_sha"])
    stock = pinned(STAGE / "stock/joint-research-receipt.json", PINS["stock"])
    config = TrackConfig(**json.loads((RELEASE / "assets/tracks.json").read_bytes())["config"])
    tracks = prepare_tracks(native, config)
    selected = {r[0] for r in stock["selected_rows"]["c0"]}
    sample = sample_tracks(tracks, selected)
    start = process_time_ns()
    screens = [PreparedNoiseScreen(times) for _, _, times, _ in sample]
    setup_cpu_ns = process_time_ns() - start
    for screen, (_, _, times, residual) in zip(screens, sample, strict=True):
        parity(screen(residual), batch_noise_screen(residual, times))

    def ordinary():
        for _, _, times, residual in sample:
            batch_noise_screen(residual, times)

    def prepared():
        for screen, (_, _, _, residual) in zip(screens, sample, strict=True):
            screen(residual)

    repetitions = 200
    timings = {"ordinary": [], "prepared": []}
    for order in ((ordinary, prepared), (prepared, ordinary), (ordinary, prepared)):
        for operation in order:
            start = process_time_ns()
            for _ in range(repetitions):
                operation()
            timings[operation.__name__].append(process_time_ns() - start)
    write(output, dict(machine=machine, parity=True, rows=[n for n, _, _, _ in sample],
                       original_support_count=len(selected), setup_cpu_ns=setup_cpu_ns,
                       timing_cpu_ns=timings, calls_per_timing=len(sample) * repetitions,
                       median_cpu_per_call_ns={name: median(t) / (len(sample) * repetitions)
                                               for name, t in timings.items()},
                       driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                       protocol_sha256=sha256((HERE / "exact-noise-gate-0402-protocol.md").read_bytes()).hexdigest(),
                       gate_source_sha256=sha256(Path(sys.modules[batch_noise_screen.__module__].__file__).read_bytes()).hexdigest(),
                       native_sha256=SETTINGS["native_sha"], stock_sha256=PINS["stock"],
                       constrained_fit_calls=0, waveform_calls=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
