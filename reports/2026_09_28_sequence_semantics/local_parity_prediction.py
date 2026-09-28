"""Test reference-constrained signs against the opposite local receiver."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent


def codewords(width, equations):
    assert width <= 18
    words = ((np.arange(1 << width)[:, None] >> np.arange(width)) & 1).astype(np.uint8)
    keep = np.ones(len(words), bool)
    for positions, parity in equations:
        keep &= np.bitwise_xor.reduce(words[:, positions], axis=1) == parity
    return words[keep]


def predict(soft, words, omit_target=False):
    signs = words.astype(float) * 2 - 1
    scores = soft @ signs.T
    out = np.zeros_like(soft)
    for target in range(soft.shape[1]):
        use = scores - soft[:, target, None] * signs[None, :, target] if omit_target else scores
        tied = np.isclose(use, use.max(axis=1)[:, None], atol=1e-10, rtol=0)
        out[:, target] = (tied @ signs[:, target]) / tied.sum(axis=1)
    return out


def summary(prediction, target, direct, majority):
    resolved = abs(prediction) > 1e-10
    if not resolved.any():
        return dict(count=0)
    chosen = prediction >= 0
    return dict(
        count=int(resolved.sum()),
        agreement=float((chosen == target)[resolved].mean()),
        direct_agreement=float((direct == target)[resolved].mean()),
        majority_agreement=float((majority == target)[resolved].mean()),
        changed=int(((chosen != direct) & resolved).sum()),
    )


def main():
    eq_path = BASE / "local/header_rank_relations.json"
    audit_path = BASE / "local/local_header_recovery.json"
    equations = json.loads(eq_path.read_text())["raw_transfers"]
    visits = json.loads(audit_path.read_text())["rows"]
    rows = []
    for visit in visits:
        if "evaluation_frames" not in visit:
            continue
        path = BASE / "local" / f"{visit['signal']}-soft.npz"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == visit["sha256"]
        data = np.load(path)
        common = set(data["bins0"]) & set(data["bins1"])
        available = [r for r in equations if all(b in common for s, b in r["coordinates"])]
        if not available:
            continue
        coords = sorted(set(tuple(c) for r in available for c in r["coordinates"]))
        rules = [
            ([coords.index(tuple(c)) for c in r["coordinates"]], r["parity"]) for r in available
        ]
        words = codewords(len(coords), rules)
        assert len(words) > 0
        streams = []
        for rx in range(2):
            mapping = {int(b): i for i, b in enumerate(data[f"bins{rx}"])}
            z = np.stack([data[f"z{rx}"][:, s, mapping[b]] for s, b in coords], axis=1)
            streams.append(z.real / np.maximum(abs(z), 1e-20))
        held, train = visit["evaluation_frames"], visit["discovery_frames"]
        for rx in range(2):
            soft = streams[rx][held]
            direct = soft >= 0
            target = streams[1 - rx][held] >= 0
            majority = np.broadcast_to((streams[rx][train] >= 0).mean(axis=0) >= 0.5, target.shape)
            full = predict(soft, words)
            extrinsic = predict(soft, words, omit_target=True)
            row = dict(
                signal=visit["signal"],
                predictor_receiver=rx,
                coordinates=coords,
                equations=len(rules),
                allowed_words=len(words),
                frames=len(held),
                constrained=summary(full, target, direct, majority),
                target_omitted=summary(extrinsic, target, direct, majority),
            )
            rows.append(row)
            print(json.dumps(row))
    output = dict(
        rows=rows,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (eq_path, audit_path)
        },
        limitation="Empirical reference constraints, not verified transmitter FEC. "
        "Directional soft scores are not calibrated log likelihoods. Opposite "
        "receiver supplies noisy validation, not truth. All equations are fixed "
        "before local prediction. Tied target signs are unresolved. Majority "
        "baseline uses predictor discovery frames only. No decoder data modified.",
    )
    (BASE / "local/local_parity_prediction.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
