"""Run one waveform-free saved per-antenna publication under the frozen North offer."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from preloaded_saved_worker import read, write


MASKED = Path("/dev/shm/leo-v3-whole-stereo-8ms-result01")
LIVE = Path("/dev/shm/leo-v3-eight-ms-native-north02")
PLAN = "e3a01bf26754d440b4f6d87a4aae67d09ef6e6571d4c6b08372b88b8e259696e"
MASKED_SEAL = "fa7d80832b84dae48038f544f01136cc966a30f94b478f417eb4db918bffb18b"
MASKED_SCORE = "b15c39283b2e25e011111f1fcb4360b71cdc562070401a0641bc9bfa2a729cbd"
LIVE_SEAL = "74f85ba14d14e085ea0832933acd3ad1fed001d6b0d698d2c05b52a39a77a849"
RECEIPT = "per-antenna-publication.json"
ARMS = ("c0", "fitted_c")


def parity(root):
    from eight_ms_held_fit import source8
    from empty_bootstrap import checked, clock, now
    from leo.contracts.digests import canonical_json_bytes
    from radio_held_8ms import select
    from whole_stereo_8ms import SAVED_PIN, SAVED_SEAL

    start = now()
    original = json.loads(checked(SAVED_SEAL, SAVED_PIN))["runs"]
    controls = {}
    for case, expected_route in (("weak", "unfiltered"), ("north", "history")):
        packet, selection = select(*source8(case))
        archived = original[case]["history8"]
        witness = archived["selector"]
        prior = checked(Path(archived["detector"]), witness["native_sha256"][7:])
        if (canonical_json_bytes(packet) != prior
                or selection["receiver_recipe"] != witness["receiver_recipe"]
                or selection["detector_recipe_sha256"] != witness["detector_recipe_sha256"]
                or set(selection["routes"].values()) != {expected_route}):
            raise ValueError(f"Same-sign byte parity failed for the original {case} control")
        controls[case] = selection
    write(root/"parity.json", dict(controls=controls, clock=clock(start), archive_sha256=SAVED_PIN))


def packet_for_north(root):
    from eight_ms_held_fit import source8
    from empty_bootstrap import checked, clock, now
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import immutable_json
    from radio_held_8ms import select
    from whole_stereo_8ms import input_stream

    start = now()
    plan = json.loads(checked(MASKED/"north/plan.json", PLAN))
    original, recipe = source8("north")
    masked, masked_recipe, schedule = input_stream(original, recipe)
    prior = plan["masked_witness"]
    if (not plan["admit"] or canonical_digest(original) != "sha256:"+plan["original_sha256"]
            or schedule != plan["schedule"] or canonical_digest(masked) != prior["parent_native_sha256"]
            or canonical_digest(masked_recipe) != prior["parent_detector_sha256"]):
        raise ValueError("Original scheduled North packet differs from the frozen mask")
    packed = clock(start)
    packet, selected = select(masked, masked_recipe)
    if (selected["choice"] != {**prior["choice"],
                               "log_score_gain_by_radio": {int(k): v for k, v in prior["choice"]["log_score_gain_by_radio"].items()}}
            or selected["global_native_sha256"] != prior["native_sha256"]
            or selected["global_detector_sha256"] != prior["detector_recipe_sha256"]
            or len(set(selected["routes"].values())) != 2):
        raise ValueError("Original masked global choice diverged from its archived witness")
    path = root/"detections.json"
    immutable_json(path, packet)
    checked(path, selected["native_sha256"][7:])
    write(root/"selection.json", dict(selection=selected, plan_sha256=PLAN, schedule=schedule,
                                     input_and_mask=packed, through_sign=clock(start)))
    return plan, path, packet, selected


def worker(root):
    import empty_bootstrap as staged
    from combined_raw_research import combined_runtime, rank_status
    from combined_raw_trial import PRODUCER
    from preloaded_saved_worker import enrolled
    from raw_cfo_north_trial import ORDER, publish_saved

    began = staged.now()
    if set(read(root/"parity.json")["controls"]) != {"weak", "north"}:
        raise ValueError("Both pre-fit byte parity checks are required")
    orbit, rank = {}, {}
    with combined_runtime(orbit, rank, PRODUCER, use_blocks=True):
        runtime = staged.load_runtime()
        plan, path, packet, selected = packet_for_north(root)
        request, archive, offer, libraries, _, original, identity = enrolled("north")
        from anchor_exposure import bind

        shared = ("offer_sha256", "inventory", "issued", "cutoff_utc_ns", "session", "authority", "archive")
        if any(identity[key] != plan["identity"][key] for key in shared):
            raise ValueError("The solver needs the identical original North offer, cutoff and authority")
        bind(original, packet)
        detector = selected["detector_recipe_sha256"]
        staged.bind_native(packet, request["session"], request["inventory"], detector[7:], expected=selected["native_sha256"])
        request = dict(request, archive={"root": str(archive)}, libraries=libraries,
                       offer_sha256={ORDER[1]: identity["offer_sha256"]}, receiver="per-antenna-20-8-held-history")
        identity = dict(identity, native_sha256=selected["native_sha256"], detector=detector,
                        route=selected["routes"], selected=selected["selected"])
        raw = dict(native_sha256=selected["native_sha256"], detector_recipe_sha256=detector)
        publish_saved(request, root/"publication", offer, path, packet, raw,
                      started=began, runtime=runtime, receipt_name=RECEIPT)
    write(root/"execution.json", dict(identity=identity, orbit=orbit, rank=rank, rank_status=rank_status(True, rank)))


def launch(root):
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from full_short_physical import environment
    from north_held_anchor_pair import tmpfs
    from short_raw_diagnostic import measure

    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Freeze the implementation before launching")
    tmpfs(root.parent)
    root.mkdir()
    (root/"fonts").mkdir()
    (root/"tmp").mkdir()
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    python = RELEASE/"venv/bin/python"
    child = [python, "-IB", Path(__file__)]
    parity_clock = measure([*child, "parity", root], env, root/"parity-process")
    write(root/"parity-clock.json", parity_clock)
    if parity_clock["exit_code"]:
        raise RuntimeError(parity_clock["stderr_tail"])
    fonts_clock = measure([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                          env, root/"font-process")
    write(root/"font-clock.json", fonts_clock)
    if fonts_clock["exit_code"]:
        raise RuntimeError(fonts_clock["stderr_tail"])
    command = ["/usr/bin/timeout", "--kill-after=2s", "40s", *child, "worker", root]
    write(root/"launch.json", dict(command=list(map(str, command)), host=host(), plan_sha256=PLAN,
                                  commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
                                  source_sha256={name: sha256((HERE/name).read_bytes()).hexdigest() for name in (
                                      "per-antenna-held-8ms-protocol.md", "radio_held_8ms.py", "radio_held_8ms_trial.py")}))
    clock = measure(command, env, root/"publication")
    write(root/"clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


def seal(root):
    from empty_bootstrap import checked
    from leo.contracts.algo08_region import Algo08Region
    from preloaded_saved_score import science
    from raw_cfo_north_trial import native_file
    from tools.pipeline_eval.qualification.paired_publication import evidence

    clock, execution = read(root/"clock.json"), read(root/"execution.json")
    target = root/"publication"
    publication, identity = read(target/RECEIPT), execution["identity"]
    receipt = publication["receipt"]
    checked(native_file(target), identity["native_sha256"][7:])
    verified = evidence(target, receipt, clock["started_unix_ns"], read_only=True)
    if (clock["exit_code"] or publication["waveform_calls"] or publication["handoffs"] != 1
            or not publication["staged_inventory"] or publication["native_sha256"] != identity["native_sha256"]
            or publication["detector_recipe_sha256"] != identity["detector"]
            or receipt["region"] != Algo08Region.parse(identity["original_offer"]).document()
            or verified["raw_authority"] != identity["authority"]):
        raise ValueError("Saved solver did not reproduce the required signed boundaries and single handoff")
    scientific = science(target, receipt, clock, identity) if receipt["decision"] == "complete" else None
    trace_path = target/"joint-research-receipt.json"
    trace = read(trace_path) if trace_path.is_file() else {}
    write(root/"seal.json", dict(clock=clock, execution=execution, publication=publication, verified=verified,
                                science=scientific, exterior=trace.get("early_regional"), route=trace.get("route_details"),
                                selection_sha256=sha256((root/"selection.json").read_bytes()).hexdigest()))


def score(root):
    from eight_ms_held_score import geographic_reference, owner_differences
    from eight_ms_native_score import outcome
    from empty_bootstrap import checked
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km

    sealed = read(root/"seal.json")
    masked = json.loads(checked(MASKED/"north-seal.json", MASKED_SEAL))
    live = json.loads(checked(LIVE/"science-seal.json", LIVE_SEAL))
    old_score = json.loads(checked(MASKED/"north-score.json", MASKED_SCORE))
    truth, pin = geographic_reference("north")
    receipt = sealed["publication"]["receipt"]
    region = receipt["region"]
    shared = ("inventory", "issued", "cutoff_utc_ns", "session", "authority", "offer_sha256", "archive")
    identity = sealed["execution"]["identity"]
    for control in (masked["science"], live["science"]):
        if any(identity[key] != control["identity"][key] for key in shared):
            raise ValueError("Geographic comparator is outside the frozen original request")
    candidate = outcome(sealed["verified"]["arms"], region, truth)
    controls = dict(masked=old_score["candidate"], all8=old_score["controls"]["all8"], named=old_score["controls"]["named"])
    owner_changes = {}
    if sealed["science"] is not None:
        for mode, reference in (("masked", masked["science"]), ("all8", live["science"])):
            owner_changes[mode] = {arm: owner_differences(reference["roles"][arm], sealed["science"]["roles"][arm])
                                   for arm in ARMS}
    errors = {mode: {arm: candidate[arm]["error_m"] - control[arm]["error_m"]
                     for arm in ARMS if candidate[arm] is not None}
              for mode, control in controls.items()}
    write(root/"score.json", dict(candidate=candidate, controls=controls, owner_changes=owner_changes, delta_error_m=errors,
                                 decision=receipt["decision"], truth_source_sha256=pin,
                                 truth_face_km=face_clearance_km(region, truth), clock=sealed["clock"],
                                 comparator_clocks=dict(masked_saved=masked["clock"], all8_raw=live["clock"],
                                                        named_raw=live["historical"]["named"]),
                                 named_plus_250m=(set(errors["named"]) == set(ARMS)
                                                  and all(error <= 250.0 for error in errors["named"].values()))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "parity", "worker", "seal", "score"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.action == "parity":
        from empty_bootstrap import load_runtime

        load_runtime()
    {"launch": launch, "parity": parity, "worker": worker, "seal": seal, "score": score}[args.action](args.root)
