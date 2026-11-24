"""Account for the frozen DS30-0147 fallback using compact sealed receipts."""

import argparse
import gzip
import json
from hashlib import sha256
from math import isclose, isfinite
from pathlib import Path
from statistics import median

from repair_first_arm_veto import REPAIR_SHA256


TARGET = "DS30-0147"
SCOPE = "raw_launcher_through_exit_plus_common_publication_verification"
BUILD = {
    "installed": "6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f",
    "successor": "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab",
}
PANEL = "5606ef6c2e7ca891bdeba243cfb471ef0c65f65dd1d1676bfea6e9d82cc4390f"
# pair, stock result, successor result, successor bootstrap, exact-route witness
CASES = {
    TARGET: (
        "e4e6b32aa6e6c1c1a1e67a2515651431c8d4f51db53178224d65db7356010252",
        "0e6d01763f43045c970c9e1f3506f750ef73cb2451f8e6203dc29979661bb9ee",
        "40535af864b91ee71ef1046e3c32b1a2569e9b08ac3bdde161402128a1dc226d",
        "998d7313cb63aa750130f287fabd7d83d7ace55ef30e760c6143f85208c4fade",
        "e3277a09631eb3b8af95dcb02d06878750d939727e970955baec6101f7693837",
    ),
    "DS30-0220": (
        "d307ff5f4a02fe144eb1547574728a46bf19b4365d971687c471adea65aa4755",
        "9028a2ced763361d74677ce23cd420bae3ca315fadd1b2481c2adb409db35aa3",
        "71683203e2acadf5b7d8402be7d848a6713628aa58e7c22728e332d97f50e4f9",
        "c9dacc53e748d67d9e923bf86240a74eb9e144210bce554882ef3acccd7ffcaa",
        "b8be7fef63a425d3fd15de1ca206f6ec40be65b96afa8d114fb0e8808c8a36eb",
    ),
    "DS30-0019": (
        "5a5307be75290e5bed14cb42380e47cd9679030a327fdcce2fa1fd2f3c910719",
        "2f44c2d64d6ad162235d6cb85e55f68a0c9df3c24c92fc6b6f0236ec4ec65f69",
        "8c6612053a07750ec41b1b98ede51f6e0831b8c498b979b427fabcef350bb962",
        "8da040a96db25e25df583ea72849eee507786159bf9906480e20f138fe03d6e1",
        "3479b478512a650c8f76269e0838b62c8e4e865911544bab86597f601a066e63",
    ),
}
SAVED_STOCK = "329693cc9562cf7dc9e4828199003d4c332994ff9ee5a1f47b7d1e332c3e3eb3"
SAVED_WITNESS = "982156b3591877e1f875d11dd7fc9e13618cb6fc5db013d37051a955ec83ff4b"
SAVED_OVER_CAP = "7bf15041645696fe4ddc06eef6f5d293df98467e8d1b85f457db971df95ebd54"
CLOCK = ("elapsed_s", "cpu_s")


def read_sealed(path, pin):
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    if sha256(raw).hexdigest() != pin:
        raise ValueError(f"Sealed receipt changed at {path}")
    return json.loads(raw)


def remainder(total, *parts):
    residual = {key: total[key] - sum(part[key] for part in parts) for key in CLOCK}
    if any(not isfinite(value) or value < -1e-9 for value in residual.values()):
        raise ValueError("Expected disjoint clocks contained by their parent interval")
    return residual


def stats(pairs):
    if not pairs or any(not isfinite(v) or v <= 0 for pair in pairs for v in pair):
        raise ValueError("Expected finite positive paired elapsed clocks")
    stock = sum(installed for installed, _ in pairs)
    candidate = sum(successor for _, successor in pairs)
    return dict(pairs=len(pairs), installed_s=stock, successor_s=candidate, summed_ratio=stock / candidate,
                median_ratio=1 / median(successor / installed for installed, successor in pairs),
                excess_s=candidate - stock / 2)


def summarize_panel(panel):
    rows = {}
    for row in panel["rows"]:
        arm = row["algorithm"]
        if (row["build_sha256"] != "sha256:" + BUILD[arm] or not row["verified_pair"]
                or not row["acquisition_verified"]
                or row["raw_authority_sha256"] != row["requested_raw_authority_sha256"]):
            raise ValueError("Unexpected arm in frozen original-file panel")
        pair = rows.setdefault(row["case"], {})
        if arm in pair:
            raise ValueError("Duplicate original-file arm")
        pair[arm] = row
    pairs, unmatched_scope = {}, {}
    for case, pair in rows.items():
        stock, candidate = pair["installed"], pair["successor"]
        if any(stock[key] != candidate[key] for key in ("case_id", "generation", "raw_authority_sha256")):
            raise ValueError("Original-file pair identity changed")
        if any(arm["timing_scope"] != SCOPE or arm["outcome"] not in ("complete", "withheld")
               for arm in (stock, candidate)):
            unmatched_scope[case] = {key: [arm["outcome"], arm["timing_scope"]] for key, arm in pair.items()}
            continue
        if case in CASES and (stock["attempt_result_sha256"], candidate["attempt_result_sha256"]) != tuple(
                "sha256:" + pin for pin in CASES[case][1:3]):
            raise ValueError("Case comparison uses an unexpected attempt")
        pairs[case] = (stock["elapsed_s"], candidate["elapsed_s"])
    without = [value for case, value in pairs.items() if case != TARGET]
    return dict(source={key: value for key, value in panel.items() if key != "rows"},
                per_case_elapsed_s=pairs, unmatched_scope=unmatched_scope,
                measured=stats(list(pairs.values())), without_0147=stats(without),
                replace_0147_with_half_time=stats(without + [(pairs[TARGET][0], pairs[TARGET][0] / 2)]))


def ns_clock(row):
    return dict(elapsed_s=row["elapsed_ns"] / 1e9, cpu_s=row["cpu_ns"] / 1e9)


def raw_case(path, pins):
    pair = read_sealed(path / "pair.json", pins[0])
    arms = {arm: read_sealed(path / arm / "attempt-000001/result.json", pin)
            for arm, pin in zip(BUILD, pins[1:3], strict=True)}
    stock, candidate = arms.values()
    publication = path / "successor/attempt-000001/publication"
    boot = read_sealed(publication / "unified-short-bootstrap.json", pins[3])
    witness = read_sealed(publication / "exact-named-raw-witness.json", pins[4])
    risk = witness["ports"]["history_risk"]
    attempt, = risk["lean_attempts"]
    detail = witness["evidence"]["detail"]
    if (not pair["verified_pair"] or not pair["chronological"] or pair["generation"] != 1
            or pair["attempt_result_sha256"] != dict(zip(BUILD, ("sha256:" + pin for pin in pins[1:3]), strict=True))
            or stock["raw_identity"] != candidate["raw_identity"]
            or len({candidate["native_sha256"], boot["native_sha256"], detail["input_sha256"]}) != 1
            or boot["receipt"]["terminal_sha256"] != detail["terminal_sha256"]
            or boot["receipt"]["region"] != detail["region"]
            or witness["source_sha256"] != boot["solver_source_sha256"]
            or witness["source_sha256"]["reports/ALGO08/v3/blind_joint_repair.py"] != REPAIR_SHA256
            or boot["raw_acquisitions"] != 1 or boot["verified_handoffs"] != 1):
        raise ValueError("Paired source, packet, terminal, or region binding changed")
    for result in arms.values():
        if (result["timing_scope"] != SCOPE or result["process"]["exit_code"] != 0
                or result["outcome"] != "complete" or len(result["figures"]) != 8
                or set(result["evidence"]["arms"]) != {"c0", "fitted_c"}
                or not all(isclose(result[key], result["process"][key] + result["validation"][key]) for key in CLOCK)):
            raise ValueError("Unexpected verified raw process or publication")
    phases = boot["phases"]
    (analyze,), (render,), (solve,) = (witness["timing"][stage] for stage in ("analyze", "render", "solve"))
    decision = phases["decision_and_publication"]
    acquire = phases["authenticated_raw_acquisition"]
    route_selection = phases["held_anchor_route_selection"]
    history = witness["ports"]["history"]
    prep_row, = history["prepare"]
    inference_row, = history["infer"]
    prepare, inference = ns_clock(prep_row), ns_clock(inference_row)
    out = dict(receipts=dict(zip(("pair", *BUILD, "bootstrap", "witness"), pins, strict=True)),
               order=pair["actual_order"], same_lease=pair["same_lease"], native_sha256=candidate["native_sha256"],
               terminal_sha256=detail["terminal_sha256"], raw_route=witness["raw_route"],
               initial_risk_reason=risk["choice"]["reason"], held_anchor_route=boot["held_anchor_route"]["choice"]["route"],
               verified={key: {unit: value[unit] for unit in CLOCK} for key, value in arms.items()},
               child={key: {unit: value["process"][unit] for unit in CLOCK} for key, value in arms.items()},
               verification={key: value["validation"] for key, value in arms.items()},
               arm_result={key: value["evidence"]["arms"] for key, value in arms.items()},
               phases=phases, raw_other=remainder(candidate["process"], acquire, route_selection, decision),
               solve=solve, analyze_outside_solve_and_render=remainder(analyze, solve, render), render=render,
               decision_outside_analyze=remainder(decision, analyze),
               solve_outside_preparation_and_inference=remainder(solve, prepare, inference),
               prepare=prepare, inference=inference,
               lean_attempt=attempt["decision"], lean_reason=attempt.get("reason"),
               lean_pre_evidence=attempt["candidate_pre_evidence_clocks"],
               repair=attempt.get("repair"), repair_prepare=attempt.get("repair_prepare_clocks"),
               repair_fit=attempt.get("repair_fit_clocks"), fallback=attempt.get("fallback_clocks"))
    if path.name == TARGET:
        salvage = attempt["provisional_salvage"]
        if salvage["status"] != "untouched" or salvage["fit_calls"] != 0 or risk["choice"]["route"] != "lean":
            raise ValueError("Predictive timer reset requires the archived untouched salvage path")
        stages = {name: attempt[name + "_clocks"] for name in (
            "cold", "initial_gate", "salvage", "predictive", "finish", "repair_prepare", "repair_fit")}
        stages.update(provisional_seed=salvage["seed_gate_clocks"], provisional_isolation=salvage["isolation_clocks"])
        stages["unassigned"] = remainder(out["lean_pre_evidence"], *stages.values())
        out.update(lean_stages=stages, initial_finish=attempt["finish"], boundary=risk["boundary_checks"],
                   named_nomination=risk["nomination_handoff"], rank=witness["ports"]["rank"],
                   inference_outside_lean_and_fallback=remainder(inference, out["lean_pre_evidence"], out["fallback"]))
        target = stock["elapsed_s"] / 2
        gap = candidate["elapsed_s"] - target
        out["budget"] = dict(half_time_s=target, deficit_s=gap,
                             solver_budget_s=solve["elapsed_s"] - gap,
                             decision_publication_budget_s=decision["elapsed_s"] - gap,
                             deficit_if_full_named_fallback_were_free_s=gap - out["fallback"]["elapsed_s"],
                             deficit_if_all_lean_pre_evidence_were_free_s=gap - out["lean_pre_evidence"]["elapsed_s"],
                             deficit_if_acquisition_were_free_s=gap - acquire["elapsed_s"],
                             upper_bound_first_arm_veto_wall_s=out["repair_fit"]["elapsed_s"])
    return out


def saved_controls(stock_dir, over_cap_dir):
    stock = read_sealed(stock_dir / "score.json", SAVED_STOCK)
    witness = read_sealed(stock_dir / "candidate/exact-named-raw-witness.json", SAVED_WITNESS)
    over_cap = read_sealed(over_cap_dir / "score.json", SAVED_OVER_CAP)
    attempt, = witness["ports"]["history_risk"]["lean_attempts"]
    return dict(receipt_sha256=[SAVED_STOCK, SAVED_WITNESS, SAVED_OVER_CAP],
                measured_saved_exit={key: stock["process"][key] for key in CLOCK},
                fallback=attempt["fallback_clocks"], reason=attempt["reason"], repair=attempt["repair"],
                exact_terminal=stock["terminal_exact"], over_cap_reason=over_cap["other_veto"],
                over_cap_repair=over_cap["repair"], over_cap_fallback=over_cap["fallback"], raw_timing_credit=0)


def main():
    command = argparse.ArgumentParser(description=__doc__)
    for name in ("campaign", "panel", "saved_stock", "saved_over_cap"):
        command.add_argument(name, type=Path)
    args = command.parse_args()
    result = dict(panel_input_sha256=PANEL, panel=summarize_panel(read_sealed(args.panel, PANEL)),
                  raw={case: raw_case(args.campaign / "cases" / case, pins) for case, pins in CASES.items()},
                  saved_0220=saved_controls(args.saved_stock, args.saved_over_cap))
    print(json.dumps(result, indent=2, allow_nan=False, sort_keys=True))


if __name__ == "__main__":
    main()
