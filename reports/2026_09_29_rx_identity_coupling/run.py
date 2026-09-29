"""Compute fixed-position signal potentials and all frozen coupling scores."""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from mixture import evaluate_pairs, single_density  # noqa: E402
from potentials import track_potentials  # noqa: E402


def read(p):
    return json.loads(p.read_text())


def main(key):
    plan = read(HERE / "plan.json")
    unit = next(u for u in plan["units"] if u["unit_id"] == key)
    docs = baseline.load_documents({"config": plan["config"], "inputs": unit["group"]["inputs"]})
    assert [d["session_id"] for d in docs] == unit["group"]["session_ids"]
    source = {s["session_id"]: s for s in read(ROOT / plan["pair_source"])["scans"]}
    train, joint = {}, {}
    actual, matched, shuffled = [], [], []
    serialized = []
    for di, (doc, entry) in enumerate(zip(docs, unit["group"]["inputs"], strict=True)):
        sid = doc["session_id"]
        manifest = read(
            Path(
                next(
                    a["path"]
                    for a in entry["artifacts"]
                    if a["kind"] == "candidates" and a["path"].endswith(".json")
                )
            )
        )
        indices = {t["track_id"]: t["index"] for t in manifest["tracks"]}
        bankpath = Path(next(a["path"] for a in entry["artifacts"] if a["path"].endswith(".npz")))
        model = baseline.Stationary(doc, plan["config"])
        x = np.array(unit["x"][:2] + [unit["x"][di + 2]])
        with np.load(bankpath, allow_pickle=False) as bank:
            for t in doc["tracks"]:
                tid = t["track_id"]
                identity = (sid, tid)
                prediction, visible = model.prediction(t, x)
                a, b = track_potentials(
                    t,
                    prediction,
                    visible,
                    bank[f"candidate_ids_{indices[tid]}"],
                    manifest["baseline_snapshot_sha256"],
                )
                train[identity], joint[identity] = a, b
                serialized.append(
                    dict(
                        session_id=sid,
                        track_id=tid,
                        training_observations=int(t["mask"].sum()),
                        held_observations=int((~t["mask"]).sum()),
                        train={**a, "ids": a["ids"].tolist(), "signal": a["signal"].tolist()},
                        joint={**b, "ids": b["ids"].tolist(), "signal": b["signal"].tolist()},
                    )
                )
        for p in source[sid]["pairs"]:
            a, b = (sid, p["rx0"]), (sid, p["rx1"])
            assert a in train and b in train
            actual.append((a, b))
            if p["control_rx1"] is not None:
                c = (sid, p["control_rx1"])
                assert c in train
                matched.append((a, b))
                shuffled.append((a, c))
    assert len(train) == unit["group"]["tracks"]
    assert (
        sum(r["training_observations"] for r in serialized)
        == unit["group"]["training_observations"]
    )
    assert sum(r["held_observations"] for r in serialized) == unit["group"]["held_observations"]
    old = read(ROOT / unit["baseline_held"])
    oldrows = {(r["session_id"], r["track_id"]): r for r in old["rows"]}
    for identity in train:
        a = single_density(train[identity])
        b = single_density(joint[identity])
        assert abs(a - oldrows[identity]["training_log_score"]) < 1e-7
        assert abs(b - a - oldrows[identity]["held_log_score"]) < 1e-7
    arms = {}
    for population, pairs in (("all", actual), ("matched", matched), ("shuffled", shuffled)):
        for rho in plan["couplings"]:
            a, b = evaluate_pairs(train, pairs, rho), evaluate_pairs(joint, pairs, rho)
            assert a["paired_tracks"] + a["unpaired_tracks"] == len(train)
            result = dict(
                training_log_score=a["score"],
                held_log_score=b["score"] - a["score"],
                training_pairs=a["pairs"],
                joint_pairs=b["pairs"],
                paired_tracks=a["paired_tracks"],
                unpaired_tracks=a["unpaired_tracks"],
            )
            if rho == 0:
                assert abs(result["training_log_score"] - old["training_log_score"]) < 1e-7
                assert abs(result["held_log_score"] - old["held_log_score"]) < 1e-7
            arms[f"{population}_{rho}"] = result
    with (HERE / "runs" / key / "result.json").open("x") as f:
        json.dump(
            dict(unit_id=key, audit_passed=True, potentials=serialized, arms=arms),
            f,
            indent=2,
            allow_nan=False,
        )
    print(key, "all zero-coupling replays passed", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
