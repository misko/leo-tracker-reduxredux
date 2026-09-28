"""Recover published 60-bit tessellation codes with receiver-held-out checks.

These are physical-layer patterns, conjectured to occupy unladen allocations;
they are not decoded user traffic, identity, timing, or orbit messages.
"""

import argparse
import csv
import hashlib
import json

import numpy as np
from analyze import OUT, ROOT, demodulate
from recover import geometry, pilot_calibrate, references
from scipy.signal import resample_poly


def compact_indices(bins):
    valid = np.array(
        [k for k in range(2, 1022) if k not in range(488, 496) and k not in range(528, 536)]
    )
    physical = valid[np.argsort(np.fft.fftfreq(1024)[valid])]
    lookup = {int(k): n for n, k in enumerate(physical)}
    return np.array([lookup[int(k)] for k in bins])


def slots(bins, symbols):
    # Qin et al. (2026), equations 62--64: reduce the shift modulo 60
    # BEFORE circularly shifting the finite 1004-element non-pilot vector.
    shift = (16 * np.asarray(symbols)[:, None]) % 60
    return ((compact_indices(bins)[None, :] - shift) % 1004) % 60


def fit_code(values, mapping):
    count = np.bincount(mapping.ravel(), minlength=60)
    sums = np.bincount(mapping.ravel(), weights=values.real.ravel(), minlength=60)
    means = np.divide(sums, count, out=np.zeros(60), where=count > 0)
    return np.where(count > 0, np.where(means >= 0, 1, -1), 0), means, count


def bit_word(code):
    return "".join("1" if v > 0 else "0" if v < 0 else "?" for v in code)


def score_code(values, mapping, code):
    return float(np.mean(values.real * code[mapping]) / np.sqrt(np.mean(abs(values) ** 2)))


def select_window(deviations, bins):
    # Start after the observed short header. Selection uses RX0 only.
    trials = []
    for first in range(14, 239, 32):
        symbols = np.arange(first, first + 64)
        z = deviations[symbols - 2]
        mapping = slots(bins, symbols)
        code, _, _ = fit_code(z[::2], mapping[::2])
        heldout = score_code(z[1::2], mapping[1::2], code)
        trials.append((heldout, first))
    score, first = max(trials)
    return first, score, trials


def ut_control(edge="upper"):
    bins, _, center = geometry(edge)
    sss, template, _ = references(edge)
    source = ROOT / "docs/research/starlink-literature/local/data/ut-pilots"
    raw = np.memmap(source / "exemplar250-257/exemplar250-257.bin", dtype="<i2", mode="r").reshape(
        -1, 2
    )
    frames = json.loads((ROOT / "reports/2026_09_27_ut_header/local/results.json").read_text())[
        "frames"
    ]
    results = []
    for frame in frames:
        start = round((frame["acquired_toa_s"] - 10e-6) * 250e6)
        v = raw[start : start + 340000].astype(float)
        x = v[:, 0] + 1j * v[:, 1]
        x *= np.exp(-2j * np.pi * (center + frame["cfo_hz"]) * np.arange(len(x)) / 250e6)
        sy = demodulate(resample_poly(x, 1, 25), 1e7, 100, 0, center)
        z = sy[1:, bins] / (sy[0, bins] / sss[bins]) * template[bins, 1:].T.conj()
        first, score, trials = select_window(z, bins)
        mapping = slots(bins, np.arange(first, first + 64))
        code, means, _ = fit_code(z[first - 2 : first + 62], mapping)
        results.append(
            dict(
                frame_id=frame["frame_id"],
                first_symbol=first,
                heldout_correlation=score,
                code=bit_word(code),
                trials=trials,
                minimum_mean_amplitude=float(abs(means).min()),
            )
        )
    name = "ut-tcode-control.json" if edge == "upper" else "ut-tcode-control-lower.json"
    (OUT / name).write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results))


def ds7(group, limit, allow_lower=False):
    out = OUT / group
    inventory = json.loads((out / "inventory.json").read_text())
    records = json.loads((out / "recovery.json").read_text())
    archive = np.load(out / "recovery-soft-symbols.npz")
    edge = inventory["exports"][0]["probe"]["edge"]
    if edge != "upper" and not (allow_lower and edge == "lower"):
        raise ValueError("This T-code decoder currently qualifies upper-edge bins only")
    bins, _, center = geometry(edge)
    _, template, pilot = references(edge)
    rawstreams = []
    for row in inventory["exports"]:
        raw = np.load(out / (row["name"] + ".npy"))
        assert hashlib.sha256(raw.tobytes()).hexdigest() == row["excerpt_sha256"]
        rawstreams.append(raw[:, 0].astype(float) + 1j * raw[:, 1])
    results = []
    soft_arrays = {}
    rng = np.random.default_rng(6027)
    for frame in range(min(limit, len(records[0]["diagnostics"]))):
        deviations = []
        for row, record, x in zip(inventory["exports"], records, rawstreams, strict=True):
            ep = record["corrected_frame_epochs_samples"][frame]
            start = int(ep) - 100
            sy = demodulate(
                x[start : start + 13600],
                1e7,
                ep - start,
                row["candidate"]["fractional_tracking_cfo_hz"],
                center,
            )
            y, _ = pilot_calibrate(sy, pilot, record["diagnostics"][frame]["phase_slope"], edge)
            h = archive[row["name"] + "_sss_channel"][frame]
            deviations.append(y[1:, bins] / h * template[bins, 1:].T.conj())
        first, score, trials = select_window(deviations[0], bins)
        mapping = slots(bins, np.arange(first, first + 64))
        a, b = [d[first - 2 : first + 62] for d in deviations]
        code0, means0, count = fit_code(a, mapping)
        code1, means1, _ = fit_code(b, mapping)
        held = score_code(b, mapping, code0)
        known = count > 0
        controls = []
        for _ in range(1000):
            wrong = code0.copy()
            wrong[known] = rng.permutation(code0[known])
            controls.append(score_code(b, mapping, wrong))
        combined, means, _ = fit_code((a + b) / 2, mapping)
        split_codes = [
            fit_code(z[parity::2], mapping[parity::2])[0] for z in [a, b] for parity in [0, 1]
        ]
        soft_arrays[f"frame_{frame}_rx0_means"] = np.array(
            [np.mean(a[mapping == bit]) if known[bit] else np.nan for bit in range(60)]
        )
        soft_arrays[f"frame_{frame}_rx1_means"] = np.array(
            [np.mean(b[mapping == bit]) if known[bit] else np.nan for bit in range(60)]
        )
        soft_arrays[f"frame_{frame}_raw_rx0"] = a
        soft_arrays[f"frame_{frame}_raw_rx1"] = b
        soft_arrays[f"frame_{frame}_mapping"] = mapping
        result = dict(
            frame=frame,
            first_symbol=first,
            last_symbol=first + 63,
            rx0_selection_score=score,
            rx1_heldout_correlation=held,
            wrong_code_max=max(controls),
            receiver_bit_agreement=float(np.mean(code0[known] == code1[known])),
            disagreements=np.flatnonzero(code0 != code1).tolist(),
            rx0_word=bit_word(code0),
            rx1_word=bit_word(code1),
            combined_word=bit_word(combined),
            combined_hex=format(int(bit_word(combined), 2), "015X") if known.all() else None,
            observed_code_slots=int(known.sum()),
            split_code_agreements=[
                float(np.mean(code[known] == combined[known])) for code in split_codes
            ],
            minimum_combined_mean_amplitude=float(abs(means[known]).min()),
            observations_per_bit=count.tolist(),
            trials=trials,
            repeated_code_candidate=bool(
                score > 0.25
                and held > 0.25
                and held > max(controls)
                and np.array_equal(code0, code1)
            ),
        )
        results.append(result)
        print(json.dumps(result), flush=True)
    (out / "tcodes.json").write_text(
        json.dumps(
            dict(
                group=group,
                mapping_validation="qualified-upper" if edge == "upper" else "experimental-lower",
                results=results,
                bins=bins.tolist(),
                convention="T[((n - (16*i mod 60)) mod 1004) mod 60]; "
                "n indexes ascending physical-frequency non-pilot bins; "
                "i is OFDM symbol number; positive deviation maps to 1; ? means unobserved",
                interpretation="Recovered physical-layer repetition codes, "
                "not parsed metadata or user traffic",
            ),
            indent=2,
        )
        + "\n"
    )
    np.savez_compressed(out / "tcode-soft-evidence.npz", **soft_arrays)
    with (out / "recovered-tcodes.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "frame",
                "first_ofdm_symbol",
                "last_ofdm_symbol",
                "tcode_60_bits",
                "tcode_hex_display",
                "rx_agreement",
                "rx1_heldout_correlation",
                "same_weight_wrong_code_max",
                "candidate_passed",
            ]
        )
        for row in results:
            writer.writerow(
                [
                    row["frame"],
                    row["first_symbol"],
                    row["last_symbol"],
                    row["combined_word"],
                    row["combined_hex"],
                    row["receiver_bit_agreement"],
                    row["rx1_heldout_correlation"],
                    row["wrong_code_max"],
                    row["repeated_code_candidate"],
                ]
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ut", action="store_true")
    parser.add_argument("--ut-edge", choices=("upper", "lower"), default="upper")
    parser.add_argument("--group", default="best-upper")
    parser.add_argument("--frames", type=int, default=14)
    parser.add_argument("--allow-lower", action="store_true")
    args = parser.parse_args()
    if args.ut:
        ut_control(args.ut_edge)
    else:
        ds7(args.group, args.frames, allow_lower=args.allow_lower)


if __name__ == "__main__":
    main()
