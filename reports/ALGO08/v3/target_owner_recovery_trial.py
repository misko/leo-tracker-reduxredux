"""Seal the owner-union price and run a single staged dense publication."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
from inspect import getsourcefile
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from prospective_0316_solver import denied, owner_delta, saved_inventory
from prospective_small_physical import checked
from target_owner_recovery import ARMS, concentration, price, reopen


HERE = Path(__file__).resolve().parent
MASKS = Path("/dev/shm/leo-v3-modest-mask-results.0qfAjbDv")
STAGED = Path("/dev/shm/leo-held-anchor-selected-dense-01")
DENSE = "DS30-0008"
PINS = {
    "DS30-0016": ("5ece20b49e82a5362eb8f13345078a1eb2ab2492c367875c396690f842154640",
                  "75b929db168a7671d3b5e71597033a6548c0b15d5f82d0f8d64eb90d7a89dba9",
                  "05be8813345cf5be010c5525cd1144d0e80df56c036bf08d88673fb0f2e39a7d"),
    DENSE: ("c1fa8fc87db8c2836c616b843d99527c8ec317264d7cd638bb280f70e61a7f1b",
            "09e83c2bb448351638bcc7e7be164025e7a793dc58df61d582e77d58213760dc",
            "7ccb374875fee65bd88e24236b18b59b6d5aac2aa8443e07b42d2b5910cd9cc7"),
}
FULL = {
    "DS30-0016": (Path("/dev/shm/leo-cumulative-grid-projection-01/weak/detections.json"),
                  Path("/dev/shm/leo-cumulative-grid-projection-01/weak/installed"),
                  "e96fbfd7283dadf675a8db58cae0c33c799c7354f205b237afd7756a559f5883"),
    DENSE: (STAGED / "original-detections.json", Path("/var/tmp/leo-v3-regional-dense-pair/native"),
            "11c554cbcca4f756e07e810bbc7b34b548a799fd005645fd4d9e5fcbba8ef72e"),
}
SOURCES = {
    "joint_publication.py": "9df6978f279577f972460a6b752511df9bf4c511e74d072ce4ff23ebd39ac5f7",
    "full_short_run.py": "0e32d54e7a854d3b038a891457a84415b82e6c1cc283e0d7fb07afc0b4436945",
    "contiguous_third.py": "e540a38c8b131e967df895bf9e4fb3497f05815bdbb348feda14994228df1acc",
    "stereo_lane_schedule.py": "ac8cfb5ad6c298644afe25c02326d8c56611ae8e55b5f72c2a7c1456af013746",
}
TRACKS_SHA = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
GRAPH_SOURCE_SHA = "db44a947666c2dd7946534f69bf6af72ced63c8af553bb1b089c0fba3d5b7b6f"
STAGED_SHA = "8abec0e2f60def947cd03883662611c3fcfdbd5f255eb0ba60e8306085abf502"
TARGET_DRIVER_SHA = "b873b99c21e1230c14c0bc58a78c51e55fc6c5c57d8eba7327f55f9d657b1473"
TARGET_PROTOCOL_SHA = "27e65fbfffc8fdac33e8d966289ffb85971616acfcd74eabd7421355db0c3892"


def pinned(path, pin):
    return json.loads(checked(path, pin))


def load(case):
    target_dir = MASKS / case
    binding, target, result = (pinned(target_dir / name, pin) for name, pin in zip(
        ("binding.json", "target-input.json", "target-sealed.json"), PINS[case], strict=True))
    original, publication, report_pin = FULL[case]
    report = pinned(publication / "joint-research-receipt.json", report_pin)
    rec = report["receipt"]
    terminal = pinned(publication / "fast-scan-automatic-work" / rec["run_id"] / "terminal.json", rec["terminal_sha256"])
    controls = binding["controls"]
    control = controls["full"]
    meta = binding["binding"]
    full = pinned(original, meta["original_native_sha256"])
    if (meta["case"] != case or binding["protocol_sha256"] != TARGET_PROTOCOL_SHA
            or case == DENSE and binding["driver_sha256"] != TARGET_DRIVER_SHA
            or terminal["native_sha256"] != meta["original_native_sha256"]
            or terminal["arms"] != control["arms"] or terminal["region"] != meta["offer"]
            or rec["decision"] != "complete" or result["process"]["exit_code"] or result["waveform_calls"]
            or report_pin != control["report_sha256"] or report["selected_rows"] != control["selected_rows"]
            or rec["terminal_sha256"] != control["terminal_sha256"] or full["source"]["raw_recording_authority_digest"] != meta["raw_authority"]
            or full["source"]["analysis_manifest_sha256"] != controls["raw_audit"]["analysis_manifest"]):
        raise ValueError("The full ownership, original packet or sealed masked control disagree")
    return full, target, meta, controls, result


def prepare_case(case):
    from aperture_trial import RELEASE
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig

    full, target, binding, controls, result = load(case)
    restored, audit, owners = reopen(full, target, controls["full"]["selected_rows"], result["mask"],
                                     "sha256:"+controls["full"]["report_sha256"])
    checked(Path(getsourcefile(prepare_tracks)), GRAPH_SOURCE_SHA)
    graph = prepare_tracks(full, TrackConfig(**pinned(RELEASE / "assets/tracks.json", TRACKS_SHA)["config"]))
    keys = {row["observation_id"] for row in graph["observations"]}
    if not all(by_arm.keys() <= keys for by_arm in owners.values()):
        raise ValueError("The original owner join failed verification against installed observation identities")
    return restored, dict(binding=binding, audit=audit, concentration=concentration(audit, owners, graph),
                          price=price(controls["raw_audit"], audit, result["budget"]))


def inventory_for(candidate, binding):
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    stage = pinned(STAGED / "request.json", STAGED_SHA)
    archive = stage["archive"]
    inventory = STAGED / "selected/fast-scan-inputs" / f"{stage['session']}.json"
    verified = pinned(inventory, stage["inventory"])
    files = [inventory, Path(archive["root"]), Path(stage["offer"]), *(Path(p) for p in stage["libraries"].values())]
    if (any(not path.resolve(strict=True).is_relative_to(STAGED) for path in files)
            or archive_identity(Path(archive["root"]))["snapshots_sha256"] != binding["archive"]["snapshots_sha256"]
            or stage["authority"] != binding["raw_authority"] or stage["recording"] != binding["recording"]
            or candidate["source"]["input_manifest_sha256"] != stage["inventory"]
            or candidate["clock_anchor"]["before"]["realtime_ns"] != stage["cutoff_utc_ns"]
            or verified["window_count"] != candidate["provenance"]["window_count"]):
        raise ValueError("The staged request changed the original region, causal input or raw authority")
    checked(Path(stage["offer"]), stage["offer_sha256"])
    return dict(recording=stage["recording"], session=stage["session"], inventory=stage["inventory"],
                offer=stage["offer"], archive=archive, local_libraries=stage["libraries"],
                manifests=[[str(Path(row["path"])/"manifest.json"), row["manifest_digest"]] for row in verified["segments"]]), inventory


def worker(job, inventory, output):
    from empty_bootstrap import load_runtime

    _, specification, _, publication, _ = load_runtime()
    from aperture_trial import read, write
    from contiguous_third import observe_prepared
    from dense_geographic_trial import elapsed, now
    from full_short_run import geographic_projection
    import joint_publication as joint
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource
    from leo.storage.short_window import ShortWindowReader

    request = read(job)
    original = publication.run
    graph = []

    def instrument(*args, **kwargs):
        from leo.application import localization_v3 as application

        prepare = application.prepare_tracks

        def measure(*values, **options):
            clock = now()
            try:
                return prepare(*values, **options)
            finally:
                graph.append(elapsed(clock))

        with patch.object(application, "prepare_tracks", measure):
            return original(*args, **kwargs)

    libraries = {k: Path(v) for k,v in request["local_libraries"].items()}
    options = SimpleNamespace(recording=Path(request["recording"]), archive=Path(request["archive"]["root"]),
                              region=Path(request["offer"]), output=output, saved=Path(request["saved_file"]),
                              saved_digest=request["native_pin"], optimized_full_catalogue=True,
                              observe_prepared=observe_prepared, verify_images=True)
    with ExitStack() as scope:
        scope.enter_context(patch.object(joint, "configuration", return_value=(publication, dict(specification, startup="stock"))))
        scope.enter_context(patch.object(publication, "run", instrument))
        scope.enter_context(patch.object(FastScanStore, "inventory", saved_inventory(request, inventory)))
        scope.enter_context(patch.object(FastSegmentSource, "windows", denied))
        scope.enter_context(patch.object(ShortWindowReader, "windows", denied))
        joint.run(options, early_regional=True, saved_receiver=request["receiver"][7:], reuse_cold_rows=True,
                  geographic_projector=lambda: geographic_projection(libraries["geographic_library"], libraries["regional_track_library"]),
                  reuse_grid_phase_states=True)
    write(output / "timed-graph.json", graph)


def run(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    for path, pin in SOURCES.items():
        checked(HERE / path, pin)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("The oracle has a single fresh tmpfs publication root")
    root.mkdir()
    (root / "tmp").mkdir()
    cpu, wall = process_time(), perf_counter()
    cases = {}
    for case in PINS:
        projected, cases[case] = prepare_case(case)
    request, inventory = inventory_for(projected, cases[DENSE]["binding"])
    native_path = root / "dense-reopened.json"
    write(native_path, projected)
    audit = cases[DENSE]["audit"]
    request.update(saved_file=str(native_path), native_pin=audit["native_sha256"], receiver=audit["detector"])
    write(root / "request.json", request)
    write(root / "seal.json", dict(cases=cases, machine=machine, source_pins=SOURCES, input_pins=PINS,
                                  staged_request_sha256=STAGED_SHA, target_driver_sha256=TARGET_DRIVER_SHA,
                                  protocol_sha256=sha256((HERE/"target-owner-recovery-protocol.md").read_bytes()).hexdigest(),
                                  driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                                  oracle_source_sha256=sha256((HERE/"target_owner_recovery.py").read_bytes()).hexdigest(),
                                  setup=dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-wall)))
    output = root / "dense"
    env = environment(STAGED)
    env["TMPDIR"] = str(root / "tmp")
    command = [RELEASE / "venv/bin/python", "-IB", __file__, "worker", root / "request.json", inventory, output]
    timing = measure(command, env, output)
    write(root / "dense-clock.json", dict(timing=timing, command=list(map(str, command))))


def evaluate(root, output):
    from aperture_trial import read, write
    from joint_publication import artifacts
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    clock = read(root / "dense-clock.json")["timing"]
    if clock["exit_code"]:
        raise ValueError("The one dense saved process did not complete; retain its original clock")
    seal, request = read(root / "seal.json"), read(root / "request.json")
    reco = seal["cases"][DENSE]
    directory = root / "dense"
    report = read(directory / "joint-research-receipt.json")
    receipt = report["receipt"]
    science = evidence(directory, receipt, clock["started_unix_ns"], read_only=True)
    workspace = FastScanStore(directory).automatic_workspace(receipt["run_id"], create=False)
    terminal = read(workspace / "terminal.json")
    native_path, = workspace.parent.glob("*/detections.json")
    checked(native_path, request["native_pin"])
    if (terminal["native_sha256"] != request["native_pin"] or report["saved_digest"] != request["native_pin"]
            or science["raw_authority"] != reco["binding"]["raw_authority"] or terminal["region"] != reco["binding"]["offer"]):
        raise ValueError("Published native bytes, region or original raw authority disagree")
    figures = artifacts(directory, receipt)["images"]
    if receipt["decision"] == "complete":
        store = FastStandardAnalysisStore(directory)
        grid, path = store.position_grid(receipt["run_id"]), store.position_path(receipt["run_id"])
        if (grid["evaluated_points"] != 179 or not grid["complete"] or len(figures) != 8
                or any(row["binding"]["position_png_sha256"] != figures["position"]["sha256"] for row in (path, grid))):
            raise ValueError("The dense counterfactual must publish its own completed grid, path, and eight images")
    _, _, _, controls, mask = load(DENSE)
    table = {"named": controls["named"]["arms"], "full": controls["full"]["arms"],
             "target": mask["result"]["terminal"]["arms"], "reopened": terminal["arms"]}
    result_rows = report["selected_rows"]
    owners = {a: dict(from_full=owner_delta(controls["full"]["selected_rows"][a], result_rows.get(a, [])),
                      from_target=owner_delta(mask["result"]["selected_rows"][a], result_rows.get(a, []))) for a in ARMS}
    refs = pinned(REFERENCE, REFERENCE_SHA256)
    reference, = (row["reference"] for row in refs["cases"] if row["dataset_label"] == DENSE and row["authority_eligible"]
                  and row["sealed_metadata_digests_verified"])
    truth = [reference[k] for k in ("latitude_deg", "longitude_deg")]
    scored = {name: {a: dict(horizontal_error_km=distance_km(truth, row["latlon"]) if row["latlon"] else None,
                             rf_rms_hz=row.get("rf_rms_hz")) for a,row in arms.items()} for name,arms in table.items()}
    write(output, dict(seal=seal, process=clock, no_waveform=True, science=science, terminal=terminal, figures=figures,
                       research=report, timed_graph=read(directory/"timed-graph.json"), owners=owners, scores=scored,
                       reference_sha256=REFERENCE_SHA256, dense_historical_target_process=mask["process"],
                       dense_historical_target_solve=mask["result"]["solve"], dense_historical_full_solve=controls["full"]["solve"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run").add_argument("root", type=Path)
    audit = commands.add_parser("evaluate")
    audit.add_argument("root", type=Path)
    audit.add_argument("output", type=Path)
    child = commands.add_parser("worker")
    for name in ("job", "inventory", "output"):
        child.add_argument(name, type=Path)
    args = parser.parse_args()
    if args.command == "run":
        run(args.root)
    elif args.command == "evaluate":
        evaluate(args.root, args.output)
    else:
        worker(args.job, args.inventory, args.output)
