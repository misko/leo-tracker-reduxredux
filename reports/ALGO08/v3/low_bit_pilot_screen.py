"""Count direct low-bit blind pilot work and measure packed representation sensitivity."""

import argparse
import csv
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path

import numpy as np


PINS = {
    "lower": "1b98937cbd87fd5f27b82e4d535512ca5ee12b33a64a6bae90e07ec041368adb",
    "upper": "eef7b89526adb80fc64cd0be61f35b7cc5edceb3eb293d72066378e751b4467c",
}
ADC, POINTS, PERIOD, TICKS = 10_000_000, 200_000, 13_333, 40_000
TAPS, SCOUTS_PER_LANE, OPTIMISTIC_VECTOR_S = 704, 148 / 96, 24e9
SEED = 8904
STRENGTHS = (.05, .10, .20, .40)


def bank_count(epochs, carrier_cells, frames, *, signed_bits):
    cells = epochs * carrier_cells
    packs = math.ceil(TAPS / 256)
    popcounts_per_scout = cells * frames * packs * 4 * signed_bits**2
    vnni_per_scout = cells * frames * math.ceil(TAPS / 16) * 2
    return dict(epochs=epochs, carrier_cells=carrier_cells, frames=frames, cells_per_scout=cells,
                hypothetical_popcounts_per_scout=popcounts_per_scout,
                optimistic_popcount_ms_per_lane=1e3 * popcounts_per_scout * SCOUTS_PER_LANE / OPTIMISTIC_VECTOR_S,
                byte_expanded_vnni_dot_ops_per_scout=vnni_per_scout,
                optimistic_vnni_ms_per_lane=1e3 * vnni_per_scout * SCOUTS_PER_LANE / OPTIMISTIC_VECTOR_S,
                bitpacked_template_bytes_per_sweep=carrier_cells * math.ceil(TAPS * 2 * signed_bits / 8),
                optional_float32_score_grid_bytes_per_sweep=cells * 4,
                optional_float32_score_grid_bytes_per_lane=cells * 4 * SCOUTS_PER_LANE,
                low_rate_packed_lane_bytes=POINTS // 4 * 2 * signed_bits // 8,
                native_rate_packed_lane_bytes=POINTS * 2 * signed_bits // 8)


def geometry_counts():
    fine_grid = (round((ADC / 4) / 750), 2 * math.floor(800_000 / (ADC / 4 / 4096)) + 1)
    coarse_grid = (math.ceil(PERIOD / 8), math.ceil(1_600_000 / 4500) + 1)
    return {
        f"{name}_frames{frames}_bits{bits}": bank_count(*grid, frames, signed_bits=bits)
        for name, grid in (("frozen", fine_grid), ("coarse", coarse_grid))
        for frames in (1, 14) for bits in (1, 2)
    }


def whole_budgets(acquisition, warm):
    lanes = acquisition["ordered_probes"]
    outside = acquisition["outside_detector_cpu_s"]
    cold = acquisition["in_process_to_solver_cpu_s"]
    callback = sum(g["cpu_s"] for g in acquisition["detector_groups"].values())
    warm_elapsed = float(warm["launch_to_detections_s"])
    warm_target = (warm_elapsed - float(warm["terminal_to_exit_s"])) / 2
    warm_outside = warm_elapsed - callback
    return dict(
        lanes=lanes, cold_cpu_callback_budget_s=cold / 2 - outside,
        cold_cpu_callback_budget_ms_per_lane=1000 * (cold / 2 - outside) / lanes,
        measured_cold_outside_elapsed_s=acquisition["outside_detector_wall_s"],
        measured_cold_half_acquisition_elapsed_s=acquisition["in_process_to_solver_wall_s"] / 2,
        projected_warm_outside_elapsed_s=warm_outside, projected_warm_acquisition_budget_s=warm_target,
        projected_warm_callback_budget_s=warm_target - warm_outside,
        projected_warm_callback_budget_ms_per_lane=1000 * (warm_target - warm_outside) / lanes,
    )


def quantize(values, bits, scale):
    polarity = np.where(values < 0., -1, 1)
    if bits == 1:
        return polarity
    if bits == 2:
        return polarity * (1 + 2 * (np.abs(values) >= scale))
    raise ValueError("only one or two bits per component")


def rms(values):
    return float(np.sqrt(np.mean(np.abs(values)**2)))


def components(iq):
    return np.stack((iq.real, iq.imag), axis=-1)


def shape_correlation(a, b):
    x, y = a.ravel(), b.ravel()
    denom = float(np.dot(x, x) * np.dot(y, y))
    return float(np.dot(x, y)**2 / denom) if denom else 0.


def sensitivity(before, after):
    scale = rms(before)
    change = after - before
    return {
        str(bits): dict(changed_component_fraction=float(np.mean(left != right)),
                        squared_change_projection=shape_correlation(right - left, change))
        for bits in (1, 2)
        for left, right in ((quantize(before, bits, scale), quantize(after, bits, scale)),)
    }


def quantization_efficiency(bits):
    # Q1(X) = sign(X); Q2(X) = sign(X) (1 + 2 1{|X| >= 1}).
    phi = lambda x: math.exp(-x * x / 2) / math.sqrt(2 * math.pi)
    numerator = 2 * phi(0)
    denominator = 1.
    if bits == 2:
        numerator += 4 * phi(1)
        denominator += 8 * math.erfc(1 / math.sqrt(2))
    efficiency = numerator**2 / denominator
    return dict(one_side_efficiency=efficiency, two_side_efficiency=efficiency**2,
                one_side_loss_db=-10 * math.log10(efficiency),
                two_side_loss_db=-20 * math.log10(efficiency))


def carrier_wave(asset, phase, hz, *, rolled):
    sample = np.arange(POINTS)
    tick = (3 * sample - phase) % TICKS
    if rolled:
        native = asset[2 * PERIOD:4 * PERIOD].view(np.complex64)
        i, f = (tick // 3) % PERIOD, (tick % 3) / 3
        pulse = native[i] * (1 - f) + native[(i + 1) % PERIOD] * f
    else:
        native = asset[4 * PERIOD + 81:].view(np.complex64)
        pulse = native[tick]
    mixer = np.exp(2j * np.pi * hz / ADC * sample)
    return pulse * mixer / rms(pulse)


def adc(values):
    pair = np.clip(np.rint(components(values)), -32768, 32767)
    return pair[:, 0] + 1j * pair[:, 1]


def screening_inputs(assets):
    rng = np.random.default_rng(SEED)
    cases = []
    for edge, pin in PINS.items():
        blob = (assets / f"{edge}.f32").read_bytes()
        if sha256(blob).hexdigest() != pin:
            raise ValueError(f"unexpected {edge} pilot asset")
        asset = np.frombuffer(blob, dtype="<f4")
        fir = asset[4 * PERIOD:4 * PERIOD + 81]
        for orientation in (-1, 1):
            primary = 4096 * carrier_wave(asset, 3071, 275_000 * orientation, rolled=False)
            noise = 1250 * (rng.normal(size=POINTS) + 1j * rng.normal(size=POINTS))
            before = adc(primary + noise)
            # Grant exact subtraction of the analogue primary, followed by the signed ADC quantizer.
            baseline_residual = adc(before - primary)
            before_q = components(np.convolve(before, fir, mode="same")[::4])
            residual_q = components(np.convolve(baseline_residual, fir, mode="same")[::4])
            for rolled in (False, True):
                weak = 4096 * carrier_wave(asset, 7023, -410_000 * orientation, rolled=rolled)
                weak_component = components(weak)
                class_center = rng.choice((-3., -1., 1., 3.), size=weak_component.shape)
                shift = .3 * weak_component / np.max(np.abs(weak_component))
                raw_witness = class_center + shift
                witness = {str(bits): bool(np.array_equal(
                    quantize(class_center, bits, rms(class_center)),
                    quantize(raw_witness, bits, rms(raw_witness)),
                )) for bits in (1, 2)}
                for strength in STRENGTHS:
                    after = adc(primary + noise + strength * weak)
                    residual = adc(after - primary)
                    after_q = components(np.convolve(after, fir, mode="same")[::4])
                    after_res = components(np.convolve(residual, fir, mode="same")[::4])
                    cases.append(dict(
                        edge=edge, primary_sign=orientation, companion="rolled" if rolled else "exact",
                        weak_rms_ratio=strength,
                        native_changed_component_fraction=float(np.mean(components(before) != components(after))),
                        original_adc_delta_rms=rms(components(after - before)),
                        quarter_rate_delta_rms=rms(after_q - before_q),
                        raw=sensitivity(before_q, after_q),
                        ideal_signed_residual=sensitivity(residual_q, after_res),
                        collision=dict(same_packed_codes=witness, nonzero_original_delta_rms=rms(shift)),
                    ))
    return cases


def downstream_scales(receipt):
    dense = receipt["groups"]["dense"]
    checks = dense["checks"]
    strict = checks["strict_decode"]
    guarded = checks["strict_fixed_guard"]
    return dict(
        exact_oracle_ms_per_dense_lane=strict["cpu_ms"]["mean"],
        guarded_fixed_oracle_ms_per_dense_lane=guarded["cpu_ms"]["mean"] * guarded["counts"]["lanes"] / dense["lanes"],
        guarded_fixed_oracle_with_false_slots_ms_per_dense_lane=checks["oracle_fixed_guard_2"]["cpu_ms"]["mean"],
        pure_decoy_empty_lane_ms={
            str(size): checks[f"negatives_fixed_guard_{size}"]["negative_cpu_ms"]["mean"]
            for size in (1, 2, 4)
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("acquisition", "warm_clocks", "assets", "directed"):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    acquisition = args.acquisition.read_bytes()
    receipt = args.directed.read_bytes()
    with args.warm_clocks.open() as source:
        warm = next(row for row in csv.DictReader(source) if row["recording"] == "DS30-0008")
    result = dict(
        budget=whole_budgets(json.loads(acquisition), warm),
        acquisition_sha256=sha256(acquisition).hexdigest(),
        asset_sha256=PINS,
        synthetic_seed=SEED,
        standalone_directed_receipt_sha256=sha256(receipt).hexdigest(),
        vector_rate_counterfactual_s=OPTIMISTIC_VECTOR_S,
        dense_scouts_per_lane=SCOUTS_PER_LANE,
        bank=geometry_counts(),
        downstream=downstream_scales(json.loads(gzip.decompress(receipt))),
        gaussian_small_correlation={str(bits): quantization_efficiency(bits) for bits in (1, 2)},
        synthetic=screening_inputs(args.assets),
    )
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
