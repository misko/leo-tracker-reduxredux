"""Saved-IQ research: causal decimation and bounded temporal decision probes.

No RF, production writes, threshold tuning, or satellite truth. Native 10M C
execution is deliberately excluded until its fixed-size pilot arrays are audited.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from leo.storage.persistent_hop import PersistentHopIqStore
from tools.native_presence import ROOT, build_dwell_presence
from tools.presence_dwell import NativeDwell, unpack

SESSIONS = ("scan-hop-b80df494d948f78a", "scan-hop-b96cfdd5fb0ee91c")
SWEEPS = (40, 110, 180, 250)
RATES = (5_000_000, 2_500_000)


def taps_for(rate: int) -> np.ndarray:
    if rate not in RATES:
        raise ValueError("decision rate must be 2.5 or 5 MS/s")
    count = 129 if rate == 5_000_000 else 257
    cutoff = rate * 0.4 / 10_000_000
    positions = np.arange(count) - (count - 1) / 2
    taps = 2 * cutoff * np.sinc(2 * cutoff * positions) * np.kaiser(count, 8.6)
    return taps / taps.sum()


def decimate(iq: np.ndarray, rate: int) -> tuple[np.ndarray, dict]:
    if iq.dtype != np.dtype("int16") or iq.ndim != 2 or iq.shape[1] != 2:
        raise ValueError("one physical RX as CI16 required")
    taps = taps_for(rate)
    factor = 10_000_000 // rate
    if len(iq) % factor:
        raise ValueError("input count must divide exactly")
    start, cpu = time.perf_counter(), time.process_time()
    # Causal FIR, zero initial history after the hop. Do not shift away its
    # delay or append output requiring samples beyond the captured dwell.
    filtered = np.zeros((len(iq) // factor, 2), dtype=np.float64)
    for phase in range(factor):
        start_index = 0 if phase == 0 else factor - phase
        output_offset = int(phase != 0)
        for component in range(2):
            part = np.convolve(iq[start_index::factor, component], taps[phase::factor])
            filtered[output_offset:, component] += part[: len(filtered) - output_offset]
    rounded = np.rint(filtered)
    clipped = int(np.count_nonzero((rounded < -32768) | (rounded > 32767)))
    output = np.clip(rounded, -32768, 32767).astype("<i2")
    return output, {
        "cpu_ms": (time.process_time() - cpu) * 1000,
        "wall_ms": (time.perf_counter() - start) * 1000,
        "group_delay_native_samples": (len(taps) - 1) // 2,
        "initial_history": "zero-after-hop",
        "clipped_components": clipped,
    }


def positive(result: dict) -> bool:
    return any(
        c["fractional_complete"] and c["exact_score"] >= 0.175 and c["margin"] >= 0.025
        for c in result["candidates"][: result["candidate_count"]]
    )


def decimate_window(iq: np.ndarray, rate: int, window: int) -> tuple[np.ndarray, dict]:
    if not 0 <= window < 6 or len(iq) != 1_200_000:
        raise ValueError("one window in a complete native 10M dwell required")
    factor = 10_000_000 // rate
    start = window * 200_000
    history = min(start, len(taps_for(rate)) - 1)
    values, stats = decimate(iq[start - history : start + 200_000], rate)
    return values[history // factor :], stats


def temporal_windows(name: str, visit: int) -> tuple[int, ...]:
    return {
        "first1": (0,),
        "rotating1": (visit % 6,),
        "uniform2": (0, 3),
        "uniform3": (0, 2, 4),
        "all6": tuple(range(6)),
    }[name]


def summarize(rows: list[dict]) -> dict:
    reference = {
        (r["session"], r["visit"]): r["decisions"]["all6"]["positive"]
        for r in rows
        if r["rate_hz"] == 5_000_000
    }
    summary = {}
    for rate in RATES:
        selected = [r for r in rows if r["rate_hz"] == rate]
        if not selected:
            continue
        for name in selected[0]["decisions"]:
            costs = [
                r["decisions"][name]["filter_cpu_ms"] + r["decisions"][name]["cpu_ms"]
                for r in selected
            ]
            ref_positive = sum(reference[(r["session"], r["visit"])] for r in selected)
            retained = sum(
                reference[(r["session"], r["visit"])] and r["decisions"][name]["positive"]
                for r in selected
            )
            extra = sum(
                not reference[(r["session"], r["visit"])] and r["decisions"][name]["positive"]
                for r in selected
            )
            summary[f"{rate}:{name}"] = {
                "dwells": len(selected),
                "reference_positive_dwells": ref_positive,
                "retained_reference_positives": retained,
                "additional_positives": extra,
                "cpu_ms_p50": float(np.percentile(costs, 50)),
                "cpu_ms_p95": float(np.percentile(costs, 95)),
                "cpu_ms_mean": float(np.mean(costs)),
                "cpu_ms_max": max(costs),
                "cpu_percent_at_126ms_arrivals": float(np.mean(costs) / 126 * 100),
            }
    return summary


def control_iq(edge: str, kind: str, window: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    count = 1_200_000
    values = 800 * (rng.normal(size=count) + 1j * rng.normal(size=count))
    time_s = np.arange(count) / 10_000_000
    if kind == "tone":
        values += 8000 * np.exp(2j * np.pi * (-173123) * time_s)
    if kind == "alias_tone":
        values += 8000 * np.exp(2j * np.pi * 2_812_345 * time_s)
    if kind == "pilot":
        template = qin_edge_pilot_frame(10_000_000, edge)
        for frame in range(15):
            start = window * 200_000 + 1268 + round(frame * 10_000_000 / 750)
            end = min(start + len(template), (window + 1) * 200_000)
            if start < end:
                values[start:end] += (
                    4000 * template[: end - start] * np.exp(2j * np.pi * 312345 * time_s[start:end])
                )
    return np.clip(np.rint(np.column_stack((values.real, values.imag))), -32768, 32767).astype(
        "<i2"
    )


def controls(output: Path, library: Path) -> None:
    rows = []
    with ExitStack() as stack:
        engines = {
            (r, e): stack.enter_context(NativeDwell(library, r, e, 512))
            for r in RATES
            for e in ("lower", "upper")
        }
        cases = [("pilot", w, 100 + w) for w in range(6)]
        cases += [
            (kind, 0, seed) for kind in ("noise", "tone", "alias_tone") for seed in (301, 302)
        ]
        for edge in ("lower", "upper"):
            for kind, window, seed in cases:
                iq = control_iq(edge, kind, window, seed)
                for rate in RATES:
                    filtered, _ = decimate(iq, rate)
                    result = unpack(engines[rate, edge].run(filtered, maximum=6, seeded=False))
                    by_window = dict(
                        zip(result["rank"]["order"], result["confirmations"], strict=True)
                    )
                    rows.append(
                        dict(
                            edge=edge,
                            kind=kind,
                            injected_window=window,
                            seed=seed,
                            rate_hz=rate,
                            positive_windows=[w for w in range(6) if positive(by_window[w])],
                            selected_window=result["rank"]["order"][0],
                            native_result=result,
                        )
                    )
    (output / "controls.json").write_text(
        json.dumps(
            {
                "scope": "generated 10M controls; not a false-alarm calibration",
                "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--controls-library", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if any(output.is_relative_to(Path(p)) for p in ("/srv/bulk/leo", "/mnt/qnap01")):
        parser.error("research output must be separate from corpus storage")
    output.mkdir(parents=True, exist_ok=False)
    if args.controls_library:
        controls(output, args.controls_library)
        return
    algorithm = json.loads((ROOT / "runtime/scanner-glrt/algorithm.json").read_text())
    library = build_dwell_presence(output / "dwell.so", cflags=tuple(algorithm["native_defines"]))
    protocol = {
        "schema": "adaptive-decision-budget-research-v1",
        "sessions": SESSIONS,
        "sweeps": SWEEPS,
        "source_rate_hz": 10_000_000,
        "decision_rates_hz": RATES,
        "selection": "four-frozen-sweeps-all-eight-targets",
        "thresholds": {"minimum_exact_score": 0.175, "minimum_margin": 0.025},
        "reference": "5M-filtered-all-six-confirmations; not RF truth",
        "host": platform.platform(),
        "machine": platform.machine(),
        "fft": "portable native FFT; not deployed ARM FFTW timing",
        "fewer_probe_timing": "sum of measured independent confirmations; no screening",
        "filter_timing": "NumPy polyphase full-dwell causal FIR including CI16 conversion",
        "sparse_filter": "filter selected 20ms windows with true preceding FIR history",
        "progressive_order": [0, 2, 4, 1, 3, 5],
        "timing_scope": "component sums; IPC, ARM, RF contention and scheduling excluded",
        "partial_misses": "UNKNOWN: insufficient coverage to demote using old policy",
        "filters": {
            str(r): {
                "taps": len(taps_for(r)),
                "sha256": hashlib.sha256(taps_for(r).tobytes()).hexdigest(),
                "group_delay_us": (len(taps_for(r)) - 1) / 2 / 10,
            }
            for r in RATES
        },
    }
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    rows = []
    store = PersistentHopIqStore.open_read_only(args.bulk_root)
    with ExitStack() as stack, (output / "rows.jsonl").open("x") as sink:
        engines = {
            (rate, edge): stack.enter_context(NativeDwell(library, rate, edge, 512))
            for rate in RATES
            for edge in ("lower", "upper")
        }
        # Setup and one zero-dwell warmup per workspace are outside measurements.
        for (rate, _), engine in engines.items():
            engine.run(np.zeros((rate * 120 // 1000, 2), dtype="<i2"), maximum=1, seeded=False)
        for sid in SESSIONS:
            capture = store.inspect(sid)
            assert capture.manifest.receipt.plan.sample_rate_hz == 10_000_000
            assert len(capture.manifest.receiver_ids) == 1
            for sweep in SWEEPS:
                visits, raw = store.read_sweep_ci16(capture, sweep)
                offset = 0
                for visit in visits:
                    count = visit.valid_sample_count
                    iq = np.ascontiguousarray(raw[offset : offset + count, 0])
                    offset += count
                    for rate in RATES:
                        filtered, filter_stats = decimate(iq, rate)
                        engine = engines[rate, visit.target.edge.value]
                        result = unpack(engine.run(filtered, maximum=6, seeded=False))
                        by_window = dict(
                            zip(result["rank"]["order"], result["confirmations"], strict=True)
                        )
                        sparse_filter = {}
                        for window in range(6):
                            partial, stats = decimate_window(iq, rate, window)
                            np.testing.assert_array_equal(
                                partial, filtered[window * rate // 50 : (window + 1) * rate // 50]
                            )
                            sparse_filter[window] = stats["cpu_ms"]
                        decisions = {}
                        for name in ("first1", "rotating1", "uniform2", "uniform3", "all6"):
                            windows = temporal_windows(name, visit.visit_index)
                            decisions[name] = {
                                "windows": windows,
                                "positive": any(positive(by_window[w]) for w in windows),
                                "cpu_ms": sum(by_window[w]["total_cpu_ms"] for w in windows),
                                "filter_cpu_ms": filter_stats["cpu_ms"]
                                if name == "all6"
                                else sum(sparse_filter[w] for w in windows),
                            }
                        attempted = []
                        for window in (0, 2, 4, 1, 3, 5):
                            attempted.append(window)
                            if positive(by_window[window]):
                                break
                        decisions["progressive_until_positive"] = {
                            "windows": attempted,
                            "positive": any(positive(by_window[w]) for w in attempted),
                            "cpu_ms": sum(by_window[w]["total_cpu_ms"] for w in attempted),
                            "filter_cpu_ms": sum(sparse_filter[w] for w in attempted),
                        }
                        best = result["rank"]["order"][0]
                        decisions["screen6_confirm1"] = {
                            "windows": [best],
                            "positive": positive(by_window[best]),
                            "cpu_ms": result["prefix_cpu_ms"][0],
                            "filter_cpu_ms": filter_stats["cpu_ms"],
                        }
                        row = {
                            "session": sid,
                            "input_manifest_sha256": capture.manifest_sha256,
                            "visit": visit.visit_index,
                            "receiver": capture.manifest.receiver_ids[0],
                            "target": visit.target_index,
                            "edge": visit.target.edge.value,
                            "iq_sha256": hashlib.sha256(iq.tobytes()).hexdigest(),
                            "rate_hz": rate,
                            "filter": filter_stats,
                            "screen_cpu_ms": result["rank"]["total_cpu_ms"],
                            "decisions": decisions,
                            "native_result": result,
                        }
                        sink.write(json.dumps(row) + "\n")
                        sink.flush()
                        rows.append(row)
                print(json.dumps({"session": sid, "sweep": sweep, "rows": len(rows)}), flush=True)
    (output / "summary.json").write_text(json.dumps(summarize(rows), indent=2) + "\n")


if __name__ == "__main__":
    main()
