"""Chronological tests of decoded phase state and a header de-tessellation hypothesis."""

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict

import numpy as np
from phase_model import BASE, JOINT, OUT

sys.path.insert(0, str((BASE.parents[3] / "reports") / "2026_09_27_ds7_header"))
from tcodes import references, slots  # noqa: E402


def mode(values):
    return min(Counter(values), key=lambda value: (-Counter(values)[value], value))


def offsets(rows, slope):
    by_visit = defaultdict(list)
    for r in rows:
        by_visit[r["signal"]].append((r["phase_index"] - slope * r["frame"]) % 60)
    return {visit: mode(values) for visit, values in by_visit.items()}


def affine_predict(rows, slope, per_visit):
    return [(slope * r["frame"] + per_visit[r["signal"]]) % 60 for r in rows]


def chronological_pairs(rows, lower, upper):
    keyed = {(r["signal"], r["frame"]): r for r in rows}
    return [
        (r, keyed[(r["signal"], r["frame"] + 1)])
        for r in rows
        if lower <= r["frame"] < upper - 1 and (r["signal"], r["frame"] + 1) in keyed
    ]


def evaluate_header(bits, valid, train, test):
    counts = valid[train].sum(axis=0)
    means = np.divide(
        (bits[train] * valid[train]).sum(axis=0),
        counts,
        out=np.zeros_like(counts, float),
        where=counts > 0,
    )
    stable = (counts >= 8) & (abs(means) >= 0.8)
    predicted = np.where(means >= 0, 1, -1)
    tested = valid[test] & stable
    matches = tested & (bits[test] == predicted)
    return dict(
        eligible_positions=int((counts >= 8).sum()),
        corroborated_training_bits=int(valid[train].sum()),
        stable_positions=int(stable.sum()),
        stable_position_indices=np.argwhere(stable).tolist(),
        evaluated_bits=int(tested.sum()),
        evaluation_agreement=float(matches.sum() / tested.sum()) if tested.any() else None,
        per_symbol_stable=stable.sum(axis=1).tolist(),
    )


def phase_header_fields(bits, valid, phases, train, test):
    """Test literal phase bits and their affine binary combinations on held-out frames."""
    parity = np.array([[(int(k) & mask).bit_count() % 2 for mask in range(64)] for k in phases])
    signs = 2 * parity - 1
    rows = []
    for symbol in range(bits.shape[1]):
        for carrier in range(bits.shape[2]):
            tr = train & valid[:, symbol, carrier]
            te = test & valid[:, symbol, carrier]
            if tr.sum() < 20 or te.sum() < 20:
                continue
            target = bits[:, symbol, carrier]
            correlations = np.mean(signs[tr] * target[tr, None], axis=0)
            mask = int(np.argmax(abs(correlations)))
            flip = 1 if correlations[mask] >= 0 else -1
            prediction = signs[te, mask] * flip
            baseline = 1 if target[tr].mean() >= 0 else -1
            rows.append(
                dict(
                    symbol=symbol + 2,
                    carrier_index=carrier,
                    phase_bit_mask=mask,
                    polarity=flip,
                    discovery_agreement=(1 + abs(correlations[mask])) / 2,
                    evaluation_n=int(te.sum()),
                    evaluation_agreement=float(np.mean(prediction == target[te])),
                    baseline_agreement=float(np.mean(target[te] == baseline)),
                )
            )
    return rows


def main():
    with (OUT / "phase_indices.csv").open() as stream:
        rows = [
            dict(signal=r["signal"], frame=int(r["frame"]), phase_index=int(r["phase_index"]))
            for r in csv.DictReader(stream)
            if r["signal"] != "UT-ref"
        ]
    # One fixed chronological boundary across each 89-frame local excerpt.
    discovery = [r for r in rows if r["frame"] < 22]
    validation = [
        r for r in rows if 22 <= r["frame"] < 44 and r["signal"] in {x["signal"] for x in discovery}
    ]
    trials = []
    for slope in range(60):
        predicted = affine_predict(validation, slope, offsets(discovery, slope))
        trials.append(
            dict(
                slope=slope,
                hits=sum(p == r["phase_index"] for p, r in zip(predicted, validation, strict=True)),
            )
        )
    best = max(trials, key=lambda r: r["hits"])["slope"]
    train = [r for r in rows if r["frame"] < 44]
    evaluation = [
        r for r in rows if r["frame"] >= 44 and r["signal"] in {x["signal"] for x in train}
    ]
    predicted = affine_predict(evaluation, best, offsets(train, best))
    baseline = affine_predict(evaluation, 0, offsets(train, 0))
    train_pairs = chronological_pairs(rows, 0, 44)
    test_pairs = chronological_pairs(rows, 44, 90)
    candidates = []
    for a in range(60):
        bs = [(q["phase_index"] - a * p["phase_index"]) % 60 for p, q in train_pairs]
        b = mode(bs)
        candidates.append((bs.count(b), a, b))
    _, a, b = max(candidates, key=lambda r: r[0])
    transitions = defaultdict(set)
    for p, q in chronological_pairs(rows, 0, 90):
        transitions[(p["signal"], p["phase_index"])].add(q["phase_index"])
    temporal = dict(
        selected_frame_slope=best,
        discovery_validation_trials=trials,
        evaluation_count=len(evaluation),
        evaluation_correct=sum(
            p == r["phase_index"] for p, r in zip(predicted, evaluation, strict=True)
        ),
        per_visit_mode_correct=sum(
            p == r["phase_index"] for p, r in zip(baseline, evaluation, strict=True)
        ),
        lcg=dict(
            a=a,
            b=b,
            train_pairs=len(train_pairs),
            evaluation_pairs=len(test_pairs),
            evaluation_correct=sum(
                (a * p["phase_index"] + b) % 60 == q["phase_index"] for p, q in test_pairs
            ),
            persistence_correct=sum(p["phase_index"] == q["phase_index"] for p, q in test_pairs),
        ),
        branching_states=sum(len(v) > 1 for v in transitions.values()),
    )

    model = json.loads((OUT / "phase_model.json").read_text())
    codes = np.array([[2 * int(bit) - 1 for bit in w] for w in model["generated_words"]])
    headers = []
    for path in sorted(OUT.glob("S*-soft.npz")):
        signal = path.name.split("-")[0]
        archive = np.load(path)
        b0, b1 = archive["bins0"], archive["bins1"]
        common = np.intersect1d(b0, b1)
        z0, z1 = [
            archive[f"z{i}"][:, :12, [list(b).index(k) for k in common]]
            for i, b in enumerate([b0, b1])
        ]
        states = {r["frame"]: r["phase_index"] for r in rows if r["signal"] == signal}
        frames = sorted(states)
        x, y = z0[frames], z1[frames]
        valid = (
            (x.real * y.real > 0)
            & (abs(x.real) > 0.25)
            & (abs(y.real) > 0.25)
            & (abs(x.real) > 0.85 * abs(x))
            & (abs(y.real) > 0.85 * abs(y))
        )
        bits = np.where(x.real >= 0, 1, -1)
        mapping = slots(common, np.arange(2, 14))
        modulation = codes[[states[f] for f in frames]][:, mapping]
        train_mask = np.array(frames) < 44
        test_mask = ~train_mask
        headers.append(
            dict(
                signal=signal,
                header_ofdm_symbols=list(range(2, 14)),
                header_bins=common.tolist(),
                train_frames=int(train_mask.sum()),
                evaluation_frames=int(test_mask.sum()),
                raw=evaluate_header(bits, valid, train_mask, test_mask),
                phase_removed=evaluate_header(bits * modulation, valid, train_mask, test_mask),
            )
        )
    ut_rows = json.loads((OUT / "UT-windows.json").read_text())["results"]
    lookup = {w: k for k, w in enumerate(model["generated_words"])}
    ut_states = {r["frame"]: lookup[r["word"]] for r in ut_rows if r["accepted"]}
    _, template, _ = references()
    pieces, bins = [], []
    for start in [100, 200]:
        data = np.load(JOINT / f"ut-codebook/bins-{start}.npz")
        pieces.append(data["symbols"][:, 1:13] * template[data["bins"], 1:13].T.conj())
        bins.extend(data["bins"].tolist())
    ut_frames = sorted(ut_states)
    z = np.concatenate(pieces, axis=2)[ut_frames]
    ut_valid = np.isfinite(z) & (abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)
    ut_bits = np.where(z.real >= 0, 1, -1)
    ut_modulation = codes[[ut_states[f] for f in ut_frames]][
        :, slots(np.array(bins), np.arange(2, 14))
    ]
    ut_train = np.array(ut_frames) < 466
    ut_test = ~ut_train
    ut_header = dict(
        header_ofdm_symbols=list(range(2, 14)),
        header_bins=bins,
        training_frames=int(ut_train.sum()),
        evaluation_frames=int(ut_test.sum()),
        raw=evaluate_header(ut_bits, ut_valid, ut_train, ut_test),
        phase_removed=evaluate_header(ut_bits * ut_modulation, ut_valid, ut_train, ut_test),
        phase_field_tests=phase_header_fields(
            ut_bits, ut_valid, [ut_states[f] for f in ut_frames], ut_train, ut_test
        ),
        scope="Published hard-symbol header at eight carriers, first 466 dataset frames "
        "for discovery and remaining frames for evaluation; only frames with a recovered phase.",
    )
    output = dict(
        temporal=temporal,
        header=headers,
        ut_header=ut_header,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                OUT / "phase_indices.csv",
                OUT / "phase_model.json",
                OUT / "UT-windows.json",
                JOINT / "ut-codebook/bins-100.npz",
                JOINT / "ut-codebook/bins-200.npz",
                *sorted(OUT.glob("S*-soft.npz")),
            ]
        },
        limits="Chronological evaluation reuses inspected recordings. Phase-index zero and "
        "direction are mathematical conventions, not a decoded field layout. "
        "Header stability is receiver-agreeing hard signs at narrow-band positions, "
        "not a FEC or semantic decode. No gaps are concatenated into transitions.",
    )
    (OUT / "state_and_header.json").write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            {
                **output,
                "temporal": {
                    k: v for k, v in temporal.items() if k != "discovery_validation_trials"
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
