"""Probe seven-tap convolutional relations between separate OFDM symbols."""

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from blind_header_114 import mixed_null_check
from scipy.io import loadmat

BASE = Path(__file__).parent


def paired_windows(bits, valid, symbol_pair):
    count = len(bits) // 2 * 2
    difference = bits[:count:2] ^ bits[1:count:2]
    good = valid[:count:2] & valid[1:count:2]
    windows = [
        np.lib.stride_tricks.sliding_window_view(difference[:, s], 7, axis=1) for s in symbol_pair
    ]
    quality = [np.lib.stride_tricks.sliding_window_view(good[:, s], 7, axis=1) for s in symbol_pair]
    return np.concatenate(windows, axis=2), np.concatenate(quality, axis=2).all(axis=2)


def take_word(windows, good, start):
    selected = windows[:, start : start + 32]
    keep = good[:, start : start + 32]
    support = keep.sum(axis=1)
    return selected[keep], bool(support.sum() >= 30 and (support >= 8).all())


def main():
    old_path = BASE / "local/pilot_referenced_header_bits.npz"
    new_path = BASE / "local/full-soft-reference-0-12.npz"
    template_path = (
        BASE.parents[1]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    old = np.load(old_path)
    bins = old["bins"]
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(new_path)["symbols"][:, 1:7][:, :, bins] * np.exp(
        -0.5j * np.pi * template[bins, 1:7].T
    )
    datasets = [
        (old["bits"], old["valid"]),
        (
            (z.real >= 0).astype(np.uint8),
            np.isfinite(z) & (abs(z.real) / np.maximum(abs(z), 1e-20) > 0.9),
        ),
    ]
    counts = dict(
        configurations=0,
        discovery_supported=0,
        discovery_exact=0,
        evaluation_supported=0,
        evaluation_variable=0,
        evaluation_exact=0,
    )
    rows = []
    for order_name, order in (
        ("fft", np.argsort(bins)),
        ("physical", np.argsort(np.fft.fftfreq(1024)[bins])),
    ):
        for direction in (1, -1):
            ids = order[::direction]
            for pair in itertools.combinations(range(6), 2):
                streams = [paired_windows(b[:, :, ids], v[:, :, ids], pair) for b, v in datasets]
                for start in range(len(bins) - 38 + 1):
                    counts["configurations"] += 1
                    train, enough = take_word(*streams[0], start)
                    if not enough:
                        continue
                    counts["discovery_supported"] += 1
                    mask = mixed_null_check(train, activity_floor=0)
                    if mask is None:
                        continue
                    counts["discovery_exact"] += 1
                    evaluation, enough = take_word(*streams[1], start)
                    if not enough:
                        continue
                    counts["evaluation_supported"] += 1
                    selected = np.array([(mask >> j) & 1 for j in range(14)], dtype=bool)
                    variable = bool(
                        (
                            (evaluation[:, selected].mean(axis=0) > 0)
                            & (evaluation[:, selected].mean(axis=0) < 1)
                        ).all()
                    )
                    if not variable:
                        continue
                    counts["evaluation_variable"] += 1
                    errors = int((evaluation[:, selected].sum(axis=1) % 2).sum())
                    counts["evaluation_exact"] += errors == 0
                    rows.append(
                        dict(
                            order=order_name,
                            direction=direction,
                            symbols=[s + 2 for s in pair],
                            start=start,
                            first_bin=int(bins[ids[start]]),
                            mask=mask,
                            evaluation_errors=errors,
                            evaluation_windows=len(evaluation),
                        )
                    )
    output = dict(
        counts=counts,
        candidates=rows,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (old_path, new_path, template_path)
        },
        limitation="Restricted exact seven-tap pair relations across distinct OFDM "
        "symbols and38-carrier blocks. Frame differences cancel fixed masks only. "
        "No full encoder, arbitrary time/frequency interleaver, or noise tolerance. "
        "Same acquisition; different frame sets and processing paths.",
    )
    (BASE / "local/time_separated_code_probe.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
