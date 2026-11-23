"""One saved publication per case with original-ownership CFO refinement."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from aperture_trial import RELEASE, archive_identity, read, write


CASES = ("north", "weak")
MODES = ("before", "owned", "upstream")
NORTH = Path("/dev/shm/leo-v3-north-cfo-contrasts-01")
NORTH_RAW = Path("/dev/shm/leo-v3-north-cfo-final-03")
WEAK = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
WEAK_RAW = Path("/dev/shm/leo-v3-raw-cfo-0016-result03")
DETECTORS = ("13c4ecdb521d02960e61572e8d401a54f165e2c7882112889ede0582abb3ca40",
             "701c05ac380d8c1b4b528ddbfd6925d1c13dd9b1832dbe2959f52c3177065d66")
PACKETS = {"north": ("2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427",
                     "83d1c79b8acb8dc1d8720999af9791264558b2ac43505b6312e535fe832b91d0"),
           "weak": ("c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589",
                    "6329ba6eb4893ae12a05259fef9ce14ff8678a320a133ff1dc5ee839527af2ea")}
ARCHIVE = {"north": ("f9ed20a7c229fbb08042c3148f117882e45664514eea9ba5cf235a4d6f6c7298",
                      "949f1aa6045d8c0449a2322a8968e24c388851169aaaafb7cfcc0f6a1c2f6691"),
            "weak": ("81ae6f59cdcafaa11207a9fb326c6186d1a64a7d612b599238014b90d6fe8d6d",
                     "b722cad5157cf1b51002dbc920a9bb2cc104dd26bab659e39db76fb4aeefc81d")}


def verified(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected.removeprefix("sha256:"):
        raise ValueError(f"Changed archived evidence at {path}")
    return data


def publication_path(root):
    path, = root.glob("fast-scan-automatic-work/*/detections.json")
    return path


def inputs(case):
    from combined_frontier_run import BLOCK_SHA
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from grid_feature_projection import LIBRARY_SHA
    from leo.contracts.digests import canonical_digest

    if case == "north":
        values = json.loads(verified(NORTH / "binding.json", "ac818cb0c05a25eb92720cc1ad1e99570b6ada23af62d62eee12de0a6292a64f"))
        assignment = values["request"]
        baseline, refined = NORTH / "unrefined-full", NORTH_RAW / "containing"
        region, offer_sha = Path(values["offer"]), assignment["inside_offer_sha256"]
        archive, inventory = assignment["archive"], Path(assignment["saved_inventory"])
        libraries = {name: assignment["libraries"][name] for name in (
            "frontier_block_library", "geographic_library", "regional_track_library")}
        projection = assignment["libraries"]["grid_feature_projection_library"]
    else:
        assignment = json.loads(verified(WEAK_RAW / "admission.json", "93b311dc73a5474eb252502123672b00d599f9e8bc66a7e4f463241adfe2ca15"))
        baseline, refined = WEAK / "candidate", WEAK_RAW / "candidate"
        region, offer_sha = WEAK / "offer.json", assignment["offer_sha256"]
        archive = dict(root=str(WEAK_RAW / "tle"), snapshots_sha256=assignment["archive"]["sha256"])
        inventory = baseline / "fast-scan-inputs" / (assignment["session"] + ".json")
        libraries = {name: str(WEAK / f"{file}.so") for name, file in (
            ("frontier_block_library", "block"), ("geographic_library", "geographic"), ("regional_track_library", "regional"))}
        projection = str(WEAK / "projection.so")
    verified(region, offer_sha)
    verified(inventory, assignment["inventory"])
    if archive_identity(Path(archive["root"])) != archive:
        raise ValueError("The original causal archive changed")
    for name, pin in (("frontier_block_library", BLOCK_SHA), ("geographic_library", GEOGRAPHIC_SHA),
                      ("regional_track_library", TRACK_SCORES_SHA)):
        verified(Path(libraries[name]), pin)
    verified(Path(projection), LIBRARY_SHA)
    packet, other = publication_path(baseline), publication_path(refined)
    before, after = (json.loads(verified(path, pin)) for path, pin in zip((packet, other), PACKETS[case], strict=True))
    for value, detector in zip((before, after), DETECTORS, strict=True):
        source = value["source"]
        if (source["input_manifest_sha256"] != assignment["inventory"] or source["session_id"] != assignment["session"]
                or source["raw_recording_authority_digest"] != assignment.get("authority", assignment.get("raw_authority"))
                or value["clock_anchor"]["before"]["realtime_ns"] != assignment["cutoff_utc_ns"]
                or value["provenance"]["detector_sha256"] != "sha256:"+detector
                or source["analysis_manifest_sha256"] != canonical_digest(
                    ["cancellation", source["raw_recording_authority_digest"], detector, source["probes"]])):
            raise ValueError("The genuine detector pair changed its validated input or scope")
    return dict(case=case, recording=assignment["recording"], archive=archive, region=str(region), offer_sha256=offer_sha,
                issued=assignment["issued"], inventory=assignment["inventory"], session=assignment["session"],
                saved_inventory=str(inventory), authority=before["source"]["raw_recording_authority_digest"],
                cutoff_utc_ns=assignment["cutoff_utc_ns"], libraries=libraries, projection=projection,
                packet=str(packet), native="sha256:"+PACKETS[case][0], refined=str(other),
                refined_native="sha256:"+PACKETS[case][1], prior=str(baseline), refined_prior=str(refined))


def worker(job, output):
    import joint_publication as joint
    from cumulative_grid_projection import worker as saved
    from mixed_aperture_receiver import FULL_RULE
    from owned_cfo_finish import OwnedCfo

    req = read(job)
    native = json.loads(verified(Path(req["packet"]), req["native"]))
    refined = json.loads(verified(Path(req["refined"]), req["refined_native"]))
    policy = OwnedCfo(native, refined, FULL_RULE)
    original = joint.run

    def apply(options, *args, **kwargs):
        from tools import algo08_position

        selected = algo08_position.selected_packet

        def capture(*v, **k):
            return policy.emitted(selected(*v, **k))

        with patch.object(algo08_position, "selected_packet", capture):
            return original(options, *args, **kwargs, local_future_policy=policy)

    with patch.object(joint, "run", apply):
        saved(job, "combined", output, named_survivor_finish=True, direct_orbit_figures=True, direct_residual_figures=True)
    if not policy.evidence or set(policy.evidence[-1]) != {"c0", "fitted_c"}:
        raise ValueError("Both emitted evidence arms must bind real CFO observations")
    expected = policy.notes.get("ids", []) if policy.notes.get("decision") == "accepted" else []
    if any(ids != expected for ids in policy.evidence[-1].values()):
        raise ValueError("The published packet did not use exactly the selected evidence view")
    slots = policy.positives.values()
    bytes_for_stereo = 200_000 * 2 * 2 * 2
    visits = len({visit for visit, _ in slots})
    write(output / "owned-cfo-update.json", dict(update=policy.notes, input_short=req["native"], input_refined=req["refined_native"],
          short_positive_lanes=len(slots), refined_available=len(policy.refined),
          stereo_positive_visits=visits, retained_stereo_ci16_bytes=visits*bytes_for_stereo,
          retained_packed_lane_ci16_bytes=len(slots)*bytes_for_stereo//2, emitted_changed_ids=policy.evidence[-1],
          sources={name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
              "owned_cfo_finish.py", "owned_cfo_trial.py", "owned-cfo-protocol.md", "joint_publication.py",
              "blind_joint_route.py", "cumulative_grid_projection.py", "unified_short_bootstrap.py")}))


def launch(case, root):
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if root.resolve() != root or not root.is_relative_to("/dev/shm"):
        raise ValueError("Use a fresh canonical tmpfs directory")
    req = dict(inputs(case), machine=machine)
    root.mkdir()
    (root / "tmp").mkdir()
    job = root / "request.json"
    write(job, req)
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=20)
    output = root / "owned"
    measured = measure([python, "-IB", __file__, "worker", job, output], env, output)
    write(root / "clock.json", measured)
    if measured["exit_code"]:
        raise RuntimeError(f"Failed saved publication: {measured['stderr_tail']}")


def score(root):
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.presentation.localization_v3 import owner_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.scoring import distance_km

    req, clock = read(root / "request.json"), read(root / "clock.json")
    case = req["case"]
    output = root / "owned"
    worker = read(output / "cumulative-grid-worker.json")
    report = read(output / "joint-research-receipt.json")
    proof = read(output / "owned-cfo-update.json")
    receipt = worker["receipt"]
    store = FastStandardAnalysisStore(output)
    run_id = receipt["run_id"]
    grid, path = store.position_grid(run_id), store.position_path(run_id)
    media = artifacts(output, receipt)
    emitted = read(output / "fast-scan-automatic-work" / run_id / "terminal.json")
    if (clock["exit_code"] or worker["handoffs"] != 1 or not worker["staged_inventory"] or worker["waveform_calls"]
            or canonical_digest(emitted) != receipt["terminal_sha256"] or receipt["decision"] != "complete"
            or emitted["native_sha256"] != req["native"] or canonical_digest(read(publication_path(output))) != req["native"]
            or len(media["images"]) != 8 or not grid["complete"] or grid["evaluated_points"] != grid["planned_points"]
            or any(doc["binding"]["position_png_sha256"] != media["images"]["position"]["sha256"] for doc in (grid, path))
            or any(abs(delta) > 1e-5 for delta in report["solve"]["objective_replay"].values())):
        raise ValueError("Owned update lacks its verified exact numerical and media publication")
    refs = {}
    for mode, folder, digest, native in zip(("before", "upstream"), (Path(req["prior"]), Path(req["refined_prior"])),
                                          ARCHIVE[case], (req["native"], req["refined_native"]), strict=True):
        saved = folder / "joint-research-receipt.json"
        archived = json.loads(verified(saved, digest))
        terminal = read(folder / "fast-scan-automatic-work" / archived["receipt"]["run_id"] / "terminal.json")
        if terminal["native_sha256"] != native or canonical_digest(terminal) != archived["receipt"]["terminal_sha256"]:
            raise ValueError("The archived comparator does not bind its own native view")
        refs[mode] = dict(arms=terminal["arms"], owners=archived["selected_rows"], solve=archived["solve"],
                          receipt_sha256=sha256(saved.read_bytes()).hexdigest())
    rows = report["selected_rows"]
    detail = store.detail(run_id)
    if any(rows[arm] != refs["before"]["owners"][arm] or owner_digest({r[0]: r[1] for r in rows[arm]}) != detail["arms"][arm]["owner_sha256"]
           for arm in rows):
        raise ValueError("Update changed the archived original accepted owner roster")
    refs["owned"] = dict(arms=emitted["arms"], owners=rows, solve=report["solve"])
    if proof["update"].get("decision") != "accepted" and emitted["arms"] != refs["before"]["arms"]:
        raise ValueError("Rejected owned-CFO update must publish the exact unchanged incumbent")
    seal = dict(request=req, clock=clock, worker=worker, update=proof, runs=refs, grid_points=grid["evaluated_points"],
                media=media, owned_same_owners=True, terminal=emitted)
    write(root / "numerical-seal.json", seal)
    if case == "north":
        truth = json.loads(verified(NORTH / "result.json", "82d93133bdf691bedcfa7c265e6f16a105bc013d8bbe4cd867e258fbfd7be438"))["truth"]
    else:
        from triage_bounds import REFERENCE, REFERENCE_SHA256

        (ref,) = (r["reference"] for r in json.loads(verified(REFERENCE, REFERENCE_SHA256))["cases"]
                  if r["dataset_label"] == "DS30-0016" and r["authority_eligible"])
        truth = [ref["latitude_deg"], ref["longitude_deg"]]
    write(root / "scored.json", dict(scores={mode: {arm: dict(error_km=distance_km(data["latlon"], truth),
                                       rf_rms_hz=data["rf_rms_hz"]) for arm, data in run["arms"].items()}
                                       for mode, run in refs.items()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("launch")
    run.add_argument("case", choices=CASES)
    run.add_argument("root", type=Path)
    invoked = commands.add_parser("worker")
    invoked.add_argument("job", type=Path)
    invoked.add_argument("output", type=Path)
    commands.add_parser("score").add_argument("root", type=Path)
    values = vars(parser.parse_args())
    {"launch": launch, "worker": worker, "score": score}[values.pop("command")](**values)
