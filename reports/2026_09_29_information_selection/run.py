import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.special import logsumexp
from selection import greedy, profile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def information(model, x, factor):
    original = model.evaluate(x, gradient=False, held=True)
    rows = iter(original["rows"])
    matrices = []
    for di, (doc, engine) in enumerate(zip(model.documents, model.models, strict=True)):
        local = np.array([*x[:2], x[di + 2]])
        matrix = np.zeros((3, 3))
        for track in doc["tracks"]:
            row = next(rows)
            weight = (
                np.array(row["weights_given_signal"]) * row["signal_responsibility"] * 5 / 70000
            )
            columns = []
            for axis, step in enumerate(np.array([0.001, 0.001, 0.0001]) * factor):
                plus, minus = local.copy(), local.copy()
                plus[axis] += step
                minus[axis] -= step
                pp, vp = engine.prediction(track, plus)
                pm, vm = engine.prediction(track, minus)
                np.testing.assert_array_equal(vp, vm)
                column = ((pp - pm) / (2 * step))[:, track["mask"]]
                columns.append(column - column.mean(axis=1, keepdims=True))
            design = np.stack(columns, axis=2)
            matrix += np.einsum("kni,knj,k->ij", design, design, weight)
        matrices.append(profile(matrix))
    return np.array(matrices)


def main(ds):
    started = time.monotonic()
    frozen = read(HERE / "manifest.json")
    for name, h in frozen["hashes"].items():
        assert sha(ROOT / name) == h, name
    budget = module("budget_runner", REPORTS / "2026_09_29_scan_budget/run.py")
    held = module("held_runner", REPORTS / "2026_09_29_curvature_scan_holdout/run.py")
    helper = budget.helper
    manifest = read(REPORTS / "2026_09_29_scan_budget/manifest.json")
    prior = read(REPORTS / f"2026_09_29_scan_budget/{ds}_n24_0.json")
    for obj in (manifest, prior):
        for name, h in obj["hashes"].items():
            assert sha(ROOT / name) == h, name
    pool = next(s for s in manifest["sets"] if s["dataset"] == ds and s["count"] == 24)
    inputs = [s["input"] for s in pool["scans"]]
    docs = helper.baseline.load_documents(dict(config=manifest["config"], inputs=inputs))
    assert [d["session_id"] for d in docs] == prior["sessions"]
    model = helper.TrendMixturePosition(docs, manifest["config"], helper.baseline.Stationary, 0.2)
    x = np.array(prior["selected"]["x"])
    assert prior["selected"]["qualified"]
    assert abs(model.evaluate(x, gradient=False)["score"] - prior["selected"]["score"]) < 1e-7
    matrices = information(model, x, 1.0)
    audit = information(model, x, 0.5)
    discrepancy = float(np.linalg.norm(matrices - audit) / np.linalg.norm(matrices))
    selection = greedy(matrices, 8)
    audit_selection = greedy(audit, 8)
    assert discrepancy < 1e-5 and selection["indices"] == audit_selection["indices"]
    indices = sorted(selection["indices"])
    selected = [docs[i] for i in indices]
    train = helper.TrendMixturePosition(
        selected, manifest["config"], helper.baseline.Stationary, 0.2
    )
    singles = [
        helper.TrendMixturePosition([d], manifest["config"], helper.baseline.Stationary, 0.2)
        for d in selected
    ]
    grid = np.array(manifest["config"]["timing_grid_s"])
    starts = []
    for family in ("cold", "timing_grid"):
        for east in (-2.0, 0.0, 2.0):
            z = np.zeros(10)
            z[0] = east
            if family == "timing_grid":
                for di, one in enumerate(singles):
                    scores, _ = budget.training_scores(one, z[:2], grid)
                    k = int(np.argmax(scores))
                    z[di + 2] = grid[k]
                    assert (
                        abs(one.evaluate([east, 0.0, grid[k]], gradient=False)["score"] - scores[k])
                        < 1e-7
                    )
            starts.append(dict(helper.fit_model(train, z), family=family))
    valid = [s for s in starts if s["qualified"]]
    best = max(valid, key=lambda r: r["score"]) if valid else None
    targets = []
    outside = read(REPORTS / "2026_09_29_out_of_pool/manifest.json")
    if best:
        best["estimate_deg"] = list(train.models[0].coordinates(best["x"][:3]))
        for target in (s for s in outside["sets"] if s["dataset"] == ds):
            assert target["input"]["session_id"] not in prior["sessions"]
            old = read(REPORTS / f"2026_09_29_out_of_pool/{target['unit']}.json")
            assert old["manifest_sha256"] == sha(REPORTS / "2026_09_29_out_of_pool/manifest.json")
            assert all(v["qualified"] for v in old["values"])
            testdocs = helper.baseline.load_documents(
                dict(config=manifest["config"], inputs=[target["input"]])
            )
            test = helper.TrendMixturePosition(
                testdocs, manifest["config"], helper.baseline.Stationary, 0.2
            )
            score = held.marginal(test, best["x"][:2])
            targets.append(
                dict(
                    unit=target["unit"],
                    result=score,
                    n24_delta=score["log_score"] - old["values"][1]["log_score"],
                    n8_deltas=[score["log_score"] - v["log_score"] for v in old["values"][2:]],
                    n8_mixture_delta=score["log_score"]
                    - float(logsumexp([v["log_score"] for v in old["values"][2:]]) - np.log(3)),
                )
            )
    result = dict(
        dataset=ds,
        selection=selection,
        matrix_discrepancy=discrepancy,
        information=matrices.tolist(),
        selected_sessions=[d["session_id"] for d in selected],
        selected_indices=indices,
        starts=starts,
        selected=best,
        targets=targets,
        elapsed_seconds=time.monotonic() - started,
        manifest_sha256=sha(HERE / "manifest.json"),
    )
    with (HERE / f"{ds}.json").open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(ds, best is not None, time.monotonic() - started, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
