"""Reveal the development references after the cold and fallback decisions are saved."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_score import PHYSICAL, SIMULATED, face_clearance_km, distance_km, references
from mixture_trial import ARMS, CASES


HERE = Path(__file__).resolve().parent
BUDGET_CPU_S = 24.


def section(arms, truth, control):
    scored = {}
    for arm in ARMS:
        value = arms.get(arm, {})
        position = value.get("latlon")
        error = None if position is None else distance_km(position, truth)
        rms = value.get("matched_sample_rms_hz", value.get("rf_rms_hz"))
        before = control.get(arm, {}).get("latlon")
        prior_error = None if before is None else distance_km(before, truth)
        before_rms = control.get(arm, {}).get("rf_rms_hz")
        scored[arm] = dict(
            latlon=position, error_km=error, rf_rms_hz=rms,
            delta_error_km=None if None in (error, prior_error) else error - prior_error,
            delta_rf_rms_hz=None if None in (rms, before_rms) else rms - before_rms,
        )
    zero, learnt = [scored[arm] for arm in ARMS]
    difference = {key: None if None in (zero[key], learnt[key]) else learnt[key] - zero[key]
                  for key in ("error_km", "rf_rms_hz")}
    return dict(arms=scored, fitted_minus_zero=difference)


def score(directory, full_path, summary_path):
    references_by_case = references()
    baseline = json.loads((HERE / "measurements/aperture-summary.json").read_bytes())["cases"]
    summary, receipts, source_pins = {}, {}, {}
    for case in CASES:
        path = directory / f"{case}.json"
        source = path.read_bytes()
        raw = json.loads(source)
        attempts = raw["attempts"]
        if len(attempts) != 1:
            raise ValueError("The fixed expected comparator used one orbital context")
        trial, stock = attempts[0], raw["control"]
        truth = references_by_case[case]
        cpu = raw["candidate_clocks"]["cpu_s"]
        proposed, finished = trial["proposal_clocks"]["cpu_s"], trial["finish_clocks"]["cpu_s"]
        fallback = trial.get("fallback_clocks", {}).get("cpu_s", 0.)
        prep = cpu - proposed - finished - fallback
        stage = dict(
            charged_cpu_s=cpu, charged_elapsed_s=raw["candidate_clocks"]["elapsed_s"],
            shared_prep_other_cpu_s=prep, proposal_cpu_s=proposed, validation_cpu_s=finished,
            fallback_cpu_s=fallback, free_validation_oracle_cpu_s=prep + proposed,
            one_finish_no_fallback_oracle_cpu_s=prep + proposed + finished,
            archived_v3_cpu_s=baseline[case]["full"]["cpu_s"],
        )
        if case == "DS30-0008" and fallback:
            stage["maximum_fallback_fraction_under_24s"] = max(0., min(1., (BUDGET_CPU_S - prep - proposed - finished) / fallback))
        sections = {
            name: section(arms, truth, stock["arms"])
            for name, arms in (("proposal", trial["proposal"]["arms"]), ("one_finish", trial["finish"].get("arms", {})),
                               ("control", stock["arms"]), ("terminal", raw["result"]["arms"]))
        }
        contained = face_clearance_km(raw["identity"]["offer"], truth) >= 0.
        one_finish = sections["one_finish"]["arms"]
        unguarded_pass = (contained and all(r["delta_error_km"] is not None and r["delta_error_km"] <= .25
                                           for r in one_finish.values()))
        summary[case] = dict(contained=contained, stages=stage, matches=raw["oracle"],
                             route=trial["finish"]["decision"], fallback_reasons=trial["finish"]["reasons"],
                             stock_status=stock["status"], terminal_status=raw["result"]["status"],
                             unguarded_finish_pass=unguarded_pass, **sections)
        receipts[case] = raw
        source_pins[path.name] = sha256(source).hexdigest()
    run = dict(cases=summary, dense_target_cpu_s=BUDGET_CPU_S,
               scoring_references={str(p.relative_to(HERE.parents[2])): sha256(p.read_bytes()).hexdigest()
                                   for p in (PHYSICAL, SIMULATED)}, source_sha256=source_pins)
    with full_path.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(run, receipts=receipts), sort_keys=True,
                                             separators=(",", ":"), allow_nan=False).encode(), mtime=0))
    with summary_path.open("x") as stream:
        print(json.dumps(run, indent=2, sort_keys=True, allow_nan=False), file=stream)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("directory", "full_path", "summary_path"):
        parser.add_argument(argument, type=Path)
    score(**vars(parser.parse_args()))
