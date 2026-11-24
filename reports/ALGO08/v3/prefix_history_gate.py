"""Price a single paid held-anchor prefix before the frozen short-stereo mask."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from math import log
from pathlib import Path
from time import perf_counter_ns, process_time_ns

from anchor_cycle_route import select_route
from anchor_holds import history_rows
from leo.contracts.digests import canonical_digest
from whole_stereo_blocks import CONTINUATION_SHA, RECEIVER_SHA, StereoBlocks, load_checked, signature


HERE = Path(__file__).resolve().parent
BLOCK_WIDTH = 128
CHECKPOINT = 4*BLOCK_WIDTH
MIN_BLOCK_SUPPORT = 8
MIN_STREAM_SUPPORT = 2
GROSS_GATE = 3.490
RADIOS = (0, 1)
CASES = {
    "DS30-0008": ("/dev/shm/leo-held-anchor-selected-dense-01/original-detections.json",
                  "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"),
    "north": ("/dev/shm/leo-eight-ms-north/12ms",
              "2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427"),
    "DS30-0016": ("/dev/shm/leo-eight-ms-DS30-0016-warm/12ms",
                  "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"),
    "DS30-0057": ("/tmp/leo-protected-DS30-0057-01/forward",
                  "a9a0df0458963066bfcd11de0b22b23605ad44acdc3d3e628ccd8f40312064cd"),
    "south": ("/dev/shm/leo-past-anchor-held-south",
              "a10693d167757124a036cfcd63e90966760e52b755f4bb834605ccaf74426d2e"),
}
SOURCE_SHA = {
    "anchor_cycle_route.py": "fd6cd122b01fd6865cde965c6f6f8d72d97bb804642e835398de168ce333ab13",
    "anchor_holds.py": "b0607a337c832b8a766b8e07e1f23417456e4046491a5acd26c8f7930cfbb7f5",
    "anchor_exposure.py": "aec435ae4bcd86892566bfa6a21ec5fedb3c3b6174fe4f9b4640c986bd6cf8cd",
    "whole_stereo_blocks.py": "eb8619f3c768510345663b8144a987a1c07ff890bc8351cbf9e18b992420e33a",
}
COST_PINS = {
    "DS30-0008": ("measurements/dense-full-short-raw.json.gz",
                  "51521b26848532823922cc43a198b7f91d59d3f1d81e155e5862b04b53193f38"),
    "DS30-0057": ("measurements/short-raw-diagnostic.json",
                  "7b12b73f5e104a56d9da7c47641c6014e8003bed54efc4e4174b8c08abd35e67"),
    "north": ("/dev/shm/leo-eight-ms-north/12ms/full-short-recipe.json",
              "9d9273756700f7318722bfbf0d8ece36be9991fc0184cefca7c696a919aacc44"),
    "DS30-0016": ("/dev/shm/leo-eight-ms-DS30-0016-warm/12ms/full-short-recipe.json",
                  "70594e676776ac7f1a12464865f7118c05b0126b236a2bed73616c0b8407ac1a"),
    "south": ("/var/tmp/leo-full-short-south-transfer-final/containing/full-short-recipe.json",
              "602bada259cb691808740d1ce6f3a38818be2d508e01caa175a1279499ff6a07"),
}


def now():
    return process_time_ns(), perf_counter_ns()


def clock(start):
    return dict(cpu_ns=process_time_ns()-start[0], elapsed_ns=perf_counter_ns()-start[1])


def stream(probe):
    return (probe["edge"], probe["channel"], probe["actual_rf_hz"])


def paid_prefix(probes, issued):
    horizon = min(issued, CHECKPOINT)
    rows = []
    for probe in probes:
        if probe["visit_index"] >= horizon:
            break
        rows.append(probe)
    if len(rows) % 2 or len(rows)//2 > horizon:
        raise ValueError("Expected a complete paid stereo prefix")
    return dict(source=dict(probes=rows), provenance=dict(window_count=horizon,
        processed_windows=len(rows)//2, invalid_capture=horizon-len(rows)//2))


def decide(prefix):
    start = now()
    if prefix["provenance"]["window_count"] < CHECKPOINT:
        return dict(route="full-guarded", reason="checkpoint_not_reached", clocks=clock(start))
    held = select_route(prefix, audit=True)
    seen = Counter(stream(row) for row in prefix["source"]["probes"][::2])
    closed = Counter((tuple(row["stream"]), row["radio"]) for row in held["cycles"])
    blocks = defaultdict(list)
    for row in held["cycles"]:
        blocks[row["visit"]//BLOCK_WIDTH,row["radio"]].append(row)
    support, signs = True, True
    rows = []
    for block in range(CHECKPOINT//BLOCK_WIDTH):
        for radio in RADIOS:
            observed = blocks[block,radio]
            count = len(observed)
            hit = sum(row["outcome"] for row in observed)
            gain = sum(row["delta_log_score"] for row in observed)
            support &= count >= MIN_BLOCK_SUPPORT and 0 < hit < count
            signs &= gain < 0.
            rows.append(dict(block=block, radio=radio, complete_cycles=count, positives=hit, history_gain_nats=gain))
    stream_counts = [dict(stream=key, visits=n, complete_cycles=[closed[key,r] for r in RADIOS])
                     for key,n in sorted(seen.items())]
    enough_streams = bool(seen) and all(closed[key,r] >= MIN_STREAM_SUPPORT for key in seen for r in RADIOS)
    thin = support and enough_streams and signs and held["route"] == "unfiltered"
    return dict(route="thin-unfiltered" if thin else "full-guarded",
                reason=("paid_blocks_agree" if thin else "insufficient_support" if not support or not enough_streams
                        else "history_or_inconsistent_sign"),
                observed_streams=stream_counts, prefix_held_winner=held["route"],
                prefix_gain=held["log_score_gain_by_radio"], blocks=rows, incomplete=held["incomplete_cycles"],
                prediction_digest=held["prediction_digest"], prefix_held_rows=len(held["cycles"]),
                prefix_cycles_per_radio=held["radio"][0]["held"], clocks=clock(start))


def load_original(case):
    raw_path, pin = CASES[case]
    path = Path(raw_path)
    if path.is_dir():
        path, = path.glob("fast-scan-automatic-work/*/detections.json")
    original = load_checked(path, pin)
    source = original["source"]
    meta = original["provenance"]
    factor_rows = source["probes"]
    if (not source["qualified"] or meta["detector_sha256"] != "sha256:"+RECEIVER_SHA
            or source["sample_rate_hz"] != 10_000_000 or meta["skipped_fast_score"] != 0
            or meta["scope"] != "cancellation"
            or signature(source, meta["detector_sha256"], factor_rows) != source["analysis_manifest_sha256"]
            or any(len(row["candidates"]) > 1 or any(not item["passed_fractional_margin_gate"]
                   for item in row["candidates"]) for row in factor_rows)):
        raise ValueError("Expected original qualified unfiltered mixed aperture factors")
    local, cost_pin = COST_PINS[case]
    costs = load_checked(HERE/local, cost_pin)
    if case == "DS30-0008":
        costs = costs["candidate"]["recipe"]["receiver_audit"]
    elif case == "DS30-0057":
        medium, = [row for row in costs["cases"] if row["case"] == case]
        costs = medium["runs"]["candidate"]["receiver"]
    else:
        costs = costs["receiver_audit"]
    if (costs["analysis_manifest"] != source["analysis_manifest_sha256"]
            or costs["input_manifest"] != source["input_manifest_sha256"]
            or costs["recording_authority"] != source["raw_recording_authority_digest"]):
        raise ValueError("Original receiver audit did not time the current signed observations")
    return original, costs, dict(path=str(path), native_sha256=pin, priced_audit_path=str(HERE/local),
                                 priced_audit_sha256=cost_pin, analysis=source["analysis_manifest_sha256"],
                                 raw_authority=source["raw_recording_authority_digest"],
                                 original_inventory=source["input_manifest_sha256"])


def count_plan(original, outcome):
    """Look at the complete roster strictly after the prefix decision was sealed."""
    scheduled = StereoBlocks()
    prior = {tuple(row["stream"]) for row in outcome.get("observed_streams", [])}
    all_calls, prefix_calls = Counter(), Counter()
    skipped, factors = [], Counter()
    rows = original["source"]["probes"]
    previous = -1
    for a,b in zip(rows[::2],rows[1::2],strict=True):
        visit = a["visit_index"]
        key = stream(a)
        if visit <= previous or b["visit_index"] != visit or stream(b) != key or (
                a["receiver_id"], b["receiver_id"]) != (0,1):
            raise ValueError("Original stereo timeline changed")
        previous = visit
        mode, keep = scheduled.next(a)
        all_calls[mode] += 2
        if visit < CHECKPOINT:
            prefix_calls[mode] += 2
        elif not keep and key in prior:
            skipped.append(visit)
            for row in (a,b):
                if row["candidates"]:
                    factors[row["receiver_id"]] += 1
    return dict(original_calls=dict(all_calls), paid_prefix_calls=dict(prefix_calls),
                potential_short_skips=2*len(skipped), potential_skip_factors=dict(factors),
                skipped_visits_if_allowed=skipped,
                actual_skipped_lanes=2*len(skipped) if outcome["route"]=="thin-unfiltered" else 0)


def price(costs, plan, route):
    native = costs["native"]
    count, cpu = native["native_calls"], native["native_cpu_ns"]
    if count != plan["original_calls"]:
        raise ValueError("Cost model and signed aperture schedules disagree")
    unit = {key: cpu[key]/count[key]/1e9 for key in count}
    gross = plan["potential_short_skips"]*unit["short_primary"]
    skipped = plan["actual_skipped_lanes"]
    selector_cost = (route["clocks"]["cpu_ns"]+route["view_clock"]["cpu_ns"])/1e9
    return dict(original_acquire_cpu_s=costs["acquire"]["cpu_ns"]/1e9,
        mandatory_other_acquire_cpu_s=(costs["acquire"]["cpu_ns"]-sum(cpu.values()))/1e9,
        original_native_cpu_s=sum(cpu.values())/1e9, unit_aperture_cpu_s=unit,
        prefix_native_model_cpu_s=sum(plan["paid_prefix_calls"][key]*unit[key] for key in count),
        prefix_gate_cpu_s=selector_cost, potential_gross_cpu_s=gross,
        potential_net_before_other_overhead_cpu_s=gross-selector_cost,
        realized_credit_after_gate_cpu_s=skipped*unit["short_primary"]-selector_cost,
        rollback_short_compute_model_cpu_s=skipped*unit["short_primary"],
        original_iq_bytes_for_exact_missing_visits=skipped//2*1_600_000,
        dense_gross_target_cpu_s=GROSS_GATE)


def potential_rollback(plan, model):
    visits = plan["potential_short_skips"]//2
    return dict(missing_stereo_visits=visits,
                short_native_redo_cpu_s_using_archive_mean=model["potential_gross_cpu_s"],
                full_stereo_iq_bytes=visits*1_600_000, short_stereo_iq_bytes=visits*960_000)


def run(output):
    from tools.pipeline_eval.variants import carrier_continuation

    if sha256(Path(carrier_continuation.__file__).read_bytes()).hexdigest() != CONTINUATION_SHA or any(
        sha256((HERE/name).read_bytes()).hexdigest()!=pin for name,pin in SOURCE_SHA.items()
    ):
        raise ValueError("Frozen receiver-only selector sources changed")
    if output.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs receipt")
    results = {}
    for case in CASES:
        doc, audit, binding = load_original(case)
        issued = doc["provenance"]["window_count"]
        step = now()
        prefix = paid_prefix(doc["source"]["probes"],issued)
        prefix_clock = clock(step)
        selected = decide(prefix)
        selected["view_clock"] = prefix_clock
        count = count_plan(doc, selected)
        model = price(audit,count,selected)
        model["prefix_view_cpu_s"] = prefix_clock["cpu_ns"]/1e9
        step = now()
        eof = select_route(doc)
        eof["clocks"] = clock(step)
        if eof["route"] == "history":
            step = now()
            restored = history_rows(doc["source"]["probes"])
            eof["restore_clocks"] = clock(step)
            eof["restored_factors"] = sum(len(row["candidates"]) for row in restored)
        # A remaining whole cycle can contribute as much as log(15) toward history.
        # Paid incomplete cycles can reuse their already paid slots. Treat every remaining issued visit as valid.
        paid = sum(row["visits"]%8 for row in selected.get("observed_streams", []))
        future = (max(0,issued-CHECKPOINT)+paid)//8
        upper = {radio:gain+future*log(15) for radio,gain in selected.get("prefix_gain", {}).items()}
        skipped = set(count["skipped_visits_if_allowed"])
        count["actual_skipped_factors"] = (sum(count["potential_skip_factors"].values())
                                            if selected["route"]=="thin-unfiltered" else 0)
        results[case] = dict(binding=binding, prefix=selected, eof=eof, pricing=model, schedule=count,
              prefix_issued=prefix["provenance"]["window_count"],
              prefix_admitted=prefix["provenance"]["processed_windows"], issued=issued,
              original_factors=sum(len(row["candidates"]) for row in doc["source"]["probes"]),
              if_thinned_rollback=potential_rollback(count, model),
              pessimistic_future_cycle_bound=future, history_gain_upper_if_unknown_suffix=upper,
              skipped_visit_count_if_allowed=len(skipped))
    with output.open("x") as stream_handle:
        json.dump(dict(cases=results, selector_source_sha256=SOURCE_SHA, original_waveform_reads=0,
                       fresh_detector_runs=0, position_solves=0),stream_handle,indent=2,sort_keys=True,allow_nan=False)
        stream_handle.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    run(parser.parse_args().output)
