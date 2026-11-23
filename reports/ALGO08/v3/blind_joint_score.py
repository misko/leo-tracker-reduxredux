"""Score frozen blind joint finishes and their checked terminal decisions."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_score import PHYSICAL, SIMULATED, face_clearance_km, references
from aperture_trial import CASES as SAVED_CASES
from mixture_score import BUDGET_CPU_S, section
from mixture_trial import ARMS, CASES


HERE = Path(__file__).resolve().parent
CLOCKS = ("cold", "initial_gate", "salvage", "predictive", "finish", "repair_prepare", "repair_fit",
          "exterior", "standard_evidence", "fallback")


def compare(record, truth, archived):
    decision = record["result"]
    stock = record["control"]
    attempt, = record["attempts"]
    clearance = face_clearance_km(record["identity"]["offer"], truth)
    contained = clearance >= 0.
    first_fit = attempt.get("finish", {})
    repair_fit = attempt.get("repair", {}).get("finish")
    diagnostic = section(repair_fit or first_fit, truth, stock["arms"])
    returned = section(decision["arms"], truth, stock["arms"])
    comparison = section(stock["arms"], truth, stock["arms"])
    errors = returned["arms"]
    exact_candidate = attempt["decision"] != "fallback"
    passes = (exact_candidate and decision["status"] == "ok"
              and all(r["delta_error_km"] is not None and r["delta_error_km"] <= .25 for r in errors.values())
              if contained else exact_candidate and decision["status"] == "withheld")
    measured = {key: attempt.get(key + "_clocks") for key in CLOCKS}
    charged = record["charged"]
    total = sum(time["cpu_s"] for time in measured.values() if time)
    headroom = BUDGET_CPU_S - charged["cpu_s"] if record["identity"]["case"] == "DS30-0008" else None
    arm_decisions = {}
    for arm in ARMS:
        provisional = (repair_fit or first_fit).get(arm)
        compatible = None if provisional is None else (
            not (provisional["failed_curved"] or provisional["failed_linear"])
            and (not provisional["linear_points"] or provisional["final_phase_change_s"] <= .01)
        )
        arm_decisions[arm] = dict(provisional_rf_gate=compatible,
                                  candidate_route=attempt["decision"],
                                  terminal="returned" if decision["arms"][arm].get("latlon") is not None else "withheld")
    return dict(
        contained=contained, truth_clearance_km=clearance, control_status=stock["status"],
        terminal_status=decision["status"], terminal_reason=decision["reason"],
        route=attempt["decision"], rejected_reason=attempt.get("reason"), triage_pass=passes,
        calibration_decisions=arm_decisions,
        diagnostic=diagnostic, returned=returned, stock=comparison,
        before_repair=section(first_fit, truth, stock["arms"]) if repair_fit is not None else None,
        repair=attempt.get("repair"),
        support={k: v for k, v in attempt.get("support", {}).items() if k not in ("salvage", "predictive_labels")},
        actual_finish=repair_fit or first_fit, stock_roles=record["stock_roles"],
        published_roles=record["published_roles"], published_owner_changes=record["published_owner_changes"],
        grid_points=decision.get("grid_points"), numerical_objective_replay=decision.get("objective_replay"),
        timing=dict(stages=measured, shared_preparation_other_cpu_s=charged["cpu_s"] - total,
                    charged=charged, archived_stock_cpu_s=archived["cpu_s"], stock=record["control_clocks"],
                    unspent_dense_budget_cpu_s=headroom,
                    pre_fallback_cpu_s=charged["cpu_s"] - (measured["fallback"] or {}).get("cpu_s", 0.)),
    )


def score(directory, summary, full, *, cases=None):
    truth = references()
    archived = json.loads((HERE / "measurements/aperture-summary.json").read_text())["cases"]
    observed, pins, results = {}, {}, {}
    for case in CASES if cases is None else cases:
        raw = (directory / f"{case}.json").read_bytes()
        record = json.loads(raw)
        results[case] = compare(record, truth[case], archived[case]["full"])
        observed[case], pins[case] = record, sha256(raw).hexdigest()
    pins.update({str(path.relative_to(HERE.parents[2])): sha256(path.read_bytes()).hexdigest()
                 for path in (PHYSICAL, SIMULATED)})
    minimal = dict(cases=results, pins=pins, dense_target_cpu_s=BUDGET_CPU_S)
    with summary.open("x") as stream:
        print(json.dumps(minimal, sort_keys=True, indent=2, allow_nan=False), file=stream)
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(minimal, receipts=observed), sort_keys=True,
                                             separators=(",", ":"), allow_nan=False).encode(), mtime=0))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("directory", "summary", "full"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--case", dest="cases", choices=SAVED_CASES, action="append")
    score(**vars(parser.parse_args(argv)))


if __name__ == "__main__":
    main()
