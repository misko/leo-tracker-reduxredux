"""Offline linear-filter diagnostic using native reference-space projections.

This is not raw-native-IQ reconstruction, threshold calibration, or an integer
FPGA replay. Unknown components orthogonal to the native basis are omitted.
"""

import hashlib
import json
from collections import Counter
from pathlib import Path
import statistics

import numpy as np
from scipy.signal import lfilter
from tests.starlink_glrt.ddc import coefficients as fir, group_delay, stages
from tools.starlink_glrt_native_replay import coefficients
from tools.starlink_glrt_tracking_journal import review

BASE = Path(__file__).parent
BANK = Path(
    "/home/mouse9911/gits/plutosdr-fw-radio20-tracking/hdl/library/starlink_glrt/native_cubic_60000000_upper.mem"
)


def filter_signal(values, origin, rate):
    indexes = np.arange(len(values), dtype=np.int64) + origin
    stride = 1
    for fs, decimation in stages(rate):
        values = lfilter(fir(fs) / 2**17, [1.0], values)
        stride *= decimation
        take = indexes % stride == 0
        indexes = indexes[take]
        values = values[take]
    return values, indexes - group_delay(rate)


def geometry_checks(rate):
    ratio = rate // 2500000
    gd = group_delay(rate)
    assert gd % ratio == 0
    origin = 12000 * ratio
    impulse = np.zeros(8 * gd + 1, complex)
    impulse[4 * gd] = 1
    y, indexes = filter_signal(impulse, origin, rate)
    assert indexes[np.argmax(abs(y))] == origin + 4 * gd
    f = 400000.0
    x = np.exp(2j * np.pi * f * np.arange(12 * gd) / rate)
    y, indexes = filter_signal(x, origin, rate)
    center = indexes - origin
    valid = (center >= 3 * gd) & (center < 8 * gd)
    measured = y[valid] * np.exp(-2j * np.pi * f * center[valid] / rate)
    expected = 1.0
    for fs, _ in stages(rate):
        h = fir(fs) / 2**17
        expected *= np.sum(
            h * np.exp(-2j * np.pi * f * (np.arange(len(h)) - (len(h) - 1) / 2) / fs)
        )
    np.testing.assert_allclose(measured, expected, rtol=1e-10, atol=1e-12)
    return {"impulse_center_correct": True, "tone_transfer_correct": True}


def main():
    assert (
        hashlib.sha256((BASE / "direct-references.ci16").read_bytes()).hexdigest()
        == "78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2"
    )
    references = np.fromfile(BASE / "direct-references.ci16", dtype="<i2").reshape(4, 3300, 4)
    coarse = [r[:, 0].astype(float) + 1j * r[:, 1] for r in references]
    result = {
        "scope": "native_projected_component_through_frozen_ddc",
        "native_raw_iq_available": False,
        "unknown_orthogonal_component_included": False,
        "arithmetic": "floating linear filter; excludes fixed-point rounding and clipping",
        "new_rf_samples": 0,
        "runtime_change": False,
        "threshold_calibrated": False,
        "input_sha256": {},
        "rates": {},
    }
    for rate in (30000000, 60000000):
        root = BASE / f"cpu-live{rate // 1000000}-causal-lo1690-v1"
        pairs = json.loads((root / "paired-coherence-review.json").read_text())
        estimates = json.loads((root / "native-epoch-estimate-review.json").read_text())
        assert pairs["status"] == estimates["status"] == "pass"
        for name in ("paired-coherence-review.json", "native-epoch-estimate-review.json"):
            result["input_sha256"][str(root / name)] = hashlib.sha256(
                (root / name).read_bytes()
            ).hexdigest()
        native = {}
        for ep in estimates["episodes"]:
            name = "native.journal" if ep["episode"] == 0 else f"native-{ep['episode']}.journal"
            native[ep["episode"]] = review((root / name).read_bytes(), epoch=ep["epoch"], rate=rate)
            result["input_sha256"][str(root / name)] = hashlib.sha256(
                (root / name).read_bytes()
            ).hexdigest()
        raw = np.asarray(coefficients(BANK.read_bytes(), rate_hz=rate), dtype=float)
        n = len(raw)
        ref = raw[:, 0] + 1j * raw[:, 1]
        derivative = raw[:, 2] + 1j * raw[:, 3]
        basis = np.column_stack(
            (ref, -derivative, 1j * np.pi * 1000 / rate * (2 * np.arange(n) - (n - 1)) * ref)
        )
        gram = basis.conj().T @ basis
        ratio = rate // 2500000
        gd = group_delay(rate)
        checked = []
        for row in pairs["comparisons"]:
            head = native[row["native_episode"]]["heads"][row["sequence"]]
            center = [
                (n - 1) * r - 2 * p
                for r, p in zip(head.reference_sum, head.reference_prefix_integral, strict=True)
            ]
            p = np.array(
                [
                    complex(*head.reference_sum),
                    complex(*head.delay_sum),
                    -1j * np.pi * 1000 / rate * complex(*center),
                ]
            )
            projected = basis @ np.linalg.solve(gram, p)
            np.testing.assert_allclose(basis.conj().T @ projected, p, rtol=2e-12, atol=2e-5)
            origin = ((head.start - 4 * gd) // ratio) * ratio
            offset = head.start - origin
            values = np.zeros(n + 8 * gd + ratio, dtype=complex)
            step = head.phase_step if head.phase_step < 2**31 else head.phase_step - 2**32
            # Native and coarse CORDIC gains cancel in this ideal linear model.
            phase = (
                2
                * np.pi
                * ((head.phase_seed + np.arange(n, dtype=np.int64) * step) % 2**32)
                / 2**32
            )
            values[offset : offset + n] = projected * np.exp(1j * phase)
            filtered, indexes = filter_signal(values, origin, rate)
            coarse_start = head.start // ratio + row["coarse_start_carry"]
            first = (coarse_start * ratio - int(indexes[0])) // ratio
            assert indexes[first] == coarse_start * ratio
            center_indexes = indexes[first : first + 3300]
            phase = (
                2
                * np.pi
                * ((head.phase_seed + (center_indexes - head.start) * step) % 2**32)
                / 2**32
            )
            signal = filtered[first : first + 3300] * np.exp(-1j * phase)
            r = coarse[row["coarse_reference_phase"]]
            predicted = float(abs(np.vdot(r, signal)) ** 2 / (np.vdot(r, r).real * 3300))
            observed = row["coarse_matched_energy_per_sample"]
            checked.append(
                {
                    "episode": row["native_episode"],
                    "sequence": row["sequence"],
                    "frame": row["frame"],
                    "carrier_hz": step * rate / 2**32,
                    "observed_coarse_native_matched_ratio": observed
                    / row["native_matched_energy_per_sample"],
                    "predicted_coarse_native_matched_ratio": predicted
                    / row["native_matched_energy_per_sample"],
                    "observed_to_predicted_matched_ratio": observed / predicted,
                    "coarse_fixed_coherence": row["coarse_coherence"],
                    "coarse_best_timing_coherence": row["timing_search_best"][2],
                    "native_coherence": row["native_coherence"],
                }
            )
        heads = [h for ep in estimates["episodes"] for h in ep["estimates"]]
        result["rates"][str(rate)] = {
            "geometry_checks": geometry_checks(rate),
            "pairs": len(checked),
            "observed_matched_ratio_median": statistics.median(
                x["observed_coarse_native_matched_ratio"] for x in checked
            ),
            "predicted_matched_ratio_median": statistics.median(
                x["predicted_coarse_native_matched_ratio"] for x in checked
            ),
            "observed_to_predicted_median": statistics.median(
                x["observed_to_predicted_matched_ratio"] for x in checked
            ),
            "native_heads": len(heads),
            "native_coherence_supported": sum(h["coherence"] >= 0.05 for h in heads),
            "native_linearized_coherence_supported": sum(
                h["linearized_coherence"] >= 0.05 for h in heads
            ),
            "rejection_counts": dict(Counter(h["rejection"] for h in heads)),
            "native_residual_hz_min_median_max": np.quantile(
                [h["residual_hz"] for h in heads], [0, 0.5, 1]
            ).tolist(),
            "native_delay_ns_min_median_max": np.quantile(
                [h["delay_s"] * 1e9 for h in heads], [0, 0.5, 1]
            ).tolist(),
            "coarse_fixed_coherence_median": statistics.median(
                x["coarse_fixed_coherence"] for x in checked
            ),
            "coarse_best_timing_coherence_median": statistics.median(
                x["coarse_best_timing_coherence"] for x in checked
            ),
            "comparisons": checked,
        }
    result["source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["native_bank_sha256"] = hashlib.sha256(BANK.read_bytes()).hexdigest()
    from tests.starlink_glrt import ddc

    for path in [
        Path(ddc.__file__),
        BASE / "direct-references.ci16",
        *[ddc.BANK_ROOT / f"ddc_{rate}_q17.mem" for rate in (5000000, 30000000, 60000000)],
    ]:
        result["input_sha256"][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    with (BASE / "native-filter-transfer-diagnostic-v2.json").open("x") as out:
        json.dump(result, out, indent=2)
        out.write("\n")
    print(
        json.dumps(
            {
                **result,
                "rates": {
                    k: {n: v for n, v in d.items() if n != "comparisons"}
                    for k, d in result["rates"].items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
