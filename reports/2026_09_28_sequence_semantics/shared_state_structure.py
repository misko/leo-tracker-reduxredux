"""Compare empirical shared-state labels with separately measured frame structure."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent


def runs(states):
    result = []
    for index, state in enumerate(states):
        if not result or result[-1]["state"] != state:
            result.append(dict(state=state, first_frame=index, last_frame=index, length=1))
        else:
            result[-1]["last_frame"] = index
            result[-1]["length"] += 1
    return result


def loo(values, labels):
    errors, baseline = [], []
    for i in range(len(values)):
        other = np.arange(len(values)) != i
        peers = other & (labels == labels[i])
        if not peers.any():
            continue
        errors.append(abs(values[i] - np.median(values[peers])))
        baseline.append(abs(values[i] - np.median(values[other])))
    return dict(
        count=len(errors),
        state_median_mae=float(np.mean(errors)),
        overall_median_mae=float(np.mean(baseline)),
    )


def main():
    state_path = BASE / "local/shared_header_coordinates.json"
    boundary_path = BASE / "local/soft_tail_boundary.json"
    map_path = BASE / "local/frame_binary_map.json"
    states = json.loads(state_path.read_text())["reference_state_indices"]
    boundary = json.loads(boundary_path.read_text())
    primary = boundary["primary_flank"]
    boundaries = {r["frame"]: r["boundary"] for r in boundary["rows"] if r["flank"] == primary}
    maps = {r["frame_index"]: r for r in json.loads(map_path.read_text())["frames"]}
    rows = [
        dict(
            frame=f,
            state=states[f],
            tail_boundary=b,
            early_hard_binary_last_symbol=maps[f]["binary_like_intervals"][0][1],
        )
        for f, b in sorted(boundaries.items())
    ]
    groups = []
    for state in sorted(set(r["state"] for r in rows)):
        members = [r for r in rows if r["state"] == state]
        groups.append(
            dict(
                state=state,
                frames=[r["frame"] for r in members],
                tail_boundaries=[r["tail_boundary"] for r in members],
                early_hard_binary_ends=[r["early_hard_binary_last_symbol"] for r in members],
            )
        )
    labels = np.array([r["state"] for r in rows])
    metrics = {
        key: loo(np.array([r[key] for r in rows]), labels)
        for key in ("tail_boundary", "early_hard_binary_last_symbol")
    }
    stretches = runs(states)
    same = sum(a == b for a, b in zip(states[:-1], states[1:], strict=True))
    counts = np.bincount(states)
    # Expected adjacent equality under uniform permutation of the observed labels.
    expected = float(np.sum(counts * (counts - 1)) / (len(states) * (len(states) - 1)))
    summary = dict(
        frames=len(states),
        runs=len(stretches),
        longest_run=max(r["length"] for r in stretches),
        adjacent_same_fraction=same / (len(states) - 1),
        permutation_expected_adjacent_same=expected,
        structure_frames=len(rows),
        loo=metrics,
    )
    output = dict(
        summary=summary,
        runs=stretches,
        structure_rows=rows,
        state_groups=groups,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (state_path, boundary_path, map_path)
        },
        limitation="Exploratory association, same acquisition. State labels fitted "
        "on all78frames; structural measures available only13. Early hard-axis "
        "region is a processing diagnostic, not decoded header length. LOO "
        "does not undo prior exploratory selection or prove semantics.",
    )
    (BASE / "local/shared_state_structure.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(json.dumps(groups, indent=2))


if __name__ == "__main__":
    main()
