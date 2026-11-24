"""Test a one-arm lower bound on the ordinary paired repair's curved losses."""

import argparse
from hashlib import sha256
import gzip
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE/"measurements"
INSTANT = "repair_rejection_cap"
SOURCE_PINS = {
    HERE/"blind_joint_repair.py": "f89e80dd65606b065e4c8097d0d3204362993e070dc7dd3f2c2590dc2c32b2a0",
    HERE/"blind_joint_finish.py": "7d8d5a65ceb0e11150e28d0dbbddeabb7741ef1408ded6272500e4f0e012c708",
}
INSTALLED = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/src/leo/analysis/localization_v3")
SOURCE_PINS.update({INSTALLED/name: pin for name, pin in {
    "history_policy.py": "429c230cb01438a4889f6e77256b7f00df4435b3522632bbef8cc2a83d223ca1",
    "conservative_recovery.py": "9d5047f873a22790c4f0818877b09270ee91a0761a9a3d7204c8a849639ee656",
    "position.py": "c3507e6ecaba0adf6d3677f56d8056afcccbcf90d6a561bca7a42b06b0daef9d",
    "families.py": "d165b623a36a1a3c396348b665ca5a9ad51342c6bc7472d5b05694cc1619150c",
}.items()})
ROUTED = "873d97f662f93f0ed9625b6400f9187569db9c3b9b5c6d86196c1d4f182ae220"
SCORED = "89aeaee758857adfad44ceb7980bff7a0da7371e04739ef3b79e3d3023d389d6"
ACCEPTED = (
    ("DS30-0016", "strict-cairo-0016.json.gz", "92eb659eeb74b1e1ec90cdf083673fb75f9e4640324aaf0cd976b143337e64a7",
     ("witness", "route", "history_risk", "lean_attempts", 0)),
    ("DS30-0402", "owner-loss-0402.json.gz", "92d7ce67d7cda1caca8345de6e6166ecdbe44c276a96652dc0be5f3769defd83",
     ("candidate", "route_details")),
)


def curved_bound(total, compatible):
    if type(total) is not int or type(compatible) is not int or not 0 <= compatible <= total or total == 0:
        return None
    lost = total - compatible
    return dict(curved_total=total, lost_at_least=lost, allowed=total//20,
                refusal=INSTANT if lost*20 > total else None)


def first_arm_certificate(arm, expected_points):
    """Use complete finalized c0 gates on the frozen mask; abstain otherwise."""
    if type(expected_points) is not int or arm.get("active_points") != expected_points:
        return None
    rows = arm.get("gates", {}).get("tracks", [])
    if (not rows or any(type(row.get("points")) is not int or row["points"] <= 0
                        or type(row.get("compatible")) is not bool or not isinstance(row.get("component"), str) for row in rows)
            or any(not row["component"] for row in rows) or len({row["component"] for row in rows}) != len(rows)
            or sum(row["points"] for row in rows) != expected_points):
        return None
    return curved_bound(expected_points, sum(row["points"] for row in rows if row["compatible"]))


def checked(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Expected the original frozen bytes in {path}")
    return data


def audited_attempt(attempt):
    fixed, fitted = (attempt["finish"][arm] for arm in ("c0", "fitted_c"))
    result = curved_bound(fixed["curved_points"], fixed["compatible_curved_points"])
    if (result is None or fixed["curved_points"] != fitted["curved_points"]
            or (attempt["pair_passes"] and result["refusal"])):
        raise ValueError("The saved pair has inconsistent matched curved support")
    return dict(prefix=result, repair=attempt.get("repair"), pair_passes=attempt["pair_passes"],
                fixed_failures=fixed["failed_curved"], fitted_failures=fitted["failed_curved"],
                fitted_failed_points=fitted["curved_points"]-fitted["compatible_curved_points"])


def audit(root):
    for filename, pin in SOURCE_PINS.items():
        checked(filename, pin)
    route = json.loads(checked(root/"routed/risk-route.json", ROUTED))
    score = json.loads(checked(root/"result.json", SCORED))
    solve, = route["solves"]
    attempt, = solve["lean_attempts"]
    dense = audited_attempt(attempt)
    if (score["case"] != "DS30-0004" or not score["no_waveform"] or not all(score["named_parity"].values())
            or attempt["decision"] != "fallback" or attempt["reason"] != INSTANT or dense["prefix"]["refusal"] != INSTANT
            or dense["repair"]["attempted_refits"] != 0 or dense["prefix"]["lost_at_least"] != dense["repair"]["rejection_counts"]["curved"][1]
            or not set(dense["fitted_failures"]) <= set(dense["fixed_failures"])):
        raise ValueError("The saved prefix must independently prove the measured original fallback")
    positive = {}
    for case, name, pin, keys in ACCEPTED:
        obj = json.loads(gzip.decompress(checked(MEASUREMENTS/name, pin)))
        for key in keys:
            obj = obj[key]
        test = audited_attempt(obj)
        if test["prefix"]["refusal"] is not None or not (test["pair_passes"] or test["repair"]["status"] == "complete"):
            raise ValueError("The first-arm screen cannot reject either genuine accepted control")
        positive[case] = test | {"sha256": pin}
    clocks = {field: attempt[field+"_clocks"] for field in ("cold", "initial_gate", "salvage", "predictive", "finish", "repair_prepare", "fallback")}
    return dict(case=score["case"], route_sha256=ROUTED, score_sha256=SCORED, certificate=dense, positive=positive,
                source_sha256={str(name): pin for name, pin in SOURCE_PINS.items()}, original_science_parity=score["named_parity"],
                clocks=clocks, original_lean_attempt=attempt["candidate_pre_evidence_clocks"],
                optimistic_removable={key: clocks["finish"][key]+clocks["repair_prepare"][key] for key in ("cpu_s", "elapsed_s")},
                fitter_reruns=0, waveform_reads=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.root), sort_keys=True, indent=2, allow_nan=False))
