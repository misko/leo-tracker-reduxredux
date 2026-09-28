"""Search exact seven-tap convolutional relations without chosen generators."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from short_header_parity import check_score, pair_windows

BASE = Path(__file__).parent


def mixed_null_check(windows, activity_floor=0.1):
    """Return a nontrivial homogeneous check using variable columns in both streams."""
    means = windows.mean(axis=0)
    active = (means > 0) & (means < 1)
    active &= (means >= activity_floor) & (means <= 1 - activity_floor)
    rows = list(map(int, windows.astype(np.int64) @ (1 << np.arange(14))))
    rows.extend(1 << j for j in range(14) if not active[j])
    pivots = {}
    for row in rows:
        while row:
            bit = row.bit_length() - 1
            if bit not in pivots:
                pivots[bit] = row
                break
            row ^= pivots[bit]
    basis = []
    for free in range(14):
        if free in pivots:
            continue
        mask = 1 << free
        for bit, row in sorted(pivots.items()):
            if (row & mask).bit_count() % 2:
                mask |= 1 << bit
        basis.append(mask)
    # If no basis vector mixes streams, a pair of opposite-stream vectors does.
    candidates = basis + [a ^ b for a, b in itertools.combinations(basis, 2)]
    candidates = [m for m in candidates if m & 127 and m >> 7]
    return min(candidates, key=lambda m: (m.bit_count(), m)) if candidates else None


def serialized_words(words, layout):
    if layout == "interleaved":
        return words
    if layout == "stream_blocks":
        return words.reshape(*words.shape[:-1], 3, 38).swapaxes(-1, -2).reshape(words.shape)
    raise ValueError(f"Unknown layout {layout}")


def qualified_checks(words, quality, layout, pair):
    windows = pair_windows(serialized_words(words, layout), 0, pair)
    keep = pair_windows(serialized_words(quality, layout), 0, pair).all(axis=1)
    support = keep.reshape(len(words), -1).sum(axis=1)
    enough = int(keep.sum()) >= 30 and bool((support >= 8).all())
    return windows[keep], support.tolist(), enough


def ordered_symbol_span(data, count, symbol, ids, crossing=False):
    width = 2 if crossing else 1
    return data[:count, symbol : symbol + width][:, :, ids].reshape(count, -1)


def main(layout="interleaved", activity_floor=0.1, quality_mode="whole_word", boundaries="within"):
    paths = [
        BASE / "local/pilot_referenced_header_bits.npz",
        BASE / "local/full-reference-0-12.npz",
    ]
    old, new = [np.load(p) for p in paths]
    bins = old["bins"]
    template_path = (
        BASE.parents[1]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    template = np.exp(0.5j * np.pi * loadmat(template_path)["referenceTemplateRotations"])
    z = new["symbols"][:, 1:7][:, :, bins] * template[bins, 1:7].T.conj()
    bits = [old["bits"], (z.real >= 0).astype(np.uint8)]
    valid = [old["valid"], (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)]
    candidates = []
    tested = 0
    coverage = dict(total_windows=0, quality_rejected=0, activity_rejected=0, admitted=0)
    coverage["pair_support_rejected"] = 0
    for order_name, order in [
        ("physical", np.argsort(np.fft.fftfreq(1024)[bins])),
        ("fft", np.argsort(bins)),
    ]:
        crossing = boundaries == "crossing"
        for direction, symbol in itertools.product([1, -1], range(5 if crossing else 6)):
            ids = order[::direction]
            datasets = []
            for b, v in zip(bits, valid, strict=True):
                count = len(b) // 2 * 2
                b = ordered_symbol_span(b, count, symbol, ids, crossing)
                v = ordered_symbol_span(v, count, symbol, ids, crossing)
                datasets.append((b[::2] ^ b[1::2], v[::2] & v[1::2]))
            discovery, quality = datasets[0]
            starts = range(len(ids) - 113, len(ids)) if crossing else range(len(ids) - 113)
            for start in starts:
                words = discovery[:, start : start + 114]
                coverage["total_windows"] += 1
                if quality_mode == "whole_word" and not quality[:, start : start + 114].all():
                    coverage["quality_rejected"] += 1
                    continue
                activity = float(words.mean())
                if not 0 < activity < 1 or not activity_floor <= activity <= 1 - activity_floor:
                    coverage["activity_rejected"] += 1
                    continue
                coverage["admitted"] += 1
                for pair in itertools.combinations(range(3), 2):
                    w = pair_windows(serialized_words(words, layout), 0, pair)
                    discovery_support = [32] * len(words)
                    if quality_mode == "parity_window":
                        w, discovery_support, enough = qualified_checks(
                            words, quality[:, start : start + 114], layout, pair
                        )
                        if not enough:
                            coverage["pair_support_rejected"] += 1
                            continue
                    tested += 1
                    mask = mixed_null_check(w, activity_floor)
                    if mask is None:
                        continue
                    evaluation, q = datasets[1]
                    e = pair_windows(
                        serialized_words(evaluation[:, start : start + 114], layout), 0, pair
                    )
                    evaluation_support = [32] * len(evaluation)
                    evaluation_qualified = bool(q[:, start : start + 114].all())
                    if quality_mode == "parity_window":
                        e, evaluation_support, evaluation_qualified = qualified_checks(
                            evaluation[:, start : start + 114],
                            q[:, start : start + 114],
                            layout,
                            pair,
                        )
                    selected_columns = ((mask >> np.arange(14)) & 1).astype(bool)
                    variable_evaluation = bool(len(e)) and bool(
                        (
                            (e[:, selected_columns].mean(axis=0) > 0)
                            & (e[:, selected_columns].mean(axis=0) < 1)
                        ).all()
                    )
                    candidates.append(
                        dict(
                            order=order_name,
                            direction=direction,
                            symbol=symbol + 2,
                            start=start,
                            first_bin=int(bins[ids[start]]),
                            pair=pair,
                            mask=mask,
                            discovery_activity=activity,
                            discovery=check_score(w, mask),
                            evaluation=check_score(e, mask) if len(e) else None,
                            evaluation_qualified=evaluation_qualified,
                            evaluation_columns_variable=variable_evaluation,
                            discovery_support=discovery_support,
                            evaluation_support=evaluation_support,
                        )
                    )
    result = dict(
        layout=layout,
        activity_floor=activity_floor,
        quality_mode=quality_mode,
        boundaries=boundaries,
        coverage=coverage,
        tested=tested,
        exact_discovery_candidates=candidates,
        exact_evaluation=sum(
            c["evaluation"] == 1 and c["evaluation_qualified"] and c["evaluation_columns_variable"]
            for c in candidates
        ),
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths + [template_path]
        },
        scope="114-bit windows under specified boundary mode and serialization; all starts, "
        "two carrier orders "
        "and directions, each pair of three streams, all homogeneous seven-tap checks "
        "on variable columns. Fixed masks cancel by frame XOR. Exact checks only; "
        "noise, interleaving, variable masks and low-activity regions remain limitations. "
        "Discovery/evaluation reuse prior UT frames from the same recording.",
    )
    suffix = "" if layout == "interleaved" else "_stream_blocks"
    if activity_floor != 0.1:
        suffix += f"_activity_{activity_floor:g}"
    if quality_mode != "whole_word":
        suffix += "_parity_window"
    if crossing:
        suffix += "_crossing"
    (BASE / f"local/blind_header_114{suffix}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ("input_sha256", "exact_discovery_candidates")
            },
            indent=2,
        )
    )
    print("Exact discovery candidates:", len(candidates))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", choices=["interleaved", "stream_blocks"], default="interleaved")
    parser.add_argument("--activity-floor", type=float, default=0.1)
    parser.add_argument(
        "--quality-mode", choices=["whole_word", "parity_window"], default="whole_word"
    )
    parser.add_argument("--boundaries", choices=["within", "crossing"], default="within")
    args = parser.parse_args()
    if not 0 <= args.activity_floor <= 0.5:
        parser.error("activity floor must be in [0, 0.5]")
    main(args.layout, args.activity_floor, args.quality_mode, args.boundaries)
