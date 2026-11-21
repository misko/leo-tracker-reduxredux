"""Count known individual signals in controlled mixtures on measured noise spectra."""

import argparse
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame

from ..variants import two_carrier
from .full_v5_check import _load_case, _sha
from .original_kernel_trial import decode
from .reverse_glrt_reference import CASES, REPORT, digest, packed
from .reverse_glrt_report import read, write_csv
from .reverse_quarter_trial import null_samples
from .two_carrier_roster import OUT, WORK
from .two_carrier_trial import MODES, Trial


def unit_wave(template, ticks, hz, seed, short):
    rng = np.random.default_rng(seed)
    n = np.arange(200000)
    frame, phase = np.divmod(3 * n - ticks, 40000)
    active = (phase >= 264) & (phase < 132 * (66 if short else 302))
    gain = rng.uniform(0.75, 1.25, 18) * np.exp(2j * np.pi * rng.random(18))
    slope = float(rng.uniform(-8000, 8000))
    t = n / 1e7 - 0.01
    wave = template[phase] * gain[frame + 1] * np.exp(2j * np.pi * (t * hz + 0.5 * t * t * slope))
    wave[~active] = 0.0
    wave /= np.sqrt(np.mean(abs(wave[active]) ** 2))
    return wave, dict(epoch=(ticks / 3) % 13333, hz=hz, slope=slope)


def mix(background, rx, waves):
    out = background.copy()
    x = out[:, rx, 0].astype(float) + 1j * out[:, rx, 1]
    rms = np.sqrt(np.mean(abs(x) ** 2))
    for wave, db in waves:
        x += wave * rms * 10 ** (db / 20)
    pair = np.rint(np.stack((x.real, x.imag), axis=1))
    clips = int(np.count_nonzero((pair < -32768) | (pair > 32767)))
    out[:, rx] = np.clip(pair, -32768, 32767).astype("<i2")
    return out, clips


def evaluate(record):
    r, binaries, cpu = record
    os.sched_setaffinity(0, {cpu})
    _, _, w = decode(_load_case(r["case"]), r["visit"])
    template = qin_edge_pilot_frame(30000000, r["edge"])
    trial = Trial(r["edge"], binaries)
    rx = r["rx"]
    rows = []
    try:
        for separated in (False, True):
            for gap in (40000, 227000):
                seed = int(digest(packed(["two-pilot-v1", r["id"], separated, gap]))[:12], 16)
                rng = np.random.default_rng(seed)
                noise = null_samples(w.samples, int(rng.integers(2**48)))
                tick = int(rng.integers(40000))
                tick2 = (tick + 12001) % 40000 if separated else tick
                sign = 1 if seed % 2 else -1
                first, one = unit_wave(template, tick, sign * 244000, seed + 1, gap == 227000)
                second, two = unit_wave(
                    template, tick2, sign * (244000 - gap), seed + 2, gap == 40000
                )
                for db in (None, -24, -18, -12):
                    waves = [(first, -15)] if db is None else [(first, -15), (second, db)]
                    iq, clipped = mix(noise, rx, waves)
                    sha = "sha256:" + digest(iq.tobytes())
                    data = trial.run(replace(w, samples=iq, iq_sha256=sha), MODES)
                    for m in MODES:
                        peaks = data[m]["lanes"][rx]["peaks"]
                        truths = [one] if db is None else [one, two]
                        hits = [any(two_carrier.same(p, t) for p in peaks) for t in truths]
                        extras = sum(not any(two_carrier.same(p, t) for t in truths) for p in peaks)
                        rows.append(
                            dict(
                                case=r["case"],
                                source_id=r["id"],
                                source_iq=w.iq_sha256,
                                iq=sha,
                                seed=seed,
                                method=m,
                                rx=rx,
                                separated=separated,
                                frequency_separation_hz=gap,
                                secondary_snr_db=db,
                                primary_hz=one["hz"],
                                primary_epoch=one["epoch"],
                                secondary_hz=two["hz"] if db is not None else None,
                                secondary_epoch=two["epoch"] if db is not None else None,
                                true_signals=len(truths),
                                returned=len(peaks),
                                signals_recovered=sum(hits),
                                primary_hit=hits[0],
                                secondary_hit=hits[1] if db is not None else None,
                                all_known=all(hits),
                                extra=extras,
                                clipped=clipped,
                            )
                        )
    finally:
        trial.close()
    return rows


def run(out, work, cpus):
    roster = read(REPORT / "roster.json")
    cases = [
        min(
            (r for r in roster if r["case"] == c),
            key=lambda r: digest(packed(["two-carrier-noise-v1", r["id"]])),
        )
        for c in CASES
    ]
    binaries = two_carrier.build(work)
    with ProcessPoolExecutor(max_workers=len(cpus)) as pool:
        sets = list(
            pool.map(evaluate, [(r, binaries, cpus[i % len(cpus)]) for i, r in enumerate(cases)])
        )
    results = [row for block in sets for row in block]
    dest = out / "injections.csv"
    write_csv(dest, results)
    (out / "injection-receipt.json").write_bytes(
        packed(
            dict(
                cases=CASES,
                inputs=len({r["iq"] for r in results}),
                source=_sha(Path(__file__)),
                protocol=_sha(out / "INJECTIONS.md"),
                table=_sha(dest),
            )
        )
        + b"\n"
    )
    print("checked", len(results), "injection receiver trials", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, default=OUT)
    p.add_argument("--work", type=Path, default=WORK)
    p.add_argument("--cpus", type=int, nargs="+", default=[10, 12, 14, 16, 18])
    a = p.parse_args()
    run(a.report, a.work, a.cpus)
