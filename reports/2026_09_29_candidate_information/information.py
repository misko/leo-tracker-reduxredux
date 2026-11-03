"""Conditional design information with shared candidate slopes profiled out."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402


def profile_information(matrix):
    nuisance = matrix[2:, 2:]
    values, vectors = np.linalg.eigh(nuisance)
    threshold = max(float(values.max()), 0) * 1e-10
    keep = values > threshold
    inv = (vectors[:, keep] / values[keep]) @ vectors[:, keep].T
    result = matrix[:2, :2] - matrix[:2, 2:] @ inv @ matrix[2:, :2]
    return (result + result.T) / 2, int(keep.sum())


def compare(blocks):
    base = sum(b["a"].T @ b["a"] for b in blocks)
    groups = {}
    separate = base.copy()
    for b in blocks:
        cross = b["a"].T @ b["z"]
        norm = float(b["z"] @ b["z"])
        separate -= np.outer(cross, cross) / norm
        g = groups.setdefault(b["group"], [np.zeros(base.shape[0]), 0.0])
        g[0] += cross
        g[1] += norm
    shared = base.copy()
    for cross, norm in groups.values():
        shared -= np.outer(cross, cross) / norm
    fixed, rank = profile_information(base)
    eigen, vec = np.linalg.eigh(fixed)
    assert eigen.min() > 0
    inverse_root = (vec / np.sqrt(eigen)) @ vec.T
    result = dict(baseline=fixed.tolist(), timing_rank=rank, groups=len(groups))
    for name, matrix in (("shared", shared), ("track", separate)):
        info, nuisance_rank = profile_information(matrix)
        retention = np.linalg.eigvalsh(inverse_root @ info @ inverse_root)
        assert retention.min() > -1e-7 and retention.max() <= 1 + 1e-7
        result[name] = dict(
            information=info.tolist(), timing_rank=nuisance_rank, retention=retention.tolist()
        )
    return result


def main():
    paths = [
        HERE.parent / "2026_09_29_donor_residual_transfer/plan.json",
        HERE.parent / "2026_09_29_catalogue_recurrence/result.json",
        HERE.parent / "2026_09_29_candidate_rx_transfer/results.json",
    ]
    plan, recurrence, transfer = [json.loads(p.read_text()) for p in paths]
    for name, digest in transfer["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    selected = {
        (r["unit_id"], r["session_id"], r["track_id"], r["number"])
        for r in transfer["rows"]
        if r["candidate_predictor"]
    }
    mapping = {
        (s["session_id"], t["track_id"]): t["numbers"]
        for s in recurrence["scans"]
        for t in s["tracks"]
    }
    results, hashes = {}, {}
    max_residual_difference = 0.0
    count = 0
    for u in plan["units"]:
        if u["role"] != "target":
            continue
        key = u["unit_id"]
        residual_path = (
            HERE.parent / "2026_09_29_donor_residual_transfer/runs" / key / "result.json"
        )
        paths.append(residual_path)
        cases = json.loads(residual_path.read_text())["cases"]
        selected_cases = {
            (c["session_id"], c["track_id"]): c
            for c in cases
            if (key, c["session_id"], c["track_id"], c["number"]) in selected
        }
        blocks = [[], []]
        minimum_knot_distance = float("inf")
        for index, entry in enumerate(u["group"]["inputs"]):
            for artifact in entry["artifacts"]:
                path = Path(artifact["path"])
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                assert digest == artifact["sha256"].removeprefix("sha256:")
                hashes[str(path.relative_to(ROOT))] = digest
            doc = baseline.load_documents(dict(config=plan["config"], inputs=[entry]))[0]
            model = baseline.Stationary(doc, plan["config"])
            x = np.array([*u["x"][:2], u["x"][index + 2]])
            minimum_knot_distance = min(
                minimum_knot_distance, float(np.min(abs(model.taus - x[2])))
            )
            for track in doc["tracks"]:
                c = selected_cases.get((doc["session_id"], track["track_id"]))
                if c is None:
                    continue
                slot = mapping[doc["session_id"], track["track_id"]].index(c["number"])
                predicted, visible = model.prediction(track, x)
                assert visible[slot]
                diff = float(np.max(abs(track["y"] - predicted[slot] - c["residual"])))
                max_residual_difference = max(max_residual_difference, diff)
                assert diff < 1e-7
                mask = np.asarray(c["mask"], bool)
                np.testing.assert_array_equal(mask, track["mask"])
                np.testing.assert_allclose(c["times"], track["times_s"], rtol=0, atol=1e-12)
                t = np.asarray(c["times"])[mask]
                scale = np.sqrt(c["candidate_weight"] * c["signal_responsibility"] * 5 / 70000)
                for variant, factor in enumerate((1.0, 0.5)):
                    columns = []
                    for axis, step in enumerate(np.array([0.001, 0.001, 0.0001]) * factor):
                        plus, minus = x.copy(), x.copy()
                        plus[axis] += step
                        minus[axis] -= step
                        a, av = model.prediction(track, plus)
                        b, bv = model.prediction(track, minus)
                        assert av[slot] and bv[slot]
                        column = ((a[slot] - b[slot]) / (2 * step))[mask]
                        columns.append(column - column.mean())
                    design = np.zeros((len(t), 10))
                    design[:, :2] = np.array(columns[:2]).T
                    design[:, index + 2] = columns[2]
                    blocks[variant].append(
                        dict(
                            a=design * scale,
                            z=(t - t.mean()) * scale,
                            group=(doc["session_id"], c["number"], c["rf_hz"]),
                        )
                    )
                count += 1
            del doc, model
        full, half = [compare(b) for b in blocks]
        change = max(
            float(np.max(abs(np.asarray(full[arm]["retention"]) - half[arm]["retention"])))
            for arm in ("shared", "track")
        )
        results[key] = dict(
            cases=len(selected_cases),
            minimum_timing_knot_distance_s=minimum_knot_distance,
            full=full,
            half=half,
            maximum_retention_step_change=change,
        )
        print(
            key,
            "shared",
            full["shared"]["retention"],
            "track",
            full["track"]["retention"],
            "step change",
            change,
            flush=True,
        )
    assert count == len(selected) == 1847
    for p in paths + [
        HERE / "information.py",
        HERE / "PROTOCOL.md",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
    ]:
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (HERE / "results.json").write_text(
        json.dumps(
            dict(
                hashes=hashes,
                cases=count,
                max_residual_difference=max_residual_difference,
                panels=results,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
