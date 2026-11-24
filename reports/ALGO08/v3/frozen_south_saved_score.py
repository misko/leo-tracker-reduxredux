"""Independently verify and score the frozen saved South publications."""

import argparse
from io import BytesIO
import json
from math import isfinite
from pathlib import Path
import subprocess
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from frozen_south_saved import FREEZE_SHA, PINS, RUNTIME, bootstrap, digest, inputs, read


ARMS = ("c0", "fitted_c")
IMAGES = {"ch1-4-all", "ch5-8-all", "ch1-4-unassociated", "ch5-8-unassociated", "ch1-4-residuals",
          "ch5-8-residuals", "track-rms", "position"}


def publication(target, clock, mode, offer, authority, packet_sha):
    from history_risk_0016_cairo import active_renderer
    import integrated_original_batch as batch
    from leo.presentation.localization_v3 import owner_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from PIL import Image

    worker = read(target / "saved-south-worker.json")
    receipt, rows = worker["receipt"], worker["ordered_owners"]
    run_id = receipt["run_id"]
    terminal = batch.document(target / "fast-scan-automatic-work" / run_id / "terminal.json", receipt["terminal_sha256"])
    (native,) = target.glob("fast-scan-automatic-work/*/detections.json")
    batch.checked(native, packet_sha)
    store = FastStandardAnalysisStore(target)
    detail = store.detail(run_id)
    if (clock["exit_code"] or worker["mode"] != mode or worker["waveform_reads"] or worker["verified_handoffs"] != 1
            or worker["submitted_native_sha256"] != detail["input_sha256"] or detail["input_sha256"] != packet_sha
            or terminal["native_sha256"] != packet_sha or terminal["region"] != offer
            or receipt["region"] != offer or set(terminal["arms"]) != set(ARMS)
            or receipt["counts"]["processed"] != authority["window_count"]
            or detail["terminal_sha256"] != receipt["terminal_sha256"] or detail["state"] != receipt["decision"]
            or detail["raw_authority"] != authority["raw_authority_sha256"]):
        raise ValueError("The standard terminal and publication must bind both calibration arms to the authenticated offer")
    audit = worker["audit"]
    witness = {}
    if receipt["decision"] == "withheld":
        if rows or detail["artifacts"] or any(target.rglob("*.png")) or any(row["latlon"] is not None for row in terminal["arms"].values()):
            raise ValueError("A true withheld publication must have null positions and zero media")
        grid, trace, figures, owners = None, None, {}, {}
    else:
        grid, trace, figures = store.position_grid(run_id), store.position_path(run_id), {}
        for item in detail["artifacts"]:
            name, checksum = item["name"], item["sha256"]
            body = store.artifact(run_id, name, checksum)
            if batch.tagged_bytes(body) != checksum or name in figures:
                raise ValueError("Stored figure content or identity changed")
            with Image.open(BytesIO(body)) as image:
                if image.format != "PNG":
                    raise ValueError("Expected an encoded standard PNG")
                figures[name] = dict(encoded_sha256=checksum, rgba_sha256=batch.tagged_bytes(image.convert("RGBA").tobytes()),
                                     size=list(image.size))
        owners = {arm: owner_digest({uid: sat for uid, sat, _ in values}) for arm, values in rows.items()}
        expected = dict(run_id=run_id, input_sha256=packet_sha, owner_sha256=owners,
                        terminal_sha256=receipt["terminal_sha256"], position_png_sha256=figures["position"]["encoded_sha256"])
        if (set(figures) != IMAGES or set(owners) != set(ARMS) or any(owners[k] != detail["arms"][k]["owner_sha256"] for k in ARMS)
                or not grid["complete"] or not grid["matched_c_grid"]
                or not 0 < len(grid["points"]) == grid["planned_points"] == grid["evaluated_points"]
                or any(set(row["scores"]) != set(ARMS) for row in grid["points"])
                or any(doc["region_center"] != offer["center"] or doc["box_width_km"] != offer["width_km"]
                       or any(doc["binding"][key] != value for key, value in expected.items()) for doc in (grid, trace))
                or any(not all(isfinite(f) for f in (*row["latlon"], row["rf_rms_hz"])) for row in terminal["arms"].values())):
            raise ValueError("Expected full matched grids, owner digests, path, and eight verified bound images")
        if mode.endswith(":integrated"):
            exact = read(target / "exact-named-raw-witness.json")
            ports = exact["ports"]
            if (not active_renderer(ports) or audit["successor_ports"]["png_native"]["native"] != 8
                    or audit["successor_ports"]["png_native"]["fallback"] != 0
                    or len(exact["timing"]["solve"]) != 1 or len(exact["timing"]["render"]) != 1):
                raise ValueError("The complete successor did not use its six-Cairo and native PNG paths")
            witness = dict(route=exact["raw_route"], recipe=exact["solver_recipe"], history=ports["history_risk"],
                           rank=ports["rank"], portable=ports["portable"], render=ports["cairo_layout"],
                           png=audit["successor_ports"]["png_native"])
    return dict(receipt=receipt, terminal=terminal, archive_digest=authority["archive_sha256"], clock=clock,
                ordered_owners=rows, owner_digests=owners, figures=figures, grid=grid, path=trace, charted_witness=witness)


def score(root):
    from time import perf_counter, process_time

    clocks = perf_counter(), process_time()
    freeze, _, producer, _, _, _, crossover = bootstrap()
    batch = crossover.batch
    authority, _, _, _, _, roster, offers = inputs(freeze, producer, batch)
    authority["archive_sha256"] = roster
    from clean_saved_0169_trial import output_seal
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    seal_path = root / "prediction-seal.json"
    if read(seal_path) != output_seal(root):
        raise ValueError("Outputs changed before the independent scorer")
    trial = freeze["proposed_saved_pair"]
    outcomes = {}
    for mode in trial["planned_order"]:
        offer, role = mode.split(":")
        target = root / mode.replace(":", "-")
        outcomes[mode] = publication(target, read(target.with_suffix(".clock.json")), mode, read(offers[offer]), authority,
                                     batch.tagged(trial["packets"][role]["sha256"]))
    body = subprocess.check_output(["git", "-c", f"safe.directory={RUNTIME.parents[2]}", "-C", str(RUNTIME.parents[2]),
                                    "show", "HEAD:" + trial["reference_key_path"]])
    if batch.tagged_bytes(body) != batch.tagged(trial["reference_key_sha256"]):
        raise ValueError("The scoring reference changed")
    reference = json.loads(body)["answers"][trial["reference_key_row"]]
    if reference["recording"] != trial["recording_name"]:
        raise ValueError("The sealed simulated reference belongs to a different original")
    truth = reference["truth"]
    summary = {}
    for mode, value in outcomes.items():
        terminal, region = value["terminal"], value["receipt"]["region"]
        margin = face_clearance_km(region, truth)
        expected = trial["offers"][mode.split(":")[0]]["north_face_signed_clearance_km"]
        if abs(margin - expected) > 1e-7:
            raise ValueError("The frozen pair does not put the reference at its predeclared signed distance")
        fixed = value["receipt"]["decision"] == "complete"
        disposition = ("valid_fix" if fixed else "false_withhold") if margin > 0 else ("false_fix" if fixed else "correct_withhold")
        arms = {}
        for arm, row in terminal["arms"].items():
            point = row["latlon"]
            arms[arm] = dict(latlon=point, horizontal_error_m=None if point is None else 1000 * distance_km(point, truth),
                             conditional_rf_rms_hz=row.get("rf_rms_hz"),
                             endpoint_clearance_m=None if point is None else 1000 * face_clearance_km(region, point),
                             ordered_owners=len(value["ordered_owners"].get(arm, ())))
        clock = value["clock"]
        summary[mode] = dict(disposition=disposition, signed_reference_margin_km=margin, arms=arms,
                             reason=terminal["reason"], wall_s=clock["elapsed_s"], cpu_s=clock["user_s"]+clock["system_s"],
                             grid_points=0 if value["grid"] is None else value["grid"]["evaluated_points"],
                             figures=len(value["figures"]))
    return dict(schema="algo08v3-frozen-south-saved-result-v1", freeze_sha256=FREEZE_SHA, seal_sha256=digest(seal_path),
                summary=summary, outcomes=outcomes, waveform_reads=0,
                scoring_clock=dict(elapsed_s=perf_counter()-clocks[0], cpu_s=process_time()-clocks[1]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    result = score(args.root)
    with (args.root / "result.json").open("x") as stream:
        json.dump(result, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
    print(json.dumps(result["summary"]))
