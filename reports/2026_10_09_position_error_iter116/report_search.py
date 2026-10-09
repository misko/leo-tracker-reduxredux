"""Read durable search traces only; no observations, predictor or reference ports."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def read(path, digest, hashes):
    payload = path.read_bytes()
    row = json.loads(payload)
    assert row["protocol_sha256"] == digest, "Foreign durable receipt"
    hashes[str(path)] = hashlib.sha256(payload).hexdigest()
    return row


def summarize(events):
    evaluated = [e for e in events if e["event"] == "evaluated"]
    coordinates = [(e["east"], e["north"]) for e in evaluated]
    assert len(coordinates) == len(set(coordinates)), "Duplicate evaluated point"
    statuses = [e for e in events if e["event"] == "fit-status"]
    deferred = [e for e in events if e["event"] == "deferred"]
    ranks = [e for e in events if e["event"] == "ranks"]
    assert len(deferred) <= 1 and len(ranks) <= 1
    sealed = bool(ranks)
    if sealed:
        assert deferred and events[-1]["event"] == "ranks"
        assert len(ranks[0]["rows"]) == len(evaluated)
    cells = deferred[0]["cells"] if deferred else None
    return {
        "trace_sealed": sealed,
        "initial_grid_sealed": any(
            e["event"] in ("pop", "child", "deferred", "ranks") for e in events
        ),
        "event_count": len(events),
        "sample_count": len(evaluated),
        "samples_by_depth": dict(sorted(Counter(e["depth"] for e in evaluated).items())),
        "fit_status_counts": dict(Counter(e["status"] for e in statuses)),
        "unqualified_point_count": sum(e.get("converged") is False for e in statuses),
        "qualification_unknown_count": sum(
            e["status"] == "complete" and e.get("converged") is None for e in statuses
        ),
        "failed_point_count": sum(e["status"] == "failed" for e in statuses),
        "deferred_cell_count": None if cells is None else len(cells),
        "deferred_by_depth": None if cells is None else dict(Counter(c["depth"] for c in cells)),
        "sampled_points": [
            {k: e[k] for k in ("east", "north", "depth", "score")} for e in evaluated
        ],
    }


def compare_initial(native, fixed):
    maps = [
        {(e["east"], e["north"]): e["score"] for e in x["sampled_points"] if e["depth"] == 0}
        for x in (native, fixed)
    ]
    common = sorted(set(maps[0]) & set(maps[1]))
    complete = bool(common) and set(maps[0]) == set(maps[1])
    # Compare ranks only on this identical domain, never against different sample sets.
    ranking = [
        {
            point: rank + 1
            for rank, point in enumerate(sorted(common, key=lambda p: (values[p], *p)))
        }
        for values in maps
    ]
    return {
        "common_initial_points": len(common),
        "initial_domains_equal": complete,
        "initial_rank_comparison_complete": complete
        and native["initial_grid_sealed"]
        and fixed["initial_grid_sealed"],
        "initial_rank_changes": [
            {
                "east": p[0],
                "north": p[1],
                "native_rank": ranking[0][p],
                "fixed_rank": ranking[1][p],
                "rank_delta": ranking[1][p] - ranking[0][p],
            }
            for p in common
        ],
        "rank_scope": "Intersection of initial grids; partial domains explicitly flagged",
    }


def build(directory, digest):
    directory = Path(directory)
    hashes, traces = {}, {}
    terminal = directory / "result.json"
    result = read(terminal, digest, hashes) if terminal.exists() else None
    if result is not None:
        assert result["status"] in ("complete", "failed", "incomplete", "budget-exhausted")
        assert result["complete"] == (result["status"] == "complete")
    for arm in ("fitted-c", "zero-c"):
        for mode in ("native", "fixed"):
            name = arm + "-" + mode
            paths = sorted((directory / "traces" / name).glob("*.json"))
            assert [p.stem for p in paths] == [f"{i:05}" for i in range(len(paths))]
            traces[name] = summarize([read(p, digest, hashes)["event"] for p in paths])
    starts = sorted((directory / "slices").glob("*.started.json"))
    finishes = sorted((directory / "slices").glob("*.finished.json"))
    assert all(p.with_name(p.name.replace("finished", "started")) in starts for p in finishes)
    for path in starts:
        read(path, digest, hashes)
    finished = [read(path, digest, hashes) for path in finishes]
    gate = directory / "native-parity.json"
    parity = read(gate, digest, hashes) if gate.exists() else None
    if parity is not None:
        assert parity["status"] == "verified"
        assert parity["count"] == traces["fitted-c-native"]["sample_count"]
    if result is not None and result["status"] == "complete":
        assert all(row["trace_sealed"] for row in traces.values())
    return {
        "scope": "Search-only durable metadata snapshot; no position accuracy claim",
        "protocol_sha256": digest,
        "terminal_status": None if result is None else result["status"],
        "study_terminal": result is not None,
        "native_parity": parity,
        "claimed_slices": len(starts),
        "finished_slices": len(finishes),
        "unfinished_slices": len(starts) - len(finishes),
        "known_finished_elapsed_s": sum(row["elapsed_s"] for row in finished),
        "slice_statuses": [r["status"] for r in finished],
        "traces": traces,
        "initial_grid_comparisons": {
            arm: compare_initial(traces[arm + "-native"], traces[arm + "-fixed"])
            for arm in ("fitted-c", "zero-c")
        },
        "receipt_sha256": hashes,
        "limitations": [
            "Live snapshot captures only already durable receipts; future events excluded",
            "Deferred heap cells can overlap or lie at the radius edge; count is not area coverage",
            "Native/fixed scores belong to different scoring models; "
            "rank changes imply no accuracy gain",
            "No reference coordinates, operational winner errors or recording inputs were read",
        ],
    }


def markdown(data):
    lines = [
        "# Search-only checkpoint",
        "",
        f"Terminal status: {data['terminal_status'] or 'not terminal'}. "
        f"Finished/claimed slices: {data['finished_slices']}/{data['claimed_slices']}; "
        f"known finished elapsed: {data['known_finished_elapsed_s']:.3f}s.",
        "",
        "| Queue | Sealed | Sampled | Depth0/1/2/3 | Unqualified | Failed | Deferred |",
        "|---|---|---:|---|---:|---:|---:|",
    ]
    for name, row in data["traces"].items():
        counts = row["samples_by_depth"]
        depths = "/".join(str(counts.get(i, counts.get(str(i), 0))) for i in range(4))
        deferred = row["deferred_cell_count"]
        lines.append(
            f"| {name} | {row['trace_sealed']} | {row['sample_count']} | {depths} | "
            f"{row['unqualified_point_count']} | {row['failed_point_count']} | "
            f"{deferred if deferred is not None else 'pending'} |"
        )
    lines += [
        "",
        "Unfinished slice duration is not imputed. A live fit-status event can precede "
        "its evaluated-point event; counts need not agree mid-write. Deferred-cell counts "
        "are heap entries, not area coverage. Initial-grid rank comparisons are complete "
        "only after both initial grids seal and their domains agree. This checkpoint reads "
        "no reference coordinates or operational winner errors and makes no position claim.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--protocol-digest", required=True)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    result = build(args.directory, args.protocol_digest)
    print(markdown(result) if args.markdown else json.dumps(result, indent=2, allow_nan=False))
