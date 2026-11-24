"""Replay the unchanged whole-stereo schedule before any signed 8 ms selection."""

from collections import Counter
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
SCHEDULE_SHA = "eb8619f3c768510345663b8144a987a1c07ff890bc8351cbf9e18b992420e33a"
SELECTOR_SHA = "7c6a0ee22f66144ec8f65fde0fc2e019ad5eb91149a5b0fb611a7e3e68768a49"
EIGHT_RAW = "2604afe118cebc24fa4fb0a975a439e5a6e9c2858ca4ae793dbc5b7f7afe7b9d"
SAVED_SEAL = Path("/dev/shm/leo-v3-eight-ms-held-fit-result01/containing-seal.json")
SAVED_PIN = "954fea001cd8591559f471a5d5b28e1725f2935b80ebe8700da8f0b78b5cf0df"
CASES = ("north", "weak")


def input_stream(rec, recipe):
    from continued_cfo_trial import rebinding
    from full_short_run import EIGHT_MS_RECIPE_SHA, checked_recipe
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.variants.capture_bursts import visit_pairs
    from whole_stereo_blocks import BLACKOUT_RULE, schedule, signature

    source, parent = rec["source"], rec["provenance"]["detector_sha256"]
    if (recipe != checked_recipe(eight_ms=True) or parent != "sha256:"+EIGHT_MS_RECIPE_SHA
            or rec["provenance"]["scope"] != "cancellation" or not source["qualified"]
            or signature(source, parent, source["probes"]) != source["analysis_manifest_sha256"]):
        raise ValueError("The pre-history input must be the complete original signed 20/8 ms receiver")
    decisions = schedule(rec)
    rows, kept, skipped, skipped_visits = [], Counter(), Counter(), []
    for (visit, mode, keep), (observed, pair) in zip(decisions, visit_pairs(source["probes"]), strict=True):
        if visit != observed or not keep and mode != "short_primary":
            raise ValueError("Whole-stereo scheduling dropped or moved a full anchor")
        if keep:
            for row in pair:
                factors = row["candidates"]
                if (len(factors) > 1 or any(f["passed_fractional_margin_gate"] is not True for f in factors)
                        or (mode == "short_primary" and factors and factors[0]["candidate_rank"] != 0)):
                    raise ValueError("The scheduled lane failed the original mixed-aperture proposal ABI")
            rows.extend(pair)
            kept[mode] += 2
        else:
            # Keep the real opportunity and its clock with neither measured proposal.
            rows.extend(dict(row, candidates=[]) for row in pair)
            skipped[mode] += 2
            skipped_visits.append(visit)
    parent_recipe = dict(recipe, whole_stereo=dict(parent_detector_sha256=parent,
                         schedule_source_sha256=SCHEDULE_SHA, projection_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                         rule=BLACKOUT_RULE, provenance="saved original per-lane 20/8 ms proposals admitted by schedule"))
    packet = rebinding(rec, rows, parent_recipe)
    return packet, parent_recipe, dict(schedule_sha256=canonical_digest(decisions),
                                       paid_native_lanes=dict(kept), skipped_native_lanes=dict(skipped),
                                       skipped_stereo_visits=skipped_visits)


def coverage(before, paid, full, selected, skipped_visits):
    from anchor_exposure import bind, enroll

    for packet in (paid, full, selected):
        bind(before, packet)
    omitted = set(skipped_visits)
    rows = [packet["source"]["probes"] for packet in (before, paid, full, selected)]
    radio = {0: {}, 1: {}}
    for event, original, masked, all_visits, used in zip(enroll(before), *rows, strict=True):
        visit, _, antenna, _, aperture, _ = event
        a, b, f, c = (row["candidates"] for row in (original, masked, all_visits, used))
        skip = visit in omitted
        if (skip and (b or c or aperture == "anchor") or not skip and a != b
                or c and c != b or f and f != a):
            raise ValueError("Skipped measurements, altered signed factors or moved full anchors reached the selector")
        count = radio[antenna].setdefault(aperture, Counter())
        count.update(original_measured=int(bool(a)), paid_measured=int(bool(b)),
                     original_real_empty=int(not a), paid_real_empty=int(not skip and not a),
                     skipped_unmeasured=int(skip), selected_full=int(bool(f)), selected_masked=int(bool(c)),
                     direct_loss=int(skip and bool(f)), paid_loss=int(not skip and bool(f) and not c),
                     paid_gain=int(not skip and not f and bool(c)))
    return radio


def price(acquisition, schedule, planner_s):
    native = acquisition["native"]
    lanes, paid, removed = native["native_calls"], schedule["paid_native_lanes"], schedule["skipped_native_lanes"]
    if (native.get("cfo_refinement") is not None or set(lanes) != {"full", "short_primary"}
            or any(paid.get(k,0)+removed.get(k,0) != n for k,n in lanes.items()) or removed.get("full",0)):
        raise ValueError("Budget requires the actual no-tail, full-anchor and 8 ms short aperture witness")
    short_pool = native["native_cpu_ns"]["short_primary"]/1e9
    fraction = removed["short_primary"]/lanes["short_primary"]
    gross = short_pool*fraction
    cost = acquisition["acquire"]["cpu_ns"]/1e9
    return dict(short_cpu_pool_s=short_pool, modeled_short_credit_cpu_s=gross,
                modeled_incremental_after_planning_cpu_s=gross-planner_s, planner_cpu_s=planner_s,
                native_full_cpu_s=native["native_cpu_ns"]["full"]/1e9, short_removed_fraction=fraction,
                original_acquisition_cpu_s=cost, modeled_acquisition_cpu_s=cost-gross, fixed_verified_ingress=True)


def anchor_support(original_audit, masked_audit):
    import operator

    projection = operator.itemgetter("index", "visit", "radio", "stream", "n", "outcome")
    if ([projection(row) for row in original_audit["cycles"]] != [projection(row) for row in masked_audit["cycles"]]
            or original_audit["incomplete_cycles"] != masked_audit["incomplete_cycles"]):
        raise ValueError("Held anchor labels and donor opportunities must be unchanged by the mask")
    return {mode: dict(route=audit["route"], scores=audit["radio"], incomplete_cycles=audit["incomplete_cycles"],
                       prediction_sha256=audit["prediction_digest"])
            for mode, audit in (("full", original_audit), ("masked", masked_audit))}


def plan(case, directory):
    from anchor_cycle_route import select_route
    from anchor_exposure import PINS, packet
    from eight_ms_held_fit import RECEIVER_RECIPE_PINS, select
    from empty_bootstrap import checked
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import immutable_json
    from whole_stereo_blocks import exposure, load_checked
    from preloaded_saved_worker import write

    checked(HERE/"whole_stereo_blocks.py", SCHEDULE_SHA)
    checked(HERE/"eight_ms_held_fit.py", SELECTOR_SHA)
    source, native_pin = PINS["DS30-0016" if case == "weak" else case]["8ms"]
    source = Path(source)
    original = packet(source, native_pin)
    native_receipt = load_checked(source/"full-short-recipe.json", RECEIVER_RECIPE_PINS[case])
    if native_receipt["saved_digest"] is not None:
        raise ValueError("Need the original independently measured pre-history acquisition")
    recipe = native_receipt["recipe"]
    saved = load_checked(SAVED_SEAL, SAVED_PIN)["runs"][case]["history8"]
    full, full_witness = select(original, recipe)
    stripped = lambda decision: {k:v for k,v in decision.items() if k != "selector"}
    if (canonical_digest(full) != saved["identity"]["native_sha256"] or
            canonical_digest(stripped(full_witness)) != canonical_digest(stripped(saved["selector"]))):
        raise ValueError("Full original policy failed byte-identical history and held decisions")

    begin = process_time(), perf_counter()
    paid, masked_recipe, schedule = input_stream(original, recipe)
    selected, witness = select(paid, masked_recipe)
    elapsed = dict(cpu_s=process_time()-begin[0], elapsed_s=perf_counter()-begin[1])
    stats = coverage(original, paid, full, selected, schedule["skipped_stereo_visits"])
    anchors = anchor_support(select_route(original, audit=True), select_route(paid, audit=True))
    if case == "north":
        reference = load_checked(HERE/"measurements/eight-ms-native-live.json.gz", EIGHT_RAW)["scientific_seal"]["raw"]
        if (reference["native_sha256"] != saved["identity"]["native_sha256"]
                or reference["held_anchor_route"]["parent_native_sha256"] != "sha256:"+native_pin):
            raise ValueError("North budget must be the completed native no-tail candidate")
        acquisition = reference["receiver_audit"]
    else:
        acquisition = native_receipt["receiver_audit"]
    supported = all(counts["held"] and counts["positive"] for counts in anchors["masked"]["scores"].values()) and all(
        sum(group["selected_masked"] for group in strata.values()) for strata in stats.values())
    directory.mkdir()
    path = directory/"detections.json"
    start = process_time(), perf_counter()
    immutable_json(path, selected)
    checked(path, witness["native_sha256"][7:])
    elapsed.update(seal_cpu_s=process_time()-start[0], seal_elapsed_s=perf_counter()-start[1])
    cost = price(acquisition, schedule, elapsed["cpu_s"]+elapsed["seal_cpu_s"])
    result = dict(case=case, identity=saved["identity"], original_sha256=native_pin, schedule=schedule,
                  full_witness=full_witness, masked_witness=witness, figures_required_on_fix=8, cost=cost,
                  actual_selected_coverage=stats, all_outcomes_held=anchors,
                  continuation=exposure(original, paid, set(schedule["skipped_stereo_visits"])),
                  planning=elapsed, admit=supported and cost["modeled_incremental_after_planning_cpu_s"] > 0)
    write(directory/"plan.json", result)
