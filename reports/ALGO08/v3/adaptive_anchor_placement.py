"""One causal stereo anchor reservation per eight measured stream visits."""

import argparse
import gzip
import json
import sys
from collections import Counter, defaultdict, deque
from hashlib import sha256
from math import log
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ds30_0049_receiver_factorial import ARMS, observation  # noqa: E402
from late_pilot_rescue import key, near  # noqa: E402
from staggered_anchors import FULL, HISTORY_PIN, SHORT, measured_rows, schedule  # noqa: E402

FULL_NAME = "ds30-0049-receiver-factorial"
HELD_NAME = "late-pilot-rescue"
OWNER_NAME = "ds30-0049-saved-crossover"
HELD_AUTH = "ds30-0016-full-primary-transfer"
ARCHIVES = {
    FULL_NAME: "4af8b73101dce9b71a06b38a10e2484ef04b74f42b5221cfec1e818d21ea3b58",
    HELD_NAME: "2b725ccdb473948c2fdbd042a4029060912783f424b8d73c98db34e7537e5a50",
    OWNER_NAME: "76ffa1841268d1f9dd8348a3549c8927655653abdcc804697b6a36f00aebf8ce",
    HELD_AUTH: "ace7652af6fa0945f28dd161d1b16ecb293f0ca7c8bdf8340dfeff610c87fd9c",
}
POLICIES = ("periodic", "fixed_late", "lagged_empty")
MAX_GAP = 80_000_000
WINDOW = 8


def canonical(doc):
    return json.dumps(doc, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode()


def digest(body):
    return sha256(body).hexdigest()


def save(path, doc):
    body = canonical(doc)
    with path.open("xb") as stream:
        stream.write(body)
    path.chmod(0o400)
    return digest(body)


def archive(name):
    path = HERE/"measurements"/(name+".json.gz")
    body = path.read_bytes()
    if digest(body) != ARCHIVES[name]:
        raise ValueError("Archived aperture or owner product changed")
    return json.loads(gzip.decompress(body))


def load_inputs():
    full = archive(FULL_NAME)
    replay = full["selection.json"]["document"]
    baseline = replay["cells"][SHORT+"/strongest"]["probes"]
    named = replay["cells"][FULL+"/continuation"]["probes"]
    parity = full["final-diagonal.json"]["document"]
    if parity["antenna_slots"] != 724 or sum(parity["changes"].values()):
        raise ValueError("The dual-aperture prefix did not match the original diagonals")
    cross = archive(OWNER_NAME)
    owners = cross["ordered_owner_rows"]["installed-installed"]
    successor = cross["ordered_owner_rows"]["successor-successor"]
    if not all(all(x.values()) for x in cross["raw_diagonal_equivalence"].values()):
        raise ValueError("Original published ownership or scientific parity changed")
    session = "fast-"+cross["raw_metadata"]["inventory_sha256"].removeprefix("sha256:")[:32]
    main = dict(tape=full["native-rows.json"]["document"], named=named, baseline=baseline,
                owned=owners, successor=successor, session=session, short_clock=None,
                parity=parity, original_held=replay["original_held_selector_at_prefix"])

    late = archive(HELD_NAME)["DS30-0016"]
    held = archive(HELD_AUTH)
    stock, mixed = (held["detector_packets"][name]["document"] for name in ("installed", "charted"))
    scout = late["nominations.json"]["document"]["short"]
    if sorted(key(row) for row in scout) != sorted(key(row) for row in stock["source"]["probes"]):
        raise ValueError("Independent short-clock opportunities changed")
    transfer = dict(tape=late["long-receiver.json"]["document"], named=stock["source"]["probes"],
                    baseline=mixed["source"]["probes"], session=stock["source"]["session_id"],
                    owned=held["installed_owners"], successor=held["charted_owners"],
                    short_clock={key(row): row["short_cpu_wall_ns"] for row in scout})
    return main, transfer


def pair_tape(scope):
    plan, _ = schedule(scope["named"])
    measured = measured_rows(scope["tape"], plan, scope["baseline"])
    captured = {key(row["opportunity"]): row for row in scope["tape"]}
    if len(captured) != len(plan):
        raise ValueError("Incomplete or nonunique aperture ledger")
    visits = []
    for i in range(0, len(plan), 2):
        entries = plan[i:i+2]
        probes = [row["opportunity"] for row in entries]
        calls = [captured[key(probe)] for probe in probes]
        actual = measured[i:i+2]
        values, cpu = {}, {}
        for mode in (FULL, SHORT):
            have = [mode in lane for lane in actual]
            if any(have) and not all(have):
                raise ValueError("Asymmetric missing evidence prevents stereo evaluation")
            if not all(have):
                continue
            values[mode] = [lane[mode] for lane in actual]
            if scope["short_clock"] is None:
                cpu[mode] = sum(row["clocks"][mode][0] for row in calls)
            elif mode == FULL:
                cpu[mode] = sum(row["full_cpu_wall_ns"][FULL][0] for row in calls)
            else:
                cpu[mode] = sum(scope["short_clock"][key(probe)][0] for probe in probes)
        visits.append(dict(
            stream=entries[0]["stream"], slot=entries[0]["slot"], cpu=cpu,
            probes=probes, choices=values, counter=probes[0]["valid_start_counter"],
        ))
    return visits


def freeze_schedule(visits, policy):
    """Make each aperture decision from metadata and already paid occupancy."""
    if policy not in POLICIES:
        raise ValueError("Unknown placement")
    count = Counter()
    spent = {}
    previous = {}
    empties = defaultdict(lambda: deque(maxlen=2))
    predictions = []
    for index, row in enumerate(visits):
        stream, slot, now = row["stream"], row["slot"], row["counter"]
        if set(row["choices"]) != {FULL, SHORT}:
            empties[stream].clear()
            previous[stream] = slot
            continue
        if previous.get(stream) != slot-1:
            empties[stream].clear()
        previous[stream] = slot
        phase = count[stream] % WINDOW
        block = count[stream]//WINDOW
        history = empties[stream]
        if history and now-history[0] > MAX_GAP:
            history.clear()
        trigger = len(history) == 2
        full = (phase == 0 if policy == "periodic" else
                phase == 7 or (policy == "lagged_empty" and trigger)) and spent.get(stream) != block
        aperture = FULL if full else SHORT
        why = ("periodic" if policy == "periodic" else "force_last" if phase == 7 else
               "past_two_empty") if full else "short"
        # Current factor read occurs only after the mode is chosen.
        factors = row["choices"][aperture]
        predictions.append(dict(index=index, phase=phase, count=count[stream], aperture=aperture,
                                trigger=why, prior_empty_counters=list(history), factors=factors))
        if full:
            spent[stream] = block
        if full or any(factor is not None for factor in factors):
            history.clear()
        else:
            history.append(now)
        count[stream] += 1
    return predictions


def references(scope):
    session = scope["session"]
    named = {}
    baseline = {}
    for a, b in zip(scope["named"], scope["baseline"], strict=True):
        if dict(a, candidates=[]) != dict(b, candidates=[]):
            raise ValueError("Original comparison changed the nominal opportunity")
        if len(a["candidates"]) > 1 or len(b["candidates"]) > 1:
            raise ValueError("Expected one originally selected winner per row")
        oid = observation(a, session)
        named[oid] = next(iter(a["candidates"]), None)
        baseline[oid] = next(iter(b["candidates"]), None)
    groups = {}
    for arm in ARMS:
        owned = {row[0] for row in scope["owned"][arm]}
        successor = {row[0] for row in scope["successor"][arm]}
        dropped = owned-successor
        groups["owned_"+arm] = owned
        groups["dropped_empty_"+arm] = {i for i in dropped if i in baseline and baseline[i] is None}
        groups["dropped_displaced_"+arm] = {
            i for i in dropped if i in named and baseline[i] is not None and
            not near(named[i], baseline[i])
        }
    return named, groups


def scope_scores(visits, schedules, scope):
    ref, groups = references(scope)
    ids = [[observation(p, scope["session"]) for p in row["probes"]] for row in visits]
    strata = dict(all=set(ref), **groups)
    registered = defaultdict(list)
    for choice in schedules["periodic"]:
        row = visits[choice["index"]]
        registered[row["stream"], choice["count"]//WINDOW].append(choice["index"])
    periodic = {row["index"]: row["factors"] for row in schedules["periodic"]}
    complete = [group for group in registered.values() if len(group)==WINDOW]
    eligible = {i for group in complete for i in group}

    def match(row, mode, members):
        return sum(oid in members and ref[oid] is not None and near(ref[oid], factor)
                   for oid, factor in zip(ids[row], visits[row]["choices"][mode], strict=True))

    oracle = {}
    for group, members in strata.items():
        short = sum(match(i, SHORT, members) for i in eligible)
        gains = sum(max(match(i,FULL,members)-match(i,SHORT,members) for i in block)
                    for block in complete)
        oracle[group] = dict(all_short_matches=short, best_same_budget_matches=short+gains,
                             gain_above_all_short=gains)
    summaries = {}
    for policy, predictions in schedules.items():
        results = {}
        partial = set(range(len(visits))) - eligible
        for name, include in (("complete", eligible), ("partial", partial)):
            windows = [choice for choice in predictions if choice["index"] in include]
            groups_stats, clocks, actions = {}, Counter(), Counter()
            for choice in windows:
                row = visits[choice["index"]]
                mode = choice["aperture"]
                actions.update((choice["trigger"],))
                clocks["native_cpu_ns"] += row["cpu"][mode]
                if mode == FULL:
                    clocks["short_first_extra_cpu_ns"] += row["cpu"][SHORT]
                    actions["full_visits"] += 1
            for tag, members in strata.items():
                scores = Counter()
                for choice in windows:
                    i = choice["index"]
                    for oid, factor, first in zip(
                        ids[i], choice["factors"], periodic[i], strict=True,
                    ):
                        if oid not in members:
                            continue
                        stock = ref[oid]
                        matched = stock is not None and near(stock, factor)
                        matched_periodic = stock is not None and near(stock, first)
                        scores.update(lanes=1, positives=factor is not None,
                                      references=stock is not None,
                                      matched=matched, exact=stock is not None and stock==factor,
                                      gained_over_periodic=matched and not matched_periodic,
                                      lost_from_periodic=matched_periodic and not matched)
                groups_stats[tag] = dict(scores)
            results[name] = dict(visit_count=len(windows), actions=dict(actions),
                                 clocks=dict(clocks), stats=groups_stats)
        if (results["complete"]["actions"].get("full_visits",0) != len(complete)
                or any(sum(x["aperture"]==FULL for x in predictions if x["index"] in block)!=1
                       for block in map(set, complete))):
            raise ValueError("Complete-cycle stereo budgets diverged")
        summaries[policy] = results
    return dict(complete_cycles=len(complete), paired_visits=len(schedules["periodic"]),
                total_visits=len(visits), oracle=oracle, policies=summaries)


def causal_readout(visits, predictions, continuation, scope):
    if len(visits) != len(predictions):
        raise ValueError("Unknown selected predecessors prevent chronological replay")
    selected, erased = continuation(), continuation()
    streams = defaultdict(list)
    full_modes, live = {}, []
    for choice in predictions:
        row = visits[choice["index"]]
        full = choice["aperture"] == FULL
        for probe, factor in zip(row["probes"], choice["factors"], strict=True):
            buf = [] if factor is None else [factor]
            key_ = (*row["stream"], probe["receiver_id"])
            live_probe = dict(probe, candidates=buf)
            erased_probe = dict(probe, candidates=[] if full else buf)
            _, keep, _ = selected.select(live_probe)
            _, survives, _ = erased.select(erased_probe)
            streams[key_].append((full, factor is not None, survives is not None))
            live.append(buf[keep] if keep is not None else None)
            full_modes[key(probe)] = full
    gain, witnesses = Counter(), defaultdict(Counter)
    for lane, rows in streams.items():
        radio = lane[-1]
        for i, (full, outcome, _) in enumerate(rows):
            if not full:
                continue
            donors = rows[i+1:i+8]
            if len(donors) != 7:
                witnesses[radio]["end"] += 1
            elif any(window[0] for window in donors):
                witnesses[radio]["intervening_anchor"] += 1
            else:
                witnesses[radio]["complete"] += 1
                raw, chosen = ((sum(row[j] for row in donors)+.5)/8 for j in (1,2))
                gain[radio] += log(chosen if outcome else 1-chosen)-log(raw if outcome else 1-raw)
    ref, groups = references(scope)
    obs = [observation(probe,scope["session"]) for visit in visits for probe in visit["probes"]]
    refs = dict(all=set(ref), **groups)
    return dict(
        live_chronological_sha256=digest(canonical(live)),
        selected_positives=sum(row is not None for row in live),
        signed_match={g:sum(i in names and ref[i] is not None and near(ref[i],row)
                            for i,row in zip(obs,live,strict=True)) for g,names in refs.items()},
        held_witnesses={radio:dict(witnesses[radio]) for radio in (0,1)},
        held_log_gain={radio:gain[radio] for radio in (0,1)},
        standard_eof_role_layout=all(
            full_modes[key(probe)] == (visit["slot"] % WINDOW == 0)
            for visit in visits for probe in visit["probes"]),
    )


def unknown_predecessors(visits):
    prior = defaultdict(lambda: deque(maxlen=12))
    exposed = 0
    for row in visits:
        unknown = SHORT not in row["choices"]
        for p in row["probes"]:
            lane = (p["receiver_id"],p["channel"],p["actual_rf_hz"])
            old = prior[lane]
            exposed += any(unmeasured and row["counter"]-t <= MAX_GAP for t,unmeasured in old)
            old.append((row["counter"],unknown))
    return dict(
        unmeasured_short_lanes=sum(2 for v in visits if SHORT not in v["choices"]),
        later_lanes_with_missing_short_alternative_in_original_history_window=exposed,
    )


def run(output, continuation):
    main, held = load_inputs()
    all_data = {}
    prediction = dict(
        protocol_sha256=digest((HERE/"anchor-placement-protocol.md").read_bytes()),
        source_sha256=digest(Path(__file__).read_bytes()), archive_sha256=ARCHIVES,
    )
    for name, scope in (("DS30-0049-prefix", main), ("DS30-0016-paired-stratum", held)):
        visits = pair_tape(scope)
        variants = {policy: freeze_schedule(visits, policy) for policy in POLICIES}
        all_data[name] = visits, variants, scope
        prediction[name] = variants
    output.mkdir(mode=0o700)
    seal = save(output/"predictions.json",prediction)
    reports = {name:scope_scores(*inputs) for name,inputs in all_data.items()}
    visits, variants, scope = all_data["DS30-0049-prefix"]
    replay = {
        name: causal_readout(visits, row, continuation, scope) for name, row in variants.items()
    }
    original = replay["periodic"]
    held_scores = scope["original_held"]["log_score_gain_by_radio"]
    if not original["standard_eof_role_layout"] or any(
        abs(original["held_log_gain"][radio]-held_scores[str(radio)])>1e-10 for radio in (0,1)
    ):
        raise ValueError("The fixed-role held replay differs from the original receipt")
    reports["DS30-0049-prefix"]["replay"] = replay
    reports["DS30-0016-paired-stratum"]["unresolved"] = unknown_predecessors(
        all_data["DS30-0016-paired-stratum"][0])
    print(save(output/"result.json", dict(
        prediction_sha256=seal, cases=reports, original_waveform_reads=0, detector_calls=0,
        solver_calls=0,
        continuation_component="released kernel and diagnostic adaptive held witnesses",
    )))


if __name__ == "__main__":
    from empty_bootstrap import PAYLOAD, RELEASE

    sys.path[:0] = [str(PAYLOAD),str(RELEASE/"src")]
    from tools.pipeline_eval.variants import carrier_continuation

    if digest(Path(carrier_continuation.__file__).read_bytes()) != HISTORY_PIN:
        raise ValueError("Original Continuation implementation differs")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    run(parser.parse_args().output,carrier_continuation.Continuation)
