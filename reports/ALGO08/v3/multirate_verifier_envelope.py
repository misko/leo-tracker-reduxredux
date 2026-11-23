"""Estimate the four-recording ceiling for replacing waveform processing."""

import argparse
from dataclasses import asdict, dataclass
import gzip
from hashlib import sha256
import json
from math import isclose
from pathlib import Path

import numpy as np

from acquisition_throughput import gates, minimum_rate
from .mixed_aperture_receiver import PILOT_SHA
from .scout_readout_trial import check_machine


HERE = Path(__file__).resolve().parent
PINS = {
    "measurements/regional-dense-budget.json": "20ca6db13e6294d34ae732635158aef332f622127d120d6f6ca1229082e78677",
    "measurements/acquisition-throughput.json": "fc46925e68437054169e2a3008388493554baf5c92f495eb3beb9434c10e620a",
    "measurements/dense-full-short-raw.json.gz": "51521b26848532823922cc43a198b7f91d59d3f1d81e155e5862b04b53193f38",
    "measurements/full-short-cold.json.gz": "58892accfa3da056d432031d0a476ec869239963cdc5cd40cd52002c6b2553bc",
    "development/stages.json": "0bc940b1181b6fdb5f52ec1c5b768bfdbd6d2334e721fe8350cfc9ad3ca643c3",
}
NATIVE_RATE = 10_000_000
RATES = (1_250_000, 2_500_000, 5_000_000)
RESIDUALS = (-1000, 0, 1000)
SAMPLES_PER_SYMBOL = 44
SYMBOLS = 64
PERIOD = 13333


def checked(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Unexpected archived file {path}")
    return data


def projection(aperture, sample_rate, fft_size, residuals):
    freq = np.fft.fftfreq(fft_size, d=1/sample_rate)
    energy = np.abs(np.fft.fft(aperture, n=fft_size, axis=-1)) ** 2
    norm = energy.sum(axis=-1)
    if np.any(norm <= 0):
        raise ValueError("Projection needs nonzero template energy")
    result = {}
    for residual in residuals:
        result[residual] = {}
        for rate in RATES:
            in_band = np.abs(freq + residual) < rate/2
            retained = energy[..., in_band].sum(axis=-1)
            result[residual][rate] = dict(weighted=float(retained.sum()/norm.sum()),
                                          minimum=float(np.min(retained/norm)))
    return result


def pilot_power(assets):
    result = {}
    for edge, pin in PILOT_SHA.items():
        asset = np.frombuffer(checked(assets / (edge+".f32"), pin), dtype="<f4")
        if len(asset) != 133413:
            raise ValueError("Missing signed verifier pilot and rolled control")
        pilot = asset[:4*PERIOD].astype(np.float64).view(np.complex128)
        result[edge] = {}
        for shape, start in (("exact", 0), ("rolled", PERIOD)):
            base = start + 2*SAMPLES_PER_SYMBOL
            taps = pilot[base:base+SYMBOLS*SAMPLES_PER_SYMBOL]
            result[edge][shape] = dict(
                coherent=projection(taps, NATIVE_RATE, 131072, RESIDUALS),
                symbols=projection(taps.reshape(SYMBOLS, SAMPLES_PER_SYMBOL), NATIVE_RATE, 32768, RESIDUALS))
    return result


@dataclass(frozen=True)
class Observation:
    compressed_MB: float
    elapsed_s: float
    cpu_s: float
    short_native_elapsed_s: float
    all_native_elapsed_s: float

    @classmethod
    def from_ns(cls, compressed_MB, clocks, native):
        spans = native["native_wall_ns"]
        return cls(compressed_MB, clocks["wall_ns"] / 1e9, clocks["cpu_ns"] / 1e9,
                   spans["short_primary"] / 1e9, sum(spans.values()) / 1e9)


def price(rows, observation, solve_fraction, overhead, target_rate):
    s = observation
    removed = dict(observed=0, entire_short_twice_as_fast=s.short_native_elapsed_s/2,
                   entire_short_four_times_as_fast=3*s.short_native_elapsed_s/4, free_short_native=s.short_native_elapsed_s,
                   free_all_native=s.all_native_elapsed_s, free_all_acquisition_cpu=s.cpu_s)
    scenarios = {}
    for name, reduction in removed.items():
        remaining = s.elapsed_s - reduction
        if remaining < 0:
            raise ValueError("Removed time exceeds its source clock")
        rate = s.compressed_MB / remaining if remaining else float("inf")
        per_case = {}
        for row in rows:
            acquire, solve, tail = row["stages"]
            if acquire <= 0:
                raise ValueError("Frozen first four need full instrumented clocks")
            bound = row["compressed_MB"]/rate + solve_fraction*solve + tail + overhead
            per_case[row["case"]] = dict(elapsed_s=bound, ratio=bound/sum(row["stages"]))
        scenarios[name] = dict(elapsed_s_in_observation=remaining, effective_MB_s=rate if remaining else None,
                               elapsed_gates=gates(rows, rate, solve_fraction, startup_s=overhead), cases=per_case)
    allowed = s.compressed_MB / target_rate
    needed = s.elapsed_s - allowed
    return dict(observed=asdict(s), target_acquisition_s=allowed, needed_elapsed_s=needed,
                fraction_entire_short_needed=needed / s.short_native_elapsed_s,
                fraction_all_native_needed=needed / s.all_native_elapsed_s, scenarios=scenarios)


def budget():
    blobs = {}
    for name, pin in PINS.items():
        data = checked(HERE / name, pin)
        blobs[Path(name).name] = json.loads(gzip.decompress(data) if name.endswith(".gz") else data)
    qualification = blobs["regional-dense-budget.json"]
    cases = [item["case"] for item in blobs["stages.json"]["stages"]["4"]["cases"]]
    if len(set(cases)) != 4 or cases != qualification["panels"]["4"]["cases"]:
        raise ValueError("Enrolled first-four rosters differ")
    rows_by_case = {r["case"]: r for r in blobs["acquisition-throughput.json"]["rows"]}
    rows = [rows_by_case[case] for case in cases]
    fraction = qualification["solve_cpu_s"] / qualification["historical_installed_solve_cpu_s"]
    overhead = qualification["common_charge_s"]
    required = [minimum_rate(rows, fraction, index, startup_s=overhead) for index in (0, 1)]
    if any(not isclose(calculated, pinned, rel_tol=1e-12)
           for calculated, pinned in zip(required, qualification["panels"]["4"]["required_MB_s_by_gate"], strict=True)):
        raise ValueError("The published four-recording gate was not reproduced")
    full = blobs["dense-full-short-raw.json.gz"]["candidate"]["recipe"]["receiver_audit"]
    prefix = blobs["full-short-cold.json.gz"]["acquisition"]
    dense = rows_by_case["DS30-0008"]
    if full["input_manifest"] != dense["inventory_sha256"] or prefix["inventory_sha256"] != full["input_manifest"]:
        raise ValueError("Acquisition receipts use different recording authorities")
    fastest = min((arm for pair in prefix["repeats"] for arm in pair if arm["arm"] == "full-short"),
                  key=lambda arm: arm["acquire_wall_ns"])
    full_observation = Observation.from_ns(dense["compressed_MB"], full["acquire"], full["native"])
    prefix_observation = Observation.from_ns(prefix["compressed_bytes"]/1e6,
                                              dict(wall_ns=fastest["acquire_wall_ns"], cpu_ns=fastest["acquire_cpu_ns"]),
                                              fastest["native"])
    return dict(cases=cases, source_pins=PINS, numerical_fraction=fraction, once_per_recording_s=overhead,
                required_MB_s_by_gate=required, complete=price(rows, full_observation, fraction, overhead, max(required)),
                fastest_prefix=price(rows, prefix_observation, fraction, overhead, max(required)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    result = dict(machine=check_machine(), model=budget(), pilot_power=pilot_power(args.assets),
                  pilot_pins=PILOT_SHA, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  protocol_sha256=sha256((HERE / "multirate-verifier-envelope-protocol.md").read_bytes()).hexdigest())
    with args.out.open("x") as receipt:
        json.dump(result, receipt, sort_keys=True, indent=2, allow_nan=False)
        receipt.write("\n")
