"""Verify all cached/new exact folds and seal reference-free family selection."""
import argparse
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAMILIES = ("iid_t4_scale100", "source_receiver_equal", "robust_t8_scale100", "robust_t4_scale200")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_sources(record):
    for path, expected in record["sources"].items():
        assert digest(path) == expected, path


def qualifies(fold):
    optimizer = fold["optimizer"]
    if "failure" in fold:
        assert not optimizer["qualified"]
        return False
    x = fold["x"]
    boundary = any(abs(v) > bound - 0.001 for v, bound in zip(x, (12, 12, 5)))
    assert optimizer["boundary"] == boundary
    qualified = bool(optimizer["success"] and not boundary
                     and all(math.isfinite(v) for v in x)
                     and math.isfinite(fold["retained_score"])
                     and optimizer["gradient_max_abs"] is not None
                     and optimizer["gradient_max_abs"] <= 0.01
                     and optimizer["gradient_audit_max_abs"] is not None
                     and optimizer["gradient_audit_max_abs"] <= 0.02)
    assert optimizer["qualified"] == qualified
    return qualified


def main(index):
    plan_path = HERE / "plan.json"
    plan = json.loads(plan_path.read_text())
    assert plan["schema"] == "ds11-source-loo-exact-screen-plan/v1"
    check_sources(plan)
    jobs = [j for j in plan["jobs"] if j["index"] == index]
    expected_folds = sum(j["family"] == FAMILIES[0] for j in jobs)
    assert expected_folds >= 1 and len(jobs) == 4 * expected_folds
    sources = {str(plan_path): digest(plan_path), str(Path(__file__).resolve()): digest(__file__)}
    rows = []
    for job in jobs:
        key = f"{job['index']:02d}_{job['family']}_{job['norad']}"
        cache = job["cache"]
        row = dict(job_key=key, index=job["index"], family=job["family"], norad=job["norad"],
                   cached=cache is not None, qualified=False, available=False,
                   track_ids=job["source_track_ids"])
        if cache:
            path = Path(cache["path"])
        else:
            path = HERE / "runs" / f"{key}.json"
            receipt_path = path.with_suffix(".receipt.json")
            receipt = json.loads(receipt_path.read_text())
            assert receipt["job_key"] == key
            assert receipt["family"] == job["family"] and receipt["norad"] == job["norad"]
            assert receipt["run_sha256"] == digest(HERE / "run.py")
            assert receipt["plan_sha256"] == digest(plan_path)
            assert receipt["protocol_sha256"] == digest(HERE / "PROTOCOL.md")
            sources[str(receipt_path)] = digest(receipt_path)
            row.update(exit_code=receipt["exit_code"], wall_s=receipt["wall_s"])
            if receipt["exit_code"] != 0:
                rows.append(row)
                continue
        record = json.loads(path.read_text())
        check_sources(record)
        sources[str(path)] = digest(path)
        assert record["index"] == job["index"] and record["family"] == job["family"]
        assert not record["reference_used"]
        assert record["full_endpoint_x"] == job["full_endpoint_x"]
        if cache and cache["kind"] == "family":
            fold = next(f for f in record["folds"] if f["norad"] == job["norad"])
        elif cache and cache["kind"] == "audit":
            assert record["norad"] == job["norad"]
            fold = dict(norad=record["norad"], track_ids=record["source_track_ids"],
                        x=record["exact_x"], retained_score=record["exact_score"],
                        optimizer=record["optimizer"], common_held_score=record["exact_common_held"]["score"],
                        held_observation_count=record["exact_common_held"]["held_observation_count"])
        else:
            assert (cache is None or cache["kind"] == "atomic") and record["job_key"] == key
            fold = record["fold"]
        assert fold["track_ids"] == job["source_track_ids"]
        qualified = qualifies(fold)
        score = fold.get("common_held_score")
        if qualified:
            assert score is not None and math.isfinite(score)
        row.update(available=True, qualified=qualified, common_held_score=score,
                   held_observation_count=fold["held_observation_count"],
                   position=fold.get("x"), evidence_path=str(path))
        rows.append(row)
    families = []
    for family in FAMILIES:
        subset = [r for r in rows if r["family"] == family]
        assert len(subset) == expected_folds
        qualified = all(r["qualified"] for r in subset)
        coverage = [(r["norad"], r["track_ids"], r.get("held_observation_count")) for r in subset]
        families.append(dict(family=family, qualified=qualified, coverage=coverage,
                             qualified_folds=sum(r["qualified"] for r in subset),
                             common_held_sum=sum(r["common_held_score"] for r in subset) if qualified else None))
    selectable = all(f["qualified"] for f in families) and all(f["coverage"] == families[0]["coverage"] for f in families)
    selected = max(families, key=lambda f: f["common_held_sum"])["family"] if selectable else None
    result = dict(schema="ds11-source-loo-exact-screen-selection/v1", index=index, reference_used=False,
                  planned_folds=len(jobs), cached_folds=sum(r["cached"] for r in rows),
                  qualified_folds=sum(r["qualified"] for r in rows),
                  selectable=selectable, selected_family=selected, families=families,
                  folds=rows, sources=sources)
    folder = HERE / "selections"
    folder.mkdir(exist_ok=True)
    with (folder / f"{index:02d}.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k not in ("folds", "families", "sources")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=int, choices=(0, 4, 8, 12, 16, 20, 24, 28))
    main(parser.parse_args().index)
