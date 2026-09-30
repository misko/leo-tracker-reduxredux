"""Frozen regularized state-to-sign prediction across frames and receivers."""

import hashlib
import json
from pathlib import Path

import numpy as np
from decode_tracks import SEED, codebook

BASE = Path(__file__).parent
SOURCE = BASE.parent / "2026_09_28_sequence_semantics/local"


def predict(x, y, target, penalty=1.0):
    """Fixed ridge penalty; fit the intercept exclusively from discovery data."""
    mean_x, mean_y = x.mean(0), y.mean(0)
    xc, yc = x - mean_x, y - mean_y
    weights = xc.T @ np.linalg.solve(xc @ xc.T + penalty * np.eye(len(x)), yc)
    return (target - mean_x) @ weights + mean_y


def main():
    out = BASE / "local/header-state-transfer"
    out.mkdir(exist_ok=True)
    words = np.array(
        [[1 if b == "1" else -1 for b in w] for w in codebook(list(map(int, SEED)))], dtype=float
    ) / np.sqrt(60)
    source_hashes, visits = {}, []
    for name in ["DS9-middle", "DS9-last"]:
        source = SOURCE / f"{name}-soft.npz"
        binding = SOURCE / f"ds9-{name[4:]}-10m/inventory.json"
        states = BASE / f"local/residual-constellation/{name}.npz"
        data, state = np.load(source), np.load(states)
        receipt = json.loads((BASE / "local/residual-constellation/summary.json").read_text())
        bound = next(v for v in receipt["visits"] if v["name"] == name)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == bound["source_sha256"]
        assert str(data["inventory_sha256"]) == hashlib.sha256(binding.read_bytes()).hexdigest()
        bins = state["bins"]
        arrays = [
            data[f"z{rx}"][state["frames"]][:, :, np.searchsorted(data[f"bins{rx}"], bins)]
            for rx in range(2)
        ]
        visits.append(
            dict(
                name=name, arrays=arrays, bins=bins, frames=state["frames"], phases=state["phases"]
            )
        )
        for path in (source, binding, states):
            source_hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert np.array_equal(visits[0]["bins"], visits[1]["bins"])
    split = len(visits[0]["frames"]) // 2
    x = words[visits[0]["phases"][:split]]
    rng = np.random.default_rng(20260929)
    rows = []
    for label, start, stop in [("header", 0, 6), ("tail_control", 270, 276)]:
        train = visits[0]["arrays"][0][:split, start:stop].real.reshape(split, -1)
        y = np.where(train >= 0, 1.0, -1.0)
        variable = abs(y.mean(0)) <= 0.6
        for vi, visit in enumerate(visits):
            selection = slice(split, None) if vi == 0 else slice(None)
            states = visit["phases"][selection]
            target_x = words[states]
            z = visit["arrays"][1][selection, start:stop].real.reshape(len(states), -1)
            truth = z >= 0
            predictions = predict(x, y, target_x) >= 0
            baseline = np.broadcast_to(y.mean(0) >= 0, truth.shape)
            controls = [predict(x[rng.permutation(len(x))], y, target_x) >= 0 for _ in range(199)]
            for group, included in [
                ("all", np.ones(len(states), bool)),
                ("state_seen_in_training", np.isin(states, visits[0]["phases"][:split])),
                ("state_unseen_in_training", ~np.isin(states, visits[0]["phases"][:split])),
            ]:
                mask = included[:, None] & variable[None]
                if not mask.any():
                    continue
                def score(p, truth=truth, mask=mask):
                    return float(np.mean((p == truth)[mask]))
                control = [score(p) for p in controls]
                rows.append(
                    dict(
                        region=label,
                        visit=visit["name"],
                        group=group,
                        frames=int(included.sum()),
                        coordinates=int(variable.sum()),
                        decisions=int(mask.sum()),
                        accuracy=score(predictions),
                        majority_accuracy=score(baseline),
                        shuffle_quantiles=np.quantile(control, [0.025, 0.5, 0.975]).tolist(),
                        shuffle_max=max(control),
                    )
                )
            np.savez_compressed(
                out / f"{visit['name']}-{label}.npz",
                frames=visit["frames"][selection],
                phases=states,
                variable=variable,
                predictions=predictions,
                observed=truth,
            )
    result = dict(
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        input_sha256=source_hashes,
        training_frames=split,
        training_receiver=0,
        evaluation_receiver=1,
        penalty=1.0,
        rows=rows,
    )
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    for r in rows:
        print(json.dumps(r))


if __name__ == "__main__":
    main()
