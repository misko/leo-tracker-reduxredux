"""Credit individual operations at their measured elapsed cost on one raw North input."""

import gzip
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def receipt(name):
    with gzip.open(HERE / "measurements" / name, "rt") as stream:
        return json.load(stream)


def elapsed(clock):
    if clock["exit_code"] != 0 or clock["elapsed_s"] <= 0:
        raise ValueError("Expected a successful whole-process clock")
    return clock["elapsed_s"]


def scenario(original, target, credit):
    if not 0 <= credit <= original:
        raise ValueError("Out-of-scope time credit")
    remaining = original - credit
    return dict(original_s=original, credited_s=credit, conditional_elapsed_s=remaining,
                seconds_above_half=remaining - target)


def evaluate(mixed, live):
    runs = mixed["runs"]
    named = elapsed(runs["stock"]["through_exit"])
    masked = runs["masked"]
    north = live["scientific_seal"]
    raw = north["raw"]
    audit = raw["receiver_audit"]
    if (elapsed(north["historical"]["named"]) != named
            or masked["acquisition"]["recording_authority"] != audit["recording_authority"]
            or masked["receipt"]["region"] != runs["stock"]["receipt"]["region"]
            or not live["figures"]["all_eight_encoded_decoded_and_dimensions_match"]
            or masked["replica_route"]["reason"] != "repair_rejection_cap"
            or north["route"]["decision"] != "complete"):
        raise ValueError("Expected the original matched North receivers and solver routes")
    short = audit["native"]["native_wall_ns"]["short_primary"] / 1e9
    full = audit["native"]["native_wall_ns"]["full"] / 1e9
    if not 0 < short + full < raw["phases"]["authenticated_raw_acquisition"]["elapsed_s"]:
        raise ValueError("Native time is outside the measured acquisition window")
    target = named / 2
    eight = elapsed(north["clock"])
    thinned = elapsed(masked["through_exit"])
    route = masked["replica_route"]
    fallback = route["fallback_clocks"]["elapsed_s"]
    return dict(named_s=named, target_s=target, masked_fallback_free=scenario(thinned, target, fallback),
                masked_failed_attempt_free=scenario(thinned, target, route["candidate_pre_evidence_clocks"]["elapsed_s"]),
                all8_short_free=scenario(eight, target, short), all8_native_twice_as_fast=scenario(eight, target, (short + full) / 2),
                all8_required_fraction_of_full_and_short=(eight-target)/(short+full),
                all8_preparation_and_ingress_outside_native_s=raw["phases"]["authenticated_raw_acquisition"]["elapsed_s"]-short-full,
                masked_fixed_error_m=masked["arms"]["c0"]["error_m"],
                all8_fixed_error_m=live["position_score"]["outcomes"]["live_8ms"]["c0"]["error_m"])


if __name__ == "__main__":
    print(json.dumps(evaluate(receipt("live-stereo-north.json.gz"), receipt("eight-ms-native-live.json.gz")), indent=2))
