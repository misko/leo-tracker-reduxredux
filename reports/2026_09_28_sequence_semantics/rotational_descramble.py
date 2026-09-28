"""Reconstruct two rotational PN planes; export header bits with explicit gauge."""

import hashlib
import json
from pathlib import Path

import numpy as np
from phase_lfsr import extend
from rest_signal import SEED
from scipy.io import loadmat

BASE = Path(__file__).parent
ROOT = BASE.parents[1]


def pn_planes(seed, symbols, physical_indices):
    sequence = extend(seed, 32782)
    if not np.array_equal(sequence[:15], sequence[32767:]):
        raise ValueError("Seed did not close at the expected period")
    position = (np.asarray(symbols)[:, None] - 2) * 1020 + physical_indices[None] - 40
    return sequence[position % 32767], sequence[(position + 16383) % 32767]


def main():
    path = BASE / "local/pilot_polarity.npz"
    templatepath = (
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    rotations = loadmat(templatepath)["referenceTemplateRotations"].astype(int)
    archive = np.load(path)
    physical = np.array([k for k in np.argsort(np.fft.fftfreq(1024)) if 2 <= k < 1022])
    keep = ~np.isin(physical, np.r_[488:496, 528:536])
    bins, indices = physical[keep], np.flatnonzero(keep)
    ordered = [archive["bins"].tolist().index(int(b)) for b in bins]
    symbols = np.arange(2, 302)
    received = archive["deviations"][:, 0][:, :, ordered] * np.exp(
        0.5j * np.pi * rotations[bins, 1:].T
    )
    quadrant = np.rint(np.angle(received) / (np.pi / 2)).astype(int) % 4
    # One seed, from one observed symbol, predicts every other symbol and frame.
    seed = (quadrant[0, 0, 32:47] % 2).astype(np.uint8)
    low, high = pn_planes(seed, symbols, indices)
    template_low = rotations[bins, 1:].T % 2
    template_high = (rotations[bins, 1:].T // 2) % 2
    s = np.array([int(c) for c in SEED])
    slots = (np.arange(1004)[None] - 16 * symbols[:, None]) % 60
    residual = template_high ^ s[slots] ^ 1 ^ high
    # Unit complex phase removes the predicted rotational PN without using a
    # header bit decision or independently aligning individual symbol axes.
    descrambled = received * np.exp(-0.5j * np.pi * (low + 2 * high))
    header = descrambled[:, :6]
    good = abs((header / np.maximum(abs(header), 1e-12)).real) > 0.9
    np.savez_compressed(
        BASE / "local/rotational_header_bits.npz",
        bits=(header.real >= 0).astype(np.uint8),
        valid=good,
        soft=header,
        bins=bins,
        frame_labels=np.arange(250, 257),
        symbols=np.arange(2, 8),
    )
    result = dict(
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [path, templatepath]
        },
        seed=seed.tolist(),
        period=32767,
        symbol_stride=1020,
        second_plane_shift=16383,
        low_template_errors=int((low != template_low).sum()),
        low_template_decisions=int(low.size),
        raw_header_low_errors=int(((quadrant[:, :6] % 2) != low[:6]).sum()),
        raw_header_low_decisions=int(quadrant[:, :6].size),
        raw_header_low_error_locations=np.argwhere((quadrant[:, :6] % 2) != low[:6]).tolist(),
        qualified_header_decisions=int(good.sum()),
        high_template_errors_by_symbol=residual.sum(axis=1).tolist(),
        postheader_high_errors=int(residual[12:].sum()),
        postheader_high_decisions=int(residual[12:].size),
        header_positive_fractions=(header.real >= 0).mean(axis=-1).tolist(),
        limitations="Exploratory model inferred from this corpus and empirical template. "
        "Second-plane phase and constant inversion are a selected representation, "
        "not independently verified transmitter wiring. Header signs are not FEC/CRC "
        "decoded. Full-band data remain local and excluded from Git.",
    )
    (BASE / "local/rotational_descramble.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ["input_sha256", "high_template_errors_by_symbol"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
