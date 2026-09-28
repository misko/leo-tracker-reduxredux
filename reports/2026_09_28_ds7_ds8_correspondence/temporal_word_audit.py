"""Test exact within-visit periodicity and observable-word transition models."""

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent


def periodic_conflicts(rows, period):
    phases = defaultdict(set)
    for row in rows:
        phases[(row["group"], row["frame"] % period)].add(row["word"])
    return sum(len(words) > 1 for words in phases.values())


def branches(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["group"]].append(row)
    successors = defaultdict(list)
    for group, observations in groups.items():
        observations.sort(key=lambda r: r["frame"])
        for a, b in zip(observations, observations[1:], strict=False):
            if b["frame"] - a["frame"] == 1:
                # Test within a single visit to avoid configuration/pass changes
                # and uncertain identity assignments explaining a branch.
                successors[(group, a["word"])].append(
                    dict(from_frame=a["frame"], to_frame=b["frame"], next_word=b["word"])
                )
    return [
        dict(group=g, word=w, transitions=transitions)
        for (g, w), transitions in successors.items()
        if len({t["next_word"] for t in transitions}) > 1
    ]


def main():
    source = BASE / "local/decoded-bits.csv"
    rows = [
        dict(
            group=r["group"],
            frame=int(r["frame"]),
            word=r["raw_bits"],
            norad_id=r["norad_id"] or None,
        )
        for r in csv.DictReader(source.open())
    ]
    trials = [
        dict(
            period_frames=p,
            period_nominal_ms=p / 750 * 1000,
            contradictory_phase_groups=periodic_conflicts(rows, p),
        )
        for p in range(1, 24)
    ]
    repeated = defaultdict(list)
    for row in rows:
        repeated[(row["group"], row["word"])].append(row["frame"])
    output = dict(
        input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        periodicity=trials,
        within_visit_branching=branches(rows),
        within_visit_recurrences=[
            dict(group=g, word=w, frames=frames)
            for (g, w), frames in repeated.items()
            if len(frames) > 1
        ],
        limitations=[
            "Exact recovered words tested; same-word recurrences "
            "do not prove a hidden state repeats.",
            "Frame intervals are nominal 1/750 s, not a decoded time field.",
            "No cross-visit absolute frame alignment or UTC synchronization is assumed.",
            "Contradictions reject exact models conditional on recovery; not a noisy-model fit.",
            "No contradictions at long periods with few repeated phases is not positive evidence.",
        ],
    )
    (BASE / "local/temporal-word-audit.json").write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                periodicity=trials,
                branches=len(output["within_visit_branching"]),
                branch_groups=sorted({r["group"] for r in output["within_visit_branching"]}),
                recurrences=len(output["within_visit_recurrences"]),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
