import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent


def read(p):
    return json.loads(p.read_text())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def partition(pool, targets):
    scans = sorted(pool, key=lambda r: (r["start_utc_ns"], r["input"]["session_id"]))[:12]
    assert len(scans) == 12 and len({s["input"]["session_id"] for s in scans}) == 12
    cutoff = scans[-1]["start_utc_ns"] + 300_000_000_000
    sourceids = {s["input"]["session_id"] for s in scans}
    eligible = [t for t in targets if t["start_utc_ns"] > cutoff]
    assert eligible and not sourceids & {t["input"]["session_id"] for t in eligible}
    return dict(scans=scans, targets=eligible, source_end_utc_ns=cutoff)


def main(ds):
    started = time.monotonic()
    sys.path.insert(0, str(REPORTS / "2026_09_29_information_selection"))
    info = module("info_driver", REPORTS / "2026_09_29_information_selection/run.py")
    budget = module("budget_driver", REPORTS / "2026_09_29_scan_budget/run.py")
    diag = module("disagreement", REPORTS / "2026_09_29_scan_disagreement/study.py")
    selector = module(
        "score_selector", REPORTS / "2026_09_29_score_balanced_selection/score_selector.py"
    )
    held = module("held_driver", REPORTS / "2026_09_29_curvature_scan_holdout/run.py")
    helper = budget.helper
    frozen = read(HERE / "manifest.json")
    for name, h in frozen["hashes"].items():
        assert info.sha(ROOT / name) == h, name
    unit = next(u for u in frozen["units"] if u["dataset"] == ds)
    config = frozen["config"]
    docs = helper.baseline.load_documents(
        dict(config=config, inputs=[s["input"] for s in unit["scans"]])
    )

    def model(documents):
        return helper.TrendMixturePosition(documents, config, helper.baseline.Stationary, 0.2)

    def fit(documents):
        train = model(documents)
        singles = [model([d]) for d in documents]
        grid = np.array(config["timing_grid_s"])
        starts = []
        for family in ("cold", "timing_grid"):
            for east in (-2.0, 0.0, 2.0):
                x = np.zeros(2 + len(documents))
                x[0] = east
                if family == "timing_grid":
                    for i, one in enumerate(singles):
                        scores, _ = budget.training_scores(one, x[:2], grid)
                        k = int(np.argmax(scores))
                        x[i + 2] = grid[k]
                        assert (
                            abs(
                                scores[k]
                                - one.evaluate([east, 0.0, grid[k]], gradient=False)["score"]
                            )
                            < 1e-7
                        )
                starts.append(dict(helper.fit_model(train, x), family=family))
        valid = [s for s in starts if s["qualified"]]
        if not valid:
            return dict(starts=starts, selected=None)
        best = max(valid, key=lambda s: s["score"])
        best["estimate_deg"] = list(train.models[0].coordinates(best["x"][:3]))
        return dict(starts=starts, selected=best)

    scout = fit(docs)
    with (HERE / f"{ds}.scout.json").open("x") as out:
        json.dump(
            dict(
                scout=scout,
                sessions=[d["session_id"] for d in docs],
                manifest_sha256=info.sha(HERE / "manifest.json"),
            ),
            out,
            indent=2,
            allow_nan=False,
        )
    assert scout["selected"] is not None, "No qualified scouting fit"
    x = np.array(scout["selected"]["x"])
    full = model(docs)
    geometry = info.information(full, x, 1.0)
    audit_geometry = info.information(full, x, 0.5)
    geo_discrepancy = float(np.linalg.norm(geometry - audit_geometry) / np.linalg.norm(geometry))
    assert geo_discrepancy < 1e-5
    rows = []
    for i, d in enumerate(docs):
        one = model([d])
        local = np.array([*x[:2], x[i + 2]])
        g = one.evaluate(local)["gradient"]
        h, asym = diag.curvature(one, local, 1.0)
        ha, aa = diag.curvature(one, local, 0.5)
        discrepancy = float(np.linalg.norm(h - ha) / max(np.linalg.norm(h), 1e-12))
        profiled = diag.profile(h, g)
        passed = profiled is not None and max(asym, aa, discrepancy) < 0.01
        rows.append(
            dict(
                index=i,
                qualified=bool(passed),
                asymmetry=asym,
                half_step_asymmetry=aa,
                half_step_discrepancy=discrepancy,
                hessian=None if profiled is None else profiled[0].tolist(),
                gradient=None if profiled is None else profiled[1].tolist(),
            )
        )
    with (HERE / f"{ds}.derivatives.json").open("x") as out:
        json.dump(
            dict(rows=rows, geometry=geometry.tolist(), geometry_discrepancy=geo_discrepancy),
            out,
            indent=2,
            allow_nan=False,
        )
    assert all(r["qualified"] for r in rows), "Derivative audit failed"
    h = [r["hessian"] for r in rows]
    g = [r["gradient"] for r in rows]
    selection = selector.choose(geometry, h, g, 8)
    assert selection["indices"] == selector.choose(audit_geometry, h, g, 8)["indices"]
    reduced = fit([docs[i] for i in selection["indices"]])
    assert reduced["selected"] is not None, "No qualified subset fit"
    old = read(REPORTS / f"2026_09_29_time_balanced_scans/grid_{ds}_contiguous_early.json")
    assert old["sessions"] == [d["session_id"] for d in docs[:8]]
    assert old["selected"]["qualified"]
    assert (
        abs(
            model(docs[:8]).evaluate(old["selected"]["x"], gradient=False)["score"]
            - old["selected"]["score"]
        )
        < 1e-7
    )
    positions = dict(
        prefix8=old["selected"], prefix12=scout["selected"], selected8=reduced["selected"]
    )
    targets = []
    for target in unit["targets"]:
        test = model(helper.baseline.load_documents(dict(config=config, inputs=[target["input"]])))
        targets.append(
            dict(
                unit=target["unit"],
                start_utc_ns=target["start_utc_ns"],
                scores={arm: held.marginal(test, p["x"][:2]) for arm, p in positions.items()},
            )
        )
    result = dict(
        dataset=ds,
        selection=selection,
        scout=scout,
        reduced=reduced,
        prefix8=old["selected"],
        targets=targets,
        elapsed_seconds=time.monotonic() - started,
        manifest_sha256=info.sha(HERE / "manifest.json"),
    )
    with (HERE / f"{ds}.json").open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
    print(ds, len(targets), time.monotonic() - started, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
