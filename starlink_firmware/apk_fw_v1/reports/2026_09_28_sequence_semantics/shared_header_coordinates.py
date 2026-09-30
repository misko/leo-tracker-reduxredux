"""Extract empirical binary coordinates represented in both header symbols."""

import hashlib
import json
from pathlib import Path

import numpy as np
from header_block_predictor import fit
from header_block_rank import rank
from header_rectangle_rank import packed_rows
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def shared_rules(bits, width):
    _, rules = fit(bits)
    results = []
    for r in rules:
        positions = r["inputs"] + [r["output"]]
        left = sorted(i for i in positions if i < width)
        right = sorted(i for i in positions if i >= width)
        if not left or not right:
            continue
        trace = np.bitwise_xor.reduce(bits[:, left], axis=1)
        normalized = trace ^ trace[0]
        word = packed_rows(normalized[None])[0]
        if word:
            results.append(
                dict(
                    left=left, right=right, constant=r["constant"], trace=trace.tolist(), word=word
                )
            )
    return results


def main():
    control_path = BASE / "local/rectangle_rank_control.json"
    prior = json.loads(control_path.read_text())
    for path, digest in prior["input_sha256"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    source = BASE / "local/header-reference-0-77.npz"
    template_path = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(source)["symbols"] * np.exp(-0.5j * np.pi * template[:, 1:7].T)
    bits = (z.real >= 0).astype(np.uint8)
    raw_path = BASE / "local/pilot_referenced_header_bits.npz"
    raw = np.load(raw_path)
    binmap = {int(b): i for i, b in enumerate(raw["bins"])}
    groups, windows = {}, []
    for c in prior["rows"]:
        if c["shifted_at_most32"]:
            continue
        symbols = [s - 2 for s in c["symbols"]]
        start, width = c["start_bin"], 57
        rectangle = bits[:, symbols, start : start + width].reshape(78, 114)
        rules = shared_rules(rectangle, width)
        dimension = rank([r["word"] for r in rules])
        assert dimension == c["individual_rank_sum"] - c["observed"]
        windows.append(dict(symbols=c["symbols"], start_bin=start, shared_dimensions=dimension))
        for rule in rules:
            left = [(symbols[0] + 2, start + i) for i in rule["left"]]
            right = [(symbols[1] + 2, start + i - width) for i in rule["right"]]
            coords = left + right
            selected = raw["bits"][:, [s - 2 for s, b in coords], [binmap[b] for s, b in coords]]
            valid = raw["valid"][:, [s - 2 for s, b in coords], [binmap[b] for s, b in coords]].all(
                axis=1
            )
            left_trace = np.bitwise_xor.reduce(selected[:, : len(left)], axis=1)
            right_trace = np.bitwise_xor.reduce(selected[:, len(left) :], axis=1) ^ rule["constant"]
            record = dict(
                left=left,
                right=right,
                constant=rule["constant"],
                reference_bits="".join(map(str, rule["trace"])),
                ones=sum(rule["trace"]),
                raw_left_bits="".join(map(str, left_trace.tolist())),
                raw_right_bits="".join(map(str, right_trace.tolist())),
                raw_valid=valid.tolist(),
                raw_errors=int(((left_trace != right_trace) & valid).sum()),
            )
            word = rule["word"]
            if word not in groups or len(coords) < len(groups[word]["left"]) + len(
                groups[word]["right"]
            ):
                groups[word] = record
    entries = list(groups.values())
    state_words = ["".join(r["reference_bits"][i] for r in entries) for i in range(78)]
    vocabulary = list(dict.fromkeys(state_words))
    states = [vocabulary.index(w) for w in state_words]
    summary = dict(
        windows=len(windows),
        distinct_traces_up_to_inversion=len(entries),
        union_binary_rank=rank(list(groups)),
        distinct_shared_states=len(vocabulary),
        state_counts=[states.count(i) for i in range(len(vocabulary))],
        min_reference_ones=min(min(r["ones"], 78 - r["ones"]) for r in entries),
        max_reference_minority=max(min(r["ones"], 78 - r["ones"]) for r in entries),
        raw_nonconstant=sum(
            len(set(np.array(list(r["raw_left_bits"]))[r["raw_valid"]])) > 1 for r in entries
        ),
    )
    output = dict(
        summary=summary,
        windows=windows,
        coordinates=entries,
        reference_state_indices=states,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, template_path, raw_path, control_path)
        },
        limitation="Empirical coordinates fitted on all78 reference frames and "
        "selected rectangles; not transmitter source bits or semantic fields. "
        "Equal observed traces need not be equal outside these observations. "
        "Raw checks are another portion of the same acquisition.",
    )
    (BASE / "local/shared_header_coordinates.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
