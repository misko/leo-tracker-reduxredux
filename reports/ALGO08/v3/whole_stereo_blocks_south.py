"""Transfer the fixed saved stereo mask to both original South offers."""

import argparse
from hashlib import sha256
from pathlib import Path

from whole_stereo_blocks import exposure, load_checked, project, schedule
from whole_stereo_blocks_trial import ARMS, PROJECTION_SOURCE_SHA, seal


HERE = Path(__file__).resolve().parent
BENCH = Path("/tmp/leo-algo08v2-2x-bench")
SOURCE = Path("/dev/shm/leo-past-anchor-held-south")
SOURCE_SHA = "a10693d167757124a036cfcd63e90966760e52b755f4bb834605ccaf74426d2e"
REQUESTS = Path("/dev/shm/leo-v3-named-south-transfer-01")
NAMED = {"containing": (BENCH/"exact-curved-lookahead-south-inside/pair.json", "48fed3c62639ef81fb99e4b76921bcacd999e769a78ebb607b2b886b6f0951f0"),
         "near-omitted": (BENCH/"exact-curved-lookahead-south-offers.json", "5181abf1c8a36d45dfe140e8851f0a423b69ec69b8ca231a3f87bcc9fdcecca9")}
MODES = {
    "containing": ("e3ba4f9153eb1cc2348666aea2a9b3afdb98c8b3ac8e792413063d98ed5830fd", Path("/var/tmp/leo-short-graph-20261123-south-inside"),
                   "5d7b28ab3ce6dd3f06e09153481eb125dfad45a11486cc863fdd2fd2e018ce64"),
    "near-omitted": ("3ac64915a3fe5d5115ce0428ed0b133e00343bae45d0321acff804f62626c1b7", Path("/var/tmp/leo-regional-track.O238AD0C/south-near"),
                     "df45f0df4baec45322d790ec8971fdd40d298fda15fa19be3b60b3c92b8a5c40"),
}
PROJECTION = Path("/dev/shm/leo-cumulative-grid-projection-01/projection.so")
KEY = HERE.parent/"regional-release/scoring-key.json"
KEY_SHA = "0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def historic(mode):
    _, root, pin = MODES[mode]
    return root, load_checked(root/"joint-research-receipt.json", pin)


def geographic_result(clearance_km, decision):
    if clearance_km >= 0:
        return "valid_fix" if decision == "complete" else "false_withhold"
    return "false_fix" if decision == "complete" else "valid_withhold"


def run(root):
    from aperture_trial import RELEASE, archive_identity, read, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from grid_feature_projection import LIBRARY_SHA
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_json_bytes
    from prospective_0316_solver import LIBRARIES
    from short_raw_diagnostic import measure

    if not root.parent.resolve(strict=True).is_relative_to(Path("/dev/shm")):
        raise ValueError("Require a fresh saved-only tmpfs destination")
    packet_path, = SOURCE.glob("fast-scan-automatic-work/*/detections.json")
    native = load_checked(packet_path, SOURCE_SHA)
    masked, plan = project(native, schedule(native))
    targets = {}
    pins = {HERE/"grid_feature_projection.c": PROJECTION_SOURCE_SHA, PROJECTION: LIBRARY_SHA}
    staged_archive = None
    for mode, (request_pin, _, _) in MODES.items():
        original = load_checked(REQUESTS/f"{mode}-request.json", request_pin)
        _, control = historic(mode)
        inventory, offer = Path(original["saved_inventory"]), Path(original["region"])
        pins.update({inventory: original["inventory"][7:], offer: original["offer_sha256"]})
        offer_value = Algo08Region.parse(load_checked(offer, original["offer_sha256"])).document()
        source = native["source"]
        if (control["saved_digest"] != "sha256:"+SOURCE_SHA or control["receipt"]["region"] != offer_value
                or control["receipt"]["session_id"] != original["session"] or source["session_id"] != original["session"]
                or source["raw_recording_authority_digest"] != original["authority"]
                or source["input_manifest_sha256"] != original["inventory"]
                or native["clock_anchor"]["before"]["realtime_ns"] != original["cutoff_utc_ns"]):
            raise ValueError("Historical mixed, named and planned South inputs differ")
        if staged_archive is None:
            staged_archive = archive_identity(Path(original["archive"]["root"]))
        if staged_archive != original["archive"]:
            raise ValueError("Original South causal archive changed")
        pins.update({Path(path): LIBRARIES[key][1] for key,path in original["libraries"].items()})
        targets[mode] = dict(original, packet=str(root/"candidate-detections.json"), native=plan["native_sha256"],
                             receiver="whole-stereo-blocks", detector=plan["detector_sha256"], recipe=plan["recipe"],
                             projection=str(PROJECTION))
    if any(digest(path) != expected for path,expected in pins.items()):
        raise ValueError("A predeclared South input pin differs")
    root.mkdir()
    (root/"candidate-detections.json").write_bytes(canonical_json_bytes(masked))
    write(root/"plan.json", dict(plan=plan, native_sha256=SOURCE_SHA,
                                 archive=staged_archive, inputs={str(p):v for p,v in pins.items()}, host=host(),
                                 protocol_sha256=digest(HERE/"whole-stereo-blocks-south-protocol.md"),
                                 receiver_history=exposure(native, masked, set(plan["skipped_visits"]))))
    for mode, request in targets.items():
        stage = root/mode
        stage.mkdir()
        job = stage/"request.json"
        write(job, request)
        command = [RELEASE/"venv/bin/python", "-IB", HERE/"whole_stereo_blocks_trial.py", "worker", job, stage/"candidate"]
        write(stage/"launch.json", dict(command=list(map(str,command)), request_sha256=digest(job)))
    for mode in MODES:
        stage = root/mode
        result = measure(read(stage/"launch.json")["command"], environment(stage), stage/"candidate")
        write(stage/"clock.json", result)
        if result["exit_code"]:
            raise ValueError(result["stderr_tail"])
        seal(stage)


def score(root):
    from aperture_trial import read, write
    from leo.contracts.digests import canonical_digest
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    sealed = {mode: read(root/mode/"sealed.json") for mode in MODES}
    if len({case["native_sha256"] for case in sealed.values()}) != 1:
        raise ValueError("The predeclared South offers must share one masked packet")
    (truth,) = {tuple(row["truth"]) for row in load_checked(KEY, KEY_SHA)["answers"].values()
                if row["recording"] == "6bd1f26bfa0bedfcf3f100f8"}
    rows = {}
    for mode, trial in sealed.items():
        full_root, control = historic(mode)
        full_run = control["receipt"]
        full = read(full_root/"fast-scan-automatic-work"/full_run["run_id"]/"terminal.json")
        if (full_run["terminal_sha256"] != canonical_digest(full) or full["native_sha256"] != "sha256:"+SOURCE_SHA
                or full["region"] != trial["terminal"]["region"]):
            raise ValueError("Historical full mixed control differs from its frozen native and offer")
        named = load_checked(*NAMED[mode])
        if mode == "containing":
            baseline = named["runs"]["baseline"]
            stock = dict(region=baseline["receipt"]["region"], decision=baseline["receipt"]["decision"], arms=baseline["arms"])
        else:
            baseline = named["results"]["south-mirror-outside"]
            stock = dict(region=baseline["offer"], decision=baseline["status"], arms=baseline["arms"])
        if stock["region"] != full["region"]:
            raise ValueError("Named v3 and full mixed use different South offers")
        truth_clearance = face_clearance_km(full["region"], truth)
        values = {}
        for label, terminal in (("named", stock), ("full_mixed",full), ("masked",trial["terminal"])):
            values[label] = {"decision": terminal["decision"], "arms": {
                arm: dict(row, error_km=distance_km(row["latlon"], truth),
                          estimated_clearance_km=face_clearance_km(full["region"],row["latlon"]) if row["latlon"] else None)
                for arm,row in terminal["arms"].items()}}
        rows[mode] = dict(truth_clearance_km=truth_clearance, positions=values,
                          geographic=geographic_result(truth_clearance, trial["science"]["receipt"]["decision"]),
                          full_grid_points=control["solve"]["grid_points"],
                          full_route=control["route_details"], full_graph=control["early_regional"],
                          full_solve_clock=control["solve"],
                          owners={arm:owner_delta(control["selected_rows"].get(arm,[]),trial["selected_rows"].get(arm,[])) for arm in ARMS})
    write(root/"score.json", dict(cases=rows, reference_sha256=KEY_SHA, sealed={mode:digest(root/mode/"sealed.json") for mode in MODES}))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("run", "score"))
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    {"run":run,"score":score}[args.action](args.output)
