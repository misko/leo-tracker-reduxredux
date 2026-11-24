"""Transfer measured single-core acquisition costs using the original RF cadence."""

from collections import Counter
import json
from math import isclose
from pathlib import Path
from statistics import mean, median

from reports.ALGO08.v3.blind_saved_figure import read_receipt
from reports.ALGO08.v3.intake_scale_check import combined_blind_trials, combined_intake_budget
from reports.ALGO08.v3.mixed_aperture_receiver import FULL_RULE
from reports.ALGO08.v3.release_stage_budget import checked


MODES = ("full", "short_primary")


def schedule(probes):
    """Count the exact receiver calls implied by ordered, admitted stereo probes."""
    if len(probes) % 2:
        raise ValueError("Incomplete stereo opportunity")
    counts = Counter()
    per_stream = Counter()
    last = {}
    for first, second in zip(probes[::2], probes[1::2], strict=True):
        fields = ("edge", "channel", "actual_rf_hz", "valid_start_counter", "visit_index")
        if ([first["receiver_id"], second["receiver_id"]] != [0, 1]
                or any(first[k] != second[k] for k in fields)):
            raise ValueError("Mismatched original stereo measurements")
        stream = first["edge"], first["channel"], first["actual_rf_hz"]
        counter = first["valid_start_counter"]
        if stream in last and counter <= last[stream]:
            raise ValueError("Nonchronological original receiver stream")
        last[stream] = counter
        counts[FULL_RULE[per_stream[stream] % len(FULL_RULE)]] += 2
        per_stream[stream] += 1
    return dict(counts), [dict(edge=e, channel=c, rf_hz=f, admitted=n)
                          for (e, c, f), n in sorted(per_stream.items())]


def observed(name, run, original):
    if not run["qualified"] or run["process"]["exit_code"]:
        raise ValueError("Expected a completed scientific comparison")
    receiver = run["receiver"]
    native = receiver["receiver_audit"]["native"]
    calls = native["native_calls"]
    expected = Counter()
    for stream in native["streams"]:
        for i in range(stream["admitted"]):
            expected[FULL_RULE[i % len(FULL_RULE)]] += 2
    if tuple(native["rule"]) != FULL_RULE or calls != expected:
        raise ValueError("The measured recording used a different receiver schedule")
    total = receiver["phases"]["authenticated_raw_acquisition"]["cpu_s"]
    seconds = {k: native["native_cpu_ns"][k] / 1e9 for k in MODES}
    other = total - sum(seconds.values())
    if other <= 0 or min(calls.values()) <= 0:
        raise ValueError("Invalid acquisition or native callback accounting")
    volume = sum(m["encoded"] for m in original["members"])
    return dict(name=name, calls=calls, encoded_bytes=volume, cpu_s=total,
                cpu_s_per_call={k: seconds[k] / calls[k] for k in MODES},
                other_cpu_s_per_byte=other / volume)


def predict(source, target):
    return (sum(source["cpu_s_per_call"][k] * target["calls"][k] for k in MODES)
            + source["other_cpu_s_per_byte"] * target["encoded_bytes"])


def study():
    physical = read_receipt("integrated-original.json.gz",
                            "eb115ec1dd7a734693e21d8be49e2f7de87fe48936b8db8d51e1216cf37a0dff")
    south = read_receipt("integrated-south.json.gz",
                         "8953474fff07f72f81bd58848c6075797e5e1ffacdd4973f9049e2a64cc5a674")
    sources = []
    for order, pair in physical["runs"].items():
        run = pair["DS30-0016"]["result"]["document"]
        sources.append(observed("DS30-0016/" + order, run, run["acquisition"]))
    for offer, run in south["offers"].items():
        sources.append(observed("South/" + offer, run, run["original"]))
    cross = []
    for donor in sources:
        for target in sources:
            predicted = predict(donor, target)
            if donor is target:
                if not isclose(predicted, target["cpu_s"]):
                    raise ValueError("Measured costs do not reconstruct their original total")
            elif donor["name"].split("/")[0] != target["name"].split("/")[0]:
                cross.append(dict(source=donor["name"], target=target["name"], predicted_s=predicted,
                                  measured_s=target["cpu_s"], error_s=predicted-target["cpu_s"]))
    targets = []
    budgets = {r["case"]: r for r in combined_intake_budget()["rows"]}
    for trial in combined_blind_trials():
        original = trial["admission"]["original_inputs"]
        data = json.loads(checked(Path(original["native_path"]), original["native_sha256"]))
        probes = data["source"]["probes"]
        counts, streams = schedule(probes)
        if len(probes) != original["probes"] or len(probes) != 2 * original["admitted"]:
            raise ValueError("Saved packet and blind admission disagree")
        budget = budgets[trial["case"]]
        target = dict(case=trial["case"], encoded_bytes=budget["byte_high"], calls=counts, streams=streams,
                      native_sha256=original["native_sha256"], intake_allowance_s=budget["allowance_s"])
        target["transfer"] = {s["name"]: predict(s, target) for s in sources}
        target["remaining_s"] = {name: budget["allowance_s"] - cost for name, cost in target["transfer"].items()}
        targets.append(target)
    # For three paired cases the median time ratio passes when at least two cases pass.
    uniform_extra = {}
    for source in sources:
        headrooms = [target["remaining_s"][source["name"]] for target in targets]
        uniform_extra[source["name"]] = min(mean(headrooms), median(headrooms))
    return dict(measured=sources, cross_recording_checks=cross, projected=targets,
                uniform_extra_s_per_case_for_both_timing_gates=uniform_extra)


if __name__ == "__main__":
    print(json.dumps(study(), indent=2, allow_nan=False))
