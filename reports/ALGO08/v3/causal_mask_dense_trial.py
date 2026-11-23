"""Test one already sealed causal recovery plan in a fresh dense saved publication."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import perf_counter, process_time

from aperture_trial import ARMS, RELEASE, read, write
from causal_mask_recovery import MASK_PINS, MASK_ROOT, ORIGINALS
from contiguous_third import native_signature
from dense_full_short_raw import checked
from dense_geographic_trial import host
from full_short_physical import environment
from prospective_0316_solver import owner_delta
from short_raw_diagnostic import measure
from target_owner_recovery_trial import DENSE, SOURCES, STAGED, inventory_for


HERE = Path(__file__).resolve().parent
MEASURES = HERE / "measurements"
PLAN_GZ = "45d5dfac24a65b0e48c2ea4b7be06df9e584df881e5fec804038d7562c4b303e"
PLAN_SHA = "fd16998ac56979d9efffbf3805d4ebe74934c6d37477d9d099078a03600fa1f3"
BUY_SHA = "51f4c8e114ce277c33f7606d5a6fc5100e591b0e50708f75545130ebc18f73b0"
SCREEN_SHA = "74c23da94c06b07b5b66d3c6d6688c97eade7adf3c20eef58efdd723b1352a39"
HINDSIGHT_SHA = "5d18b7b4f975fdf0cb0f584b249f0a6ed2cc5c60e34fd9f9165378235d99da38"
WORKER_SHA = "9da442b4a2f917f27dbc134f59ca997f30efc65fa569fae76cc538c209dfd6e6"
INVENTORY_HOOK_SHA = "73e3fb562115933bd5f6fb28d7a3e281c11c8f11c834a45d4b1c0914c33a280c"


def purchase_list():
    from leo.contracts.digests import canonical_digest

    payload = gzip.decompress(checked(MEASURES / "causal-mask-recovery-plans.json.gz", PLAN_GZ).read_bytes())
    if sha256(payload).hexdigest() != PLAN_SHA:
        raise ValueError("Coverage plan changed after sealing")
    case = json.loads(payload)["cases"][DENSE]
    best, = (row for row in case["schedules"] if (row["rule"], row["fraction"]) == ("recent", [3, 8]))
    slots = sorted(tuple(slot) for lane in best["lanes"] for slot in lane["bought"])
    if canonical_digest(slots) != "sha256:"+BUY_SHA or len(slots) != 1625 or len(set(slots)) != len(slots):
        raise ValueError("This diagnostic must purchase exactly the single frozen plan")
    return slots


def restore(full, target, slots):
    from leo.contracts.digests import canonical_digest
    from stereo_lane_schedule import StereoSchedule
    from tools.pipeline_eval.variants.selective_capture import same_support, visit_pairs

    same_support(full, target)
    original, base = full["source"], target["source"]
    selected = set(slots)
    if len(selected) != len(slots):
        raise ValueError("Attempted purchase repeats a billed slot")
    schedule, restored, positive_ids, omitted = StereoSchedule("target"), [], [], set()
    parents = (original["probes"], base["probes"])
    for (visit, physical), (_, masked) in zip(*(visit_pairs(rows) for rows in parents), strict=True):
        p, _ = physical
        aperture, omit = schedule.next((p["edge"], p["channel"], p["actual_rf_hz"]))
        for before, after in zip(physical, masked, strict=True):
            radio = before["receiver_id"]
            slot = (visit, radio)
            if radio == omit:
                if aperture != "short_primary" or after["candidates"]:
                    raise ValueError("Target mask did not omit the expected original short lane")
                omitted.add(slot)
            elif before != after:
                raise ValueError("An original paid factor changed")
            restored.append(before if slot in selected else after)
            if slot in selected and before["candidates"]:
                key = f"{base['session_id']}:{radio}:{before['valid_start_counter']}".encode()
                positive_ids.append("sha256:"+sha256(key).hexdigest())
    if not selected <= omitted:
        raise ValueError("Recovery can only buy an originally omitted short lane")
    detector = canonical_digest(dict(policy="sealed Recent 3/8", original=full["provenance"]["detector_sha256"],
                    base=target["provenance"]["detector_sha256"], purchased_slots_sha256=canonical_digest(slots),
                    restore_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    analysis = native_signature(base, detector, restored)
    native = dict(target, source=dict(base, probes=restored, analysis_manifest_sha256=analysis),
                  provenance=dict(target["provenance"], detector_sha256=detector, run_id="blind-compact-"+analysis[7:39]))
    audit = dict(purchased_short_lanes=len(slots), purchased_slots_sha256=canonical_digest(slots),
                 bought_positive_observation_ids=positive_ids, positive_buys=len(positive_ids),
                 paid_factors=sum(len(row["candidates"]) for row in restored), original_omission_lanes=len(omitted),
                 receiver=detector, native_pin=canonical_digest(native), analysis_sha256=analysis)
    return native, audit


def run(root):
    from leo.contracts.digests import canonical_digest

    machine = host()
    worker = checked(HERE / "target_owner_recovery_trial.py", WORKER_SHA)
    checked(HERE / "prospective_0316_solver.py", INVENTORY_HOOK_SHA)
    for name, digest in SOURCES.items():
        checked(HERE / name, digest)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use one fresh tmpfs publication root")
    clock = process_time(), perf_counter()
    inputs = MASK_ROOT / DENSE
    target_pin, binding_pin, _ = MASK_PINS[DENSE]
    full, target = read(checked(*ORIGINALS[DENSE])), read(checked(inputs / "target-input.json", target_pin))
    binding = read(checked(inputs / "binding.json", binding_pin))["binding"]
    if canonical_digest(full) != binding["original_native_sha256"]:
        raise ValueError("Native supplier changed")
    candidate, audit = restore(full, target, purchase_list())
    if (audit["original_omission_lanes"], audit["positive_buys"], audit["paid_factors"]) != (4435, 1112, 6034):
        raise ValueError("A selected signed-factor contribution changed after the sealed plan")
    request, inventory = inventory_for(candidate, binding)
    root.mkdir()
    scratch = root / "tmp"
    scratch.mkdir()
    native_path = root / "candidate-detections.json"
    write(native_path, candidate)
    request.update(saved_file=str(native_path), native_pin=audit["native_pin"], receiver=audit["receiver"])
    job = root / "request.json"
    write(job, request)
    write(root / "seal.json", dict(audit=audit, machine=machine, binding=binding, no_waveform=True,
          plan_sha256=PLAN_SHA, restored_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          protocol_sha256=sha256((HERE / "causal-mask-dense-protocol.md").read_bytes()).hexdigest(),
          worker_sha256=WORKER_SHA, stage_setup=dict(cpu_s=process_time()-clock[0], elapsed_s=perf_counter()-clock[1])))
    env = environment(STAGED)
    env["TMPDIR"] = str(scratch)
    output = root / "dense"
    command = [RELEASE / "venv/bin/python", "-IB", worker, "worker", job, inventory, output]
    timing = measure(command, env, output)
    write(root / "dense-clock.json", dict(timing=timing, command=list(map(str, command))))


def score(root, output):
    from joint_publication import artifacts
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    timing = read(root / "dense-clock.json")["timing"]
    seal, request = read(root / "seal.json"), read(root / "request.json")
    if timing["exit_code"]:
        write(output, dict(timing=timing, seal=seal, eligible=False, reason="fresh saved process was not complete"))
        return
    directory = root / "dense"
    report = read(directory / "joint-research-receipt.json")
    receipt = report["receipt"]
    workspace = FastScanStore(directory).automatic_workspace(receipt["run_id"], create=False)
    terminal = read(workspace / "terminal.json")
    packet, = workspace.parent.glob("*/detections.json")
    verified = read(checked(packet, request["native_pin"]))
    binding = seal["binding"]
    if (terminal["native_sha256"] != request["native_pin"] or report["saved_digest"] != request["native_pin"]
            or verified["source"]["raw_recording_authority_digest"] != binding["raw_authority"]
            or terminal["region"] != binding["offer"]):
        raise ValueError("Published candidate changed the sealed science support")
    figures = artifacts(directory, receipt)
    complete = receipt["decision"] == "complete"
    if complete:
        store = FastStandardAnalysisStore(directory)
        grid, path = store.position_grid(receipt["run_id"]), store.position_path(receipt["run_id"])
        actual = figures["images"]["position"]["sha256"]
        if not grid["complete"] or grid["evaluated_points"] != 179 or len(figures["images"]) != 8 or any(
                sidecar["binding"]["position_png_sha256"] != actual for sidecar in (grid, path)):
            raise ValueError("Incomplete numerical sidecars or genuine dense PNG publication")
    case = MASK_ROOT / DENSE
    _, binding_pin, sealed_pin = MASK_PINS[DENSE]
    baseline = read(checked(case / "binding.json", binding_pin))["controls"]
    target = read(checked(case / "target-sealed.json", sealed_pin))["result"]
    oracle = json.loads(gzip.decompress(checked(MEASURES / "target-owner-recovery.json.gz", HINDSIGHT_SHA).read_bytes()))
    controls = dict(full=baseline["full"]["arms"], named=baseline["named"]["arms"], target=target["terminal"]["arms"],
                    hindsight=oracle["terminal"]["arms"], causal=terminal["arms"])
    comparisons = dict(full=baseline["full"]["selected_rows"], target=target["selected_rows"],
                       hindsight=oracle["research"]["selected_rows"])
    owners = {arm: {name: owner_delta(rows[arm], report["selected_rows"][arm]) for name, rows in comparisons.items()}
              for arm in ARMS}
    purchased = set(seal["audit"]["bought_positive_observation_ids"])
    bought_owner_counts = {arm: len(purchased & {r[0] for r in report["selected_rows"][arm]}) for arm in ARMS}
    refs = read(checked(REFERENCE, REFERENCE_SHA256))
    ref, = (row["reference"] for row in refs["cases"] if row["dataset_label"] == DENSE
            and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    truth = [ref[k] for k in ("latitude_deg", "longitude_deg")]
    arms = {n: {a: dict(error_km=distance_km(truth, row["latlon"]) if row["latlon"] else None,
                          rf_rms_hz=row.get("rf_rms_hz")) for a, row in pairs.items()} for n, pairs in controls.items()}
    deltas = {n: {a: arms["causal"][a]["error_km"]-arms[n][a]["error_km"] for a in ARMS}
              for n in ("full", "named", "target", "hindsight")} if complete else {}
    pass_science = complete and all(v <= .250 for n in ("full", "named") for v in deltas[n].values())
    coverage = read(checked(MEASURES / "causal-mask-recovery-score.json", SCREEN_SHA))
    charged, = (r for r in coverage["cases"][DENSE]["rows"] if r["rule"] == "recent" and r["fraction"] == [3, 8])
    if charged["recovered_calls"] != seal["audit"]["purchased_short_lanes"] or coverage["selected"] is not None:
        raise ValueError("Unexpected coverage-study result")
    write(output, dict(timing=timing, seal=seal, terminal=terminal, research=report, figures=figures,
          timed_graph=read(directory / "timed-graph.json"), arms=arms, error_deltas_from_controls=deltas,
          within_position_allowance=pass_science, owners=owners, bought_owners_selected=bought_owner_counts,
          receiver_projection=charged, reference_sha256=REFERENCE_SHA256, raw_waveform_calls=0,
          prior_solve={"full": baseline["full"]["solve"], "target": target["solve"], "hindsight": oracle["research"]["solve"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run").add_argument("root", type=Path)
    audit = commands.add_parser("score")
    audit.add_argument("root", type=Path)
    audit.add_argument("output", type=Path)
    args = vars(parser.parse_args())
    {"run": run, "score": score}[args.pop("command")](**args)
