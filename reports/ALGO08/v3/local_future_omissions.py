"""Replay the pinned local-future repair and a matched control on public offers."""

import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import perf_counter, process_time
from types import SimpleNamespace

from aperture_trial import RELEASE, archive_identity, read, write
from dense_full_short_raw import usage
from dense_geographic_trial import host
from full_short_physical import environment


HERE = Path(__file__).resolve().parent
NORTH = Path("/var/tmp/leo-north-short-regional-nov23")
NORTH_PRIOR = Path("/var/tmp/leo-north-short-causal-raw-nov23")
SOUTH = Path("/var/tmp/leo-full-short-south-transfer-final")
SOUTH_PRIOR = Path("/var/tmp/leo-regional-track.O238AD0C")
DONOR_ROOT = Path("/var/tmp/leo-local-future-repair.DqnORtL8/replay")
PROTOCOL = "local-future-omissions-protocol.md"
PRIOR = {
    "north-near": (NORTH_PRIOR / "north-mirror-outside", "21bffd79b4af8cd2dc277911f4b6b3eb4ad2dc29a1a6aaee67d10cf61dc3c012"),
    "south-near": (SOUTH_PRIOR / "south-near", "f70e582d012cda0599bfd67652288d219da99a36f5b39fbac3f7303e8db7418f"),
    "north-far": (NORTH_PRIOR / "north-far", "5591721667b573b9bb97fc9e56b750e6cf4c14a559bface6b70e512459bbc48b"),
    "south-far": (SOUTH_PRIOR / "south-far", "b216acbe50f61e516cc0e8d7e5362a8e45bbcbc74d5f9cd6a924a51602bac1d9"),
    "north-containing": (NORTH_PRIOR / "containing", "9a02ae260474be04d98e963a9b6c4ac56ea24651cd02c7445bc67684323e9337"),
    "south-containing": (Path("/var/tmp/leo-causal-weak-south-nov23/south-inside"),
                         "c21cbfe4060402e8ee2d27bec41503c8cd7d0bc37d6040c5f9764af5b8c16fba"),
}
OFFERS = {
    "north-near": (NORTH / "north-mirror-outside-offer.json", "eacc9fd6b5da3e9e38a7b13edee43aad63e229622c9973aa401a2dbb8c7f20d7"),
    "south-near": (SOUTH / "near-offer.json", "0c89bd52594b706b2772fbcf6ea627065eeb3d94eb6266f35de09ebb6b7a5d2a"),
    "north-far": (NORTH / "north-far-offer.json", "6b48044ea39e5a32611da86c0aebe3efb922d072773456da3d9d75de9b687ed4"),
    "south-far": (SOUTH / "far-offer.json", "a5127d5844ca98f58a157ec2b6b962f60ec2894c58b8122a0ee244b248a5eb62"),
    "north-containing": (None, "f4ff743e9f3d00bc18344143bffaaf7801276018dbd75b6ab2ec5207e887e891"),
    "south-containing": (None, "471704a6dfcfd4acdb72f3aacae638fe8f6ae6a796b01dd59cfd3d7a9d92610c"),
}
FROZEN = {
    "local_future_repair_trial.py": "873612d549e1deef09fd6561cce0b8c79e791dcdda1138eb5eaf382d1ec47cc0",
    "local_future_inputs.py": "6283ef3c7643276cf83703209f73bf9e5c2a2b39f4bd41ed4812e11a081c22c4",
    "local_future_repair.py": "2c22d0badf4431e8ef7f914d1b65d80bfd96344dc8b9b52ed0c9687ee8150fbe",
    "local-future-repair-protocol.md": "34d8a3121846bd0d9e01e2ad88913313ceabd26046c6a4ccf322607a65095bde",
    "joint_publication.py": "dfbf0024b6055d2eae3c77eabcaf1f09c79653bded96bdb7b362f89f8fd245fa",
    "blind_joint_route.py": "f7a66aea7ed875f5de067a0125948cd51c91e329ac0ea4b4ab1b4da6db5d1ca6",
}
ARMS = ("c0", "fitted_c")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def publication(directory):
    from leo.contracts.digests import canonical_digest
    from short_stereo_trial import single_packet

    report = read(directory / "joint-research-receipt.json")
    receipt = report["receipt"]
    terminal = read(directory / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
    native = read(single_packet(directory))
    if (canonical_digest(terminal) != receipt["terminal_sha256"]
            or canonical_digest(native) != terminal["native_sha256"]
            or terminal["region"] != receipt["region"]):
        raise ValueError("Inconsistent saved publication receipt")
    return report, terminal, native


def assigned(case):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from short_stereo_trial import source_for

    site = case.split("-", 1)[0]
    source_case = "north" if site == "north" else "south-inside"
    recording, archive, inside, packet, pin, _ = source_for(source_case)
    region, offer_pin = OFFERS[case]
    region = inside if region is None else region
    offer = Algo08Region.parse(read(region)).document()
    original, terminal, historical_native = publication(PRIOR[case][0])
    native = read(packet)
    if (digest(region) != offer_pin or canonical_digest(native) != pin
            or "sha256:" + PRIOR[case][1] != original["receipt"]["terminal_sha256"]
            or offer != terminal["region"] or archive_identity(Path(archive["root"])) != archive
            or historical_native["source"]["raw_recording_authority_digest"]
                != native["source"]["raw_recording_authority_digest"]
            or original["receipt"]["decision"] != ("withheld" if case.endswith("-far") else "complete")):
        raise ValueError(f"Unbound region, archive, short input or historical decision for {case}")
    return dict(recording=str(recording), archive=archive, region=str(region), packet=str(packet),
                offer=offer, offer_sha256=offer_pin, native_sha256=pin,
                historic_report=str(PRIOR[case][0]), historic_terminal=terminal,
                historic_terminal_sha256=original["receipt"]["terminal_sha256"],
                historic_figures=original["evidence"]["images"], historic_native=terminal["native_sha256"])


def forward_worker(saved, pin, output, recording, archive, region, geo, regional):
    """Run the donor's identical graph and scorer with only forward observations."""
    from full_short_run import geographic_projection
    from joint_publication import run

    native = read(saved)
    selection = {}

    def project(expected, prepare, packet, *args, **kwargs):
        from leo.contracts.digests import canonical_digest
        from north_factor_swap import continued

        start, wall = process_time(), perf_counter()
        if canonical_digest(packet) != expected:
            raise ValueError("Forward control received different native input")
        forward = continued(packet)
        selection.update(forward_sha256=canonical_digest(forward),
                         selection=dict(cpu_s=process_time()-start, elapsed_s=perf_counter()-wall))
        return prepare(forward, *args, **kwargs)

    args = SimpleNamespace(saved=saved, saved_digest=pin, output=output, recording=recording,
                           archive=archive, region=region, verify_images=True, optimized_full_catalogue=True)
    run(args, early_regional=True, keep_selected_rows=True,
        saved_receiver=native["provenance"]["detector_sha256"][7:],
        geographic_projector=lambda: geographic_projection(geo, regional), reuse_cold_rows=True,
        reuse_grid_phase_states=True, prepare_native_projection=partial(project, pin))
    write(output / "forward-policy.json", selection)


def launch(root, geo, regional):
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA

    settings = host()
    libraries = {"geographic": digest(geo), "scores": digest(regional)}
    if libraries != {"geographic": GEOGRAPHIC_SHA, "scores": TRACK_SCORES_SHA} or any(
        digest(HERE / name) != pin for name, pin in FROZEN.items()
    ):
        raise ValueError("The measured donor branch or its reviewed native libraries changed")
    cases = {case: assigned(case) for case in OFFERS}
    root.mkdir(exist_ok=False)
    write(root / "binding.json", dict(cases=cases, donor_pins=FROZEN, libraries=libraries, host=settings,
                                      protocol_sha256=digest(HERE / PROTOCOL), runner_sha256=digest(Path(__file__))))
    env = environment(root)
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    for index, (case, assignment) in enumerate(cases.items()):
        order = ("forward", "repair") if index % 2 == 0 else ("repair", "forward")
        for arm in order:
            folder = root / f"{case}-{arm}"
            cmd = [python, "-BPs", Path(__file__) if arm == "forward" else HERE / "local_future_repair_trial.py",
                   "worker", assignment["packet"], assignment["native_sha256"], folder, assignment["recording"],
                   assignment["archive"]["root"], assignment["region"], geo, regional]
            before, start = usage(), perf_counter()
            process = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=55)
            after = usage()
            write(root / f"{case}-{arm}-clock.json", dict(
                order=order, elapsed_s=perf_counter()-start, status=process.returncode,
                **{k: after[k]-before[k] for k in before},
            ))
            (root / f"{case}-{arm}-stderr").write_text(process.stderr)
            if process.returncode:
                raise ValueError(process.stderr[-4000:])


def owner_delta(before, after, future, repair):
    def owner_map(rows):
        data = {oid: (norad, role) for oid, norad, role in rows}
        if len(data) != len(rows):
            raise ValueError("Duplicate original owner")
        return data

    original, current = owner_map(before), owner_map(after)
    gained = {key: current[key] for key in current.keys() - original.keys()}
    eligible = {row["observation_id"]: (row["norad"], row["role"]) for row in repair.get("added", [])}
    if (not original.items() <= current.items() or not gained.keys() <= future
            or gained != (eligible if repair.get("decision") == "accepted" else {})):
        raise ValueError("Changed incumbent owner, role, or signed addition")
    return dict(before=len(original), after=len(current), added=len(gained))


def run_packet(root, case, arm, assignment):
    from joint_publication import artifacts

    directory = root / f"{case}-{arm}"
    report, terminal, _ = publication(directory)
    receipt, clocks = report["receipt"], read(root / f"{case}-{arm}-clock.json")
    reported = report["evidence"]
    actual = json.loads(json.dumps(artifacts(directory, receipt)))
    if (terminal["native_sha256"] != assignment["native_sha256"] or terminal["region"] != assignment["offer"]
            or report["saved_digest"] != assignment["native_sha256"] or clocks["status"] != 0 or actual != reported):
        raise ValueError("Saved replay publication changed source or failed its evidence gates")
    decision = receipt["decision"]
    if decision == "complete":
        if not report["solve"]["grid_complete"] or any(terminal["arms"][a]["latlon"] is None for a in ARMS):
            raise ValueError("Fix is missing a calibrated arm or complete numerical evidence")
    elif decision != "withheld" or actual != {"images": {}} or any(terminal["arms"][a]["latlon"] is not None for a in ARMS):
        raise ValueError("Withholding produced a figure or nonnull arm")
    return report, terminal, clocks


def score(root):
    from aperture_score import face_clearance_km, references
    from local_future_inputs import future_observations
    from mixture_score import section
    from north_factor_swap import continued
    from leo.contracts.digests import canonical_digest

    host()
    binding = read(root / "binding.json")
    if binding["cases"] != {case: assigned(case) for case in OFFERS}:
        raise ValueError("A frozen source changed after inference")
    sealed = {case: {arm: run_packet(root, case, arm, binding["cases"][case]) for arm in ("forward", "repair")}
              for case in OFFERS}
    truth_by_case = references()
    results = {}
    for case, pair in sealed.items():
        assignment = binding["cases"][case]
        native = read(Path(assignment["packet"]))
        forward = continued(native)
        future = {row["observation_id"] for row in future_observations(native, forward)}
        before_policy = read(root / f"{case}-forward/forward-policy.json")
        after_policy = read(root / f"{case}-repair/local-future-policy.json")
        if (after_policy["implementation"] != FROZEN or after_policy["native_sha256"] != assignment["native_sha256"]
                or canonical_digest(forward) != before_policy["forward_sha256"] or canonical_digest(forward)
                != after_policy["forward_sha256"] or future != set(after_policy["future_ids"])):
            raise ValueError("Replay did not bind the same forward packet and future-only roster")
        before, after = (pair[name][0] for name in ("forward", "repair"))
        details = after["route_details"] or {}
        repair = details.get("local_future_repair")
        owners = {arm: owner_delta(before["selected_rows"].get(arm, []), after["selected_rows"].get(arm, []),
                                     future, repair or {}) for arm in ARMS}
        site = case.split("-", 1)[0]
        truth = truth_by_case[f"{site}-containing"]
        clearance = face_clearance_km(assignment["offer"], truth)
        if (clearance >= 0.) != case.endswith("-containing"):
            raise ValueError("The sealed geographic control does not match its classification")
        historic = assignment["historic_terminal"]["arms"]
        stock = pair["forward"][1]["arms"]
        result = dict(clearance_km=clearance, owners=owners, local_repair=repair, forward_policy=before_policy,
                      repair_policy={k: v for k, v in after_policy.items() if k != "future_ids"},
                      future_count=len(future), historical=section(historic, truth, historic),
                      historical_decision=assignment["historic_terminal"]["decision"])
        for arm, (report, terminal, clocks) in pair.items():
            result[arm] = dict(science=section(terminal["arms"], truth, stock), decision=terminal["decision"],
                               reason=terminal.get("reason"), terminal_sha256=report["receipt"]["terminal_sha256"],
                               geographically_correct=(clearance >= 0.) == (terminal["decision"] == "ok"),
                               evidence=report["evidence"], solve=report["solve"], process=clocks,
                               publication_cpu_s=report["publication_cpu_s"], proof=report["early_regional"],
                               route=report["route"], signed=(report["route_details"] or {}).get("signed"))
        result["early_regional_proof_equal"] = [row["result"] for row in before["early_regional"]] == [
            row["result"] for row in after["early_regional"]
        ]
        result["identical_figures"] = dict(
            bytes=sum(a["sha256"] == after["evidence"]["images"][name]["sha256"]
                      for name, a in before["evidence"]["images"].items() if name in after["evidence"]["images"]),
            pixels=sum(a["rgba_sha256"] == after["evidence"]["images"][name]["rgba_sha256"]
                       for name, a in before["evidence"]["images"].items() if name in after["evidence"]["images"]),
        )
        if clearance >= 0.:
            original_repair, original_terminal, _ = publication(DONOR_ROOT / ("north" if site == "north" else "south-inside"))
            result["matches_donor_containing"] = (original_terminal == pair["repair"][1]
                                                   and original_repair["selected_rows"] == after["selected_rows"]
                                                   and original_repair["evidence"]["images"] == after["evidence"]["images"])
        results[case] = result
    return dict(binding=binding, results=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    for mode, options in (
        ("run", ("root", "geo", "regional")), ("score", ("root", "output")),
        ("worker", ("saved", "pin", "output", "recording", "archive", "region", "geo", "regional")),
    ):
        current = modes.add_parser(mode)
        for name in options:
            current.add_argument(name, type=str if name == "pin" else Path)
    args = vars(parser.parse_args())
    mode = args.pop("mode")
    if mode == "run":
        launch(**args)
    elif mode == "worker":
        forward_worker(**args)
    else:
        write(args["output"], score(args["root"]))
