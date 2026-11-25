"""Verify a future ordinary saved replay against the authenticated raw 0274."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from held_shrink_0019_score import verify_publication  # noqa: E402
from held_shrink_0274 import BASE, BLOCK, CASE, EXPERIMENT, NATIVE, WITNESS, archived, trial  # noqa: E402
from held_shrink_0274_control import PARITY  # noqa: E402
from sparse8_cfo_epoch_trial import geography, scientific_grid  # noqa: E402


def reference():
    _, _, original, raw, witness = archived()
    receipt = raw["evidence"]["receipt"]
    offer = witness["evidence"]["detail"]["region"]
    terminal, evidence, numerical = verify_publication(original, receipt, WITNESS, "sha256:"+NATIVE, offer)
    if terminal["decision"] != "ok":
        raise ValueError("The original signed charted comparison must be complete")
    return original, terminal, evidence, numerical, witness


def require_parity(ordinary, raw):
    differences = sorted(key for key in ordinary.keys() | raw.keys() if ordinary.get(key) != raw.get(key))
    if differences:
        raise ValueError(f"Ordinary saved science differs from the signed raw incumbent: {differences}")


def graph_identity(witness):
    original = witness["ports"]["graph"]["graph"]
    return {field: original[field] for field in ("assigned", "tracks", "calls", "edges", "edge_lanes")}


def check_control():
    trial.start_runtime().load_runtime()
    _, terminal, evidence, numerical, _ = reference()
    print(json.dumps(dict(arms=list(terminal["arms"]), owners={k:len(v) for k,v in evidence["owner_rows"].items()},
                          grid_points=numerical["grid_points"], pngs=len(evidence["images"]))))


def score(pin):
    root = BLOCK/"ordinary-capsule/output"
    seal = trial.document(root/"prediction-seal.json", pin)
    clock = trial.document(root/"clock.json", seal["clock"])
    plan = trial.document(root/"plan.json", seal["plan_sha256"])
    run = trial.document(root/"receipt.json", seal["receipt"])
    if (clock["exit_code"] or run["input"] != "sha256:"+NATIVE or run["handoffs"] != 1 or run["waveform_reads"]
            or plan["cell"] != "ordinary" or seal["protocol"] != trial.protocol(EXPERIMENT)):
        raise ValueError("Expected an exit-zero ordinary saved control on the exact original detector")
    trial.start_runtime().load_runtime()
    original, raw, raw_evidence, _, raw_witness = reference()
    output = root/"substituted"
    terminal, evidence, verified = verify_publication(output, run["receipt"], run["witness"],
                                                     "sha256:"+NATIVE, raw["region"])
    witness = trial.document(output/"exact-named-raw-witness.json", run["witness"])
    require_parity(
        dict(terminal=terminal, sources=witness["source_sha256"], owners=evidence["owner_rows"],
             graph=graph_identity(witness), scientific_recipe=witness["solver_recipe"],
             path=evidence["sidecars"]["path"], figures=evidence["images"], grid=scientific_grid(output)),
        dict(terminal=raw, sources=raw_witness["source_sha256"], owners=raw_evidence["owner_rows"],
             graph=graph_identity(raw_witness), scientific_recipe=raw_witness["solver_recipe"],
             path=raw_evidence["sidecars"]["path"], figures=raw_evidence["images"], grid=scientific_grid(original)),
    )
    print(trial.write(root/"ordinary-parity.json", dict(input=run["input"], original_witness=WITNESS,
          saved_prediction_sha256=pin, exact_ordinary_reproduction=True, verified=verified)))


def score_shrunk(pin):
    root = BLOCK/"half-blend-capsule/output"
    parity = trial.document(BLOCK/"ordinary-capsule/output/ordinary-parity.json", PARITY)
    seal = trial.document(root/"prediction-seal.json", pin)
    clock = trial.document(root/"clock.json", seal["clock"])
    plan = trial.document(root/"plan.json", seal["plan_sha256"])
    if (clock["exit_code"] or not seal["receipt"] or not parity["exact_ordinary_reproduction"]
            or plan["cell"] != "half-blend" or seal["protocol"] != trial.protocol(EXPERIMENT)):
        raise ValueError("Only a completed, pre-enrolled saved worker can be compared")
    run = trial.document(root/"receipt.json", seal["receipt"])
    native = plan["change"]["derived_native_sha256"]
    if run["input"] != native or run["handoffs"] != 1 or run["waveform_reads"] or not run["graph_replayed"]:
        raise ValueError("The original capture or omitted raw boundary changed")
    trial.start_runtime().load_runtime()
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.scoring import distance_km

    _, ordinary, old_evidence, _, raw_witness = reference()
    pub = root/"substituted"
    witness = trial.document(pub/"exact-named-raw-witness.json", run["witness"])
    result, evidence, check = verify_publication(pub, run["receipt"], run["witness"], native, ordinary["region"])
    if (witness["source_sha256"] != raw_witness["source_sha256"]
            or witness["solver_recipe"]["archive_sha256"] != raw_witness["solver_recipe"]["archive_sha256"]):
        raise ValueError("Changed scientific source or causal catalogue")
    report = dict(case=CASE, native_sha256=native, candidate_exit=clock["exit_code"], decision=run["receipt"]["decision"],
                  prediction_sha256=pin, graph=graph_identity(witness), verified=check,
                  archived_ordinary_parity_sha256=PARITY)
    if report["decision"] == "complete":
        pair, authority, _, _, _ = archived()
        stock_path = BASE/"installed"/f"attempt-{pair['generation']:06d}"/"result.json"
        installed = trial.document(stock_path, pair["attempt_result_sha256"]["installed"])
        if installed["raw_identity"] != authority or installed["outcome"] != "complete":
            raise ValueError("The named full detector comparison does not bind the same offer")
        site = geography(CASE)
        edited = {row["observation_id"] for row in plan["change"]["edits"]}
        arms = {}
        for arm in trial.ARMS:
            full, old, after = installed["evidence"]["arms"][arm], ordinary["arms"][arm], result["arms"][arm]
            reference_errors = {key:1000*distance_km(site, row["latlon"]) for key,row in
                                (("installed_v3",full), ("ordinary",old),("half_blend",after))}
            previous_owners, owners = (e["owner_rows"][arm] for e in (old_evidence, evidence))
            arms[arm] = dict(
                error_m=reference_errors,
                shift_from_ordinary_m=1000*distance_km(old["latlon"], after["latlon"]),
                conditional_rf_hz=[row["rf_rms_hz"] for row in (full, old, after)],
                all_owned_rf_hz=[e["detail"]["arms"][arm]["residual_rms_hz"] for e in (old_evidence,evidence)],
                edited_owners_before_after=[sum(row[0] in edited for row in values)
                                            for values in (previous_owners,owners)],
                owners=owner_delta(previous_owners, owners),
            )
        report["arms"] = arms
    print(trial.write(root/"score.json", report))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_mutually_exclusive_group()
    modes.add_argument("--score")
    modes.add_argument("--score-shrunk")
    args = cli.parse_args()
    if args.score_shrunk:
        score_shrunk(args.score_shrunk)
    elif args.score:
        score(args.score)
    else:
        check_control()
