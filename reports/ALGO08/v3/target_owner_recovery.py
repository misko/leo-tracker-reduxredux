"""Price the hindsight union of full owners omitted by the frozen lane mask."""

from collections import Counter, defaultdict
from hashlib import sha256
from time import process_time

from stereo_lane_schedule import StereoSchedule, recipe


ARMS = ("c0", "fitted_c")


def analysis_digest(source, detector, probes):
    from leo.contracts.digests import canonical_digest

    return canonical_digest(["cancellation", source["raw_recording_authority_digest"], detector[7:], probes])


def observation_id(session, row):
    key = f"{session}:{row['receiver_id']}:{row['valid_start_counter']}"
    return "sha256:" + sha256(key.encode()).hexdigest()


def owners_by_arm(owners, available):
    if set(owners) != set(ARMS):
        raise ValueError("Expected both complete and independently verified calibration owner maps")
    result = {}
    for arm in ARMS:
        members = owners[arm]
        labels = {row[0]: (row[1], row[2]) for row in members}
        if len(members) != len(labels) or not labels.keys() <= available:
            raise ValueError("An owner must bind to one genuine passed observation in the full packet")
        result[arm] = labels
    return result


def reopen(full, target, owner_rows, mask, owner_receipt):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.variants.capture_bursts import inventories, visit_pairs

    started = process_time()
    inventories(full)
    inventories(target)
    original, filtered = full["source"], target["source"]
    full_prov, target_prov = full["provenance"], target["provenance"]
    first, second = full_prov["detector_sha256"], target_prov["detector_sha256"]
    if (mask["recipe"] != recipe("target", first) or canonical_digest(mask["recipe"]) != second
            or second != mask["detector_sha256"] or canonical_digest(target) != mask["native_sha256"]):
        raise ValueError("The saved mask differs from the native target schedule and recipe")
    metadata = {"source", "provenance"}
    fields = {"probes", "analysis_manifest_sha256"}
    excluded = {"run_id", "detector_sha256"}
    if ({k:v for k,v in full.items() if k not in metadata} != {k:v for k,v in target.items() if k not in metadata}
            or {k:v for k,v in original.items() if k not in fields} != {k:v for k,v in filtered.items() if k not in fields}
            or {k:v for k,v in full_prov.items() if k not in excluded} != {k:v for k,v in target_prov.items() if k not in excluded}):
        raise ValueError("The target may only remove whole lanes from the original packet")
    probes = original["probes"]
    if (original["analysis_manifest_sha256"] != analysis_digest(original, first, probes)
            or filtered["analysis_manifest_sha256"] != analysis_digest(filtered, second, filtered["probes"])
            or original["sample_rate_hz"] != 10_000_000 or not original["qualified"]):
        raise ValueError("The original signed receiver or target packet is unqualified")

    schedule = StereoSchedule("target")
    scheduled, source_rows = [], {}
    for visit, pair in visit_pairs(probes):
        stream = tuple(pair[0][key] for key in ("edge", "channel", "actual_rf_hz"))
        mode, omit = schedule.next(stream)
        if omit is not None:
            if mode != "short_primary":
                raise ValueError("A full anchor cannot be omitted")
            scheduled.append([visit, omit])
        for row in pair:
            if row["candidates"]:
                key = observation_id(original["session_id"], row)
                if key in source_rows or len(row["candidates"]) != 1 or not row["candidates"][0]["passed_fractional_margin_gate"]:
                    raise ValueError("Expected one unique genuine signed factor on each occupied original lane")
                source_rows[key] = row
    if scheduled != mask["skipped_slots"] or canonical_digest(scheduled) != mask["mask_sha256"]:
        raise ValueError("The original admitted order does not reproduce the complete sealed target mask")
    omitted = {tuple(slot) for slot in scheduled}
    by_arm = owners_by_arm(owner_rows, source_rows.keys())
    union = set().union(*(rows.keys() for rows in by_arm.values()))
    recovery, lost_positive = [], []
    output_rows = []
    for full_row, target_row in zip(probes, filtered["probes"], strict=True):
        slot = (full_row["visit_index"], full_row["receiver_id"])
        if slot not in omitted:
            if target_row != full_row:
                raise ValueError("Target changed an ordinary paid lane")
            output_rows.append(target_row)
            continue
        if target_row != dict(full_row, candidates=[]):
            raise ValueError("An omitted lane may only replace its candidate array with an empty list")
        key = observation_id(original["session_id"], full_row)
        if full_row["candidates"]:
            lost_positive.append(key)
        if key in union:
            recovery.append(dict(visit=slot[0], radio=slot[1], observation_id=key))
            output_rows.append(full_row)
        else:
            output_rows.append(target_row)
    if lost_positive != mask["lost_positive_ids"]:
        raise ValueError("The no-call positive set differs from the authentic complete measurements")
    recovered_ids = {row["observation_id"] for row in recovery}
    if len(recovered_ids) != len(recovery) or recovered_ids != union.intersection(lost_positive):
        raise ValueError("Reopened paid lanes must equal the exact omitted full-owner union")

    identity = dict(method="saved-target-full-owner-recovery-oracle", original_detector=first, target_detector=second,
                    original_native=canonical_digest(full), original_mask=mask["mask_sha256"],
                    full_owner_receipt=owner_receipt, reopened_slots=canonical_digest(recovery))
    detector = canonical_digest(identity)
    digest = analysis_digest(original, detector, output_rows)
    restored = dict(target, source=dict(filtered, probes=output_rows, analysis_manifest_sha256=digest),
                    provenance=dict(target_prov, detector_sha256=detector, run_id="blind-compact-"+digest[7:39]))
    shared = by_arm[ARMS[0]].keys() & by_arm[ARMS[1]].keys()
    about = dict(recipe=identity, native_sha256=canonical_digest(restored), detector=detector,
                 issued=full_prov["window_count"], admitted=full_prov["processed_windows"],
                 omitted_lanes=len(scheduled), omitted_positive_lanes=len(lost_positive),
                 full_owned={a:len(rows) for a,rows in by_arm.items()}, owner_union=len(union),
                 identical_arm_owner_ids=len(shared)==len(union),
                 arm_label_disagreements=sum(by_arm[ARMS[0]][k] != by_arm[ARMS[1]][k] for k in shared),
                 directly_omitted_by_arm={a:len(rows.keys() & recovered_ids) for a,rows in by_arm.items()},
                 reopened=recovery, factors_after_recovery=sum(len(row["candidates"]) for row in output_rows),
                 audit_cpu_s=process_time()-started)
    return restored, about, by_arm


def concentration(audit, owners, graph):
    keys = {r["observation_id"] for r in audit["reopened"]}
    sats = defaultdict(set)
    for arm in ARMS:
        for key in keys & owners[arm].keys():
            sats[owners[arm][key][0]].add(key)
    track_counts, assigned = {}, set()
    for row in graph["tracks"]:
        hit = keys.intersection(row["observation_ids"])
        if assigned & hit or row["key"] in track_counts:
            raise ValueError("Graph membership of an original observation must be unique")
        if hit:
            track_counts[row["key"]] = len(hit)
            assigned.update(hit)
    counts = Counter(min(9, 10*r["visit"]//audit["issued"]) for r in audit["reopened"])
    visits = [row["visit"] for row in audit["reopened"]]
    return dict(issued_visit_deciles=[counts[i] for i in range(10)],
                visit_span=[min(visits),max(visits)] if visits else None,
                by_radio=dict(Counter(row["radio"] for row in audit["reopened"])),
                norad=sorted(((sat,len(rows)) for sat,rows in sats.items()), key=lambda row: (-row[1], row[0])),
                graph_tracks=sorted(track_counts.items(), key=lambda row: (-row[1], row[0])),
                graph_points=graph["graph_points"], graph_total_tracks=len(graph["tracks"]),
                outside_graph=len(keys-assigned))


def price(raw, audit, archived_budget):
    clocks = raw["native"]
    calls = clocks["native_calls"]["short_primary"]
    mean = clocks["native_cpu_ns"]["short_primary"] / calls / 1e9
    reopened = len(audit["reopened"])
    remaining = audit["omitted_lanes"] - reopened
    if not 0 <= remaining <= calls or mean != archived_budget["per_short_cpu_s"]:
        raise ValueError("Short search mean differs from the measured full-recording receiver budget")
    saving = mean * remaining
    return dict(method="measured full-recording mean per short-primary call; no per-lane CPU recorded",
                total_short_calls=calls, omitted_calls_target=audit["omitted_lanes"], reopened_paid_calls=reopened,
                remaining_omitted_calls=remaining, mean_short_cpu_s=mean, reopened_cpu_s=mean*reopened,
                original_gross_saving_cpu_s=mean*audit["omitted_lanes"], remaining_receiving_saving_cpu_s=saving,
                fixed_nonnative_acquisition_cpu_s=archived_budget["fixed_nonnative_acquisition_cpu_s"],
                modeled_total_acquisition_cpu_s=archived_budget["fixed_nonnative_acquisition_cpu_s"]+
                                                archived_budget["measured_full_native_cpu_s"]-saving,
                earlier_receiver_gap_residual_cpu_s={str(gap):saving-gap for gap in (2.735,4.616)})
