"""Posthoc coverage attribution; no relaxed scoring or refitting."""

from collections import defaultdict

from study import HERE, read, save


def main():
    donors = []
    targets = []
    for u in read(HERE / "plan.json")["units"]:
        cases = read(HERE / "runs" / u["unit_id"] / "result.json")["cases"]
        (donors if u["role"] == "donor" else targets).extend(cases)
    index = defaultdict(list)
    for d in donors:
        index[d["number"]].append(d)
    counts = defaultdict(
        lambda: dict(
            eligible_cases=0, two_groups_any_rx_rf=0, two_groups_same_rx=0, two_groups_same_rx_rf=0
        )
    )
    for t in targets:
        row = counts[t["unit_id"]]
        row["eligible_cases"] += 1
        prior = [d for d in index[t["number"]] if d["available_utc_ns"] < t["start_utc_ns"]]
        for field, selected in (
            ("two_groups_any_rx_rf", prior),
            ("two_groups_same_rx", [d for d in prior if d["receiver_id"] == t["receiver_id"]]),
            (
                "two_groups_same_rx_rf",
                [
                    d
                    for d in prior
                    if d["receiver_id"] == t["receiver_id"] and d["rf_hz"] == t["rf_hz"]
                ],
            ),
        ):
            row[field] += len({d["unit_id"] for d in selected}) >= 2
    save(
        HERE / "attrition.json",
        dict(
            posthoc=True,
            meaning="coverage only; original scoring gates unchanged",
            panels=dict(counts),
        ),
    )
    print(dict(counts), flush=True)


if __name__ == "__main__":
    main()
