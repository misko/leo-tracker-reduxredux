"""Test direct binary boundary fields in early signs with a fixed XOR mask."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def probe(bits, valid, labels, split=6):
    width = labels.shape[1]
    windows = np.lib.stride_tricks.sliding_window_view(bits, width, axis=1)
    quality = np.lib.stride_tricks.sliding_window_view(valid, width, axis=1)
    supported = quality[:split].all(axis=(0, 2))
    differences = windows ^ labels[:, None, :]
    masks = differences[:split].sum(axis=0) > split / 2
    errors = (differences[:split] != masks).sum(axis=(0, 2))
    starts = np.flatnonzero(supported)
    if not len(starts):
        return dict(supported_starts=0, exact_discovery_starts=0)
    selected = int(starts[np.argmin(errors[starts])])
    evaluation_valid = quality[split:, selected]
    evaluation_errors = (differences[split:, selected] != masks[selected]) & evaluation_valid
    exact = starts[errors[starts] == 0]
    validated = [
        int(start)
        for start in exact
        if quality[split:, start].all()
        and np.array_equal(
            differences[split:, start],
            np.broadcast_to(masks[start], differences[split:, start].shape),
        )
    ]
    return dict(
        supported_starts=len(starts),
        exact_discovery_starts=len(exact),
        exact_full_evaluation_starts=validated,
        selected_start=selected,
        discovery_errors=int(errors[selected]),
        discovery_decisions=split * width,
        evaluation_errors=int(evaluation_errors.sum()),
        evaluation_decisions=int(evaluation_valid.sum()),
        fixed_xor_mask=masks[selected].astype(int).tolist(),
    )


def main():
    source = BASE / "local/full-soft-reference-0-12.npz"
    boundary_path = BASE / "local/soft_tail_boundary.json"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    bounds = np.array(
        [r["boundary"] for r in json.loads(boundary_path.read_text())["rows"] if r["flank"] == 502]
    )
    fields = dict(
        compact_boundary=(bounds, 18),
        symbol_offset=(bounds // 1004, 8),
        carrier_offset=(bounds % 1004, 10),
        remaining_carriers=(301200 - bounds, 19),
    )
    bins = np.array(
        [k for k in range(2, 1022) if k not in range(488, 496) and k not in range(528, 536)]
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(source)["symbols"][:, 1:7, bins] * np.exp(-0.5j * np.pi * template[bins, 1:7].T)
    valid = np.isfinite(z) & (abs(z.real) / np.maximum(abs(z), 1e-20) > 0.9)
    rows = []
    for name, order in (
        ("fft", np.arange(len(bins))),
        ("physical", np.argsort(np.fft.fftfreq(1024)[bins])),
    ):
        for reverse in (False, True):
            index = order[::-1] if reverse else order
            bits = (z[:, :, index].real >= 0).reshape(13, -1)
            quality = valid[:, :, index].reshape(13, -1)
            for field, (values, width) in fields.items():
                for bit_order in ("lsb", "msb"):
                    shifts = np.arange(width) if bit_order == "lsb" else np.arange(width)[::-1]
                    labels = ((values[:, None] >> shifts) & 1).astype(bool)
                    result = probe(bits, quality, labels)
                    rows.append(
                        dict(
                            order=name,
                            reverse=reverse,
                            field=field,
                            bit_order=bit_order,
                            width=width,
                            **result,
                        )
                    )
    output = dict(
        rows=rows,
        discovery_frames=list(range(6)),
        evaluation_frames=list(range(6, 13)),
        symbols=[2, 7],
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, boundary_path, template_path)
        },
        limitation="Direct contiguous binary-field hypothesis only, allowing fixed "
        "positionwise XOR masks. No variable scrambling, coding, byte-layout search, "
        "or arbitrary field transforms. Previously examined single acquisition.",
    )
    (BASE / "local/header_boundary_fields.json").write_text(json.dumps(output, indent=2) + "\n")
    print(
        "supported",
        sum(r["supported_starts"] for r in rows),
        "exact discovery",
        sum(r["exact_discovery_starts"] for r in rows),
        "validated",
        sum(len(r.get("exact_full_evaluation_starts", [])) for r in rows),
    )
    print(
        "best discovery",
        min(rows, key=lambda r: r.get("discovery_errors", 1000000) / (6 * r["width"])),
    )


if __name__ == "__main__":
    main()
