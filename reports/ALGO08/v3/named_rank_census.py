"""Read the signed named-v3 finalist outcomes in their original DS30 enrollment order."""

from collections import Counter
import json
from statistics import median

from prospective_small_physical import ROSTER, ROSTER_PINS, checked


def extract(case, pair, pin):
    run = pair["runs"]["candidate"]
    receipt = run["receipt"]
    if pair["candidate_specification_digest"] != "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f":
        raise ValueError("Unexpected release in named run")
    screen = receipt.get("screened_nomination", {})
    rank = screen.get("winning_rank")
    scores = screen.get("screen_c0_scores", [])
    cost = screen.get("initial_screen_cpu_s")
    advantage = None
    if rank is not None:
        if (screen["fallback"] or screen["ranks"] != list(range(len(scores)))
                or rank != min(range(len(scores)), key=scores.__getitem__)):
            raise ValueError("Screen winner disagrees with published ordered scores")
        advantage = scores[0] - scores[rank]
    return dict(case=case, pair_sha256=pin, decision=receipt["decision"], winner=rank,
                initial_screen_cpu_s=cost, process_cpu_s=run["cpu_s"],
                early_fits=screen.get("early_fits"), finish_fits=screen.get("finish_fits"),
                ordered_screen_scores=scores, score_advantage_over_first=advantage)


def summarize(rows):
    fixes = [r for r in rows if r["decision"] == "complete"]
    costs = [r["initial_screen_cpu_s"] for r in rows if r["initial_screen_cpu_s"] is not None]
    changes = [r for r in fixes if r["winner"] is not None and r["winner"] != 0]
    return dict(assigned=len(rows), decisions=dict(Counter(r["decision"] for r in rows)),
                fixed_winners=dict(Counter(r["winner"] for r in fixes)),
                earliest_nonzero=next((r["case"] for r in changes), None),
                timed_n=len(costs), total_recorded_screen_cpu_s=sum(costs),
                median_recorded_screen_cpu_s=median(costs) if costs else None,
                timed_process_cpu_s=sum(r["process_cpu_s"] for r in rows if r["initial_screen_cpu_s"] is not None),
                median_nonzero_advantage=median(r["score_advantage_over_first"] for r in changes) if changes else None)


def study():
    panel = json.loads(checked(ROSTER/"panel.json", ROSTER_PINS["panel.json"]))
    pins = json.loads(checked(ROSTER/"final/decision.json", ROSTER_PINS["final/decision.json"]))["pair_sha256"]
    order = [r["case"] for r in panel["cases"]]
    if len(order) != 100 or len(set(order)) != 100 or set(order) != set(pins):
        raise ValueError("Panel and final signed comparison differ")
    rows = []
    for case in order:
        pair = json.loads(checked(ROSTER/"publications"/case/"pair.json", pins[case]))
        rows.append(extract(case, pair, pins[case]))
    return dict(roster_pins=ROSTER_PINS, rows=rows, panels={n: summarize(rows[:n]) for n in (4, 16, 100)})


if __name__ == "__main__":
    print(json.dumps(study(), indent=2, allow_nan=False))
