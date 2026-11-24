"""Price a hindsight rejected-trial oracle on the sealed exact cold finalist."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from statistics import median
from struct import pack, unpack
from time import perf_counter, process_time

from finalist_tangent_summary import classify


HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE/"measurements"
TRACE = "06eedd0a32ddd013dea8a7398600bbe39f9a85018fc83ca04c285358d1cfd925"
BINDING = "18a61b117fb02561b97e7f32b99bd0377b8a9cb17e8a913718e968bc29a1ab38"
OPTIMIZER = Path("/opt/leo-algo08/algo08v3/payload/tools/pipeline_eval/variants/compact_cavity_optimizer.py")
OPTIMIZER_PIN = "5bceea78eaece66c20f1e12c1fd109182a8cc5cc2e8b6d410f2d68d93e9110a3"
OFFER_PIN = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
EARLIER = Path("/dev/shm/leo-v3-causal-mask-dense-01/dense/joint-research-receipt.json")
EARLIER_PIN = "8dded884cd12d52f95d135d4da850fbb5f7dc62ee1252d7553a7065170668f61"
MIN_DECREASE = 1e-9
TRIALS_PER_DIRECTION = 3


def checked(path, pin, *, zipped=False):
    body = path.read_bytes()
    body = gzip.decompress(body) if zipped else body
    if sha256(body).hexdigest() != pin:
        raise ValueError(f"Archived source or score changed at {path}")
    return body


def coordinate_key(point):
    return pack("!dd", *point)


def charge(rows):
    return dict(calls=len(rows), cpu_ns=sum(row["cpu_ns"] for row in rows))


def audit_phase(trace, half_width):
    verified = classify(trace, half_width, include_requests=True)
    rows = trace["full_calls"]
    history = trace["result"]["history"]
    episodes, pending, rejected = [], [], []
    lookup, reuse, reuse_rejected, conflicts = {}, [], [], []
    incumbent = history[0]["score"]
    accepted, rejected_score_gaps = [], []
    for label, row in zip(verified.pop("request_classes"), rows, strict=True):
        if row["cpu_ns"] < 0 or not isfinite(row["score"]) or not all(map(isfinite, row["point"])):
            raise ValueError("The archived objective trace contains an invalid request")
        key = coordinate_key(row["point"])
        if key in lookup:
            if lookup[key] == row["score"]:
                reuse.append(row)
                if label == "rejected_trial":
                    reuse_rejected.append(row)
            else:
                conflicts.append(row)
        else:
            lookup[key] = row["score"]
        if label == "rejected_trial":
            if row["score"] < incumbent-MIN_DECREASE:
                raise ValueError("Archived rejection violates the strict full-score gate")
            pending.append(row)
            rejected.append(row)
            rejected_score_gaps.append(row["score"]-incumbent)
        elif pending:
            episodes.append(pending)
            pending = []
        if label == "accepted_trial":
            if not row["score"] < incumbent-MIN_DECREASE:
                raise ValueError("Archive marked a trial accepted without exact score decrease")
            accepted.append(dict(parameters=row["point"], score=row["score"]))
            incumbent = row["score"]
    terminal_rejections = pending
    if pending:
        episodes.append(pending)
    if accepted != history[1:] or any(len(run) > TRIALS_PER_DIRECTION for run in episodes):
        raise ValueError("The readout changed the released trust-region sequence")
    repeated = [row for run in episodes for row in run[1:]]
    optimizer_cpu = trace["cpu_ns"]
    scenarios = {name: charge(group) for name, group in (("all_rejected", rejected), ("after_first_rejection", repeated),
                                                       ("terminal_run", terminal_rejections))}
    for value in scenarios.values():
        value.update(optimizer_cpu_ns_remaining=optimizer_cpu-value["cpu_ns"], exact_calls_remaining=len(rows)-value["calls"],
                     retained_start=history[0], retained_endpoint=history[-1])
    gaps = dict(minimum=min(rejected_score_gaps), median=median(rejected_score_gaps), maximum=max(rejected_score_gaps)) if rejected else None
    result = dict(classes=verified, history=history, optimizer_cpu_ns=optimizer_cpu, stopped=trace["result"]["stopped"],
                  rejected_episode_lengths=Counter(len(run) for run in episodes), rejected_minus_incumbent_loss=gaps,
                  gates=dict(minimum_decrease=MIN_DECREASE, original_accepted_steps=len(accepted)),
                  ideal_hindsight=scenarios, same_phase_coordinate_reuse=charge(reuse), same_phase_rejected_reuse=charge(reuse_rejected),
                  same_phase_score_conflicts=charge(conflicts))
    return result, lookup


def audit(output):
    start_cpu, start_wall = process_time(), perf_counter()
    checked(OPTIMIZER, OPTIMIZER_PIN)
    request = json.loads(checked(MEASUREMENTS/"finalist-tangent-DS30-0008-binding.json.gz", BINDING, zipped=True))
    recorded = json.loads(checked(MEASUREMENTS/"finalist-tangent-DS30-0008.json.gz", TRACE, zipped=True))
    if recorded["binding_sha256"] != BINDING or recorded["waveform_calls"] or recorded["terminals"]:
        raise ValueError("Expected the original no-publication exact finalist trace")
    offer = json.loads(checked(Path(request["request"]["offer"]), OFFER_PIN))
    scope = recorded["scope"]
    chosen, control = scope["archived_finalist"], scope["results"]["control"]
    if chosen["branch"] != 1 or len(control["optimizer"]) != 2 or control["active_rows"] != 3895:
        raise ValueError("Changed original cold finalist, phase or full-row scope")
    phases, coordinate_scores = zip(*(audit_phase(trace, offer["width_km"]/2) for trace in control["optimizer"]), strict=True)
    if (phases[0]["history"][-1]["score"] != chosen["first_score"] or phases[1]["history"][-1]["score"] != chosen["score"]
            or phases[1]["history"][-1]["parameters"] != chosen["point"]):
        raise ValueError("The archived control no longer reproduces both exact endpoints")
    older = json.loads(checked(EARLIER, EARLIER_PIN))
    if older["route_details"]["cold"] != request["archived_cold"]:
        raise ValueError("Archived whole-solve timing belongs to a different cold run")
    left, right = coordinate_scores
    merged = left.keys() & right.keys()
    shared_xy = [dict(point=list(unpack("!dd", key)), first_score=left[key], refreshed_score=right[key])
                 for key in sorted(merged)]
    ideal = {name: sum(phase["ideal_hindsight"][name]["cpu_ns"] for phase in phases) for name in phases[0]["ideal_hindsight"]}
    data = dict(physical_case="DS30-0008", branch=chosen["branch"], archived_winner=scope["archived_winner"],
                selected_curved_rows=control["active_rows"], selected_families=len(control["labels"]),
                phases=phases, cross_phase_same_coordinate=shared_xy, ideal_rejection_cpu_ns=ideal,
                timing_reference=dict(solve=older["solve"]["cpu_s"], publication=older["publication_cpu_s"],
                                      cold=older["route_details"]["cold_clocks"]["cpu_s"]),
                pins=dict(exact_trace_sha256=TRACE, trace_binding_sha256=BINDING, optimizer_sha256=OPTIMIZER_PIN,
                          original_publication_sha256=EARLIER_PIN), additional_waveform_reads=0,
                additional_residual_calls=0, additional_position_solves=0,
                audit_clock=dict(cpu_s=process_time()-start_cpu, elapsed_s=perf_counter()-start_wall))
    with output.open("x") as stream:
        json.dump(data, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    audit(parser.parse_args().output)
