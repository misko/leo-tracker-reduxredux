import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REUSED = HERE.parent / "2026_09_29_candidate_information/information.py"
spec = importlib.util.spec_from_file_location("prior_information", REUSED)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)


def curvature(t):
    t = np.asarray(t) - np.mean(t)
    linear = np.column_stack([np.ones(len(t)), t])
    return t * t - linear @ np.linalg.lstsq(linear, t * t, rcond=None)[0]


def main():
    import time

    started = time.monotonic()
    paths = [
        HERE.parent / "2026_09_29_donor_residual_transfer/plan.json",
        HERE.parent / "2026_09_29_catalogue_recurrence/result.json",
        HERE.parent / "2026_09_29_curvature_transfer/results.json",
        REUSED,
        HERE / "study.py",
        HERE / "PROTOCOL.md",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
    ]
    plan, recurrence, transfer = [json.loads(p.read_text()) for p in paths[:3]]
    source_manifest = HERE.parent / "2026_09_29_curvature_transfer/manifest.json"
    for name, digest in json.loads(source_manifest.read_text())["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    paths.append(source_manifest)
    selected = {
        (r["unit_id"], r["session_id"], r["track_id"], r["number"])
        for r in transfer["rows"]
        if r["same"]
    }
    assert len(selected) == 1732
    mapping = {
        (s["session_id"], t["track_id"]): t["numbers"]
        for s in recurrence["scans"]
        for t in s["tracks"]
    }
    panels = {}
    count = 0
    max_residual = 0.0
    hashes = {}
    for u in plan["units"]:
        if u["role"] != "target":
            continue
        key = u["unit_id"]
        p = HERE.parent / "2026_09_29_donor_residual_transfer/runs" / key / "result.json"
        paths.append(p)
        cases = {
            (c["session_id"], c["track_id"]): c
            for c in json.loads(p.read_text())["cases"]
            if (key, c["session_id"], c["track_id"], c["number"]) in selected
        }
        blocks = {arm: [[], []] for arm in ("slope", "curvature")}
        minimum_knot = float("inf")
        for index, entry in enumerate(u["group"]["inputs"]):
            for artifact in entry["artifacts"]:
                p = Path(artifact["path"])
                h = hashlib.sha256(p.read_bytes()).hexdigest()
                assert "sha256:" + h == artifact["sha256"]
                hashes[str(p.relative_to(ROOT))] = h
            doc = prior.baseline.load_documents(dict(config=plan["config"], inputs=[entry]))[0]
            model = prior.baseline.Stationary(doc, plan["config"])
            x = np.array([*u["x"][:2], u["x"][index + 2]])
            minimum_knot = min(minimum_knot, float(np.min(abs(model.taus - x[2]))))
            for track in doc["tracks"]:
                c = cases.get((doc["session_id"], track["track_id"]))
                if c is None:
                    continue
                slot = mapping[doc["session_id"], track["track_id"]].index(c["number"])
                prediction, visible = model.prediction(track, x)
                assert visible[slot]
                delta = float(max(abs(track["y"] - prediction[slot] - c["residual"])))
                assert delta < 1e-7
                max_residual = max(max_residual, delta)
                mask = np.asarray(c["mask"], bool)
                np.testing.assert_array_equal(mask, track["mask"])
                np.testing.assert_allclose(c["times"], track["times_s"], rtol=0, atol=1e-12)
                t = np.asarray(c["times"])[mask]
                weight = np.sqrt(c["candidate_weight"] * c["signal_responsibility"] * 5 / 70000)
                for variant, factor in enumerate((1, 0.5)):
                    columns = []
                    for axis, step in enumerate(np.array([0.001, 0.001, 0.0001]) * factor):
                        plus, minus = x.copy(), x.copy()
                        plus[axis] += step
                        minus[axis] -= step
                        a, av = model.prediction(track, plus)
                        b, bv = model.prediction(track, minus)
                        assert av[slot] and bv[slot]
                        v = ((a[slot] - b[slot]) / (2 * step))[mask]
                        columns.append(v - v.mean())
                    design = np.zeros((len(t), 10))
                    design[:, :2] = np.array(columns[:2]).T
                    design[:, index + 2] = columns[2]
                    for arm, z in (("slope", t - t.mean()), ("curvature", curvature(t))):
                        blocks[arm][variant].append(
                            dict(
                                a=design * weight,
                                z=z * weight,
                                group=(doc["session_id"], c["number"], c["rf_hz"]),
                            )
                        )
                count += 1
        results = {}
        change = 0.0
        for arm, variants in blocks.items():
            full, half = [prior.compare(b) for b in variants]
            results[arm] = dict(full=full, half=half)
            for grouping in ("shared", "track"):
                change = max(
                    change,
                    float(
                        max(
                            abs(np.array(full[grouping]["retention"]) - half[grouping]["retention"])
                        )
                    ),
                )
        qualified = bool(change <= 0.001 and minimum_knot > 0.0001)
        panels[key] = dict(
            cases=len(cases),
            results=results,
            maximum_retention_step_change=change,
            minimum_timing_knot_distance_s=minimum_knot,
            qualified=qualified,
        )
        print(
            key,
            qualified,
            "curvature",
            results["curvature"]["full"]["shared"]["retention"],
            flush=True,
        )
    assert count == len(selected)
    for p in paths:
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    with (HERE / "results.json").open("x") as f:
        json.dump(
            dict(
                panels=panels,
                cases=count,
                max_residual_difference=max_residual,
                elapsed_seconds=time.monotonic() - started,
                hashes=hashes,
            ),
            f,
            indent=2,
            allow_nan=False,
        )


if __name__ == "__main__":
    main()
