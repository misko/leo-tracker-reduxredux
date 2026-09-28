"""Search seven-tap convolutional checks in surviving two-symbol rectangles."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from blind_header_114 import mixed_null_check, serialized_words
from scipy.io import loadmat

BASE = Path(__file__).parent


def windows(words, pair):
    triples = words.reshape(len(words), 38, 3)
    w = np.lib.stride_tricks.sliding_window_view(triples, 7, axis=1)
    return np.concatenate([w[:, :, pair[0]], w[:, :, pair[1]]], axis=-1).reshape(-1, 14)


def violations(w, mask):
    columns = [i for i in range(14) if mask >> i & 1]
    return int(np.bitwise_xor.reduce(w[:, columns], axis=1).sum())


def within_state_differences(words, states, split=39):
    anchors = {
        int(s): int(np.flatnonzero(states[:split] == s)[0]) for s in np.unique(states[:split])
    }
    train = [
        words[i] ^ words[anchors[int(states[i])]]
        for i in range(split)
        if i != anchors[int(states[i])]
    ]
    held = [
        words[i] ^ words[anchors[int(states[i])]]
        for i in range(split, len(words))
        if int(states[i]) in anchors
    ]
    return np.asarray(train, dtype=np.uint8), np.asarray(held, dtype=np.uint8)


def main(state_conditioned=False):
    prior_path = BASE / "local/header_rectangle_rank.json"
    prior = json.loads(prior_path.read_text())
    for path, digest in prior["input_sha256"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    candidates = [
        r for r in prior["rows"] if r["combined_rank"] is not None and r["combined_rank"] <= 32
    ]
    source = BASE / "local/header-reference-0-77.npz"
    template_path = (
        BASE.parents[1]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(source)["symbols"] * np.exp(-0.5j * np.pi * template[:, 1:7].T)
    bits = (z.real >= 0).astype(np.uint8)
    state_path = BASE / "local/shared_header_coordinates.json"
    states = (
        np.array(json.loads(state_path.read_text())["reference_state_indices"])
        if state_conditioned
        else None
    )
    rows, trials = [], 0
    for candidate in candidates:
        assert candidate["width"] == 57 and len(candidate["symbols"]) == 2
        symbols = [s - 2 for s in candidate["symbols"]]
        start = candidate["start_bin"]
        rectangle = bits[:, symbols, start : start + 57]
        for sf, ff, order, layout in itertools.product(
            (1, -1), (1, -1), ("symbol", "carrier"), ("interleaved", "stream_blocks")
        ):
            ordered = rectangle[:, ::sf, ::ff]
            if order == "carrier":
                ordered = ordered.swapaxes(1, 2)
            words = serialized_words(ordered.reshape(78, 114), layout)
            if state_conditioned:
                discovery_differences, evaluation_differences = within_state_differences(
                    words, states
                )
            else:
                differences = words ^ words[0]
                discovery_differences, evaluation_differences = differences[1:39], differences[39:]
            for pair in itertools.combinations(range(3), 2):
                trials += 1
                train = windows(discovery_differences, pair)
                mask = mixed_null_check(train, activity_floor=0)
                if mask is None:
                    continue
                held = windows(evaluation_differences, pair)
                rows.append(
                    dict(
                        symbols=candidate["symbols"],
                        start_bin=start,
                        symbol_direction=sf,
                        carrier_direction=ff,
                        order=order,
                        layout=layout,
                        streams=pair,
                        mask=mask,
                        discovery_windows=len(train),
                        evaluation_windows=len(held),
                        evaluation_errors=violations(held, mask),
                    )
                )
    summary = dict(
        rectangles=len(candidates),
        trials=trials,
        discovery_checks=len(rows),
        exact_evaluation_checks=sum(r["evaluation_errors"] == 0 for r in rows),
        state_conditioned=state_conditioned,
        discovery_difference_frames=len(discovery_differences),
        evaluation_difference_frames=len(evaluation_differences),
    )
    output = dict(
        summary=summary,
        rows=rows,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                (source, template_path, prior_path, state_path)
                if state_conditioned
                else (source, template_path, prior_path)
            )
        },
        limitation="Restricted three-stream/seven-tap mappings within rectangles. "
        "Frame XOR cancels fixed masks. Constant columns excluded. Candidates "
        "previously selected using all78frames; no independent significance claim. "
        "Exact checks sensitive to errors; other interleavers/generator memories "
        "and nonlinear or state-dependent mappings remain untested.",
        conditioning_note="When enabled, each discovery state uses its first discovery frame "
        "as fixed XOR anchor. Later unknown states abstain. Cancels fixed state-dependent "
        "masks but still assumes common encoder across states. State definitions use all78frames.",
    )
    name = (
        "rectangle_convolution_state_conditioned"
        if state_conditioned
        else "rectangle_convolution_probe"
    )
    (BASE / f"local/{name}.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-conditioned", action="store_true")
    main(parser.parse_args().state_conditioned)
