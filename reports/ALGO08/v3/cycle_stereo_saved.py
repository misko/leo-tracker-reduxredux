"""Run the frozen complete-donor-cycle packets through the verified saved solver."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import process_time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from preloaded_saved_worker import read, write


STAGE = Path("/dev/shm/leo-cycle-stereo-own01")
PLAN = {"north": "cdd3a47093683cdb936a2705eb7d2203dd401ee4aae7556e701bf364b53d03fa",
        "weak": "3ab42b72b95e7307d97b34d00a7409e99781770accd881f30eead41268c64908"}
NATIVE = {"north": "3d164600a3af30e060029be98af0556e1e79d5b6bef0828f0e2dc6e50e31c77e",
          "weak": "21f709df2d0c16b65d24e6a1e516f42b7518b0b1d449ee2544b6edbe238ccbb2"}
SCHEDULER_SHA = "85dd274dc76fb3a5ff45295b9faf2b23d3dc4b57fc63ce43a9cc3b5f590314a4"
PROTOCOL_SHA = "ddaef15bed86f737b1492eb267f38a25cff1b44a72b27655c07a2bcb91f35d4c"
INDIVIDUAL_SHA = "a24df0281cb7c6f77d5f94ed510ccca6d3eddac3455d26c3269db41c98c113f6"
ARMS = ("c0", "fitted_c")
MAX_EXTRA_M = 250


def eligible(result):
    if result["decision"] != "complete":
        return False
    candidate, controls = result["candidate"], result["controls"]
    return all(candidate[arm]["error_m"] < controls["individual"][arm]["error_m"]
               and candidate[arm]["error_m"] <= controls["named"][arm]["error_m"] + MAX_EXTRA_M for arm in ARMS)


def enrolled(case):
    from anchor_exposure import PINS, bind, packet
    from anchor_holds import history_rows
    from continued_cfo_trial import rebinding
    from cycle_stereo import project
    from eight_ms_held_fit import RECEIVER_RECIPE_PINS
    from empty_bootstrap import checked
    from leo.contracts.digests import canonical_digest

    home = STAGE/case
    expected = {"plan.json": PLAN[case], "detections.json": NATIVE[case]}
    files = {name: checked(home/name, pin) for name, pin in expected.items()}
    plan, native = (json.loads(files[name]) for name in expected)
    source, pin = PINS["DS30-0016" if case == "weak" else case]["8ms"]
    original = packet(source, pin)
    recipe = json.loads(checked(Path(source)/"full-short-recipe.json", RECEIVER_RECIPE_PINS[case]))["recipe"]
    paid, stage_recipe, schedule = project(original, recipe)
    witness, all_visits = plan["masked_witness"], plan["full_witness"]
    route = witness["choice"]["route"]
    rows = paid["source"]["probes"]
    selected = history_rows(rows) if route == "history" else rows
    final_recipe = witness["receiver_recipe"]
    if (plan["case"] != case or not plan["admit"] or plan["cost"]["modeled_incremental_after_planning_cpu_s"] <= 0
            or plan["original_sha256"] != pin or schedule != plan["schedule"]
            or route not in ("history", "unfiltered") or route != all_visits["choice"]["route"]
            or all_visits["native_sha256"] != plan["identity"]["native_sha256"]
            or witness["parent_native_sha256"] != canonical_digest(paid)
            or witness["parent_detector_sha256"] != canonical_digest(stage_recipe)
            or {k:v for k,v in final_recipe.items() if k != "held_native_8ms"} != stage_recipe
            or witness["detector_recipe_sha256"] != canonical_digest(final_recipe) or witness["refinement_calls"]
            or witness["native_sha256"] != "sha256:"+NATIVE[case]
            or native != rebinding(paid, selected, final_recipe)):
        raise ValueError("The sealed native packet must be the exact planned whole-cycle selection")
    bind(original, native)
    return files, dict(**expected, schedule_sha256=canonical_digest(schedule), original_sha256=pin)


def stage(root):
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from north_held_anchor_pair import tmpfs
    from whole_stereo_8ms_trial import pins

    tmpfs(root.parent)
    checked(HERE/"cycle_stereo.py", SCHEDULER_SHA)
    checked(HERE/"cycle-stereo-protocol.md", PROTOCOL_SHA)
    start = process_time()
    cases = {case: enrolled(case) for case in PLAN}
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("The candidate and measurement entry must be committed")
    root.mkdir()
    for case, (files, _) in cases.items():
        directory = root/case
        directory.mkdir()
        for name, data in files.items():
            with (directory/name).open("xb") as stream:
                stream.write(data)
    write(root/"binding.json", dict(host=host(), sources=pins(), cases={case: audit for case, (_, audit) in cases.items()},
          commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
          stage_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), verification_cpu_s=process_time()-start,
          protocol_sha256=PROTOCOL_SHA))


def run(root, case):
    from empty_bootstrap import checked
    from whole_stereo_8ms_trial import launch

    if read(root/"binding.json")["stage_source_sha256"] != sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("The prespecified saved admission source changed")
    for name, pin in (("plan.json", PLAN[case]), ("detections.json", NATIVE[case])):
        checked(root/case/name, pin)
    launch(root, case, next_case=lambda north: "weak" if eligible(north) else None)


def score(root, case):
    from eight_ms_held_score import geographic_reference, owner_differences
    from eight_ms_native_score import outcome
    from tools.pipeline_eval.scoring import distance_km
    from whole_stereo_8ms_trial import seal
    from whole_stereo_blocks import load_checked
    from whole_stereo_8ms import SAVED_PIN, SAVED_SEAL

    seal(root, case)
    result = read(root/f"{case}-seal.json")
    earlier = load_checked(HERE/"measurements/whole-stereo-8ms.json.gz", INDIVIDUAL_SHA)
    full = load_checked(SAVED_SEAL, SAVED_PIN)["runs"][case]["history8"]["science"]
    truth, truth_pin = geographic_reference(case)
    decision = result["publication"]["receipt"]["decision"]
    offer = result["publication"]["receipt"]["region"]
    candidate = outcome(result["verified"]["arms"], offer, truth)
    comparison = earlier["scores"][case]
    controls = {k: comparison["controls"][k] for k in ("all8", "named")}
    controls["individual"] = comparison["candidate"]
    science, mask = result["science"], earlier["publications"][case]["science"]
    ownership = ({name: {arm: owner_differences(old["roles"][arm], science["roles"][arm]) for arm in ARMS}
                  for name, old in (("individual", mask), ("all8", full))} if science else None)
    endpoint_shift_named = {arm: 1000*distance_km(candidate[arm]["latlon"],
                            controls["named"][arm].get("latlon", controls["named"][arm].get("position")))
                            for arm in ARMS if candidate[arm]}
    plan = read(root/case/"plan.json")
    data = dict(case=case, decision=decision, candidate=candidate, controls=controls, role_changes=ownership,
                solver_status=result["execution"]["rank_status"], named_endpoint_shift_m=endpoint_shift_named,
                clock=result["clock"], planner_cpu_s=plan["cost"]["planner_cpu_s"], scoring_reference_sha256=truth_pin,
                individual_receipt_sha256=INDIVIDUAL_SHA)
    if case == "north":
        data["admit_weak"] = eligible(data)
    write(root/f"{case}-score.json", data)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("stage", "run", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("case", nargs="?", choices=PLAN)
    args = cli.parse_args()
    if args.action == "stage":
        stage(args.root)
    elif args.case is None:
        cli.error("The measured action requires a staged case")
    else:
        (run if args.action == "run" else score)(args.root, args.case)
