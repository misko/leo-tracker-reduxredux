"""Score all declared gates at one unchanged no-cone panel fit."""
# ruff: noqa: I001 -- Load local study before hard_gate changes the module search path.

import sys

import numpy as np
from study import HERE, ROOT, read, save
from hard_gate import HardConeScore

from cone_trend import ConeTrendPosition
from ds7_fast_baseline_adapter import Stationary, load_documents


def main(key):
    plan = read(HERE / "plan.json")
    unit = next(u for u in plan["units"] if u["unit_id"] == key)
    docs = load_documents({"config": plan["config"], "inputs": unit["group"]["inputs"]})
    x = unit["x"]
    selection = read(ROOT / unit["selection"])["selected"]
    assert selection["x"] == x and selection["session_ids"] == unit["group"]["session_ids"]
    old = read(ROOT / unit["baseline_held"])
    assert old["audit_passed"]
    prior = {(r["session_id"], r["track_id"]): r for r in old["rows"]}
    neutral = ConeTrendPosition(docs, plan["config"], Stationary)
    baseline = neutral.evaluate(x, gradient=False, held=True)
    assert abs(baseline["score"] - old["training_log_score"]) < 1e-7
    geometry, metadata = {}, []
    for di, doc in enumerate(docs):
        local = [x[0], x[1], x[di + 2]]
        for track in doc["tracks"]:
            identity = doc["session_id"], track["track_id"]
            mask = track["mask"]
            angles = neutral.angles(track, local)
            _, visible = neutral.models[di].prediction(track, local)
            train, held = angles[:, mask].max(axis=1), angles[:, ~mask].max(axis=1)
            geometry[identity] = train, held, visible
            metadata.append(
                {
                    "session_id": identity[0],
                    "track_id": identity[1],
                    "receiver_id": int(track["receiver_id"]),
                    "training_observations": int(mask.sum()),
                    "held_observations": int((~mask).sum()),
                    "training_max_angles_deg": train.tolist(),
                    "held_max_angles_deg": held.tolist(),
                    "horizon_visible": visible.tolist(),
                }
            )
    assert len(prior) == len(geometry) == unit["group"]["tracks"]
    assert (
        sum(r["training_observations"] for r in metadata) == unit["group"]["training_observations"]
    )
    assert sum(r["held_observations"] for r in metadata) == unit["group"]["held_observations"]
    for r in baseline["rows"]:
        old_row = prior[r["session_id"], r["track_id"]]
        for field in ("training_log_score", "held_log_score", "signal_responsibility"):
            assert abs(r[field] - old_row[field]) < 1e-7
        expected = np.array(old_row["weights_given_signal"]) * old_row["signal_responsibility"]
        assert np.max(np.abs(np.array(r["candidate_responsibilities"]) - expected)) < 1e-7
        assert r["held_observations"] == old_row["held_observations"]
    assert abs(sum(r["held_log_score"] for r in baseline["rows"]) - old["held_log_score"]) < 1e-7
    outputs = {"baseline": baseline}
    for arm in plan["arms"]:
        width = int(arm[-2:])
        factory = HardConeScore if arm.startswith("hard") else ConeTrendPosition
        model = factory(docs, plan["config"], Stationary, half_angle_deg=width)
        output = model.evaluate(x, gradient=False, held=True)
        assert {(r["session_id"], r["track_id"]) for r in output["rows"]} == prior.keys()
        for r in output["rows"]:
            identity = r["session_id"], r["track_id"]
            train, held, visible = geometry[identity]
            weights = np.array(r["candidate_responsibilities"])
            supported = visible & (train <= width)
            assert np.isfinite(weights).all() and np.all(weights >= 0)
            assert abs(weights.sum() - r["signal_responsibility"]) < 1e-10
            assert abs(weights.sum() + r["background_responsibility"] - 1) < 1e-10
            assert np.all(weights[~visible] == 0)
            assert r["held_observations"] == prior[identity]["held_observations"]
            if arm.startswith("hard"):
                assert np.all(weights[~supported] == 0)
                if not supported.any():
                    assert r["signal_responsibility"] == 0 and r["background_responsibility"] == 1
            r.update(
                {
                    "hard_supported_candidates": int(supported.sum()),
                    "training_inside_signal_mass": float(weights @ (train <= width)),
                    "both_inside_signal_mass": float(
                        weights @ ((train <= width) & (held <= width))
                    ),
                }
            )
        outputs[arm] = output
    # Gradients were not requested; discard the uncomputed zero placeholders.
    for output in outputs.values():
        output.pop("gradient")
    save(
        HERE / "runs" / key / "result.json",
        {
            "unit_id": key,
            "unchanged_position_timings": x,
            "replay_passed": True,
            "audit_passed": True,
            "geometry": metadata,
            "models": outputs,
        },
    )
    print(key, "verified fixed-position scores", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
