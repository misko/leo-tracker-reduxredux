"""Independently verify scientific media and score the two calibration arms."""

import json

from held_shrink_0019 import CASE, EXPERIMENT, NATIVE, ROOT, STAGE, comparator, trial


def verify_publication(output, receipt, witness_pin, native, offer):
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_0016_best_score import position_sides

    witness = trial.document(output/"exact-named-raw-witness.json", witness_pin)
    run_id = receipt["run_id"]
    terminal = trial.document(output/"fast-scan-automatic-work"/run_id/"terminal.json", receipt["terminal_sha256"])
    evidence = witness["evidence"]
    if (terminal["native_sha256"] != native or terminal["region"] != offer
            or set(terminal["arms"]) != set(trial.ARMS) or len(witness["timing"]["solve"]) != 1):
        raise ValueError("Published scientific identity changed")
    media = artifacts(output, receipt)
    numeric = {}
    if receipt["decision"] == "complete":
        store = FastStandardAnalysisStore(output)
        numeric = position_sides(store, dict(receipt, region=offer), media, expected_points=179)
        grid = store.position_grid(run_id)
        if (terminal["decision"] != "ok" or len(media["images"]) != 8
                or json.dumps(media["images"], sort_keys=True) != json.dumps(evidence["images"], sort_keys=True)
                or media["path"] != evidence["sidecars"]["path"] or media["grid"] != evidence["sidecars"]["grid"]
                or set(grid["endpoint_objective_replay"]) != set(trial.ARMS)
                or any(abs(v) > 1e-5 for v in grid["endpoint_objective_replay"].values())):
            raise ValueError("Expected exact verified scientific figures, path, and grid evidence")
        for arm in trial.ARMS:
            owners = evidence["owner_rows"][arm]
            if (len(owners) != len({row[0] for row in owners})
                    or canonical_digest({oid:norad for oid,norad,_ in owners})
                    != evidence["detail"]["arms"][arm]["owner_sha256"]):
                raise ValueError("The ordered scientific owner roster differs")
    elif (receipt["decision"] != "withheld" or terminal["decision"] != "withheld" or media["images"]
            or any(arm["latlon"] is not None for arm in terminal["arms"].values())):
        raise ValueError("Unexpected ordinary disposition")
    return terminal, evidence, numeric


def original_publication():
    previous, clock, _ = comparator()
    witness = trial.document(STAGE/"ordinary/exact-named-raw-witness.json", previous["witness_sha256"])
    offer = witness["evidence"]["detail"]["region"]
    original = verify_publication(STAGE/"ordinary", previous["terminal"], previous["witness_sha256"],
                                  "sha256:"+NATIVE, offer)
    return original, clock


def check_control():
    trial.start_runtime().load_runtime()
    (terminal, _evidence, media), clock = original_publication()
    if terminal["decision"] != "ok" or media["grid_points"] != 179:
        raise ValueError("The archived ordinary scene must pass the fixed verifier")
    print(json.dumps(dict(ordinary_verified=True, arms=list(terminal["arms"]), grid=179,
                          archived_exit=clock["exit_code"])))


def score(pin):
    seal = trial.document(ROOT/"prediction-seal.json", pin)
    plan = trial.document(ROOT/"plan.json", seal["plan_sha256"])
    clock = trial.document(ROOT/"clock.json", seal["clock"])
    if clock["exit_code"] or not seal["receipt"] or seal["protocol"] != trial.protocol(EXPERIMENT):
        raise ValueError("An exit-zero timing requires an exited and sealed saved worker")
    run = trial.document(ROOT/"receipt.json", seal["receipt"])
    native = plan["change"]["derived_native_sha256"]
    if run["input"] != native or run["handoffs"] != 1 or run["waveform_reads"] or not run["graph_replayed"]:
        raise ValueError("Expected one verified saved handoff and ordinary Graph rebuild")
    trial.start_runtime().load_runtime()
    from prospective_0316_solver import owner_delta
    from sparse8_cfo_epoch_trial import geography
    from tools.pipeline_eval.scoring import distance_km

    (original, orig_evidence, _), old_clock = original_publication()
    derived, evidence, verification = verify_publication(ROOT/"substituted", run["receipt"], run["witness"],
                                                         native, original["region"])
    result = dict(case=CASE, decision=run["receipt"]["decision"], candidate_clock=clock,
                  archived_ordinary_clock=old_clock, verification=verification, graph_rebuilt=True,
                  evidence_input=native, prediction_sha256=pin)
    if run["receipt"]["decision"] == "complete":
        reference = geography(CASE)
        edited = {row["observation_id"] for row in plan["change"]["edits"]}
        arms = {}
        for arm in trial.ARMS:
            baseline, proposed = (terminal["arms"][arm] for terminal in (original, derived))
            a, b = (1e3*distance_km(reference, row["latlon"]) for row in (baseline, proposed))
            arms[arm] = dict(ordinary_error_m=a, half_blend_error_m=b, change_m=b-a,
                             endpoint_shift_m=1e3*distance_km(baseline["latlon"], proposed["latlon"]),
                             edited_owner_counts=[sum(row[0] in edited for row in e["owner_rows"][arm])
                                                  for e in (orig_evidence, evidence)],
                             conditional_rf_hz=[baseline["rf_rms_hz"], proposed["rf_rms_hz"]],
                             all_owned_rf_hz=[e["detail"]["arms"][arm]["residual_rms_hz"]
                                              for e in (orig_evidence, evidence)],
                             owners=owner_delta(orig_evidence["owner_rows"][arm], evidence["owner_rows"][arm]))
        result["arms"] = arms
    print(trial.write(ROOT/"score.json", result))
