"""Independently verify one sealed proposal publication against existing controls."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from graph_half_blend_trial import CASE, CONTROL, CONTROL_PINS, read, ready_runtime, sha, write  # noqa: E402
from sparse8_cfo_epoch_challenge import CROSSOVER, PARITY  # noqa: E402
from sparse8_cfo_epoch_trial import ARMS, geography  # noqa: E402


def runtime():
    base = ready_runtime()
    sys.path[:0] = [str(base.CHARTED/"reports/ALGO08/v3"), str(base.CHARTED)]
    import empty_bootstrap as boot

    boot.load_runtime()


def evidence(root, observed):
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_0016_best_score import position_sides

    receipt = observed["receipt"]
    run = receipt["run_id"]
    terminal = read(root/"fast-scan-automatic-work"/run/"terminal.json", receipt["terminal_sha256"])
    witness = read(root/"exact-named-raw-witness.json", observed["witness_sha256"])
    native, = root.glob("fast-scan-automatic-work/*/detections.json")
    if (sha(native)!=observed.get("native_sha256",observed.get("input"))
            or observed["handoffs"]!=1 or terminal["native_sha256"]!="sha256:"+sha(native)
            or set(terminal["arms"])!=set(ARMS)):
        raise ValueError("The original native bytes and two arms must bind the publication")
    media = artifacts(root,receipt)
    earned = witness["evidence"]
    if json.dumps(media["images"],sort_keys=True)!=json.dumps(earned["images"],sort_keys=True):
        raise ValueError("Published media differ from the original evidence witness")
    if receipt["decision"]=="withheld":
        if list(root.rglob("*.png")) or any(r["latlon"] is not None for r in terminal["arms"].values()):
            raise ValueError("A withhold has geometry or PNG products")
        return dict(terminal=terminal,witness=witness,media=media)
    store = FastStandardAnalysisStore(root)
    grid = store.position_grid(run)
    if (terminal["decision"]!="ok" or grid["evaluated_points"]!=179 or
            any(abs(v)>1e-5 for v in grid["endpoint_objective_replay"].values())):
        raise ValueError("Missing ordinary comprehensive fitted-position grid")
    for arm in ARMS:
        rows = earned["owner_rows"][arm]
        if (canonical_digest({oid:n for oid,n,_ in rows})!=earned["detail"]["arms"][arm]["owner_sha256"]
                or len({oid for oid,_,_ in rows})!=len(rows)):
            raise ValueError("Ordered original owner identities do not reproduce the signed digest")
    position = position_sides(store,receipt,media)
    return dict(terminal=terminal,witness=witness,media=media,position=position,
                grid={k:v for k,v in grid.items() if k!="elapsed_seconds"},
                path=store.position_path(run))


def compatible(left, right):
    def bound(witness):
        recipe = dict(witness["solver_recipe"])
        active = recipe.pop("history_risk")
        return recipe,{k:active[k] for k in ("requested","optional_prefit_exterior_probe")},witness["source_sha256"]

    if bound(left)!=bound(right):
        raise ValueError("The original charted solver configuration or source changed")


def score(root, pin):
    runtime()
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.scoring import distance_km

    caught = read(root/"prediction.json",pin)
    clock = read(root/"clock.json")
    audit = read(root/"proposal-trace.json",caught["trace_sha256"])
    if (clock["exit"] or caught["survey_reads"] or caught["waveform_reads"]
            or audit["cold_calls"]!=1 or audit["changes"]!=57 or not audit["raw_cold_models"]):
        raise ValueError("No verified independent raw-scored proposal")
    old = read(CONTROL/"observed.json",CONTROL_PINS["observed.json"])
    before = evidence(CONTROL/"publication",old)
    after = evidence(root/"publication",caught)
    compatible(before["witness"],after["witness"])
    cross = read(CROSSOVER/"final-evidence.json",PARITY)
    stock_path = CROSSOVER/"installed-installed"
    stock = read(stock_path/"crossover-worker.json",cross["owner_row_source_sha256"]["installed-installed"])
    sr = stock["receipt"]
    named = read(stock_path/"fast-scan-automatic-work"/sr["run_id"]/"terminal.json",sr["terminal_sha256"])
    candidate_risk = after["witness"]["ports"]["history_risk"]
    prior_risk = before["witness"]["ports"]["history_risk"]
    result = dict(
        case=CASE, prediction_sha256=pin, clock=clock,
        original_clock=read(CONTROL/"clock.json",CONTROL_PINS["clock.json"]),
        decision=caught["receipt"]["decision"], ranked_nominations=audit["ranked"],
        original_cold=prior_risk["lean_attempts"][0]["cold"],
        trial_cold=candidate_risk["lean_attempts"][0]["cold"],
        boundary_checks=candidate_risk.get("boundary_checks"),
    )
    if result["decision"]=="complete":
        site = geography(CASE)
        arms = {}
        for arm in ARMS:
            ordinary, proposed, comparison = (cell["arms"][arm] for cell in (
                before["terminal"],after["terminal"],named,
            ))
            companions = dict(sparse=ordinary, trial=proposed, installed=comparison)
            errors = {k:1000*distance_km(site,v["latlon"]) for k,v in companions.items()}
            archive_owners, trial_owners = (cell["witness"]["evidence"]["owner_rows"][arm]
                                             for cell in (before,after))
            arms[arm] = dict(
                error_m=errors, delta_m=errors["trial"]-errors["sparse"], endpoints=companions,
                owner_delta=owner_delta(archive_owners,trial_owners),
                all_owned_rf_hz={label: doc["witness"]["evidence"]["detail"]["arms"][arm]["residual_rms_hz"]
                                 for label,doc in (("sparse",before),("trial",after))},
            )
        result.update(arms=arms,position=after["position"],media=after["media"],
                      grid_equal=before["grid"]==after["grid"],path_equal=before["path"]==after["path"],
                      figures_equal=before["media"]["images"]==after["media"]["images"],
                      original_scientific_terminal_equal=before["terminal"]==after["terminal"])
    print(write(root/"score.json",result))


def verify_control():
    runtime()
    observed = read(CONTROL/"observed.json",CONTROL_PINS["observed.json"])
    verified = evidence(CONTROL/"publication",observed)
    if verified["witness"]["ports"]["history_risk"]["lean_attempts"][0]["decision"]!="complete":
        raise ValueError("Expected the existing lean accepted control")
    print(json.dumps(dict(images=len(verified["media"]["images"]),
                          owners={arm:len(rows) for arm,rows in
                                  verified["witness"]["evidence"]["owner_rows"].items()},
                          grid=verified["position"]["grid_points"],solver_calls=0)))


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("control","score"))
    parser.add_argument("root",type=Path,nargs="?")
    parser.add_argument("pin",nargs="?")
    args = parser.parse_args()
    if args.mode=="control":
        verify_control()
    elif args.root is None or not args.pin:
        parser.error("Require a candidate directory and prediction seal")
    else:
        score(args.root,args.pin)
