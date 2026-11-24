"""Audit fixed full-anchor phases without replacing unmeasured apertures."""

import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
from math import log
from pathlib import Path
from statistics import median
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from late_pilot_rescue import key, near, originals, verified  # noqa: E402
from ds30_0049_receiver_factorial import ARMS, CASE, CROSSOVER, CROSSOVER_PIN, controls, digest, observation, write  # noqa: E402
from mixed_aperture_receiver import strongest  # noqa: E402


POLICIES = ("coincident", "phase_four", "single_alternating")
SCOPE = (("DS30-0049/prefix", 384), ("DS30-0049/full", 986), ("DS30-0016", 808),
         ("DS30-0008", 64), ("DS30-0169", 64))
FULL, SHORT = "20-two", "8-primary"
ARCHIVES = {
    "ds30-0049-receiver-factorial": "4af8b73101dce9b71a06b38a10e2484ef04b74f42b5221cfec1e818d21ea3b58",
    "late-pilot-rescue": "2b725ccdb473948c2fdbd042a4029060912783f424b8d73c98db34e7537e5a50",
}
HISTORY_PIN = "f13fc2e02be5474de37b3efb5fba195e3a45daf534e3fa4e7d60c76500cef9ee"


def measured_archive(name):
    path = HERE / "measurements" / (name + ".json.gz")
    blob = path.read_bytes()
    if sha256(blob).hexdigest() != ARCHIVES[name]:
        raise ValueError("The prior sealed detector assay changed")
    return json.loads(gzip.decompress(blob))


def is_full(policy, slot, radio):
    cycle, phase = divmod(slot, 8)
    if policy == "phase_four":
        return phase == 4 * radio
    if policy == "single_alternating":
        return phase == 0 and radio == cycle % 2
    if policy == "coincident":
        return phase == 0
    raise ValueError("Unknown fixed anchor schedule")


def schedule(probes):
    slots = Counter()
    previous = -1
    plan = []
    for a, b in zip(probes[::2], probes[1::2], strict=True):
        metadata = dict(a, candidates=[])
        if (a["visit_index"] <= previous or a["receiver_id"] != 0
                or dict(metadata, receiver_id=1) != dict(b, candidates=[])):
            raise ValueError("The original signed stereo chronology changed")
        previous = a["visit_index"]
        stream = a["edge"], a["channel"], a["actual_rf_hz"]
        slot = slots[stream]
        slots[stream] += 1
        for probe in (a, b):
            lane = probe["receiver_id"]
            modes = {kind: FULL if is_full(kind, slot, lane) else SHORT for kind in POLICIES}
            plan.append(dict(opportunity=dict(probe, candidates=[]), stream=stream, slot=slot, modes=modes))
    return plan, slots


def full_gap(plan, slots, policy):
    by_stream = defaultdict(list)
    timings = {}
    costs = Counter()
    for row in plan:
        p = row["opportunity"]
        channel, index = row["stream"], row["slot"]
        timings[channel, index] = p["valid_start_counter"]
        if row["modes"][policy] == FULL:
            by_stream[channel].append(index)
            by_stream[(*channel, p["receiver_id"])].append(index)
            costs[p["visit_index"]] += 1
    any_radio, per_radio = [], []
    for stream, count in sorted(slots.items()):
        for tag in (stream, (*stream, 0), (*stream, 1)):
            anchors = sorted(set(by_stream[tag]))
            internal = list(zip(anchors, anchors[1:]))
            gaps = dict(stream=tag, calls=len(anchors),
                        largest_uncovered_run=max((b-a-1 for a, b in zip([-1, *anchors], [*anchors, count], strict=True))),
                        max_internal_slot_gap=max((b-a for a, b in internal), default=None),
                        max_internal_seconds=max(((timings[stream, b]-timings[stream, a])/1e7 for a, b in internal), default=None),
                        median_internal_seconds=median((timings[stream, b]-timings[stream, a])/1e7 for a, b in internal) if internal else None)
            (any_radio if len(tag) == 3 else per_radio).append(gaps)
    complete_full = sum(row["modes"][policy] == FULL and row["slot"] // 8 < slots[row["stream"]] // 8 for row in plan)
    return dict(full_calls=sum(costs.values()), short_calls=len(plan)-sum(costs.values()),
                full_calls_complete_cycles=complete_full, full_calls_partial_tails=sum(costs.values())-complete_full,
                visits_with_one_full=sum(v == 1 for v in costs.values()), visits_with_two_full=sum(v == 2 for v in costs.values()),
                visits_with_zero_full=len(plan)//2-len(costs), peak_full_calls_per_visit=max(costs.values(), default=0),
                by_stream_any=any_radio, by_stream_radio=per_radio)


def measured_rows(tape, plan, published):
    tape_by_key = {key(row["opportunity"]): row for row in tape}
    left = set(tape_by_key)
    mixed = {key(row): row for row in published}
    observed = []
    for row in plan:
        probe = row["opportunity"]
        identifier = key(probe)
        base = row["modes"]["coincident"]
        values = {}
        if identifier in tape_by_key:
            raw = tape_by_key[identifier]
            left.remove(identifier)
            if raw["opportunity"] != probe or raw["anchor"] != (base == FULL):
                raise ValueError("Paired aperture tape differs from original metadata and anchor phases")
            values = {mode: strongest(factors) for mode, factors in raw["alternatives"].items() if mode in (FULL, SHORT)}
        if identifier in mixed:
            archived = mixed[identifier]
            selected = strongest(archived["candidates"])
            if dict(archived, candidates=[]) != probe or base in values and values[base] != selected:
                raise ValueError("Scheduled strongest factor does not match the published unfiltered packet")
            values[base] = selected
        if base not in values:
            raise ValueError("Every original scheduled aperture must be measured")
        observed.append(values)
    if left:
        raise ValueError("Paired aperture tape contains rows outside of the verified original scope")
    return observed


def retention(selected, reference, base, shared):
    values = Counter()
    for (known, factor), stock, prior, common in zip(selected, reference, base, shared, strict=True):
        values.update(lanes=1, unknown=not known, installed_positive=stock is not None,
                      installed_unknown=stock is not None and not known, candidate_positive=known and factor is not None)
        if stock is None:
            continue
        matches = known and near(stock, factor)
        values.update(matched=matches, exact=known and stock == factor)
        if common:
            previous = near(stock, prior)
            values.update(shared_installed=1, shared_matched=matches, shared_exact=stock == factor,
                          shared_gained=matches and not previous, shared_lost=previous and not matches)
    lower, missing = values["matched"], values["installed_unknown"]
    values["aperture_unknown_but_no_reference_factor"] = values["unknown"]-missing
    return dict(values, installed_match_bounds=[lower, lower+missing],
                exact_bounds=[values["exact"], values["exact"]+missing])


def covered_visits(plan, selected, ids, reference):
    by_visit = defaultdict(list)
    for i in ids:
        known, current = selected[i]
        by_visit[plan[i]["opportunity"]["visit_index"]].append((known, near(reference[i], current)))
    count = sum(any(match for _, match in flags) for flags in by_visit.values())
    upper = sum(any(match or not known for known, match in flags) for flags in by_visit.values())
    return dict(installed_owner_visits=len(by_visit), matching_visit_bounds=[count, upper])


def held_replay(plan, slots, selected, policy, continuation):
    seqs = defaultdict(list)
    for i, row in enumerate(plan):
        seqs[(*row["stream"], row["opportunity"]["receiver_id"])].append(i)

    # Unknown rows are recorded for arithmetic only and are never passed to Continuation.
    witnesses = []
    tally = {radio: Counter() for radio in (0, 1)}
    for lane, positions in seqs.items():
        radio = lane[-1]
        for j, anchor_i in enumerate(positions):
            if plan[anchor_i]["modes"][policy] != FULL:
                continue
            if plan[anchor_i]["slot"] + 7 >= slots[lane[:-1]]:
                tally[radio]["partial"] += 1
                continue
            donor = positions[j+1:j+8]
            if len(donor) != 7 or any(plan[k]["modes"][policy] != SHORT for k in donor):
                raise ValueError("Held score requires exactly seven following same-lane short visits")
            tally[radio]["complete"] += 1
            tally[radio]["all_measurements_known"] += selected[anchor_i][0] and all(selected[k][0] for k in donor)
            witnesses.append((radio, anchor_i, donor))
    if not all(item[0] for item in selected):
        return dict(decision=None, held=tally, unresolved="at least one selected-aperture row is unmeasured"), None
    final_rows = [dict(row["opportunity"], candidates=[] if factor is None else [factor])
                  for row, (_, factor) in zip(plan, selected, strict=True)]
    masked_rows = [dict(probe, candidates=[]) if row["modes"][policy] == FULL else probe
                   for row, probe in zip(plan, final_rows, strict=True)]
    erased = continuation()
    in_history = [erased.select(row)[1] is not None for row in masked_rows]
    gain = {radio: 0. for radio in (0, 1)}
    for radio, label, donors in witnesses:
        p_base = (sum(bool(masked_rows[k]["candidates"]) for k in donors) + .5) / 8
        p_hist = (sum(in_history[k] for k in donors) + .5) / 8
        positive = final_rows[label]["candidates"]
        gain[radio] += log(p_hist if positive else 1-p_hist) - log(p_base if positive else 1-p_base)
    replay = continuation()
    restored = [row["candidates"][keep] if keep is not None else None
                for row in final_rows for keep in (replay.select(row)[1],)]
    return dict(decision="history" if all(x > 0 for x in gain.values()) else "unfiltered",
                held=tally, log_score_gain_by_radio=gain, history_positive=sum(x is not None for x in restored)), restored


def owner_group_indexes(stock, named, reference_owners, whole_0049):
    session = stock["source"]["session_id"]
    full_rows = {observation(row, session): row for row in stock["source"]["probes"]}
    groups = {}
    for arm, owners in reference_owners.items():
        ids = {row[0] for row in owners}
        groups["installed_" + arm] = ids
        if whole_0049 is not None:
            successor_rows, successor_owners = whole_0049
            lost = ids - {row[0] for row in successor_owners[arm]}
            groups["former_empty_" + arm] = {i for i in lost if not successor_rows[i]["candidates"]}
            groups["former_displaced_" + arm] = {i for i in lost if successor_rows[i]["candidates"]
                    and not near(strongest(full_rows[i]["candidates"]), strongest(successor_rows[i]["candidates"]))}
            if (len(groups["former_empty_" + arm]), len(groups["former_displaced_" + arm])) != (44, 21):
                raise ValueError("The original full-capture lost owners differ from the authenticated prior audit")
    names = {observation(row, session): i for i, row in enumerate(named)}
    return {name: sorted(names[i] for i in ids if i in names) for name, ids in groups.items()}


def known_pairs(values, row, policy):
    mode = row["modes"][policy]
    return mode in values, values.get(mode)


def evaluate(plan, slots, source, published, named, groups, continuation):
    known = measured_rows(source, plan, published)
    ref = [strongest(row["candidates"]) for row in named]
    paired = [FULL in row and SHORT in row for row in known]
    shared = [all(mode in values for mode in row["modes"].values()) for row, values in zip(plan, known, strict=True)]
    original = [known_pairs(values, row, "coincident")[1] for row, values in zip(plan, known, strict=True)]
    strata = defaultdict(list)
    for i, row in enumerate(named):
        strata[f"rx{row['receiver_id']}/ch{row['channel']}"].append(i)
    completed = [i for i, row in enumerate(plan) if row["slot"] // 8 < slots[row["stream"]] // 8]
    complete_set = set(completed)
    roster = dict(all=list(range(len(plan))), complete_cycles=completed, **groups)
    for name, idx in groups.items():
        for lane in idx:
            row = named[lane]
            strata[f"{name}/rx{row['receiver_id']}/ch{row['channel']}"].append(lane)
        roster[name + "/complete_cycles"] = [i for i in idx if i in complete_set]
    roster.update(strata)
    result = {}
    for policy in POLICIES:
        actual = [known_pairs(values, row, policy) for row, values in zip(plan, known, strict=True)]
        held, history = held_replay(plan, slots, actual, policy, continuation)
        groups_report = {}
        for name, idx in roster.items():
            groups_report[name] = retention([actual[i] for i in idx], [ref[i] for i in idx],
                                            [original[i] for i in idx], [shared[i] for i in idx])
            groups_report[name]["physically_paired_installed"] = sum(paired[i] and ref[i] is not None for i in idx)
            groups_report[name]["physically_paired_matches"] = sum(paired[i] and near(ref[i], actual[i][1]) for i in idx)
        result[policy] = dict(coverage=full_gap(plan, slots, policy), retention=groups_report, held=held,
                              owner_visits={n: covered_visits(plan, actual, idx, ref) for n, idx in groups.items()},
                              history_replay_retention=retention([(True, x) for x in history], ref, original, shared)
                              if history is not None else None)
    return dict(paid_lanes=len(plan), shared_measured_lanes=sum(shared), physically_paired_lanes=sum(paired), policies=result)


def score(out):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.variants import carrier_continuation

    signer = Path(carrier_continuation.__file__)
    if digest(signer) != HISTORY_PIN:
        raise ValueError("The released chronological Continuation source changed")
    factorial = measured_archive("ds30-0049-receiver-factorial")
    late = measured_archive("late-pilot-rescue")
    pair = controls()
    cross = verified(CROSSOVER, CROSSOVER_PIN)
    latter_owners = cross["ordered_owner_rows"]["successor-successor"]
    stock, successor = (pair[label][0] for label in ("installed", "successor"))
    for arm in ARMS:
        if canonical_digest({row[0]: row[1] for row in latter_owners[arm]}) != pair["successor"][1]["evidence"]["owners"][arm]:
            raise ValueError("The original successor owners differ from their terminal")
    old_route = verified(CASE/"successor/attempt-000002/publication/unified-short-bootstrap.json",
                        "01e2eb141201e8ec02a67d5ce2ce44d74e8c7262952c2e8cf61c8593ef0b845e")
    if old_route["held_anchor_route"]["choice"]["route"] != "unfiltered" or old_route["native_sha256"] != canonical_digest(successor):
        raise ValueError("The published DS30-0049 mixed packet did not preserve strongest selection")
    full_0049 = ({observation(row, stock["source"]["session_id"]): row for row in successor["source"]["probes"]}, latter_owners)
    plans = {}
    evidence = {}
    for label, stop in SCOPE:
        case = label.split("/")[0]
        stock, mixed, owners = originals(case)
        probes = [r for r in stock["source"]["probes"] if r["visit_index"] < stop]
        plan, slots = schedule(probes)
        plans[label] = canonical_digest(plan)
        if case == "DS30-0016":
            choice = verified(Path("/dev/shm/leo-v3-integrated-original-03/DS30-0016/candidate/unified-short-bootstrap.json"),
                              "d9c5bd432db0d7a380628c53b890a45120cf13dd413ff4e61e9098fae32356af")
            if choice["held_anchor_route"]["choice"]["route"] != "unfiltered" or choice["native_sha256"] != canonical_digest(mixed):
                raise ValueError("The charted redaction is not the original unfiltered mixed packet")
        subset = full_0049 if case == "DS30-0049" else None
        raw = factorial["native-rows.json"]["document"] if subset else late[case]["long-receiver.json"]["document"]
        published = [r for r in mixed["source"]["probes"] if r["visit_index"] < stop] if mixed is not None else []
        evidence[label] = (plan, slots, raw, published, probes, owner_group_indexes(stock, probes, owners, subset))
    out.mkdir(mode=0o700)
    protocol = HERE / "staggered-anchors-protocol.md"
    write(out / "plan.json", dict(plans=plans, archives=ARCHIVES, sources={path.name: digest(path) for path in (Path(__file__), protocol, signer)}))
    result = {case: evaluate(*args, carrier_continuation.Continuation) for case, args in evidence.items()}
    write(out / "result.json", dict(plan_sha256=digest(out / "plan.json"), cases=result))


if __name__ == "__main__":
    from empty_bootstrap import PAYLOAD, RELEASE

    sys.path[:0] = [str(PAYLOAD), str(RELEASE / "src"), str(HERE.parents[2])]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    score(parser.parse_args().output)
