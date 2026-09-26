"""Physical-band spectral replay with disjoint FIR support and shared splits."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from run_spectral import COMMON, HB, ROOT, seeds

RATE = 10_000_000
WINDOW = 32_768
GUARD = 128
WIDTHS = (500_000, 1_000_000, 2_000_000, 4_000_000, 8_000_000)


def schedule(visit: int) -> tuple[np.ndarray, dict[str, tuple[np.ndarray, np.ndarray]]]:
    stride = WINDOW + 2 * GUARD
    offset = (200_000 - 6 * stride) // 2
    starts = np.array(
        [group * 200_000 + offset + i * stride for group in range(6) for i in range(6)]
    )
    rng = np.random.default_rng(
        int.from_bytes(hashlib.sha256(f"20260926:{visit}:spectral-v4".encode()).digest()[:8])
    )
    train, held = [], []
    for group in range(6):
        order = rng.permutation(np.arange(group * 6, group * 6 + 6))
        train.extend(order[:3])
        held.extend(order[3:])
    return starts, {
        "random": (np.sort(train), np.sort(held)),
        "forward": (np.arange(18), np.arange(18, 36)),
    }


def assert_disjoint(starts: np.ndarray, train: np.ndarray, held: np.ndarray) -> None:
    for a in starts[train]:
        for b in starts[held]:
            if max(a - GUARD, b - GUARD) < min(a + WINDOW + GUARD, b + WINDOW + GUARD):
                raise ValueError("training and held raw FIR supports overlap")


def spectral(values, rate, starts, train, frequency, drift, centers):
    window = round(WINDOW * rate / RATE)
    taper = np.hanning(window)
    axis = np.fft.fftfreq(window, 1 / rate)
    left, right = [], []
    for start in starts:
        t = np.arange(start, start + window) / rate
        left.append(np.fft.fft(values[start : start + window, 0] * taper))
        rotated = values[start : start + window, 1] * np.exp(
            -2j * np.pi * HB.correction_cycles(t, frequency, drift)
        )
        right.append(np.fft.fft(rotated * taper))
    left, right = np.asarray(left), np.asarray(right)
    # These transforms contain only declared training blocks. The spectral mask
    # is frozen before any held coefficients are examined.
    a = np.sqrt(np.mean(abs(left[train]) ** 2, axis=0))
    b = np.sqrt(np.mean(abs(right[train]) ** 2, axis=0))
    threshold = 10 ** (HB.WEAK_BIN_DB / 20)
    keep = (a >= threshold * np.max(a)) & (b >= threshold * np.max(b))
    physical = np.ones(window, dtype=bool)
    for t in (0.0, 0.12):
        relative = frequency + drift * (t - 0.06)
        # Both original native receiver passbands, after independent recentering.
        physical &= abs(axis + centers[0]) <= RATE / 2
        physical &= abs(axis + relative + centers[1]) <= RATE / 2
        physical &= abs(axis + relative) <= rate / 2
    keep &= physical
    cross = np.conj(left) * right
    result = {
        "full": np.sum(cross, axis=1),
        "common": np.sum(cross[:, keep], axis=1),
        "phase_only": np.sum(cross[:, keep] / np.maximum(abs(cross[:, keep]), 1e-30), axis=1),
    }
    for width in WIDTHS:
        if width <= rate:
            result[str(width)] = np.sum(cross[:, keep & (abs(axis) <= width / 2)], axis=1)
    return result, int(keep.sum()) * rate / window


def evaluate(values, rate, starts, partitions, centers):
    answer = {}
    for name, (train, held) in partitions.items():
        frequency, drift, _ = HB.fit_frequency_rate(values, rate, 0.0, starts[train], 100.0, 3000.0)
        phasors, coherence, _ = HB.time_phasors(values, rate, frequency, drift, starts)
        fft, bandwidth = spectral(values, rate, starts, train, frequency, drift, centers)
        parity = np.angle(fft["full"] * np.conj(phasors))
        answer[name] = {
            "fitted_residual_cfo_hz": frequency,
            "fitted_residual_rate_hz_s": drift,
            "train_r": HB.circular_r(np.angle(phasors[train])),
            "held_r": HB.circular_r(np.angle(phasors[held])),
            "held_zero_intercept_rms_deg": float(
                np.degrees(np.sqrt(np.mean(np.angle(phasors[held]) ** 2)))
            ),
            "held_median_coherence": float(np.median(coherence[held])),
            "parseval_rms_rad": float(np.sqrt(np.mean(parity**2))),
            "retained_bandwidth_hz": bandwidth,
            "fft_held_r": {key: HB.circular_r(np.angle(value[held])) for key, value in fft.items()},
            "train_indices": train.tolist(),
            "held_indices": held.tolist(),
        }
    return answer


def run(output: Path) -> None:
    selection = ROOT / "selection.json"
    index = Path(
        "/srv/bulk/leo-dev/scan-32a202-phase-replay-cache/selected-visits/cache-index.json"
    )
    source = COMMON.CachedReplayVisitSource(index, selection)
    cfo = seeds(ROOT / "acquisition/candidate-inventory.csv")
    done = (
        {json.loads(line)["visit_index"] for line in output.read_text().splitlines()}
        if output.exists()
        else set()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a") as stream:
        for item in json.loads(selection.read_text())["visits"]:
            visit = item["visit_index"]
            if visit in done:
                continue
            row = {key: item[key] for key in ("visit_index", "split", "channel", "target_index")}
            row["schema"] = "scan-guarded-spectral/v4"
            began = time.monotonic()
            if (visit, 0) not in cfo or (visit, 1) not in cfo:
                row.update(status="unsupported", reason="no_passing_sparse_dual_rx_acquisition")
            else:
                arrays = source.read_visit(visit)
                if not np.all(arrays.valid_mask):
                    raise ValueError("unexpected invalid source support")
                raw = np.column_stack((arrays.complex64(0), arrays.complex64(1)))
                centers = (cfo[visit, 0], cfo[visit, 1])
                times = np.arange(len(raw)) / RATE
                recentered = raw * np.exp(-2j * np.pi * times[:, None] * np.array(centers)[None, :])
                starts, partitions = schedule(visit)
                for train, held in partitions.values():
                    assert_disjoint(starts, train, held)
                row.update(
                    status="completed",
                    absolute_cfo_hz=centers,
                    native_starts=starts.tolist(),
                    native_window_samples=WINDOW,
                    native_filter_guard_samples=GUARD,
                    native=evaluate(recentered, RATE, starts, partitions, centers),
                    derived_2p5=evaluate(
                        HB.decimate_four(recentered), RATE // 4, starts // 4, partitions, centers
                    ),
                )
            row["runtime_seconds"] = time.monotonic() - began
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            stream.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
