"""Test whether changes concentrate on a fixed repeated-carrier bit grid."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).parent


def transition_counts(bits, valid, width):
    count = len(bits) // 2 * 2
    d = bits[:count:2] ^ bits[1:count:2]
    good = valid[:count:2] & valid[1:count:2]
    changed = d[:, 1:] != d[:, :-1]
    usable = good[:, 1:] & good[:, :-1]
    slots = np.arange(1, bits.shape[1]) % width
    transitions = np.array(
        [(changed[:, slots == i] & usable[:, slots == i]).sum() for i in range(width)]
    )
    support = np.array([usable[:, slots == i].sum() for i in range(width)])
    return transitions, support


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
    rows = []
    for order_name, order in [
        ("fft", np.argsort(bins)),
        ("physical", np.argsort(np.fft.fftfreq(1024)[bins])),
    ]:
        for symbol in range(6):
            for width in range(2, 33):
                counts = [
                    transition_counts(b[:, symbol, order], v[:, symbol, order], width)
                    for b, v in datasets
                ]
                changes, support = counts[0]
                offset = int(np.argmax(changes / np.maximum(support, 1)))
                changes, support = counts[1]
                rows.append(
                    dict(
                        order=order_name,
                        symbol=symbol + 2,
                        width=width,
                        offset=offset,
                        evaluation_transitions=int(changes.sum()),
                        evaluation_grid_transitions=int(changes[offset]),
                        evaluation_grid_fraction=float(changes[offset] / changes.sum()),
                        evaluation_support_fraction=float(support[offset] / support.sum()),
                    )
                )
    result = dict(
        rows=rows,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (old_path, new_path, template_path)
        },
        limitation="Fixed integer carrier repetition widths2..32 after fixed-mask "
        "cancellation by frame XOR. No variable grids, independent symbol offsets, "
        "pilot-advancing layouts or formal noise model. Grid selected using raw "
        "discovery frames only; evaluated on different frames from same acquisition.",
    )
    (BASE / "local/header_repetition_grid.json").write_text(json.dumps(result, indent=2) + "\n")
    for symbol in (2, 4):
        for width in (2, 4, 8, 16):
            print(
                next(
                    r
                    for r in rows
                    if r["order"] == "physical" and r["symbol"] == symbol and r["width"] == width
                )
            )


if __name__ == "__main__":
    main()
