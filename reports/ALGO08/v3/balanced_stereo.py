"""Localize a balanced half-duty stereo mask on two signed saved inputs."""

import argparse
from collections import Counter, defaultdict
from functools import partial
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from preloaded_saved_worker import read, write


CASES = ("north", "weak")
ARMS = ("c0", "fitted_c")
PROTOCOL = HERE / "balanced-stereo-protocol.md"
INDIVIDUAL_SHA = "a24df0281cb7c6f77d5f94ed510ccca6d3eddac3455d26c3269db41c98c113f6"
MAX_EXTRA_M = 250
RULE = dict(stream=["edge", "channel", "actual_rf_hz"], anchor_period=8,
            short="(one-based channel - 1 + zero-based cycle + slot) mod 2 equals zero",
            cycle="divmod(zero-based admitted stream index, 8)", hold="Jeffreys .5 using paid donors only")


def schedule(original):
    """Choose stereo visits using only the original admitted metadata."""
    from tools.pipeline_eval.variants.capture_bursts import inventories, visit_pairs

    inventories(original)
    streams = Counter()
    previous = {}
    decisions = []
    for visit, (row, _) in visit_pairs(original["source"]["probes"]):
        stream = (row["edge"], row["channel"], row["actual_rf_hz"])
        sample = row["valid_start_counter"]
        if stream in previous and sample <= previous[stream]:
            raise ValueError("Expected increasing hardware counters in each RF stream")
        cycle, slot = divmod(streams[stream], 8)
        anchor = slot == 0
        paid = anchor or (stream[1] - 1 + cycle + slot) % 2 == 0
        decisions.append(dict(visit=visit, stream=stream, sample=sample, cycle=cycle, slot=slot, paid=paid))
        streams[stream] += 1
        previous[stream] = sample
    return decisions


def donor_budget(decisions):
    by_cycle = defaultdict(list)
    for entry in decisions:
        by_cycle[(tuple(entry["stream"]), entry["cycle"])].append(entry)
    return {cycle[0]["visit"]: sum(row["paid"] for row in cycle[1:])
            for cycle in by_cycle.values() if len(cycle) == 8}


def paid_route(document, donors, *, audit=False):
    """Score the same held labels against the history of genuinely paid short rows."""
    from anchor_cycle_route import predict, route, score, summarize
    from anchor_holds import erased_rows, history_rows
    from leo.contracts.digests import canonical_digest

    training, held = erased_rows(document)
    masked = dict(document, source=dict(document["source"], probes=training))
    history = history_rows(training)
    predictions, skipped = predict(masked, history)
    if {row["visit"] for row in predictions} != set(donors):
        raise ValueError("Paid denominator does not cover the original complete held cycles")
    for row in predictions:
        count = donors[row["visit"]]
        if not 0 <= max(row["counts"].values()) <= count <= row["n"]:
            raise ValueError("An unmeasured short slot contributed a donor vote")
        row["scheduled_donors"] = row["n"]
        row["n"] = count
        row["probabilities"] = {name: (positive+.5)/(count+1) for name, positive in row["counts"].items()}
    rows = score(predictions, document["source"]["probes"])
    totals = summarize(rows)
    result = dict(route=route(totals), log_score_gain_by_radio={key: row["delta_log_score"] for key, row in totals.items()})
    if audit:
        result.update(cycles=rows, radio=totals, prediction_digest=canonical_digest(predictions),
                      held_before_partial_cycle_drop=len(held), incomplete_cycles=skipped)
    return result


def project(original, recipe, decisions):
    from continued_cfo_trial import rebinding
    from full_short_run import EIGHT_MS_RECIPE_SHA, checked_recipe
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.variants.capture_bursts import visit_pairs
    from whole_stereo_blocks import signature

    source, provenance = original["source"], original["provenance"]
    parent = provenance["detector_sha256"]
    if (recipe != checked_recipe(eight_ms=True) or parent != "sha256:"+EIGHT_MS_RECIPE_SHA
            or not source["qualified"] or source["sample_rate_hz"] != 10_000_000
            or provenance["scope"] != "cancellation" or provenance["skipped_fast_score"]
            or signature(source, parent, source["probes"]) != source["analysis_manifest_sha256"]):
        raise ValueError("The branch requires complete original unfiltered signed 20/8 ms")
    ledger = {row["visit"]: dict(visit=row["visit"], states=["excluded_original"]*2)
              for row in provenance["excluded_windows"]}
    rows, paid, deferred, omitted = [], Counter(), Counter(), []
    for entry, (visit, pair) in zip(decisions, visit_pairs(source["probes"]), strict=True):
        anchor = entry["slot"] == 0
        mode = "full" if anchor else "short_primary"
        if entry["visit"] != visit or (anchor and not entry["paid"]):
            raise ValueError("An original stereo measurement or anchor moved")
        if entry["paid"]:
            for row in pair:
                factors = row["candidates"]
                if len(factors) > 1 or any(not f["passed_fractional_margin_gate"] or (not anchor and f["candidate_rank"] != 0)
                                           for f in factors):
                    raise ValueError("Invalid measured original signed factor")
            states = ["measured_positive" if row["candidates"] else "measured_empty" for row in pair]
            rows.extend(pair)
            paid[mode] += 2
        else:
            states = ["unmeasured"]*2
            rows.extend(dict(row, candidates=[]) for row in pair)
            omitted.append(visit)
            deferred[mode] += 2
        ledger[visit] = dict(entry, mode=mode, states=states)
    ordered = [ledger[index] for index in range(provenance["window_count"])]
    policy = dict(recipe, balanced_stereo=dict(parent_detector_sha256=parent, rule=RULE,
                  source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  schedule_sha256=canonical_digest(decisions), event_ledger_sha256=canonical_digest(ordered)))
    return rebinding(original, rows, policy), policy, ordered, dict(paid_native_lanes=dict(paid),
           skipped_native_lanes=dict(deferred), skipped_stereo_visits=omitted, schedule_sha256=policy["balanced_stereo"]["schedule_sha256"])


def support(decisions):
    streams = defaultdict(list)
    for row in decisions:
        streams[tuple(row["stream"])].append(row)
    result = []
    for stream, rows in streams.items():
        measured = [row for row in rows if row["paid"]]
        span = lambda a: (a[-1]["sample"] - a[0]["sample"])/1e7
        gap = lambda a: max(((b["sample"]-a["sample"])/1e7 for a, b in zip(a, a[1:])), default=0.)
        result.append(dict(stream=stream, anchors=sum(row["slot"] == 0 for row in rows),
                           short_calls=2*sum(row["slot"] != 0 for row in rows),
                           omitted_short_calls=2*(len(rows)-len(measured)), original_span_s=span(rows), paid_span_s=span(measured),
                           original_max_gap_s=gap(rows), paid_max_gap_s=gap(measured)))
    return result


def plan(case, directory):
    import anchor_cycle_route
    from anchor_exposure import PINS, bind, packet
    from eight_ms_held_fit import RECEIVER_RECIPE_PINS, select
    from empty_bootstrap import checked
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import immutable_json
    from north_held_anchor_pair import tmpfs
    from whole_stereo_8ms import EIGHT_RAW, SAVED_PIN, SAVED_SEAL, coverage, price
    from whole_stereo_blocks import load_checked

    source, pin = PINS["DS30-0016" if case == "weak" else case]["8ms"]
    tmpfs(source)
    original = packet(source, pin)
    meta = load_checked(Path(source)/"full-short-recipe.json", RECEIVER_RECIPE_PINS[case])
    saved = load_checked(SAVED_SEAL, SAVED_PIN)["runs"][case]["history8"]
    if meta["saved_digest"] is not None:
        raise ValueError("Require an authentic unfiltered prehistory acquisition")
    recipe = meta["recipe"]
    full, full_witness = select(original, recipe)
    if canonical_digest(full) != saved["identity"]["native_sha256"]:
        raise ValueError("All-visit held history failed original selected byte parity")
    directory.mkdir()
    started = process_time(), perf_counter()
    decisions = schedule(original)
    paid, masked_recipe, ledger, counts = project(original, recipe, decisions)
    choose = partial(paid_route, donors=donor_budget(decisions))
    with patch.object(anchor_cycle_route, "select_route", choose):
        selected, witness = select(paid, masked_recipe)
    path = directory/"detections.json"
    immutable_json(path, selected)
    checked(path, witness["native_sha256"][7:])
    planning = dict(cpu_s=process_time()-started[0], elapsed_s=perf_counter()-started[1])
    bind(original, selected)
    stats = coverage(original, paid, full, selected, counts["skipped_stereo_visits"])
    full_held = anchor_cycle_route.select_route(original, audit=True)
    masked_held = choose(paid, audit=True)
    held_label = lambda row: (row["visit"], row["radio"], row["stream"], row["outcome"])
    if list(map(held_label, full_held["cycles"])) != list(map(held_label, masked_held["cycles"])):
        raise ValueError("The genuine full held anchors and labels changed")
    audit = meta["receiver_audit"]
    if case == "north":
        raw = load_checked(HERE/"measurements/eight-ms-native-live.json.gz", EIGHT_RAW)["scientific_seal"]["raw"]
        if raw["native_sha256"] != canonical_digest(full) or raw["held_anchor_route"]["parent_native_sha256"] != "sha256:"+pin:
            raise ValueError("North short CPU price is not for the same original full receiver")
        audit = raw["receiver_audit"]
    cost = price(audit, counts, planning["cpu_s"])
    report = dict(case=case, identity=saved["identity"], original_sha256=pin, schedule=counts,
                  full_witness=full_witness, masked_witness=witness, actual_selected_coverage=stats,
                  held=dict(original=full_held["radio"], paid=masked_held["radio"], cycles=masked_held["cycles"],
                            prediction_sha256=masked_held["prediction_digest"]),
                  rf_coverage=support(decisions), events=ledger, cost=cost, planning=planning,
                  admit=True)
    write(directory/"plan.json", report)


def qualify(root, case):
    from eight_ms_held_score import geographic_reference, owner_differences
    from eight_ms_native_score import outcome
    from whole_stereo_8ms import SAVED_PIN, SAVED_SEAL
    from whole_stereo_blocks import load_checked

    verified = read(root/f"{case}-seal.json")
    historic = load_checked(HERE/"measurements/whole-stereo-8ms.json.gz", INDIVIDUAL_SHA)
    all8 = load_checked(SAVED_SEAL, SAVED_PIN)["runs"][case]["history8"]["science"]
    original = historic["scores"][case]
    offered = verified["publication"]["receipt"]["region"]
    truth, pin = geographic_reference(case)
    candidate = outcome(verified["verified"]["arms"], offered, truth)
    reference = original["controls"]
    decisions = {name: {arm: bool(candidate[arm] and candidate[arm]["error_m"] <= reference[name][arm]["error_m"]+MAX_EXTRA_M)
                        for arm in ARMS} for name in ("named", "all8")}
    new = verified["science"]
    owners = {arm: owner_differences(all8["roles"][arm], new["roles"][arm]) for arm in ARMS} if new else None
    decision = verified["publication"]["receipt"]["decision"]
    if new is not None and not new["images"]:
        raise ValueError("A complete candidate must bind eight media products")
    if decision == "withheld":
        evidence = verified["verified"]
        if (evidence["artifacts"] or evidence["scientific_digests"] or set(evidence["arms"]) != set(ARMS)
                or any(row.get("latlon") is not None for row in evidence["arms"].values())):
            raise ValueError("Withholding must bind both empty arms and zero media products")
    return dict(case=case, decision=decision, candidate=candidate,
                controls={name: reference[name] for name in ("named", "all8")}, earlier_mask=original["candidate"],
                accuracy_checks=decisions, qualified=decision == "complete" and all(all(row.values()) for row in decisions.values()),
                owners=owners, geographic_scoring_sha256=pin, verified=verified)


def run(root):
    from dense_geographic_trial import host
    from north_held_anchor_pair import tmpfs
    from preloaded_saved_worker import enrolled
    from whole_stereo_8ms_trial import launch, pins, seal

    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Freeze the planned code and protocol before using detector rows")
    tmpfs(root.parent)
    root.mkdir()
    binding = dict(host=host(), sources=pins(), commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
                   schedule_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                   protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(), order=CASES)
    write(root/"binding.json", binding)
    for case in CASES:
        request, archive, offer, libraries, *_ = enrolled(case)
        for path in (request["saved_inventory"], archive, offer, *libraries.values()):
            tmpfs(path)
        plan(case, root/case)
    scores = {}
    for case in CASES:
        try:
            launch(root, case, next_case=lambda _: "weak")
            seal(root, case)
            result = qualify(root, case)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            clock = root/f"{case}-clock.json"
            result = dict(case=case, qualified=False, worker_failure=str(error), clock=read(clock) if clock.exists() else None)
        write(root/f"{case}-score.json", result)
        scores[case] = dict(result, plan=read(root/case/"plan.json"))
    write(root/"result.json", dict(binding=binding, scores=scores, qualified=all(row["qualified"] for row in scores.values())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
