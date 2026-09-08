"""Bounded synthetic full-dwell controls; never reads or opens a radio."""

from __future__ import annotations

import argparse
import json
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.native_presence import ROOT, build_dwell_presence
from tools.presence_dwell import NativeDwell, unpack
from tools.presence_fftw import fftw_identity, fftw_options
from tools.qualify_native_presence import digest, write_json

NEGATIVE_KINDS = ("white_noise", "colored_noise", "tone", "two_tones", "pulsed_tone")


def generate(rate, edge, seed, kind, window=None):
    if rate not in (2500000, 5000000) or edge not in ("lower", "upper"):
        raise ValueError("unsupported geometry")
    positive = kind in ("pilot", "pilot_plus_tone")
    if (
        (not positive and kind not in NEGATIVE_KINDS)
        or (positive and (type(window) is not int or not 0 <= window < 6))
        or (not positive and window is not None)
    ):
        raise ValueError("invalid control or signal interval")
    rng = np.random.default_rng(seed)
    count, length = 6 * rate // 50, rate // 50
    noise = 800 * (rng.normal(size=count) + 1j * rng.normal(size=count))
    x = noise.copy()
    time = np.arange(count) / rate  # Local time only, never an absolute device epoch.
    carrier = -173123 + 137 * (seed % 7)
    if kind == "colored_noise":
        coefficients = np.hanning(17)
        coefficients /= np.sqrt(np.sum(coefficients**2))
        x = np.convolve(noise, coefficients, mode="same") * np.exp(2j * np.pi * 73123 * time)
    if kind in ("tone", "two_tones", "pulsed_tone", "pilot_plus_tone"):
        envelope = ((time * 750) % 1 < 0.45) if kind == "pulsed_tone" else 1
        x += 8000 * envelope * np.exp(2j * np.pi * carrier * time)
    if kind == "two_tones":
        x += 6000 * np.exp(2j * np.pi * 251371 * time)
    truth = {
        "starlink_model_present": positive,
        "window": window,
        "kind": kind,
        "seed": seed,
        "rate_hz": rate,
        "edge": edge,
    }
    if positive:
        template = qin_edge_pilot_frame(rate, edge).astype(np.complex128)
        delay = 0.35
        template = np.fft.ifft(
            np.fft.fft(template) * np.exp(-2j * np.pi * np.fft.fftfreq(len(template)) * delay)
        )
        epoch, cfo = 317 + seed % 13, 312345 - 371 * (seed % 9)
        for frame in range(15):
            start = epoch + round(frame * (rate / 750))
            stop = min(start + len(template), length)
            if stop > start:
                positions = window * length + np.arange(start, stop)
                x[positions] += (
                    4000 * template[: stop - start] * np.exp(2j * np.pi * cfo * positions / rate)
                )
        truth.update(epoch_samples=epoch, fractional_delay_samples=delay, cfo_hz=cfo)
    components = np.rint(np.column_stack((x.real, x.imag)))
    truth["clipped_components"] = int(
        np.count_nonzero((components < -32768) | (components > 32767))
    )
    return np.clip(components, -32768, 32767).astype(np.int16), truth


def summarize(rows):
    result = {}
    for rate in sorted({r["truth"]["rate_hz"] for r in rows}):
        subset = [r for r in rows if r["truth"]["rate_hz"] == rate]
        result[str(rate)] = {}
        for kind in sorted({r["truth"]["kind"] for r in subset}):
            cases = [r for r in subset if r["truth"]["kind"] == kind]
            result[str(rate)][kind] = {
                "cases": len(cases),
                "policies": {
                    str(k): {
                        "flagged": sum(any(r["flags"][:k]) for r in cases),
                        "signal_window_selected": sum(
                            r["truth"]["window"] in r["result"]["rank"]["order"][:k]
                            for r in cases
                            if r["truth"]["starlink_model_present"]
                        ),
                    }
                    for k in (1, 2, 3, 6)
                },
            }
    return result


def run(output: Path, prefix: Path, *, area_screen=False, hybrid_screen=False):
    if area_screen and hybrid_screen:
        raise ValueError("choose either area-only or hybrid screen")
    output = output.resolve()
    if any(output.is_relative_to(Path(p)) for p in ("/mnt/qnap01", "/srv/bulk/leo")):
        raise ValueError("controls output cannot be beneath an archive")
    options = fftw_options(prefix)
    protocol_path = ROOT / "config/analysis/arm-presence-dwell-controls-v1.json"
    protocol = json.loads(protocol_path.read_text())
    if (
        protocol["negative_kinds"] != list(NEGATIVE_KINDS)
        or protocol["positive_windows"] != list(range(6))
        or protocol["research_margin"] != 0.025
        or protocol["seeds"] != [1901, 1902, 1903, 1904]
    ):
        raise ValueError("unreviewed control configuration")
    detector = json.loads(
        (ROOT / "config/analysis/arm-presence-native-tone-ci16-v1.json").read_text()
    )
    flags = tuple(detector["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{k}={v}" for k, v in detector["variants"][0]["defines"].items()
    )
    output.mkdir(parents=True, exist_ok=False)
    write_json(
        output / "freeze.json",
        {
            "protocol": protocol,
            "protocol_sha256": digest(protocol_path),
            "generator_sha256": digest(Path(__file__)),
            "fft_backend": fftw_identity(options),
            "state": "frozen_before_execution",
            "screen_projection": "hybrid_max_second_ratio"
            if hybrid_screen
            else ("area_average" if area_screen else "point_interpolation"),
        },
    )
    library = build_dwell_presence(
        output / "controls.so",
        cflags=flags
        + ("-DLEO_PRESENCE_DIFFERENTIAL_CI16=1",)
        + options["cflags"]
        + (("-DLEO_PRESENCE_RANK_AREA_PROJECTION=1",) if area_screen else ())
        + (("-DLEO_PRESENCE_RANK_HYBRID_PROJECTION=1",) if hybrid_screen else ()),
        ldflags=options["ldflags"],
        dependencies=options["dependencies"],
    )
    rows = []
    with ExitStack() as stack, (output / "results.jsonl").open("x") as stream:
        for rate in protocol["rates_hz"]:
            for edge in protocol["edges"]:
                native = stack.enter_context(NativeDwell(library, rate, edge, 512))
                cases = [(kind, None) for kind in protocol["negative_kinds"]] + [
                    (kind, window)
                    for kind in protocol["positive_kinds"]
                    for window in protocol["positive_windows"]
                ]
                for seed in protocol["seeds"]:
                    for kind, window in cases:
                        iq, truth = generate(rate, edge, seed, kind, window)
                        result = unpack(native.run(iq, maximum=6, seeded=False))
                        result["screen_diagnostics"] = unpack(native.screens())
                        flags = [
                            any(
                                c["fractional_complete"] and c["margin"] >= 0.025
                                for c in r["candidates"][: r["candidate_count"]]
                            )
                            for r in result["confirmations"]
                        ]
                        row = {"truth": truth, "result": result, "flags": flags}
                        rows.append(row)
                        stream.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")
    result = {
        "status": "synthetic_development_not_rf_specificity",
        "cases": len(rows),
        "binary_sha256": digest(library),
        "results": summarize(rows),
    }
    write_json(output / "summary.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fftw-prefix", required=True, type=Path)
    parser.add_argument("--area-screen", action="store_true")
    parser.add_argument("--hybrid-screen", action="store_true")
    args = parser.parse_args()
    run(
        args.output,
        args.fftw_prefix,
        area_screen=args.area_screen,
        hybrid_screen=args.hybrid_screen,
    )
