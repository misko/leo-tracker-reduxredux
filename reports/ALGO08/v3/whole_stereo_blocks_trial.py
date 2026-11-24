"""Run and assess one saved dense whole-stereo acquisition counterfactual."""

import argparse
from contextlib import contextmanager
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ARMS = ("c0", "fitted_c")
CONTROL = Path("/dev/shm/leo-cumulative-grid-projection-01/dense-pair")
CONTROL_SHA = "1ac1eacb47a49aa4fccdcd50e65df4f5a66f3a78c599010b8fabb4cb63181993"
REPORT_SHA = "f378b41ceaf7a874aeb2b7cb02636647fa01b32c0ddc70efb65fd566a724182f"
DENSE_ALLOWANCE_KM = .25
DESCRIPTION = "saved whole-stereo schedule counterfactual from original signed 20/12 ms proposals"


def worker(job, output):
    import cumulative_grid_projection as governed

    def bind(request, _specification, mixed):
        from leo.contracts.digests import canonical_digest

        if (request["receiver"] != "whole-stereo-blocks" or request["recipe"]["parent"] != "sha256:" + mixed
                or canonical_digest(request["recipe"]) != request["detector"]):
            raise ValueError("Expected the bound saved masked mixed detector")
        return request["detector"].removeprefix("sha256:")

    original = governed.saved_inventory_port

    @contextmanager
    def saved_only(request):
        import joint_publication
        from leo.storage.fast_scan import FastSegmentSource
        from named_constrained_research import deny_waveform

        ordinary = joint_publication.run
        with (original(request) as staged, patch.object(FastSegmentSource, "windows", deny_waveform),
              patch.object(joint_publication, "run", partial(ordinary, detector_override=deny_waveform,
                                                           detector_description=DESCRIPTION))):
            if not staged:
                raise ValueError("Publication would lose the saved-only inventory port")
            yield staged

    with patch.object(governed, "saved_detector", bind), patch.object(governed, "saved_inventory_port", saved_only):
        governed.worker(job, "combined", output)


def run(root):
    from aperture_trial import RELEASE, archive_identity, read, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from grid_feature_projection import LIBRARY_SHA
    from prospective_0316_solver import LIBRARIES
    from short_raw_diagnostic import measure
    from whole_stereo_blocks import DENSE, REQUEST_SHA, load_checked

    if not root.resolve(strict=True).is_relative_to(Path("/dev/shm")):
        raise ValueError("Require the presealed private tmpfs mask")
    plan = read(root/"plan.json")
    if not plan["budget"]["eligible"]:
        raise ValueError("The priced dense mask misses the published cost gate")
    source = load_checked(DENSE/"request.json", REQUEST_SHA)
    full = load_checked(CONTROL/"result.json", CONTROL_SHA)
    bindings = full["inputs"]
    if (not full["verified"] or bindings["native"] != source["original"]["native_sha256"]
            or bindings["inventory"] != source["inventory"] or bindings["authority"] != source["authority"]
            or bindings["offer_sha256"] != source["offer_sha256"]
            or bindings["archive"]["snapshots_sha256"] != source["archive"]["snapshots_sha256"]):
        raise ValueError("Historical full mixed control differs from the original proposal ledger")
    inventory = DENSE/"selected/fast-scan-inputs"/(source["session"]+".json")
    archive = Path(source["archive"]["root"])
    libraries = {Path(v): LIBRARIES[name][1] for name, v in source["libraries"].items()}
    projection = Path(bindings["projection"])
    pins = {Path(source["offer"]): source["offer_sha256"], inventory: source["inventory"][7:],
            root/"candidate-detections.json": plan["frozen_plan"]["native_sha256"][7:], projection: LIBRARY_SHA, **libraries}
    for path, pin in pins.items():
        if not path.resolve(strict=True).is_relative_to(Path("/dev/shm")) or sha256(path.read_bytes()).hexdigest() != pin:
            raise ValueError(f"The original bounded saved assignment differs at {path}")
    if not archive.resolve(strict=True).is_relative_to(DENSE) or archive_identity(archive)["snapshots_sha256"] != source["archive"]["snapshots_sha256"]:
        raise ValueError("The original staged causal archive changed")
    assigned = dict(bindings, archive=source["archive"], libraries=source["libraries"], region=source["offer"],
                    packet=str(root/"candidate-detections.json"), native=plan["frozen_plan"]["native_sha256"],
                    detector=plan["frozen_plan"]["detector_sha256"], recipe=plan["frozen_plan"]["recipe"],
                    receiver="whole-stereo-blocks", saved_inventory=str(inventory))
    job = root/"request.json"
    if job.exists():
        raise ValueError("The one likelihood launch already has a frozen request")
    write(job, assigned)
    target = root/"candidate"
    env = environment(root)
    (root/"tmp").mkdir()
    env["TMPDIR"] = str(root/"tmp")
    command = [RELEASE/"venv/bin/python", "-IB", __file__, "worker", job, target]
    receipt = dict(machine=host(), study_plan_sha256=sha256((root/"plan.json").read_bytes()).hexdigest(),
                   request_sha256=sha256(job.read_bytes()).hexdigest(), immutable_inputs={str(p): x for p, x in pins.items()},
                   historical_control_sha256=CONTROL_SHA, command=list(map(str, command)),
                   sources={file: sha256((HERE/file).read_bytes()).hexdigest() for file in
                            ("whole_stereo_blocks_trial.py", "cumulative_grid_projection.py", "unified_short_bootstrap.py", "joint_publication.py")})
    write(root/"launch.json", receipt)
    measured = measure(command, env, target)
    write(root/"clock.json", measured)
    if measured["exit_code"]:
        raise ValueError(measured["stderr_tail"])
    seal(root)


def seal(root):
    from aperture_trial import read, write
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from short_raw_diagnostic import pairs

    target = root/"candidate"
    assigned, clock = read(root/"request.json"), read(root/"clock.json")
    worker_data = read(target/"cumulative-grid-worker.json")
    trial = read(target/"joint-research-receipt.json")
    receipt = trial["receipt"]
    run_id = receipt["run_id"]
    terminal = read(FastScanStore(target).automatic_workspace(run_id, create=False)/"terminal.json")
    media = artifacts(target, receipt)
    science = pairs.evidence(target, receipt, clock["started_unix_ns"], read_only=True)
    if (clock["exit_code"] or canonical_digest(terminal) != receipt["terminal_sha256"]
            or terminal["native_sha256"] != assigned["native"] or worker_data["detector"] != assigned["detector"][7:]
            or "sha256:"+sha256(native_packet(target).read_bytes()).hexdigest() != assigned["native"]
            or science["raw_authority"] != assigned["authority"] or worker_data["waveform_calls"]
            or worker_data["handoffs"] != 1 or not worker_data["staged_inventory"] or trial["input"] != DESCRIPTION):
        raise ValueError("The published masked packet, original authority or handoff changed")
    if receipt["decision"] == "complete":
        store = FastStandardAnalysisStore(target)
        grid, path = store.position_grid(run_id), store.position_path(run_id)
        if (set(science["arms"]) != set(ARMS) or len(media["images"]) != 8 or not grid["complete"]
                or any(sidecar["binding"]["position_png_sha256"] != media["images"]["position"]["sha256"]
                       for sidecar in (grid, path))):
            raise ValueError("A fix must bind its two calibration fits, grid and all eight PNGs")
    elif media["images"] or not science["reason"]:
        raise ValueError("An actual withholding needs a reason and zero media")
    write(root/"sealed.json", dict(clock=clock, terminal=terminal, science=science, worker=worker_data, media=media,
                                   solve=trial["solve"], selected_rows=trial["selected_rows"], early=trial["early_regional"],
                                   route=trial["route"], route_details=trial["route_details"],
                                   native_sha256=assigned["native"], waveform_calls=0))


def evaluate(root):
    from aperture_trial import read, write
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256
    from whole_stereo_blocks import RAW_SHA, load_checked

    sealed = read(root/"sealed.json")
    plan = read(root/"plan.json")
    full = load_checked(CONTROL/"result.json", CONTROL_SHA)["runs"]["combined"]
    report = load_checked(CONTROL/"combined/joint-research-receipt.json", REPORT_SHA)
    named = load_checked(HERE/"measurements/dense-full-short-raw.json.gz", RAW_SHA)["baseline"]
    if (named["receipt"]["session_id"] != sealed["science"]["receipt"]["session_id"]
            or named["receipt"]["region"] != sealed["science"]["receipt"]["region"]
            or named["authority"] != sealed["science"]["raw_authority"]):
        raise ValueError("Published named comparator is from a different experiment")
    survey = load_checked(REFERENCE, REFERENCE_SHA256)
    (reference,) = [r for r in survey["cases"] if r["dataset_label"] == "DS30-0008"
                    and r["authority_eligible"] and r["sealed_metadata_digests_verified"]]
    site = [reference["reference"][field] for field in ("latitude_deg", "longitude_deg")]
    scores = {}
    for key, arms in (("named_v3", named["arms"]), ("full_mixed", full["science"]["arms"]),
                      ("masked", sealed["science"]["arms"])):
        scores[key] = {arm: dict(latlon=row["latlon"], error_km=distance_km(site, row["latlon"]) if row["latlon"] else None,
                                 rf_rms_hz=row.get("rf_rms_hz")) for arm, row in arms.items()}
    compared = {}
    for role in ("named_v3", "full_mixed"):
        compared[role] = {}
        for arm in ARMS:
            before, after = scores[role][arm], scores["masked"][arm]
            compared[role][arm] = None if after["error_km"] is None else dict(
                error_delta_km=after["error_km"]-before["error_km"], endpoint_move_km=distance_km(after["latlon"], before["latlon"]),
                rf_delta_hz=after["rf_rms_hz"]-before["rf_rms_hz"])
    gross = plan["budget"]["gross_credit_cpu_s"]
    net = gross + full["worker"]["solve"]["cpu_s"] - sealed["solve"]["cpu_s"] - plan["planning_including_source_cpu_s"]
    full_replay = sealed["science"]["receipt"]["decision"] == "complete"
    quality = full_replay and all(compared["named_v3"][arm]["error_delta_km"] <= DENSE_ALLOWANCE_KM for arm in ARMS)
    write(root/"score.json", dict(value=scores, comparisons=compared, quality_vs_named=quality,
                                  second_saved_eligible=quality and net > plan["budget"]["gate_cpu_s"],
                                  reported_clock=dict(gross_mean_price_cpu_s=gross, projected_net_cpu_s=net,
                                      complete_saved_control_cpu_s=full["clock"]["cpu_s"], complete_saved_control_elapsed_s=full["clock"]["elapsed_s"],
                                      complete_saved_candidate_cpu_s=sealed["clock"]["cpu_s"], complete_saved_candidate_elapsed_s=sealed["clock"]["elapsed_s"],
                                      archived_cumulative_solve_cpu_s=full["worker"]["solve"]["cpu_s"],
                                      candidate_solve_cpu_s=sealed["solve"]["cpu_s"]),
                                  owners={arm: owner_delta(report["selected_rows"][arm], sealed["selected_rows"].get(arm, [])) for arm in ARMS},
                                  sealed_sha256=sha256((root/"sealed.json").read_bytes()).hexdigest(),
                                  reference_sha256=REFERENCE_SHA256))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "score"):
        item = command.add_parser(name)
        item.add_argument("root", type=Path)
    child = command.add_parser("worker")
    child.add_argument("job", type=Path)
    child.add_argument("output", type=Path)
    args = vars(parser.parse_args())
    {"run": run, "worker": worker, "score": evaluate}[args.pop("command")](**args)
