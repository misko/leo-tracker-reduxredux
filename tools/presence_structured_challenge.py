"""Bounded independent-symbol controls for the RX1 whole-dwell GLRT detector.

The model shares only public waveform geometry with the detector. It does not
shift, interpolate or relabel a known pilot as negative, and never opens RF.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import ExitStack
from functools import lru_cache
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    edge_frequencies_hz,
)
from tools.native_presence import ROOT, build_dwell_presence
from tools.presence_decision_challenge import associated, continuous_pilot, passing
from tools.presence_dwell import NativeDwell, unpack
from tools.presence_fftw import fftw_options
from tools.qualify_native_presence import digest, write_json

PROTOCOL = ROOT / "config/analysis/arm-presence-structured-challenge-v1.json"
NEGATIVE_KINDS = ("repeating_qpsk", "independent_qpsk", "repeating_qam16", "independent_qam16")
VARIANTS = {
    "normalized": (0, 0),
    "amplitude": (1, 0),
    "normalized-diverse": (0, 1),
    "amplitude-diverse": (1, 1),
    "amplitude-diverse-supported": (1, 1),
    "amplitude-diverse-symbol-supported": (1, 1),
}


def variant_flags(name):
    """Explicit opt-in flags; original challenge variants retain early scoring."""
    if name not in VARIANTS:
        raise ValueError("unknown structured challenge variant")
    amplitude, diversity = VARIANTS[name]
    flags = (
        f"-DLEO_PRESENCE_RANK_AMPLITUDE_WEIGHTED={amplitude}",
        f"-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY={diversity}",
    )
    if name.endswith("-supported"):
        flags += ("-DLEO_PRESENCE_ENERGY_SUPPORT=1",)
    if name == "amplitude-diverse-symbol-supported":
        flags += ("-DLEO_PRESENCE_ENERGY_SYMBOL_SUPPORT=1",)
    return flags


def validate_protocol(protocol):
    variants = protocol["variants"]
    seed_base = protocol.get("independent_case_seed_base")
    if (
        protocol["policy"] != {"minimum_exact_score": 0.175, "minimum_margin": 0.025}
        or protocol["negative_kinds"] != list(NEGATIVE_KINDS)
        or not isinstance(variants, list)
        or not 1 <= len(variants) <= len(VARIANTS)
        or any(not isinstance(v, str) or v not in VARIANTS for v in variants)
        or len(set(variants)) != len(variants)
        or protocol["screen_bins"] != 512
        or protocol["maximum_confirmations"] != 1
        or protocol["seeded"]
        or protocol["receiver"] != 1
        or protocol["dwell_ms"] != 120
        or protocol["absence_policy_enabled"]
        or protocol["live_rf_authorized"]
        or type(protocol.get("optimized_arithmetic", False)) is not bool
        or (
            seed_base is not None
            and (
                type(seed_base) is not int
                or not 0 <= seed_base < 2**32
                or type(protocol["case_count"]) is not int
                or not 0 < protocol["case_count"] <= 4096
                or seed_base + protocol["case_count"] > 2**32
            )
        )
    ):
        raise ValueError("unreviewed challenge policy")


def cases(protocol):
    """Optional fresh independent draws per case; old inventories stay exact."""
    base = protocol.get("independent_case_seed_base")
    for index, spec in enumerate(_cases(protocol)):
        yield spec if base is None else dict(spec, seed=base + index)


def _cases(protocol):
    for rate in protocol["rates_hz"]:
        for edge in protocol["edges"]:
            geometry = {"rate_hz": rate, "edge": edge}
            for seed in protocol["negative_seeds"]:
                for kind in protocol["negative_kinds"]:
                    for snr in protocol["negative_snr_db"]:
                        yield dict(
                            geometry,
                            seed=seed,
                            kind=kind,
                            snr_db=snr,
                            start_ms=0.0,
                            duration_ms=120.0,
                        )
            for seed in protocol["positive_seeds"]:
                for window in protocol["positive_windows"]:
                    for snr in protocol["positive_snr_db"]:
                        yield dict(
                            geometry,
                            seed=seed,
                            kind="pilot",
                            snr_db=snr,
                            start_ms=window * 20.0,
                            duration_ms=20.0,
                        )
                for offset in protocol["tone_offsets_hz"]:
                    yield dict(
                        geometry,
                        seed=seed,
                        kind="pilot_plus_tone",
                        snr_db=0.0,
                        start_ms=40.0,
                        duration_ms=20.0,
                        tone_offset_hz=offset,
                    )
            for seed in protocol["boundary_seeds"]:
                for boundary in range(1, 6):
                    for snr in protocol["boundary_snr_db"]:
                        duration = protocol["boundary_burst_ms"]
                        yield dict(
                            geometry,
                            seed=seed,
                            kind="boundary_pilot",
                            snr_db=snr,
                            start_ms=boundary * 20.0 - duration / 2,
                            duration_ms=duration,
                        )


def symbol_states(kind, seed, frames):
    """Independent random payload; repeating cases repeat an entire random frame."""
    if kind not in NEGATIVE_KINDS or type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("bounded independent-symbol seed and kind required")
    if type(frames) is not int or not 1 <= frames <= 92:
        raise ValueError("bounded frame inventory required")
    rng = np.random.default_rng(np.random.SeedSequence([seed, NEGATIVE_KINDS.index(kind), 1]))
    shape = (frames if kind.startswith("independent") else 1, 300, 8)
    levels = np.array([-3, -1, 1, 3]) if kind.endswith("qam16") else np.array([-1, 1])
    scale = np.sqrt(10 if kind.endswith("qam16") else 2)
    values = (rng.choice(levels, shape) + 1j * rng.choice(levels, shape)) / scale
    return np.broadcast_to(values, (frames, 300, 8)).copy()


@lru_cache(maxsize=2)
def structured_waveform(rate, edge, epoch, kind, seed):
    if rate not in (2500000, 5000000) or edge not in ("lower", "upper"):
        raise ValueError("unsupported geometry")
    if not np.isfinite(epoch) or not 0 <= epoch < rate / FRAME_RATE_HZ:
        raise ValueError("bounded fractional epoch required")
    # Everything here is local synthetic time, never a device counter.
    time = (np.arange(rate * 120 // 1000) - epoch) / rate
    frame_time = np.remainder(time, 1 / FRAME_RATE_HZ)
    symbols = np.floor(frame_time / OFDM_SYMBOL_DURATION_S).astype(int)
    frames = np.floor(time * FRAME_RATE_HZ).astype(int)
    frames -= frames.min()
    states = symbol_states(kind, seed, int(frames.max()) + 1)
    use = (symbols >= 2) & (symbols < 302)
    local = frame_time[use] - symbols[use] * OFDM_SYMBOL_DURATION_S - CYCLIC_PREFIX_DURATION_S
    values = np.zeros(len(time), dtype=np.complex128)
    for column, frequency in enumerate(edge_frequencies_hz(edge)):
        values[use] += states[frames[use], symbols[use] - 2, column] * np.exp(
            2j * np.pi * frequency * local
        )
    values /= np.sqrt(8)
    values.flags.writeable = False
    return values


def generate(spec, protocol):
    rate, edge, seed, kind = (spec[k] for k in ("rate_hz", "edge", "seed", "kind"))
    positive = kind in ("pilot", "pilot_plus_tone", "boundary_pilot")
    if (
        type(rate) is not int
        or rate not in (2500000, 5000000)
        or edge not in ("lower", "upper")
        or type(seed) is not int
        or not 0 <= seed < 2**32
        or (not positive and kind not in NEGATIVE_KINDS)
    ):
        raise ValueError("invalid model geometry or kind")
    snr, start_ms, duration_ms = (spec[k] for k in ("snr_db", "start_ms", "duration_ms"))
    if not all(np.isfinite(v) for v in (snr, start_ms, duration_ms)) or not -30 <= snr <= 20:
        raise ValueError("finite bounded signal parameters required")
    count = rate * 120 // 1000
    start, stop = round(start_ms * rate / 1000), round((start_ms + duration_ms) * rate / 1000)
    if not 0 <= start < stop <= count:
        raise ValueError("interval outside dwell")
    offset = spec.get("tone_offset_hz", 0.0)
    if not np.isfinite(offset) or abs(offset) > 220000:
        raise ValueError("bounded tone separation required")
    # Separate geometry, noise and symbol RNG streams; SNR/variant comparisons
    # see the same underlying draw, explicitly not independent trials.
    rng = np.random.default_rng(np.random.SeedSequence([seed, 0]))
    cfo = rng.uniform(-protocol["maximum_absolute_cfo_hz"], protocol["maximum_absolute_cfo_hz"])
    epoch = rng.uniform(128, 1000)
    rng = np.random.default_rng(np.random.SeedSequence([seed, 2]))
    sigma = 800.0
    values = sigma * (rng.normal(size=count) + 1j * rng.normal(size=count))
    time = np.arange(count) / rate
    waveform = (
        continuous_pilot(rate, edge, epoch)
        if positive
        else structured_waveform(rate, edge, epoch, kind, seed)
    )
    signal = waveform[start:stop]
    amplitude = np.sqrt(2 * sigma**2 * 10 ** (snr / 10) / np.mean(np.abs(signal) ** 2))
    values[start:stop] += amplitude * signal * np.exp(2j * np.pi * cfo * time[start:stop])
    if kind == "pilot_plus_tone":
        tone_amplitude = np.sqrt(2 * sigma**2 * 10 ** (protocol["tone_inr_db"] / 10))
        values += tone_amplitude * np.exp(2j * np.pi * (cfo + offset) * time)
    components = np.rint(np.column_stack((values.real, values.imag)))
    truth = dict(
        spec,
        starlink_model_present=positive,
        cfo_hz=cfo,
        epoch_samples=epoch,
        clipped_components=int(np.count_nonzero((components < -32768) | (components > 32767))),
    )
    return np.clip(components, -32768, 32767).astype(np.int16), truth


def summarize(rows, protocol):
    summary = {}
    for variant in protocol["variants"]:
        groups = {}
        for row in rows:
            truth, result = row["truth"], row["variants"][variant]
            key = f"{truth['rate_hz']}:{truth['kind']}:{truth['snr_db']}"
            group = groups.setdefault(key, dict(cases=0, flagged=0, associated=0))
            group["cases"] += 1
            group["flagged"] += int(result["flagged"])
            group["associated"] += int(result["associated"])
        negatives = [r for r in rows if not r["truth"]["starlink_model_present"]]
        primary = [r for r in rows if r["truth"]["kind"] in ("pilot", "pilot_plus_tone")]
        false_flags = sum(r["variants"][variant]["flagged"] for r in negatives)
        matches = sum(r["variants"][variant]["associated"] for r in primary)
        summary[variant] = dict(
            groups=groups,
            nonpilot_cases=len(negatives),
            nonpilot_flags=false_flags,
            primary_cases=len(primary),
            primary_associated=matches,
            bounded_challenge_pass=bool(primary)
            and bool(negatives)
            and false_flags <= protocol["gate"]["nonpilot_flags"]
            and matches / len(primary) >= protocol["gate"]["minimum_primary_association"],
        )
    return summary


def run(output, prefix, protocol_path=PROTOCOL):
    output = output.resolve()
    if any(output.is_relative_to(Path(p)) for p in ("/mnt/qnap01", "/srv/bulk/leo")):
        raise ValueError("output cannot be under archive storage")
    protocol = json.loads(protocol_path.read_text())
    validate_protocol(protocol)
    inventory = list(cases(protocol))
    if len(inventory) != protocol["case_count"]:
        raise ValueError("unexpected challenge size")
    output.mkdir(parents=True, exist_ok=False)
    options = fftw_options(prefix)
    detector_path = ROOT / protocol["detector_protocol"]
    detector = json.loads(detector_path.read_text())
    flags = (
        tuple(detector["common_flags"])
        + tuple(f"-DLEO_PRESENCE_{k}={v}" for k, v in detector["variants"][0]["defines"].items())
        + ("-DLEO_PRESENCE_DIFFERENTIAL_CI16=1", "-DLEO_PRESENCE_RANK_HYBRID_PROJECTION=1")
    )
    if protocol.get("optimized_arithmetic", False):
        flags += (
            "-DLEO_PRESENCE_BOUNDED_MAGNITUDE=1",
            "-DLEO_PRESENCE_CONDITIONED_BLOCK_ROTATION=1",
        )
    freeze = dict(
        protocol=protocol,
        protocol_sha256=digest(protocol_path),
        tool_sha256=digest(Path(__file__)),
        detector_protocol_sha256=digest(detector_path),
        cases=inventory,
        state="frozen_before_model_generation_and_scoring",
        scientific_qualification=False,
    )
    write_json(output / "freeze.json", freeze)
    libraries = {
        name: build_dwell_presence(
            output / f"{name}.so",
            cflags=flags + options["cflags"] + variant_flags(name),
            ldflags=options["ldflags"],
            dependencies=options["dependencies"],
        )
        for name in protocol["variants"]
    }
    identities = {name: digest(path) for name, path in libraries.items()}
    rows = []
    with ExitStack() as stack, (output / "results.jsonl").open("x") as stream:
        engines = {}
        for index, spec in enumerate(inventory):
            iq, truth = generate(spec, protocol)
            original = hashlib.sha256(iq.tobytes()).hexdigest()
            variants = {}
            for name in protocol["variants"] if index % 2 == 0 else reversed(protocol["variants"]):
                key = name, spec["rate_hz"], spec["edge"]
                if key not in engines:
                    engines[key] = stack.enter_context(NativeDwell(libraries[name], *key[1:], 512))
                result = unpack(engines[key].run(iq, maximum=1, seeded=False))
                selected = result["rank"]["order"][0]
                confirmation = result["confirmations"][0]
                candidates = confirmation["candidates"][: confirmation["candidate_count"]]
                accepted = passing(candidates, protocol["policy"])
                variants[name] = dict(
                    result=result,
                    screens=unpack(engines[key].screens()),
                    selected_window=selected,
                    flagged=bool(accepted),
                    associated=any(
                        associated(c, truth, selected, protocol["association"]) for c in accepted
                    ),
                )
            if hashlib.sha256(iq.tobytes()).hexdigest() != original:
                raise ValueError("detector mutated IQ")
            row = dict(truth=truth, iq_sha256=original, variants=variants)
            rows.append(row)
            stream.write(json.dumps(row, allow_nan=False) + "\n")
            stream.flush()
            if (index + 1) % 40 == 0:
                print(
                    f"{index + 1}/{len(inventory)} independent-symbol challenge cases", flush=True
                )
    if (
        freeze["protocol_sha256"] != digest(protocol_path)
        or freeze["tool_sha256"] != digest(Path(__file__))
        or freeze["detector_protocol_sha256"] != digest(detector_path)
        or identities != {name: digest(path) for name, path in libraries.items()}
    ):
        raise ValueError("source or artifact identity changed during scoring")
    summary = dict(
        scope="bounded synthetic challenge, not operational FAR or live duty",
        cases=len(rows),
        binary_sha256=identities,
        results=summarize(rows, protocol),
    )
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fftw-prefix", required=True, type=Path)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    args = parser.parse_args()
    run(args.output, args.fftw_prefix, args.protocol)
