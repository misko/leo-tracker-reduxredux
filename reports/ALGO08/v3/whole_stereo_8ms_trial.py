"""Bound and score the saved 8 ms stereo-mask candidate without opening waveform inputs."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from preloaded_saved_worker import read, write
from whole_stereo_8ms import CASES, EIGHT_RAW, SAVED_PIN, SAVED_SEAL, plan


ARM_NAMES = ("c0", "fitted_c")
RECEIPT = "masked-native-8ms-publication.json"
PROTOCOL = HERE/"whole-stereo-8ms-protocol.md"
NORTH_12 = Path("/dev/shm/leo-live-stereo-north.BYuWvuyj/pair/result.json")
NORTH_12_SHA = "202c916b98a081780f50f94d95d7485b09f6c5e0317bffda3a16ac066b146c11"
WEAK_12 = Path("/dev/shm/leo-v3-whole-stereo-blocks-weak01/score.json")
WEAK_12_SHA = "fb4a679f1f02356f04a962ac488c9c733dac4fb7247bbd6fdb60170a3ff35944"
WEAK_SCORE = Path("/dev/shm/leo-v3-eight-ms-held-fit-result01/containing-score.json")
WEAK_SCORE_SHA = "b1de2fbfab109c35bc94f06bc61f67637037034a2a401b46709b241e8b6c5b28"
SOURCES = (Path(__file__), PROTOCOL, *(HERE/name for name in (
    "whole_stereo_8ms.py", "whole_stereo_blocks.py", "eight_ms_held_fit.py", "combined_raw_research.py",
    "unified_short_bootstrap.py", "raw_cfo_north_trial.py", "cumulative_grid_projection.py", "preloaded_saved_score.py")))


def pins():
    return {path.name: sha256(path.read_bytes()).hexdigest() for path in SOURCES}


def verified_plan(binding):
    from combined_raw_trial import source_at

    originals, current = binding["sources"], pins()
    entry = Path(__file__).name
    if {k:v for k,v in originals.items() if k != entry} != {k:v for k,v in current.items() if k != entry}:
        raise ValueError("A checked planner or scientific dependency changed after census")
    source_at(binding["commit"], entry, originals[entry])


def study_plan(root):
    from dense_geographic_trial import host
    from north_held_anchor_pair import tmpfs

    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Freeze the sources before examining any case outcomes")
    tmpfs(root.parent)
    root.mkdir()
    write(root/"binding.json", dict(host=host(), sources=pins(), order=CASES,
          commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()))
    for case in CASES:
        plan(case, root/case)


def worker(root, label):
    import empty_bootstrap as staged
    from combined_raw_research import combined_runtime, rank_status
    from combined_raw_trial import PRODUCER
    from continued_cfo_north_mirror import MIRROR, MIRROR_SHA
    from preloaded_saved_worker import enrolled
    from raw_cfo_north_trial import ORDER, PUBLICATION_FLAGS, publish_saved

    began = staged.now()
    case = "north" if label == "omitted" else label
    entry = read(root/case/"plan.json")
    binding = read(root/"binding.json")
    manifest = read(root/f"{label}-launch.json")
    verified_plan(binding)
    if (manifest["entry_sha256"] != pins()[Path(__file__).name]
            or manifest["plan_sha256"] != sha256((root/case/"plan.json").read_bytes()).hexdigest()):
        raise ValueError("The solver needs its frozen signed saved planner and current selected packet")
    orbit, rank = {}, {}
    with combined_runtime(orbit, rank, PRODUCER, use_blocks=True):
        runtime = staged.load_runtime()
        request, archive, offer, libraries, _, original, identity = enrolled(case)
        from anchor_exposure import bind

        original_identity = entry["identity"]
        shared = ("offer_sha256", "inventory", "issued", "cutoff_utc_ns", "session", "authority", "archive")
        if not all(identity[key] == original_identity[key] for key in shared):
            raise ValueError("The masked publication has a different signed input, causal archive or geographical offer")
        offer_pin = identity["offer_sha256"]
        if label == "omitted":
            if json.loads(staged.checked(MIRROR, MIRROR_SHA)) != request["mirror_offer"]:
                raise ValueError("The requested omitted control changed")
            offer, offer_pin = MIRROR, MIRROR_SHA
        witness = entry["masked_witness"]
        path = root/case/"detections.json"
        packet = json.loads(staged.checked(path, witness["native_sha256"][7:]))
        bind(original, packet)
        detector = witness["detector_recipe_sha256"]
        staged.bind_native(packet, request["session"], request["inventory"], detector[7:], expected=witness["native_sha256"])
        request = dict(request, archive={"root": str(archive)}, libraries=libraries,
                       offer_sha256={ORDER[1]: offer_pin}, receiver="masked-20-8-held-history")
        identity = dict(original_identity, original_offer=json.loads(staged.checked(offer, offer_pin)), offer_sha256=offer_pin,
                        native_sha256=witness["native_sha256"], detector=detector, selected=witness["selected"],
                        route=witness["choice"]["route"], flags=list(PUBLICATION_FLAGS))
        raw = dict(native_sha256=identity["native_sha256"], detector_recipe_sha256=detector)
        publish_saved(request, root/f"{label}-publication", offer, path, packet, raw,
                      started=began, runtime=runtime, receipt_name=RECEIPT)
    write(root/f"{label}-execution.json", dict(identity=identity, orbit=orbit, rank=rank, rank_status=rank_status(True, rank)))


def followup(north):
    if north["decision"] == "complete" and all(
            north["candidate"][arm]["error_m"] <= baseline[arm]["error_m"]
            for arm in ARM_NAMES for baseline in (north["controls"]["all8"], north["controls"]["named"])):
        return "omitted"
    return "weak"


def launch(root, label, *, next_case=followup):
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    binding = read(root/"binding.json")
    verified_plan(binding)
    if binding["host"] != host():
        raise ValueError("One original frozen worker and CPU assignment is required")
    if label != "north" and (not (root/"north-score.json").is_file() or label != next_case(read(root/"north-score.json"))):
        raise ValueError("The sealed North accuracy branch did not admit this follow-up")
    case = "north" if label == "omitted" else label
    census = root/case/"plan.json"
    if not read(census)["admit"]:
        raise ValueError("The case census does not justify a saved solve")
    (root/"fonts").mkdir(exist_ok=True)
    (root/"tmp").mkdir(exist_ok=True)
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    python = RELEASE/"venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=25)
    args = ["/usr/bin/timeout", "--kill-after=2s", "40s", python, "-IB", Path(__file__), "worker", root, label]
    write(root/f"{label}-launch.json", dict(plan_sha256=sha256(census.read_bytes()).hexdigest(),
                                           entry_sha256=pins()[Path(__file__).name],
                                           command=list(map(str,args))))
    clock = measure(args, env, root/f"{label}-publication")
    write(root/f"{label}-clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


def seal(root, label):
    from empty_bootstrap import checked
    from leo.contracts.algo08_region import Algo08Region
    from preloaded_saved_score import science
    from raw_cfo_north_trial import PUBLICATION_FLAGS, native_file
    from tools.pipeline_eval.qualification.paired_publication import evidence

    clock = read(root/f"{label}-clock.json")
    execution = read(root/f"{label}-execution.json")
    target = root/f"{label}-publication"
    saved = read(target/RECEIPT)
    receipt, identity = saved["receipt"], execution["identity"]
    verified = evidence(target, receipt, clock["started_unix_ns"], read_only=True)
    offered = Algo08Region.parse(identity["original_offer"]).document()
    if (clock["exit_code"] or saved["waveform_calls"] or saved["handoffs"] != 1 or not saved["staged_inventory"]
            or saved["native_sha256"] != identity["native_sha256"] or receipt["region"] != offered
            or verified["raw_authority"] != identity["authority"]):
        raise ValueError("Saved solver did not reproduce the expected raw bindings and one waveform-free handoff")
    checked(native_file(target), identity["native_sha256"][7:])
    case = "north" if label == "omitted" else label
    planned = read(root/case/"plan.json")["masked_witness"]
    if planned["native_sha256"] != identity["native_sha256"]:
        raise ValueError("The candidate provenance must bind the paid held choice")
    identity = dict(identity, route=planned["choice"]["route"], flags=list(PUBLICATION_FLAGS))
    execution = dict(execution, identity=identity)
    scientific = science(target, receipt, clock, identity) if receipt["decision"] == "complete" else None
    report = target/"joint-research-receipt.json"
    research = read(report) if report.is_file() else {}
    write(root/f"{label}-seal.json", dict(clock=clock, execution=execution, publication=saved, verified=verified,
              science=scientific, exterior=research.get("early_regional"), route=research.get("route_details")))


def score(root, label):
    from eight_ms_held_score import geographic_reference, owner_differences
    from eight_ms_native_score import outcome
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from whole_stereo_blocks import load_checked

    case = "north" if label == "omitted" else label
    frozen = load_checked(SAVED_SEAL, SAVED_PIN)["runs"][case]["history8"]
    verified = read(root/f"{label}-seal.json")
    truth, truth_pin = geographic_reference(case)
    receipt, ending = verified["publication"]["receipt"], verified["science"]
    candidate = outcome(verified["verified"]["arms"], receipt["region"], truth)
    whole = load_checked(HERE/"measurements/eight-ms-native-live.json.gz", EIGHT_RAW)
    if label == "omitted":
        controls = dict(all8=whole["omitted_score"]["score"], guarded12=whole["omitted_score"]["earlier"]["arms"])
    elif case == "north":
        old12 = load_checked(NORTH_12, NORTH_12_SHA)
        if old12["mask"]["schedule_sha256"] != read(root/case/"plan.json")["schedule"]["schedule_sha256"]:
            raise ValueError("The separate 20/12 ms result must share the original signed opportunities and mask phase")
        mask12 = old12["runs"]["masked"]
        same_case = whole["position_score"]["outcomes"]
        controls = dict(all8=same_case["live_8ms"], named=same_case["installed_v3"],
                        masked12=mask12["arms"], masked12_full_raw_clock=mask12["through_exit"])
    else:
        mask12 = load_checked(WEAK_12, WEAK_12_SHA)
        controls = dict(all8=outcome(frozen["science"]["arms"], receipt["region"], truth),
                        named=outcome(mask12["value"]["named_v3"], receipt["region"], truth),
                        masked12=mask12["value"]["masked"], masked12_saved_clock=mask12["reported_clock"],
                        all8_saved_clock=load_checked(WEAK_SCORE, WEAK_SCORE_SHA)["cases"]["weak"]["results"]["history8"])
    owner_changes = {arm: owner_differences(frozen["science"]["roles"][arm], ending["roles"][arm])
                     for arm in ARM_NAMES} if ending is not None else None
    write(root/f"{label}-score.json", dict(case=case, label=label, candidate=candidate, decision=receipt["decision"],
                controls=controls, clock=verified["clock"], owner_changes_vs_all8=owner_changes,
                reference_source_sha256=truth_pin, truth_clearance_km=face_clearance_km(receipt["region"], truth)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "launch", "worker", "seal", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("label", nargs="?", choices=(*CASES, "omitted"))
    arguments = parser.parse_args()
    if arguments.action == "plan":
        study_plan(arguments.root)
    elif arguments.label is None:
        parser.error("This action requires its frozen case label")
    else:
        dict(launch=launch, worker=worker, seal=seal, score=score)[arguments.action](arguments.root, arguments.label)
