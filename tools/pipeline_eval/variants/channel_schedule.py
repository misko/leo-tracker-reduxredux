"""Keep complete channels before track extraction, preserving the recorded time base."""

import sys
from collections import Counter
from functools import partial
from pathlib import Path

from tools.pipeline_eval.variants import v5_core, v5_lean

SCHEDULES = {"glrt_odd_channels": (1, 3, 5, 7), "glrt_even_channels": (2, 4, 6, 8)}
BOUNDARY = "Scheduled archived GLRT observations to the paired v5 cavity positions"


def scheduled(schedule, channel):
    if type(channel) is not int or not 1 <= channel <= 8:
        raise ValueError("target must identify an RF channel from 1 through 8")
    return channel in SCHEDULES[schedule]


def analyze_scheduled(window, schedule, analyze, policy):
    if schedule != "all" and not scheduled(schedule, window.target["channel"]):
        return None
    return analyze(window, window.receiver_ids, None, policy)


def selected_probes(document, schedule):
    source = document["source"]
    rows, channels = [], {}
    for p in source["probes"]:
        visit, channel = p["visit_index"], p["channel"]
        if channels.setdefault(visit, channel) != channel:
            raise ValueError("receivers on the same visit have different RF channels")
        if scheduled(schedule, channel):
            rows.append(p)
    counts = Counter(channels.values())
    metrics = dict(
        schedule=schedule,
        channels=list(SCHEDULES[schedule]),
        original_probes=len(source["probes"]),
        kept_probes=len(rows),
        original_valid_visits=len(channels),
        kept_valid_visits=sum(counts[c] for c in SCHEDULES[schedule]),
        valid_visits_by_channel=[counts[c] for c in range(1, 9)],
    )
    # This analytic view preserves the original acquisition record and detector provenance.
    # Unscheduled probes are absent. Each retained probe keeps its native identity and values.
    return dict(document, source=dict(source, probes=rows)), metrics


def run(case, work_dir, schedule):
    if schedule not in SCHEDULES:
        raise ValueError("unknown channel schedule")
    result = v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(schedule,))
    result["boundary"] = BOUNDARY
    return result


if __name__ == "__main__":
    source, target, schedule = sys.argv[1:]
    v5_core.worker(source, target, select_document=partial(selected_probes, schedule=schedule))
