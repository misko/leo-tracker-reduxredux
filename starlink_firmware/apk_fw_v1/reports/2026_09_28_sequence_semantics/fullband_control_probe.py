"""Falsifiable direct-serialization probe; matches are not decoded packets."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def matches(bits, valid, length, fixed):
    if len(bits) < length:
        return 0, np.array([], dtype=int)
    invalid = np.r_[0, np.cumsum(~valid)]
    keep = (invalid[length:] - invalid[:-length]) == 0
    eligible = int(keep.sum())
    for offset, value in fixed.items():
        keep &= bits[offset : offset + len(keep)] == value
    return eligible, np.flatnonzero(keep)


def rlc_single_sdu_patterns(patterns):
    """Conditional direct layout: one length entry followed by one whole message."""
    result = {}
    for name, (length, fixed) in patterns.items():
        assert length % 8 == 0
        entry = ((length // 8) << 1) | 1
        for header_bits in (8, 20):
            payload_start = ((header_bits + 12 + 7) // 8) * 8
            result[f"RLC{header_bits}_{name}"] = (
                payload_start + length,
                {
                    **{header_bits + i: (entry >> i) & 1 for i in range(12)},
                    **{payload_start + i: value for i, value in fixed.items()},
                },
            )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rlc", action="store_true", help="Test single-SDU RLC envelope hypothesis"
    )
    args = parser.parse_args()
    paths = [
        BASE / "local/full-reference-0-12.npz",
        BASE / "local/soft_tail_boundary.json",
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat",
    ]
    archive = np.load(paths[0])
    rotations = loadmat(paths[2])["referenceTemplateRotations"]
    bins = np.array(
        [
            k
            for k in np.argsort(np.fft.fftfreq(1024))
            if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)
        ]
    )
    z = archive["symbols"][:, 1:, bins] * np.exp(-0.5j * np.pi * rotations[bins, 1:].T)
    boundaries = {
        r["frame"]: r["boundary"]
        for r in json.loads(paths[1].read_text())["rows"]
        if r["flank"] == 1004
    }
    patterns = {
        "PNT": (
            40,
            {**{i: ((13 | (5 << 8)) >> i) & 1 for i in range(11)}, **{i: 0 for i in range(35, 40)}},
        ),
        "minimal_SYSINFO": (
            64,
            {**{i: ((3 << 8) >> i) & 1 for i in range(11)}, **{i: 0 for i in range(59, 64)}},
        ),
    }
    if args.rlc:
        patterns = rlc_single_sdu_patterns(patterns)
    rows = []
    rng = np.random.default_rng(20260929)
    full_valid = (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)
    for frame in range(len(z)):
        full_valid[frame, boundaries[frame] // 1004 :] = False
    original_grid = z.real >= 0
    base_order = np.argsort(~full_valid, axis=0, kind="stable")
    coordinate_controls = []
    for _ in range(5):
        keys = np.where(full_valid, rng.random(z.shape), 2 + np.arange(len(z))[:, None, None])
        random_order = np.argsort(keys, axis=0, kind="stable")
        control = np.empty_like(original_grid)
        np.put_along_axis(
            control, base_order, np.take_along_axis(original_grid, random_order, axis=0), axis=0
        )
        assert np.array_equal(
            (control & full_valid).sum(axis=0), (original_grid & full_valid).sum(axis=0)
        )
        coordinate_controls.append(control)
    for frame in range(len(z)):
        # Only complete OFDM symbols preceding the independently measured tail.
        # This conservative limit is common to both carrier orderings.
        n_symbols = boundaries[frame] // 1004
        for order_name, order in [("physical", np.arange(1004)), ("fft", np.argsort(bins))]:
            values = z[frame, :n_symbols][:, order].reshape(-1)
            valid = (abs(values.imag) < 0.05) & (abs(abs(values.real) - 1) < 0.05)
            original = values.real >= 0
            shuffles = []
            for _ in range(5):
                control = original.copy()
                control[valid] = rng.permutation(original[valid])
                shuffles.append(control)
            for inverted in (False, True):
                for name, (length, fixed) in patterns.items():
                    eligible, starts = matches(original ^ inverted, valid, length, fixed)
                    controls = [
                        len(matches(c ^ inverted, valid, length, fixed)[1]) for c in shuffles
                    ]
                    candidate_words = []
                    for start in starts:
                        sequence = original[start : start + length] ^ inverted
                        word = sum(int(bit) << i for i, bit in enumerate(sequence))
                        candidate_words.append(
                            dict(
                                start=int(start),
                                sign_word_hex=hex(word),
                                **(
                                    dict(
                                        satellite_address_hypothesis=(word >> 11) & 0xFFFFFFFF,
                                        dl_channel_hypothesis=(word >> 43) & 255,
                                        ul_channel_hypothesis=(word >> 51) & 255,
                                    )
                                    if name == "minimal_SYSINFO"
                                    else {}
                                ),
                            )
                        )
                    rows.append(
                        dict(
                            frame=frame,
                            order=order_name,
                            inverted=inverted,
                            pattern=name,
                            eligible=eligible,
                            matches=len(starts),
                            first20_start_offsets=starts[:20].tolist(),
                            shuffled_counts=controls,
                            coordinate_shuffled_counts=[
                                len(
                                    matches(
                                        c[frame, :n_symbols][:, order].reshape(-1) ^ inverted,
                                        valid,
                                        length,
                                        fixed,
                                    )[1]
                                )
                                for c in coordinate_controls
                            ],
                            candidates=candidate_words,
                        )
                    )
    output = dict(
        rows=rows,
        input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        limitation="No FEC decoding. Tests contiguous real-axis sign serialization after "
        "published reference rotation only. Five shuffled controls preserve qualified "
        "sign counts and validity locations per frame/order. They do not model all "
        "correlations; no p-values. Additional controls shuffle qualified signs across "
        "frames independently at each symbol/carrier, preserving coordinate sign counts. "
        "Patterns constrain only16bits and matches are not "
        "verified messages. No satellite-ID mapping, channel-range assumption or "
        "variance plausibility tuning. Tail excluded, mixed regions remain possible.",
    )
    if args.rlc:
        output["limitation"] = (
            "Conditional single-SDU contiguous RLC hypothesis with 8/20-bit header, "
            "one 12-bit byte-length entry and byte-aligned complete control message. "
            "28 fixed bits, no SFID/fragmentation filtering. Not a general RLC decoder. "
            "No FEC, deinterleaving or RF mapping; negative result does not exclude "
            "fragmented/multiple SDUs or other PHY layouts. " + output["limitation"]
        ).replace("Patterns constrain only16bits", "Inner patterns constrain only16bits")
    name = "fullband_rlc_control_probe" if args.rlc else "fullband_control_probe"
    (BASE / f"local/{name}.json").write_text(json.dumps(output, indent=2) + "\n")
    for name in patterns:
        selected = [r for r in rows if r["pattern"] == name]
        print(
            name,
            "eligible",
            sum(r["eligible"] for r in selected),
            "matches",
            sum(r["matches"] for r in selected),
            "shuffled",
            [sum(r["shuffled_counts"][i] for r in selected) for i in range(5)],
        )
        print(
            "coordinate controls",
            [sum(r["coordinate_shuffled_counts"][i] for r in selected) for i in range(5)],
        )


if __name__ == "__main__":
    main()
