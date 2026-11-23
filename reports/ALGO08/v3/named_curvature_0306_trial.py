"""Qualify one authenticated named-curvature shortcut against the paid short pair."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
PRIOR = Path("/dev/shm/leo-v3-raw-band-pair-0306-result02")
SEAL = "821197fbfea8826da16a8538479b28f64b1b85381b16be847fbb8dbcd5117177"
WEAK = Path("/dev/shm/leo-cumulative-grid-projection-01/weak-pair/detections.json")
WEAK_PIN = "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"
FAR = dict(center=[-23.5, 121.], width_km=25.)
EMPTY_ARMS = {arm: {"latlon": None} for arm in ("c0", "fitted_c")}


def published(root, name):
    (path,) = (root / "fast-scan-automatic-work").glob("*/" + name)
    return path


def inventory():
    from empty_bootstrap import checked

    sealed = json.loads(checked(PRIOR / "prediction-seal.json", SEAL))

    def original(path):
        return json.loads(checked(path, sealed[str(path.relative_to(PRIOR))]))

    return original, original(PRIOR / "admission.json")


def saved(root):
    import empty_bootstrap as staged
    from aperture_trial import write
    from full_short_run import RECIPE_SHA
    from short_graph_guard import prove
    from unified_short_bootstrap import Handoff, publish_active

    original, assignment = inventory()
    _, spec, sources, publication, _ = staged.load_runtime()
    assets = staged.RELEASE / "assets"
    natives = {arm: original(published(PRIOR / arm, "detections.json")) for arm in ("stock", "candidate")}
    natives["positive_0016"] = json.loads(staged.checked(WEAK, WEAK_PIN))
    proofs = {key: prove(item, assets, use_time_support=True, use_curvature_extent=True)
              for key, item in natives.items()}
    extent = {key: item["curvature_extent"] for key, item in proofs.items()}
    if not all(extent[arm]["proven"] and not proofs[arm]["proven"] for arm in ("stock", "candidate")):
        raise ValueError("Expected the new curvature certificate on the original two 0306 packets")
    if extent["positive_0016"]["proven"] or extent["positive_0016"].get("largest_lane_span_s", 0) < 20:
        raise ValueError("The saved positive weak control must keep current routing")
    source = natives["candidate"]
    staged.bind_native(source, assignment["session"], assignment["inventory"], RECIPE_SHA,
                       expected=extent["candidate"]["native_sha256"])
    if (source["source"]["raw_recording_authority_digest"] != assignment["raw_authority"]
            or source["clock_anchor"]["before"]["realtime_ns"] != assignment["cutoff_utc_ns"]):
        raise ValueError("The original signed handoff changed")
    write(root / "far-offer.json", FAR)
    decisions = {}
    for label, region in (("original", PRIOR / "offer.json"), ("far", root / "far-offer.json")):
        args = SimpleNamespace(recording=Path(assignment["recording"]), archive=PRIOR / "tle", region=region,
                               output=root / ("saved-" + label), one_pass_web_png=True, exact_graph_reuse=True,
                               reuse_verified_png_reads=True, direct_residual_figures=True, direct_orbit_figures=True,
                               named_survivor_finish=True, grid_feature_projection_library=PRIOR / "projection.so",
                               geographic_library=PRIOR / "geographic.so", regional_track_library=PRIOR / "regional.so",
                               frontier_block_library=PRIOR / "block.so")
        handoff = Handoff(assignment["session"], assignment["inventory"], RECIPE_SHA, source)
        receipt, detail = publish_active(args, publication, spec, handoff, {}, graph_audit={}, png_read_audit={},
                                         no_active_curvature_sha256=extent["candidate"]["native_sha256"])
        decision = withhold(args.output, detail, receipt, assignment)
        if handoff.calls != 1:
            raise ValueError("Expected one saved handoff")
        decisions[label] = dict(result=decision, solve=detail["solve"], receipt=receipt,
                                early_regional=detail["early_regional"])
    if decisions["original"]["result"] != original(published(PRIOR / "candidate", "terminal.json")):
        raise ValueError("Candidate saved publication changed its original terminal")
    write(root / "saved.json", dict(proofs=proofs, decisions=decisions, waveform_reads=0))


def withhold(root, detail, receipt, assignment):
    from aperture_trial import read
    from joint_publication import artifacts

    terminal = read(published(root, "terminal.json"))
    (region,) = detail["early_regional"]
    if (terminal["arms"] != EMPTY_ARMS or terminal["reason"] != "no_active_curvature"
            or terminal["decision"] != "withheld" or terminal["orbit_policy"] != "stock"
            or terminal["session_id"] != assignment["session"] or receipt["window_count"] != assignment["issued"]
            or region["result"].get("reason") != "certified_named_no_active_curvature"
            or artifacts(root, receipt) != {"images": {}}):
        raise ValueError("Expected named no-curvature withholding and no artifacts")
    return terminal


def run(root, *, resume_saved=False):
    from aperture_trial import read, write
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE, checked
    from full_short_physical import CACHE_LIB, CACHE_SHA, environment
    from leo.storage.fast_scan import FastScanStore
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.cache_residency import bound_snapshot, load_query

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Require fresh tmpfs output")
    if resume_saved:
        if not (root / "saved.json").is_file() or any((root / name).exists() for name in ("raw", "before.json", "result.json")):
            raise ValueError("Recovery requires the completed saved controls and no raw attempt")
    else:
        root.mkdir()
        (root / "tmp").mkdir()
        (root / "fonts").mkdir()
        for file in (PRIOR / "fonts").glob("fontlist-*.json"):
            (root / "fonts" / file.name).write_bytes(file.read_bytes())
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    if not resume_saved:
        subprocess.run([RELEASE / "venv/bin/python", "-IB", __file__, "saved", root], env=env, check=True, timeout=35)
    original, assignment = inventory()
    previous = {arm: original(PRIOR / f"{arm}-clock.json") for arm in ("stock", "candidate")}
    command = list(previous["candidate"]["command"])
    for library, pin in assignment["library_sha256"].items():
        checked(PRIOR / (library + ".so"), pin)
    checked(PRIOR / "offer.json", assignment["offer_sha256"])
    command[2] = str(HERE / "unified_short_bootstrap.py")
    command[command.index("--output")+1] = str(root / "raw")
    command.append("--prove-no-active-curvature")
    recording = Path(assignment["recording"])
    store = FastScanStore(root)
    manifests = tuple((Path(row["path"]), row["sha256"]) for row in assignment["manifests"])
    checked(CACHE_LIB, CACHE_SHA)
    checker = load_query(CACHE_LIB)

    def cache():
        return bound_snapshot(store, recording, manifests, os.sysconf("SC_PAGE_SIZE"), checker)

    def fully_resident(row):
        return (not row["unavailable"] and row["observed_members"] == row["members"] == 7
                and row["cached_pages"] == row["observed_file_pages"] == 119934)

    before = cache()
    write(root / "before.json", before)
    result = dict(machine=machine, saved=read(root / "saved.json"), previous=previous,
                  cache_before=before, raw_admissible=fully_resident(before), command=command)
    if result["raw_admissible"]:
        timing = measure(command, env, root / "raw")
        after = cache()
        write(root / "raw-clock.json", dict(timing=timing, after=after))
        if timing["exit_code"]:
            raise ValueError(timing["stderr_tail"])
        joined = read(root / "raw/joint-research-receipt.json")
        provenance = read(root / "raw/unified-short-bootstrap.json")
        terminal = withhold(root / "raw", joined, provenance["receipt"], assignment)
        if (terminal != result["saved"]["decisions"]["original"]["result"]
                or provenance["raw_acquisitions"] != 1 or provenance["verified_handoffs"] != 1):
            raise ValueError("Complete raw replay changed the signed candidate result")
        result.update(raw=timing, cache_after=after, residency_matched=fully_resident(after),
                      phases=provenance["phases"], actual_terminal=terminal,
                      graph=provenance["exact_graph_reuse"], solve=joined["solve"],
                      regional=joined["early_regional"], graph_proof=provenance["graph_proof"])
    write(root / "result.json", result)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("saved", "run", "resume-saved"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.mode == "saved":
        saved(args.root)
    else:
        run(args.root, resume_saved=args.mode == "resume-saved")
