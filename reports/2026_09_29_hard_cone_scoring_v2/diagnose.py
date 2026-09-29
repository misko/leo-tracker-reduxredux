"""Post-hoc decomposition of stored scores; no fits or new model evaluations."""

from collections import defaultdict

from study import HERE, read, save, verify


def main():
    verify(read(HERE / "evidence-sha256.json")["sha256"])
    plan = read(HERE / "plan.json")
    totals = defaultdict(lambda: defaultdict(float))
    seen = set()
    for unit in plan["units"]:
        if unit["group"]["size"] != 8:
            continue
        result = read(HERE / "runs" / unit["unit_id"] / "result.json")
        baseline = {
            (r["session_id"], r["track_id"]): r for r in result["models"]["baseline"]["rows"]
        }
        assert seen.isdisjoint(baseline)
        seen.update(baseline)
        for arm in plan["arms"]:
            tally = totals[unit["group"]["source_dataset"], arm]
            for row in result["models"][arm]["rows"]:
                prior = baseline[row["session_id"], row["track_id"]]
                delta = row["held_log_score"] - prior["held_log_score"]
                unsupported = row["hard_supported_candidates"] == 0
                tally["tracks"] += 1
                tally["held_observations"] += row["held_observations"]
                tally["held_change_nats"] += delta
                tally["unsupported_tracks"] += unsupported
                tally["unsupported_held_change_nats"] += delta if unsupported else 0
                tally["supported_held_change_nats"] += 0 if unsupported else delta
                tally["baseline_signal_to_background"] += (
                    prior["signal_responsibility"] > 0.5 and row["signal_responsibility"] <= 0.5
                )
    assert len(seen) == 4328
    rows = []
    for (dataset, arm), tally in sorted(totals.items()):
        assert (
            abs(
                tally["held_change_nats"]
                - tally["supported_held_change_nats"]
                - tally["unsupported_held_change_nats"]
            )
            < 1e-7
        )
        rows.append({"dataset": dataset, "arm": arm, **dict(tally)})
    summary = read(HERE / "summary.json")
    for row in rows:
        original = [
            r["arms"][row["arm"]]
            for r in summary["rows"]
            if r["dataset"] == row["dataset"] and r["size"] == 8
        ]
        assert abs(row["held_change_nats"] - sum(r["held_change_nats"] for r in original)) < 1e-7
    save(HERE / "decomposition.json", {"unique_tracks": len(seen), "rows": rows})
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
