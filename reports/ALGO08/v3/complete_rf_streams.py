"""Keep continuous histories on four symmetric RF channels in each pilot edge."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from statistics import mean, pvariance
import subprocess
from time import process_time
from unittest.mock import patch

from . import balanced_stereo as common
from .balanced_stereo_support import predecessor_support


HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "complete-rf-streams-protocol.md"
CONTINUOUS = (1, 4, 5, 8)
ADMITTED = common.schedule


def schedule(original):
    return [dict(row, paid=row["slot"] == 0 or row["stream"][1] in CONTINUOUS)
            for row in ADMITTED(original)]


def original_history_support(original, events):
    from anchor_holds import history_rows
    from leo.contracts.digests import canonical_digest

    original = original["source"]["probes"]
    paid, measured = [], []
    for row in original:
        event = events[row["visit_index"]]
        radio = row["receiver_id"]
        state = event["states"][radio]
        if state == "unmeasured":
            paid.append(dict(row, candidates=[]))
        elif state == ("measured_positive" if row["candidates"] else "measured_empty"):
            paid.append(row)
        else:
            raise ValueError("The paid detector ledger differs from the original signed measurement")
        measured.append(state != "unmeasured")
    kept, anchors_only = Counter(), Counter()
    histories = list(zip(history_rows(original), history_rows(paid), strict=True))
    for paid_lane, (before, after) in zip(measured, histories, strict=True):
        if before["channel"] in CONTINUOUS:
            if not paid_lane or before != after:
                raise ValueError("A continuously measured RF stream must preserve its original signed history")
            kept.update(positive_original=bool(before["candidates"]), positive_paid=bool(after["candidates"]))
        else:
            anchors_only.update(positive_original=bool(before["candidates"]), positive_paid=bool(after["candidates"]))
        if not paid_lane and after["candidates"]:
            raise ValueError("An unmeasured lane cannot contribute a carrier observation")
    return dict(continuous=kept, anchors_only=anchors_only, histories_sha256=canonical_digest(histories))


def freq_support(rows):
    groups = defaultdict(dict)
    for row in rows:
        edge, channel, rf = row["stream"]
        groups[edge][channel, rf] = row

    def describe(values):
        if not values:
            return None
        return dict(count=len(values), min_hz=min(values), max_hz=max(values), mean_hz=mean(values),
                    variance_hz2=pvariance(values))

    return {edge: dict(all=describe([rf for _, rf in streams]),
                       continuous=describe([rf for channel, rf in streams if channel in CONTINUOUS]))
            for edge, streams in groups.items()}


def selected_coverage(packet, issued):
    counts = Counter()
    for row in packet["source"]["probes"]:
        if row["candidates"]:
            counts[row["edge"], row["channel"], row["visit_index"] * 3 // issued] += len(row["candidates"])
    return [dict(edge=edge, channel=channel, original_time_third=third, factors=n)
            for (edge, channel, third), n in sorted(counts.items())]


def run(root):
    from anchor_exposure import PINS, packet
    from dense_geographic_trial import host
    from leo.storage import fast_scan
    from north_held_anchor_pair import tmpfs
    from preloaded_saved_worker import enrolled
    from whole_stereo_8ms_trial import launch, pins, seal

    repo = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={repo}", "-C", str(repo)]
    if (subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip()
            or Path(fast_scan.__file__).resolve() != repo/"src/leo/storage/fast_scan.py"):
        raise ValueError("Freeze the policy and use the checkout's no-create verification port")
    machine = host()
    tmpfs(root.parent)
    source = sha256(Path(__file__).read_bytes()).hexdigest()
    rule = dict(continuous_in_each_pilot_edge=list(CONTINUOUS),
                others="full anchor at admitted stream index 0 modulo 8 only", scope=["edge", "channel", "actual_rf_hz"],
                both_receivers=True, hold="Jeffreys .5 using paid donors only", scheduler_sha256=source)
    root.mkdir()
    binding = dict(host=machine, sources=pins(), commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
                   scheduler_sha256=source, protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(),
                   order=common.CASES, rule=rule)
    common.write(root/"binding.json", binding)
    planned, audits = {}, {}
    for case in common.CASES:
        request, archive, offer, libraries, *_ = enrolled(case)
        folder, pin = PINS["DS30-0016" if case == "weak" else case]["8ms"]
        for path in (folder, request["saved_inventory"], archive, offer, *libraries.values()):
            tmpfs(path)
        with patch.multiple(common, schedule=schedule, RULE=rule):
            common.plan(case, root/case)
        plan = planned[case] = common.read(root/case/"plan.json")
        start = process_time()
        events = plan["events"]
        audits[case] = dict(history=original_history_support(packet(folder, pin), events),
                            causal_support=predecessor_support(events), rf_basis=freq_support(plan["rf_coverage"]),
                            selected_time_and_rf=selected_coverage(common.read(root/case/"detections.json"), len(events)))
        audits[case]["post_plan_cpu_s"] = process_time()-start
        common.write(root/f"{case}-audit.json", audits[case])

    scores = {}
    for case in common.CASES:
        try:
            launch(root, case, next_case=lambda _: "weak")
            seal(root, case)
            result = common.qualify(root, case)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            clock = root/f"{case}-clock.json"
            result = dict(case=case, qualified=False, worker_failure=str(error), clock=common.read(clock) if clock.is_file() else None)
        common.write(root/f"{case}-score.json", result)
        scores[case] = dict(result, plan=planned[case], audit=audits[case])
    common.write(root/"result.json", dict(binding=binding, scores=scores, qualified=all(row["qualified"] for row in scores.values())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
