"""Bounded, frozen-location prediction on timestamp-selected outside scans."""

import concurrent.futures
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")


def choose(captures, excluded):
    rows = sorted(
        (r for r in captures if r["session_id"] not in excluded),
        key=lambda r: (r["capture_start_utc_ns"], r["session_id"]),
    )
    if len(rows) < 5 or len({r["session_id"] for r in rows}) != len(rows):
        raise ValueError("Require at least five unique outside scans")
    return rows, [rows[j * (len(rows) - 1) // 4] for j in range(5)]


def prepare():
    authority = REPORTS / "2026_09_29_catalogue_recurrence/plan.json"
    budget = REPORTS / "2026_09_29_scan_budget/manifest.json"
    paths = [authority, budget, HERE / "study.py", HERE / "PROTOCOL.md"]
    frozen = read(budget)
    sets = []
    for group in read(authority)["groups"]:
        assert group["ready"] and group["requested_records"] == group["validated_records"]
        ds = group["dataset_id"]
        pool = next(s for s in frozen["sets"] if s["dataset"] == ds and s["count"] == 24)
        excluded = {s["session_id"] for s in pool["scans"]}
        source_paths = [REPORTS / f"2026_09_29_scan_budget/{ds}_n24_0.json"] + [
            REPORTS / f"2026_09_29_time_balanced_scans/grid_{ds}_balanced_{i}.json"
            for i in range(3)
        ]
        fits = [read(p) for p in source_paths]
        assert all(f["selected"]["qualified"] for f in fits)
        assert set(fits[0]["sessions"]) == excluded
        assert set(s for f in fits[1:] for s in f["sessions"]) == excluded
        assert sum(len(f["sessions"]) for f in fits[1:]) == 24
        manifest_path = ROOT / group["manifest_path"]
        captures = read(manifest_path)["captures"]
        outside, selected = choose(captures, excluded)
        assert len(captures) == group["validated_records"]
        inputs = {s["session_id"]: s for s in group["inputs"]}
        positions = [[0.0, 0.0]] + [f["selected"]["x"][:2] for f in fits]
        for i, row in enumerate(selected):
            entry = inputs[row["session_id"]]
            assert entry.get("state", "ready") == "ready"
            for artifact in entry["artifacts"]:
                path = Path(artifact["path"])
                assert "sha256:" + digest(path) == artifact["sha256"]
                paths.append(path)
            sets.append(
                dict(
                    unit=f"{ds}_{i}",
                    dataset=ds,
                    input=entry,
                    start_utc_ns=row["capture_start_utc_ns"],
                    positions=positions,
                    outside_count=len(outside),
                    source_sessions=sorted(excluded),
                )
            )
        paths.extend(source_paths + [manifest_path])
    for rel in [
        "2026_09_29_scan_holdout/timing.py",
        "2026_09_29_unassociated_trend/trend_mixture.py",
        "2026_09_29_frequency_contrast/contrast_position.py",
    ]:
        paths.append(REPORTS / rel)
    paths.extend(
        [ROOT / "tools/ds7_baseline_adapter.py", ROOT / "tools/ds7_fast_baseline_adapter.py"]
    )
    save(
        HERE / "manifest.json",
        dict(
            config=frozen["config"],
            sets=sets,
            hashes={str(p.relative_to(ROOT)): digest(p) for p in paths},
        ),
    )
    print("Frozen", len(sets), "targets", flush=True)


def numerical_imports():
    sys.path[:0] = [
        str(ROOT / "tools"),
        str(REPORTS / "2026_09_29_unassociated_trend"),
        str(REPORTS / "2026_09_29_scan_holdout"),
    ]
    import ds7_fast_baseline_adapter as baseline
    import timing
    from trend_mixture import TrendMixturePosition

    return baseline, timing, TrendMixturePosition


def evaluate(unit):
    started = time.monotonic()
    manifest = read(HERE / "manifest.json")
    row = next(s for s in manifest["sets"] if s["unit"] == unit)
    baseline, timing, model_class = numerical_imports()
    docs = baseline.load_documents(dict(config=manifest["config"], inputs=[row["input"]]))
    assert [d["session_id"] for d in docs] == [row["input"]["session_id"]]
    model = model_class(docs, manifest["config"], baseline.Stationary, 0.2)
    values = []
    for position in row["positions"]:
        result = timing.marginal_scan(model, position)
        if not result["qualified"]:
            initial = result.copy()
            scores = []
            for order in (64, 128):
                nodes, weights = timing.timing_nodes(order, model.models[0].taus)
                scores.append(
                    timing.log_integral(timing.full_scores(model, position, nodes), weights)
                )
            result.update(
                initial=initial,
                log_score=scores[0],
                audit_log_score=scores[1],
                quadrature_difference=abs(scores[0] - scores[1]),
                qualified=bool(abs(scores[0] - scores[1]) <= 0.01),
                refinement_orders=[64, 128],
            )
        values.append(result)
    save(
        HERE / f"{unit}.json",
        dict(
            unit=unit,
            session_id=docs[0]["session_id"],
            values=values,
            tracks=len(docs[0]["tracks"]),
            observations=sum(len(t["y"]) for t in docs[0]["tracks"]),
            elapsed_seconds=time.monotonic() - started,
            manifest_sha256=digest(HERE / "manifest.json"),
        ),
    )
    print(unit, [v["qualified"] for v in values], flush=True)


def batch():
    manifest = read(HERE / "manifest.json")
    for name, expected in manifest["hashes"].items():
        assert digest(ROOT / name) == expected, name

    def worker(row):
        unit = row["unit"]
        started = time.monotonic()
        try:
            out = subprocess.run(
                [sys.executable, str(HERE / "study.py"), "evaluate", unit],
                capture_output=True,
                text=True,
                timeout=180,
            )
            receipt = dict(exit_code=out.returncode, stdout=out.stdout, stderr=out.stderr)
        except subprocess.TimeoutExpired:
            receipt = dict(exit_code=None, timed_out=True)
        receipt["elapsed_seconds"] = time.monotonic() - started
        save(HERE / f"{unit}.receipt.json", receipt)
        print(unit, receipt, flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(worker, manifest["sets"]))


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "batch":
        batch()
    elif sys.argv[1] == "evaluate":
        evaluate(sys.argv[2])
    else:
        raise ValueError("Unknown command")
