"""Verify the ordinary DS30-0220 replay before scoring the masked challenge."""

import argparse
import json
from math import isfinite
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from three_quarter_members import ARMS, ROOT, checked, digest, read, write  # noqa: E402
from three_quarter_challenge import CASE, PANEL, PAIR_PIN  # noqa: E402


def complete_grid(grid):
    from leo.analysis.position_grid import sample_position_grid

    dimensions = ("box_width_km", "coarse_size", "local_size", "local_half_width_km")
    expected = sample_position_grid(lambda *_: 0., grid["endpoints"], clock=lambda: 0.,
                                    **{name: grid[name] for name in dimensions})
    def positions(document):
        return {(p["east_km"], p["north_km"]) for p in document["points"]}
    planned = len(positions(expected))
    if (not grid["complete"] or not grid["matched_c_grid"] or planned != grid["planned_points"]
            or planned != grid["evaluated_points"] or planned != len(grid["points"])
            or positions(grid) != positions(expected)
            or any(p["failures"] or set(p["scores"]) != set(ARMS) or not all(isfinite(v) for v in p["scores"].values())
                   for p in grid["points"])):
        raise ValueError("The paired grid did not evaluate every normally deduplicated configured location")
    return planned


def published(control, trial):
    from clean_saved_0169_trial import output_seal
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_0016_best_score import position_sides
    from tools.pipeline_eval.qualification.paired_publication import evidence

    if read(trial / "prediction-seal.json") != output_seal(trial):
        raise ValueError("The saved prediction changed before independent publication checks")
    worker = read(trial / "worker.json")
    receipt = worker["terminal"]
    if (receipt["region"] != control["evidence"]["receipt"]["region"] or worker["handoffs"] != 1
            or worker["waveform_reads"] or worker["survey_reads"]):
        raise ValueError("The original offer or single saved-only handoff changed")
    if receipt["decision"] != "complete":
        return dict(receipt=receipt, worker=worker, paid=None)
    target = trial / "candidate"
    store = FastStandardAnalysisStore(target)
    media = artifacts(target, receipt)
    position_sides(store, receipt, media, expected_points=None)
    grid = store.position_grid(receipt["run_id"])
    count = complete_grid(grid)
    paid = evidence(target, receipt, (trial / "admission.json").stat().st_mtime_ns, read_only=True)
    if paid["raw_authority"] != control["raw_identity"]["raw_authority_sha256"]:
        raise ValueError("The original raw authority changed across saved publication")
    return dict(receipt=receipt, grid_points=count, worker=worker, paid=paid)


def controls():
    field = PANEL / "cases" / CASE
    pair = read(field / "pair.json", PAIR_PIN)
    return {name: read(field / name / "attempt-000001/result.json", pin)
            for name, pin in pair["attempt_result_sha256"].items()}


def verify_ordinary(path, receipt):
    original = controls()["successor"]
    saved = published(original, path)
    prior = original["evidence"]
    paid = saved["paid"]
    parity = paid is not None and all(paid[k] == prior[k] for k in ("arms", "owners", "scientific_digests"))
    summary = dict(case=CASE, exact_scientific_control=parity, saved=saved["receipt"], grid_points=saved.get("grid_points"),
                   source_native=original["native_sha256"], saved_seal_sha256=digest(read(path / "prediction-seal.json")),
                   timings=saved["worker"]["analysis"], worker_clock=saved["worker"]["timing"])
    write(receipt, summary)
    if not parity:
        raise ValueError("The saved ordinary route must reproduce the verified original field science")
    return summary


def gate(installed, alternate, original_owners, retained_pairs):
    support = {}
    for arm in ARMS:
        retained = set(tuple(row[:2]) for row in retained_pairs[arm])
        original = set(tuple(row[:2]) for row in original_owners[arm])
        joined = retained & original
        support[arm] = dict(historical=len(original), actual=len(retained), common=len(joined),
                           satellites=len({row[1] for row in retained}), delta_km=alternate[arm]-installed[arm])
    passed = all(v["historical"] > 0 and v["delta_km"] <= .25 and 2*v["common"] >= v["historical"]
                 and v["satellites"] >= 2 for v in support.values())
    return passed, support


def final(ordinary, proof, sampled, output):
    from three_quarter_members import gates
    from three_quarter_challenge import DEVELOPMENT
    from three_quarter_readout import full_auth_model
    from tools.pipeline_eval.scoring import distance_km

    previous = read(proof)
    if not previous["exact_scientific_control"] or previous["saved_seal_sha256"] != digest(read(ordinary / "prediction-seal.json")):
        raise ValueError("Seal the verified ordinary saved control first")
    original = controls()
    alternate = published(original["successor"], sampled)
    if alternate["paid"] is None:
        write(output, dict(case=CASE, passes=False, decision=alternate["receipt"]["decision"], transfer="DS30-0144 unscored"))
        return
    ref = ROOT / "reports/2026_11_21_ds30_full/reference-audit.json"
    target, = (r["reference"] for r in json.loads(checked(ref, "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"))["cases"]
               if r["dataset_label"] == CASE and r["authority_eligible"] and r["sealed_metadata_digests_verified"])
    truth = [target["latitude_deg"], target["longitude_deg"]]
    arms = {mode: {arm: dict(error_km=distance_km(truth, row["latlon"]), rf_rms_hz=row["rf_rms_hz"])
                   for arm,row in evidence["arms"].items()}
            for mode,evidence in (("installed", original["installed"]["evidence"]),
                                  ("successor", original["successor"]["evidence"]), ("sampled", alternate["paid"]))}
    prior = read(ordinary / "worker.json")["result_evidence"]["owner_rows"]
    after = alternate["worker"]["result_evidence"]["owner_rows"]
    for groups, paid in ((prior, original["successor"]["evidence"]), (after, alternate["paid"])):
        if any(digest({row[0]:row[1] for row in groups[arm]}) != paid["owners"][arm] for arm in ARMS):
            raise ValueError("Owner receipt is inconsistent with the original scientific publication")
    passes, ownership = gate({a: r["error_km"] for a,r in arms["installed"].items()},
                             {a: r["error_km"] for a,r in arms["sampled"].items()}, prior, after)
    old, = previous["timings"]["solve"]
    new, = alternate["worker"]["analysis"]["solve"]
    delta = old["elapsed_s"] - new["elapsed_s"]
    cohort = read(DEVELOPMENT / "audit.json")
    rates = full_auth_model(cohort)
    bound = next(row for row in cohort["records"] if row["case"] == CASE)
    modeled = dict(full_original_authentication=rates["case_costs"][CASE]["without_solver"]-delta,
                   changed_omission_contract=bound["model"]["stage_scaled_no_solver_credit_s"]-delta)
    write(output, dict(case=CASE, passes=passes, transfer="DS30-0144 awaiting gate and frozen arms" if passes else "DS30-0144 unscored",
                       arms=arms, support=ownership,
                       grid=dict(ordinary=previous["grid_points"], sampled=alternate["grid_points"]),
                       saved_solve=dict(ordinary=old, sampled=new),
                       saved_worker=dict(ordinary=previous["worker_clock"], sampled=alternate["worker"]["timing"]),
                       modeled_raw_wall_s=modeled, installed_raw_wall_s=bound["installed_s"],
                       solver_credit_wall_s=delta, cohort_full_auth_model_gates=rates["gates"]))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_subparsers(dest="action", required=True)
    ordinary = modes.add_parser("verify-ordinary")
    ordinary.add_argument("ordinary", type=Path)
    ordinary.add_argument("proof", type=Path)
    score = modes.add_parser("score")
    for name in ("ordinary", "proof", "sampled", "output"):
        score.add_argument(name, type=Path)
    args = vars(cli.parse_args())
    {"verify-ordinary": lambda ordinary, proof: verify_ordinary(ordinary, proof), "score": final}[args.pop("action")](**args)
