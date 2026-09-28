"""Noise-tolerant mixed parity search across full OFDM-symbol pairs."""

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from short_header_parity import check_score, walsh
from time_separated_code_probe import paired_windows

BASE = Path(__file__).parent


def choose_check(windows):
    means = windows.mean(axis=0)
    active = (means >= 0.1) & (means <= 0.9)
    allowed = int(active.astype(np.int64) @ (1 << np.arange(14)))
    masks = np.array(
        [
            m
            for m in range(1, 16384)
            if m & 127 and m >> 7 and 4 <= m.bit_count() <= 10 and not m & ~allowed
        ]
    )
    if not len(masks):
        return None
    packed = windows.astype(np.int64) @ (1 << np.arange(14))
    scores = walsh(np.bincount(packed, minlength=16384)) / len(windows)
    excess = scores[masks] - scores[masks & 127] * scores[masks & (127 << 7)]
    mask = int(masks[np.argmax(abs(excess))])
    return mask, float(scores[mask]), len(masks)


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
    for name, order in (
        ("fft", np.argsort(bins)),
        ("physical", np.argsort(np.fft.fftfreq(1024)[bins])),
    ):
        for direction in (1, -1):
            ids = order[::direction]
            for pair in itertools.combinations(range(6), 2):
                windows = []
                for bits, valid in datasets:
                    w, q = paired_windows(bits[:, :, ids], valid[:, :, ids], pair)
                    windows.append(w[q])
                assert min(map(len, windows)) >= 100
                selected = choose_check(windows[0])
                if selected is None:
                    continue
                mask, score, count = selected
                discovery_baseline = check_score(windows[0], mask & 127) * check_score(
                    windows[0], mask & (127 << 7)
                )
                discovery_excess = score - discovery_baseline
                direction_sign = 1 if discovery_excess >= 0 else -1
                evaluation = direction_sign * check_score(windows[1], mask)
                columns = np.flatnonzero((mask >> np.arange(14)) & 1)
                baseline = direction_sign * np.prod(1 - 2 * windows[1][:, columns].mean(axis=0))
                stream_baseline = (
                    direction_sign
                    * check_score(windows[1], mask & 127)
                    * check_score(windows[1], mask & (127 << 7))
                )
                rows.append(
                    dict(
                        order=name,
                        direction=direction,
                        symbols=[s + 2 for s in pair],
                        mask=mask,
                        mask_candidates=count,
                        discovery_abs_correlation=abs(score),
                        discovery_absolute_excess=abs(discovery_excess),
                        evaluation_correlation=evaluation,
                        evaluation_marginal_correlation=float(baseline),
                        evaluation_stream_parity_baseline=float(stream_baseline),
                        evaluation_excess=float(evaluation - stream_baseline),
                        windows=list(map(len, windows)),
                    )
                )
    best = max(rows, key=lambda r: r["discovery_absolute_excess"])
    result = dict(
        rows=rows,
        discovery_selected=best,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (old_path, new_path, template_path)
        },
        limitation="Whole-symbol pooled seven-tap relations, weights4..10, variable "
        "columns only. Overlapping windows/duplicate orders are dependent. Weak "
        "short embedded codes may be diluted. Different frames, same acquisition. "
        "No full encoder/FEC decode or formal significance threshold.",
    )
    (BASE / "local/noisy_time_code_probe.json").write_text(json.dumps(result, indent=2) + "\n")
    print("configurations", len(rows), "mask candidates", sum(r["mask_candidates"] for r in rows))
    print(json.dumps(best, indent=2))


if __name__ == "__main__":
    main()
