"""Count published named orbit policies from the signed 100-case timing panel."""

from collections import Counter
import json

from prospective_small_physical import ROSTER, ROSTER_PINS, checked


def summarize(rows):
    panels = {}
    for size in (4, 16, 100):
        group = rows[:size]
        panels[size] = dict(assigned=len(group), decisions=dict(Counter(r["decision"] for r in group)),
                            complete_policies=dict(Counter(r["policy"] for r in group if r["decision"] == "complete")))
    selected = next((row["case"] for row in rows
                     if row["decision"] == "complete" and row["policy"] == "history_support"
                     and row["case"] != "DS30-0160"), None)
    return dict(panels=panels, next_case=selected)


def study():
    panel = json.loads(checked(ROSTER / "panel.json", ROSTER_PINS["panel.json"]))
    pairs = json.loads(checked(ROSTER / "final/decision.json", ROSTER_PINS["final/decision.json"]))["pair_sha256"]
    order = [row["case"] for row in panel["cases"]]
    if len(order) != 100 or len(set(order)) != 100 or set(order) != set(pairs):
        raise ValueError("Final panel and decision disagree")
    rows = []
    byte_count = 0
    for case in order:
        root = ROSTER / "publications" / case
        body = checked(root / "pair.json", pairs[case])
        byte_count += len(body)
        pair = json.loads(body)
        if pair["candidate_specification_digest"] != "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f":
            raise ValueError("Unexpected named version")
        run = pair["runs"]["candidate"]["receipt"]
        policy = None
        if run["decision"] == "complete":
            path, = (root / "candidate/fast-scan-automatic-work").glob("*/terminal.json")
            terminal_bytes = checked(path, run["terminal_sha256"])
            byte_count += len(terminal_bytes)
            terminal = json.loads(terminal_bytes)
            if terminal["decision"] != "ok" or terminal["session_id"] != run["session_id"]:
                raise ValueError("Signed terminal outcome or session differs")
            policy = terminal["orbit_policy"]
        rows.append(dict(case=case, decision=run["decision"], policy=policy, pair_sha256=pairs[case],
                         terminal_sha256=run.get("terminal_sha256")))
    return dict(rows=rows, pair_and_terminal_bytes=byte_count, **summarize(rows))


if __name__ == "__main__":
    print(json.dumps(study(), indent=2, sort_keys=True, allow_nan=False))
