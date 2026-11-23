"""Price a full-rate correlation bank using saved receiver receipts and native geometry."""

import gzip
from hashlib import sha256
import json
from math import log2
from pathlib import Path
from statistics import median
from struct import pack


HERE = Path(__file__).resolve().parent
RECEIPTS = {
    "dense-measured-budget.json": "72963a8b89ceeb265410b37ffa71d0f79778f784dd7db35bcd1ce88b91c4d985",
    "fractional-reject-ceiling.json.gz": "70c939f82a93e7d9154da7f5f05b6045155064a52c46e5d42dd7572c909f4c12",
    "receiver-polyphase-timing.json": "fc7a810e5ce43968de08c26e1e3726a4e8dbbfb047f5d41675c1aa0a7d4deba5",
    "refine-bound-audit.json.gz": "a0a1e7f3eb9b923fa0aef18164c6b81175ab21a15282f1816492556f51037cb7",
    "scout-readout.json.gz": "5d1998cee0e16165f2c355059d28b4b96f2486cc9297e7c55d760d4784f34431",
    "short-primary-dead-work.json.gz": "71bfdab2f034a041dd2d9b5b5990a181c9eddb777477d536de654851c7465100",
    "split-spectrum-trace.json.gz": "5ff3bb04368a461979a2840074e37164b82bce78d8eb1d12c68e407f565da39d",
}
SCHEDULE_RECEIPT = Path("/var/tmp/leo-full-short-dense-DS30-0008/publication/full-short-recipe.json")
SCHEDULE_SHA = "a86307c85d8405fd9c4a14b4bd09066f924016c82922b02b65d05557a6dc89bb"
STAGE_GOAL_S = {"first_four": 3.490, "first_sixteen": 0.811}
NATIVE_SOURCES = {
    "/var/tmp/leo-short-signed-02/short/timing_first_receiver.c": "a8fa28b5997ee7b4537ebaca4e41982b4976de4b00fde82011871570a616e1cc",
    "/var/tmp/leo-short-signed-02/short/delay_product_kernel.c": "944d8a9bfee130f8f12e22098ced20195464783e521ced9172c039cadb198ba2",
    "/var/tmp/leo-short-signed-02/short/portable_verifier.c": "4cceaa68fe8d7f93608d1d07f585e2bc5c68955a22619d989052d6cde2e70def",
    "/tmp/leo-algo08v2-2x-bench/receiver-fractional-exact-v1/portable_verifier.c": "3f62918238ad9107474d2f1509e953c61776eb70123ecd880c514f6e6483a707",
}


def read(path, pin):
    body = path.read_bytes()
    if sha256(body).hexdigest() != pin:
        raise ValueError(f"Saved measurement changed ({path})")
    return json.loads(gzip.decompress(body) if path.suffix == ".gz" else body)


def census(lanes):
    counts = dict(scouts=0, seeds=0, repeated_epoch=0, repeated_cfo=0, repeated_request=0,
                  close_distinct_epoch_pairs=0, wrap_seeds=0, max_same_epoch=0)
    period = 13_333
    for lane in lanes:
        for scan in lane["scans"]:
            seeds = [(s["epoch"], pack("!d", s["hz"])) for s in scan["seeds"]]
            epochs = [s[0] for s in seeds]
            cfo = [s[1] for s in seeds]
            unique_epochs = sorted(set(epochs))
            counts["scouts"] += 1
            counts["seeds"] += len(seeds)
            counts["repeated_epoch"] += len(epochs) - len(unique_epochs)
            counts["repeated_cfo"] += len(cfo) - len(set(cfo))
            counts["repeated_request"] += len(seeds) - len(set(seeds))
            counts["wrap_seeds"] += sum(e < 4 or e >= period-4 for e in epochs)
            counts["max_same_epoch"] = max(counts["max_same_epoch"], max((epochs.count(e) for e in unique_epochs), default=0))
            for i, a in enumerate(unique_epochs):
                counts["close_distinct_epoch_pairs"] += sum(min(a-b, period-(a-b)) < 9 for b in unique_epochs[:i])
    return counts


def convolution(taps, offsets, transform, *, templates=1, input_reuse=0., direct_ops_per_tap=None):
    """Optimistic direct/FFT arithmetic assuming each allowed template spectrum is free."""
    if min(taps, offsets, templates) <= 0 or transform < taps+offsets-1 or not 0 <= input_reuse < 1:
        raise ValueError("Invalid valid-correlation geometry")
    fft = 5*transform*log2(transform)
    estimate = (1-input_reuse+templates)*fft+6*templates*transform
    ops_per_tap = 8*templates if direct_ops_per_tap is None else direct_ops_per_tap
    direct = ops_per_tap*offsets*taps
    return dict(taps=taps, retained=offsets, minimum_circular_length=taps+offsets-1, transform=transform,
                templates=templates, shared_input_forward_fraction=input_reuse,
                direct_real_ops=direct, fft_real_ops=estimate, fft_over_direct=estimate/direct,
                break_even_offsets_at_this_fft=estimate/(ops_per_tap*taps),
                input_reuse_to_equal_direct=(1+templates)-(direct-6*templates*transform)/fft)


def price(stage, gap):
    return dict(stage_cpu_s=stage, fraction_to_save=gap/stage,
                required_stage_speedup=stage/(stage-gap) if stage > gap else None)


def partition_by_outcome(source, positive, lanes):
    names = ("scout", "verify_load", "verify")
    weights = (("confirmed", positive), ("empty", lanes-positive))
    return {stage: sum(source[key]["stage"]["stages"][j]*count for key, count in weights)/1e9
            for j, stage in enumerate(names)}


def screen():
    rows = {name: read(HERE / "measurements" / name, pin) for name, pin in RECEIPTS.items()}
    native = read(SCHEDULE_RECEIPT, SCHEDULE_SHA)["receiver_audit"]["native"]
    if any(sha256(Path(path).read_bytes()).hexdigest() != pin for path, pin in NATIVE_SOURCES.items()):
        raise ValueError("A pinned timing or verifier source changed")
    calls, factors = native["native_calls"], native["factors"]
    totals = {a: t/1e9 for a, t in native["native_cpu_ns"].items()}
    goal = STAGE_GOAL_S["first_four"]
    measured = rows["dense-measured-budget.json"]["cpu_s"]["receiver"]
    if sum(totals.values()) != measured:
        raise ValueError("The published budget must name the same complete native clock")
    stage_profile = rows["receiver-polyphase-timing.json"]["runs"]["dense"]["stages"][0]
    scouts = stage_profile["timing"]["calls"]
    full_sample = rows["scout-readout.json.gz"]["groups"]["dense"]["rows"]
    verify_s = sum(r["verification_cpu_ns"] for r in full_sample)/1e9
    load_s = sum(r["loading_cpu_ns"] for r in full_sample)/1e9
    full_scout_counts = [calls["full"]+factors["full"], 2*calls["full"]]
    short = rows["short-primary-dead-work.json.gz"]["summary"]
    poststratified = {panel: partition_by_outcome(section, factors["short_primary"], calls["short_primary"])
                     for panel, section in short.items()}
    projected = {}
    for stage in ("refine", "gate"):
        per_scout = stage_profile[stage]["cpu_s"]/scouts
        projected[stage] = dict(full=[n*per_scout for n in full_scout_counts],
                                short=[calls["short_primary"]*per_scout*f for f in (8/14, 1)])
    lower = projected["refine"]["full"][0]+projected["refine"]["short"][0]
    upper = projected["refine"]["full"][1]+projected["refine"]["short"][1]
    full_verify = verify_s*calls["full"]/len(full_sample)
    primary_verify = {panel: full_verify+stages["verify"] for panel, stages in poststratified.items()}
    combined = [(lower + projected["gate"]["full"][0]+projected["gate"]["short"][0]+min(primary_verify.values())),
                (upper + projected["gate"]["full"][1]+projected["gate"]["short"][1]+max(primary_verify.values()))]
    traced = {panel: census(value["lanes"]) for panel, value in rows["refine-bound-audit.json.gz"].items()
              if panel in ("dense", "weak")}
    fraction = traced["dense"]["repeated_epoch"]/traced["dense"]["seeds"]
    dense_short_sample = rows["split-spectrum-trace.json.gz"]["data"]["dense"]
    weak_verifier = rows["fractional-reject-ceiling.json.gz"]["short_weak"]["summary"]
    confirm = sum(row["frames"] > 0 for row in dense_short_sample)
    return dict(
        inputs=RECEIPTS | {str(SCHEDULE_RECEIPT): SCHEDULE_SHA}, native_source_sha256=NATIVE_SOURCES,
        native_binary_sha256={"20ms": native["installed_sha256"], "12ms": native["short_primary_sha256"]},
        goal_s=STAGE_GOAL_S, total_native_cpu_s=measured,
        stage_goals={label: price(measured, gap) for label, gap in STAGE_GOAL_S.items()},
        native_mode_cpu_s=totals, native_mode_calls=calls, native_mode_selected=factors,
        observed_full_20ms_stock_timing_profile=stage_profile,
        observed_full_20ms_stock_load_and_verify=dict(lanes=len(full_sample), load_cpu_s=load_s, verify_cpu_s=verify_s),
        observed_12ms_result_strata={p: {k: row["stage"]["stages"] for k, row in v.items()} for p, v in short.items()},
        observed_dense_12ms_support=dict(lanes=len(dense_short_sample), verifier_positive=confirm,
                                         output_positive=sum(bool(row["factor"]) for row in dense_short_sample)),
        observed_weak_12ms_verify_ns_per_examined=median(r["verifier_cpu_ns"]/r["examined"] for r in weak_verifier),
        full_recording_full_scout_count_limits=full_scout_counts, projected_full_rate_stages=projected,
        projected_full_20ms_verify_cpu_s=full_verify, projected_short_poststratified_cpu_s=poststratified,
        priced_entire_refine_stage=[price(t, goal) for t in (lower, upper)],
        priced_entire_verifiers={p: price(t, goal) for p, t in primary_verify.items()},
        priced_all_three_whole_stages=[price(t, goal) for t in combined],
        ninth_scalar_equivalent_ideal_saved_fraction=(1-1/8)/2,
        new_coarse_ninth_optimistic_s=upper*(1-1/8)/2,
        traced_requests=traced,
        operations=dict(refine_exact_length=convolution(352, 9, 360, input_reuse=fraction),
                        refine_radix_two=convolution(352, 9, 512, input_reuse=fraction),
                        integer_tight_length=convolution(44, 5, 48), integer_radix_two=convolution(44, 5, 64),
                        integer_ordered_direct=convolution(44, 5, 48, direct_ops_per_tap=14),
                        signed_gate=convolution(44, 1, 64),
                        fractional_two_templates=convolution(44, 1, 64, templates=2, direct_ops_per_tap=22)),
    )


if __name__ == "__main__":
    print(json.dumps(screen(), indent=2, sort_keys=True, allow_nan=False))
