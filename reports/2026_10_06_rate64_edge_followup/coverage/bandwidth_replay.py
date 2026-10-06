"""Report-only paired saved-IQ bandwidth experiment; no capture or product writes."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, edge_frequencies_hz
from leo.storage.adaptive_hop import AdaptiveHopIqStore

FS = 10_000_000
FACTOR = 4
NARROW_LIMIT_HZ = 429_687.5
GATE = 0.025
FILTER_TAPS = 321
FILTER_CUTOFF_HZ = 1_125_000.0
FILTER_BETA = 8.6


def fir_taps():
    """Symmetric unit-DC FIR, frozen without consulting evaluation scans."""
    n = np.arange(FILTER_TAPS) - (FILTER_TAPS - 1) / 2
    h = 2 * FILTER_CUTOFF_HZ / FS * np.sinc(2 * FILTER_CUTOFF_HZ / FS * n)
    h *= np.kaiser(FILTER_TAPS, FILTER_BETA)
    return h / h.sum()


def filter_decimate(iq, nominal_hz):
    """Mix to nominal pilot BEFORE FIR; compensate integer FIR group delay.

    Output index k represents original time 4*k/FS. Zero padding affects only
    the first/last 160 input samples; saved scoring epochs avoid that boundary.
    """
    centered = iq * np.exp(-2j * np.pi * nominal_hz * np.arange(len(iq)) / FS)
    filtered = np.convolve(centered, fir_taps(), mode="same")
    return filtered[::FACTOR], centered, filtered


def transform_seed(epoch, fraction, cfo, nominal):
    position = (epoch + fraction) / FACTOR
    integer = round(position)
    return integer, position - integer, cfo - nominal


def tone_center_eligible(cfo, nominal=0.0):
    return abs(cfo - nominal) <= NARROW_LIMIT_HZ


def edge_bias(edge):
    f = -115_429_687.5 if edge == "lower" else 115_195_312.5
    period = 1 / OFDM_SYMBOL_DURATION_S
    return (-f + period / 2) % period - period / 2


def score(iq, fs, epoch, fraction, cfo, edge):
    s = conditioned_glrt64_score(
        iq,
        fs,
        epoch_sample=epoch,
        fractional_epoch_offset_samples=fraction,
        acquired_cfo_hz=cfo,
        edge=edge,
    )
    return dict(
        exact=s.exact_score,
        control=s.control_score,
        margin=s.margin,
        residual_cfo_hz=s.residual_cfo_hz,
        tracking_cfo_hz=s.tracking_cfo_hz,
        passed=s.margin >= GATE,
    )


def frame_inventory(count, fs, epoch, fraction):
    # 64-symbol GLRT support; interpolation guard is safely far from boundaries.
    return [
        i
        for i in range(100)
        if epoch + round(i * fs / 750) + round(66 * fs * 4.4e-6) + max(32, fraction) < count
    ]


def spectral_retention(centered, filtered, tone_centers):
    # Same-rate, same-window spectral energy, before downsampling. Includes
    # background/interference: these are tone-neighborhood energies, not pilots.
    window = np.hanning(len(centered))
    before = abs(np.fft.fft(centered * window)) ** 2
    after = abs(np.fft.fft(filtered * window)) ** 2
    freqs = np.fft.fftfreq(len(centered), 1 / FS)
    h = fir_taps()
    gains = []
    retention = []
    for f in tone_centers:
        gains.append(float(abs(np.sum(h * np.exp(-2j * np.pi * f * np.arange(len(h)) / FS))) ** 2))
        band = abs(freqs - f) <= 60_000
        retention.append(float(after[band].sum() / max(before[band].sum(), 1e-30)))
    return gains, retention


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    spec_bytes = args.spec.read_bytes()
    spec = json.loads(spec_bytes)
    settings = dict(
        filter_taps=FILTER_TAPS,
        cutoff_hz=FILTER_CUTOFF_HZ,
        kaiser_beta=FILTER_BETA,
        factor=FACTOR,
        gate=GATE,
        narrow_tone_center_limit_hz=NARROW_LIMIT_HZ,
        seed_transform="(integer_epoch + fractional_epoch)/4; cfo - nominal_pilot",
        scoring="published fixed seeds; no reacquisition",
        null_seed=20261006,
        template_coordinate="production template retained, edge bias only annotated",
    )
    out = dict(spec_sha256=hashlib.sha256(spec_bytes).hexdigest(), settings=settings, rows=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2))
    store = AdaptiveHopIqStore(Path(spec["bulk_root"]), read_only=True)
    started = time.monotonic()
    for scan in spec["scans"]:
        with store.reader(scan["session_id"]) as reader:
            retained = {
                v.event.visit_index: i for i, v in enumerate(reader.session.manifest.receipt.visits)
            }
            fs = scan["rate"]
            for e in scan["examples"]:
                visit, ci16 = reader.read_visit_ci16(retained[e["visit_index"]])
                assert visit.event.visit_index == e["visit_index"]
                start = e["probe_start_ms"] * fs // 1000
                vals = ci16[start : start + fs // 50, e["receiver_id"], :]
                iq = vals[:, 0].astype(float) + 1j * vals[:, 1].astype(float)
                w = e["candidate"]
                epoch, fraction, cfo = (
                    w["integer_epoch_sample"],
                    w["fractional_epoch_offset_samples"],
                    w["acquired_cfo_hz"],
                )
                assert (
                    int(w["integer_device_sample_counter"])
                    == visit.event.valid_start_counter + start + epoch
                )
                baseline = score(iq, fs, epoch, fraction, cfo, scan["edge"])
                error = abs(baseline["margin"] - w["fractional_margin"])
                assert error < 1e-7, (scan["session_id"], e["lane"], error)
                row = dict(
                    session_id=scan["session_id"],
                    split=scan["split"],
                    rate=fs,
                    edge=scan["edge"],
                    lane=e["lane"],
                    visit_index=e["visit_index"],
                    probe_index=e["probe_index"],
                    receiver_id=e["receiver_id"],
                    channel=e["channel"],
                    input_manifest_sha256=reader.session.manifest_sha256,
                    iq_sha256=hashlib.sha256(vals.astype("<i2").tobytes()).hexdigest(),
                    published_margin_error=error,
                    baseline=baseline,
                )
                if fs == FS:
                    nominal = e["nominal_baseband_hz"]
                    low, centered, filtered = filter_decimate(iq, nominal)
                    ep, fr, cf = transform_seed(epoch, fraction, cfo, nominal)
                    before_support = frame_inventory(len(iq), fs, epoch, fraction)
                    after_support = frame_inventory(len(low), fs // FACTOR, ep, fr)
                    assert before_support == after_support, (before_support, after_support)
                    narrow = tone_center_eligible(cfo, nominal)
                    physical = baseline["tracking_cfo_hz"] - nominal - edge_bias(scan["edge"])
                    tones = edge_frequencies_hz(scan["edge"]) + physical
                    gains, retention = spectral_retention(centered, filtered, tones)
                    narrow_score = score(low, fs // FACTOR, ep, fr, cf, scan["edge"])
                    # Conditional matched noise control at the original seed, same PSD
                    # and frame inventory. This does not calibrate acquisition FAP.
                    seed = (
                        int(
                            hashlib.sha256((scan["session_id"] + e["lane"]).encode()).hexdigest()[
                                :8
                            ],
                            16,
                        )
                        ^ 20261006
                    )
                    rng = np.random.default_rng(seed)
                    null = (rng.normal(size=len(iq)) + 1j * rng.normal(size=len(iq))) * np.sqrt(
                        np.mean(abs(iq) ** 2) / 2
                    )
                    null_low, _, _ = filter_decimate(null, nominal)
                    row.update(
                        nominal_pilot_baseband_hz=nominal,
                        acquired_pilot_relative_hz=cfo - nominal,
                        acquired_distance_to_narrow_boundary_hz=NARROW_LIMIT_HZ
                        - abs(cfo - nominal),
                        search_support_only_eligible=narrow,
                        search_support_only=baseline if narrow else None,
                        decimated_seed=dict(epoch=ep, fraction=fr, cfo_hz=cf),
                        frame_indexes=before_support,
                        digitally_narrowed=narrow_score,
                        physical_tracking_pilot_relative_hz=physical,
                        physical_tone_center_distance_to_nyquist_hz=1_250_000
                        - float(np.max(abs(tones))),
                        tone_centers_hz=tones.tolist(),
                        fir_tone_power_gains=gains,
                        measured_tone_neighborhood_energy_retention=retention,
                        broadband_energy_retention=float(
                            np.mean(abs(filtered) ** 2) / np.mean(abs(centered) ** 2)
                        ),
                        null_full=score(null, fs, epoch, fraction, cfo, scan["edge"]),
                        null_narrow=score(null_low, fs // FACTOR, ep, fr, cf, scan["edge"]),
                    )
                out["rows"].append(row)
                args.output.write_text(json.dumps(out, indent=2))
                print(
                    scan["split"],
                    scan["session_id"],
                    e["lane"],
                    f"margin={baseline['margin']:.4f}",
                    flush=True,
                )
    store.close()
    out["elapsed_seconds"] = time.monotonic() - started
    args.output.write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
