"""Price selective CFO on two sealed receivers and publish one saved weak fix."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
WEAK = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
REFINED_WEAK = Path("/dev/shm/leo-v3-raw-cfo-0016-result03/candidate")
NORTH = Path("/dev/shm/leo-eight-ms-north/12ms")
REFINED_NORTH = Path("/dev/shm/leo-v3-north-cfo-final-03/containing")
INPUTS = {
    "weak": (WEAK/"candidate", "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589",
             REFINED_WEAK, "059b428e1b2fb38ff2bd098c4a647712b8813455597a64330a4bcfc739def4d5"),
    "north": (NORTH, "2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427",
              REFINED_NORTH, "83e68ceebbcc803a0d2a811da9d3f3d997c7a4e42378fcb702d0ce85afd9c4d2"),
}
EARLIER = "115a6593161c752f09ceee99c29612c0ba353384b8e4796d0e5adfff05cdf90e"
SEALED_PRICE = "25c515e90936e4e03fe858dd0070356bafb3fea84ef492d9bcc8bc629f13b232"
INSTALL = ("geographic", "regional", "block", "projection")
LIBRARY_ARGUMENTS = dict(zip(INSTALL, ("geographic_library", "regional_track_library",
                                       "frontier_block_library", "grid_feature_projection_library"), strict=True))


def rebinding(native, rows, spec):
    from leo.contracts.digests import canonical_digest

    detector = canonical_digest(spec)
    analysis = canonical_digest(["cancellation", native["source"]["raw_recording_authority_digest"], detector[7:], rows])
    return dict(native, source=dict(native["source"], probes=rows, analysis_manifest_sha256=analysis),
                provenance=dict(native["provenance"], detector_sha256=detector, run_id="blind-compact-"+analysis[7:39]))


def price(name, output):
    from anchor_exposure import bind, enroll, packet
    from anchor_holds import history_rows
    from continued_cfo import ContinuedChanges, lane_key, recipe, select_paid
    from empty_bootstrap import bind_native, checked
    from full_short_run import RECIPE_SHA
    from held_cycle_refined import CFO, FACTOR_FIELDS
    from leo.contracts.digests import canonical_digest

    original, pin, refined, bootstrap_pin = INPUTS[name]
    original_doc = packet(original, pin)
    receipt = json.loads(checked(refined/"unified-short-bootstrap.json", bootstrap_pin))
    refined_doc = packet(refined, receipt["native_sha256"][7:])
    bind(original_doc, refined_doc)
    source = original_doc["source"]
    session, inventory = source["session_id"], source["input_manifest_sha256"]
    bind_native(original_doc, session, inventory, RECIPE_SHA, expected="sha256:"+pin)
    refined_recipe = receipt["receiver_recipe"]
    refiner_pin = canonical_digest(refined_recipe)
    if refiner_pin != receipt["detector_recipe_sha256"]:
        raise ValueError("All-paid refinement receipt lost its genuine receiver identity")
    bind_native(refined_doc, session, inventory, refiner_pin[7:], expected=receipt["native_sha256"])

    gate = ContinuedChanges()
    gate.by_attempt = {}
    old = source["probes"]
    future_values = refined_doc["source"]["probes"]
    counters, new, lanes = Counter(), [], []
    by_radio = {0: Counter(), 1: Counter()}
    started = process_time(), perf_counter()
    for row, refined_row, event in zip(old, future_values, enroll(original_doc), strict=True):
        short = event[4] == "short"
        paid = gate.consider(row, short)
        a, b = row["candidates"], refined_row["candidates"]
        if len(a) != len(b) or (not short and a != b):
            raise ValueError("Genuine fixed-epoch refinement changed admission or an original full anchor")
        changed = False
        if a:
            (previous,), (altered,) = a, b
            if {k:v for k,v in previous.items() if k != CFO} != {k:v for k,v in altered.items() if k != CFO}:
                raise ValueError("The authenticated refined packet changed another measurement field")
            changed = previous[CFO] != altered[CFO]
            if paid and changed:
                gate.by_attempt[gate.attempted] = previous[CFO], tuple(altered[k] for k in FACTOR_FIELDS)
        gate.attempted += int(paid)
        new.append(refined_row if paid else row)
        fields = dict(probes=1, short_positives=int(short and bool(a)), attempts=int(paid),
                      saved_attempts=int(short and bool(a) and not paid), all_paid_edits=int(changed),
                      kept_edits=int(paid and changed), removed_edits=int(changed and not paid))
        counters.update(fields)
        by_radio[row["receiver_id"]].update(fields)
        if a and short:
            lanes.append(dict(visit=lane_key(row)[0], radio=lane_key(row)[1], paid=paid,
                              original=a[0][CFO], all_paid=b[0][CFO]))
    replay = dict(cpu_s=process_time()-started[0], elapsed_s=perf_counter()-started[1])
    all_paid = receipt["receiver_audit"]["native"]["cfo_refinement"]
    if (sum(row["counts"]["attempted"] for row in all_paid["lanes"]) != counters["short_positives"]
            or sum(row["counts"]["changed"] for row in all_paid["lanes"]) != counters["all_paid_edits"]):
        raise ValueError("Saved lane census differs from the actual all-paid receiver audit")
    filtered_recipe = recipe(refined_recipe)
    partial = rebinding(original_doc, new, filtered_recipe)
    final, selected_recipe, detector, decision = select_paid(partial, filtered_recipe, gate, session, inventory,
                                                              output/f"{name}-choice.json")
    held = decision["choice"]["route"] == "history"
    if held:
        selected = history_rows(old)
        control = [after if prior["candidates"] else dict(after, candidates=[])
                   for prior, after in zip(selected, future_values, strict=True)]
        if final["source"]["probes"] != control:
            raise ValueError("History discarded a paid refinement or used a rejected lane")
    else:
        control = future_values
        if final["source"]["probes"] != new:
            raise ValueError("The unfiltered route dropped an original admitted observation")
    from leo.storage.fast_scan import immutable_json

    final_path = output/f"{name}-selected-native.json"
    immutable_json(final_path, final)
    if sha256(final_path.read_bytes()).hexdigest() != decision["selected_native_sha256"][7:]:
        raise ValueError("Saved publication handoff differs from the selected native packet")
    return dict(route=decision["choice"]["route"], choice=decision["choice"], detector_sha256="sha256:"+detector,
                native_sha256=canonical_digest(final), packet=str(final_path), recipe=selected_recipe,
                all_paid_native=receipt["native_sha256"], original_native="sha256:"+pin,
                selected_probes_sha256=canonical_digest(final["source"]["probes"]),
                all_paid_on_same_route_probes_sha256=canonical_digest(control),
                identical_all_paid_payload=final["source"]["probes"] == control, counts=counters, by_radio=by_radio,
                selected=decision["selected"], replay=counters | dict(saved_replay_clock=replay),
                original_all_paid_refinement_cpu_ns=all_paid["cpu_ns"], original_all_paid_refinement_wall_ns=all_paid["wall_ns"],
                paid_lane_cfo=lanes, input_session=session, input_inventory=inventory)


def work(root):
    import empty_bootstrap as staged
    import unified_short_bootstrap as entry

    started = staged.now()
    _, spec, _sources, publication, checks = staged.load_runtime()
    from aperture_trial import read, write
    from cumulative_grid_projection import saved_inventory_port
    from leo.analysis.glrt_frequency_input import frequency_evidence
    from leo.contracts.digests import canonical_digest
    from local_future_cli_trial import native_packet
    from raw_0016_best_trial import FLAGS
    from short_graph_guard import prove

    job = read(root/"binding.json")
    source, target = job["saved"], root/"selective"
    detector = canonical_digest(source["recipe"])
    if detector != source["detector_sha256"]:
        raise ValueError("Selected candidate recipe changed before the one saved solve")
    packet = json.loads(staged.checked(Path(source["packet"]), source["native_sha256"][7:]))
    staged.bind_native(packet, job["session"], job["inventory"], detector[7:], expected=source["native_sha256"])
    args = SimpleNamespace(recording=Path(job["recording"]), archive=Path(job["archive"]), region=Path(job["offer"]),
                           output=target, **{flag[2:].replace("-","_"): True for flag in FLAGS},
                           **{k: Path(p) for k,p in job["libraries"].items()})
    handoff = entry.Handoff(job["session"], job["inventory"], detector[7:], packet)
    graph, layout, png = {}, {}, {}
    with saved_inventory_port(job) as ready:
        reason = staged.empty_reason(packet, frequency_evidence)
        proof = None if reason else prove(packet, staged.RELEASE/"assets", use_time_support=True, use_curvature_extent=True)
        if reason or proof["proven"]:
            raise ValueError("The enrolled one active publication did not have its bound original graph support")
        receipt, detail = entry.publish_active(args, publication, spec, handoff, layout, graph_audit=graph, png_read_audit=png,
                                     no_active_curvature_sha256=proof.get("curvature_extent", {}).get("native_sha256"))
    if (not ready or handoff.calls != 1 or native_packet(target).read_bytes() != Path(source["packet"]).read_bytes()):
        raise ValueError("Expected the selected saved native bytes through exactly one handoff")
    write(target/"continued-cfo-worker.json", dict(receipt=receipt, solve=detail["solve"], graph=graph, layout=layout,
          named_finish=detail["named_survivor_finish"], projection=detail["grid_feature_projection"], png=png, proof=proof,
          waveform_calls=0, handoffs=handoff.calls, pins=checks, complete_saved=staged.clock(started)))


def run(root, price_from=None):
    from aperture_trial import RELEASE, read, write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import owner_delta
    from raw_0016_best_trial import ARCHIVE, INVENTORY
    from short_raw_diagnostic import measure, pairs
    from triage_bounds import calibration_comparison

    machine = host()
    if root.resolve().parent != Path("/dev/shm"):
        raise ValueError("Use fresh tmpfs scientific outputs")
    root.mkdir()
    prices = ({name: price(name, root) for name in INPUTS} if price_from is None
              else json.loads(checked(price_from, SEALED_PRICE)))
    weak, north = prices["weak"], prices["north"]
    if weak["route"] != "unfiltered" or north["route"] != "history" or not north["identical_all_paid_payload"]:
        raise ValueError("Unexpected held-cycle route. Stop at the sealed saved policy price.")
    write(root/"price-seal.json", prices)
    admission = read(WEAK/"admission.json")
    if weak["input_inventory"] != INVENTORY or pairs.archive_identity(WEAK/"tle")["snapshots_sha256"] != ARCHIVE:
        raise ValueError("The saved scientific inputs do not bind the existing weak authority")
    session = weak["input_session"]
    offer = WEAK/"offer.json"
    checked(offer, admission["offer_sha256"])
    inventory = WEAK/"candidate/fast-scan-inputs"/(session+".json")
    checked(inventory, INVENTORY[7:])
    libraries = {LIBRARY_ARGUMENTS[k]: str(WEAK/f"{k}.so") for k in INSTALL}
    for k in INSTALL:
        checked(WEAK/f"{k}.so", admission["library_sha256"][k])
    write(root/"binding.json", dict(recording=admission["recording"], archive=str(WEAK/"tle"), offer=str(offer),
          saved_inventory=str(inventory), libraries=libraries, saved=weak, session=session, inventory=INVENTORY))
    (root/"tmp").mkdir()
    env = environment(root)
    env["TMPDIR"] = str(root/"tmp")
    python = RELEASE/"venv/bin/python"
    subprocess.run([python,"-Bc","from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   check=True, env=env, timeout=30)
    target = root/"selective"
    clock = measure([python, "-IB", __file__, "worker", root], env, target)
    write(root/"worker-clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])
    worker = read(target/"continued-cfo-worker.json")
    r = worker["receipt"]
    actual = pairs.evidence(target, r, clock["started_unix_ns"], read_only=True)
    media = artifacts(target, r)
    detail = read(target/"joint-research-receipt.json")
    if r["decision"] != "complete" or r["region"] != admission["offer"] or len(media["images"]) != 8:
        raise ValueError("The enrolled active saved publication did not produce its complete scientific evidence")
    store = FastStandardAnalysisStore(target)
    grid, path = (getattr(store, f"position_{key}")(r["run_id"]) for key in ("grid", "path"))
    if (not grid["complete"] or grid["evaluated_points"] != 179 or
            any(x["binding"]["position_png_sha256"] != media["images"]["position"]["sha256"] for x in (grid,path))):
        raise ValueError("Invalid published position evidence or real image bindings")
    # Scientific controls and survey are opened only after the new output is sealed.
    earlier = json.loads(gzip.decompress(checked(HERE/"measurements/raw-cfo-0016.json.gz", EARLIER)))
    references = {arm: earlier["runs"][arm] for arm in ("mixed", "refined")}
    earlier_arms = {label: value["science"] for label,value in references.items()}
    geography = calibration_comparison(earlier_arms | {"selective": actual}, "DS30-0016")
    owners = {name: {arm: owner_delta(value["research"]["selected_rows"][arm], rows)
                     for arm, rows in detail["selected_rows"].items()} for name,value in references.items()}
    write(root/"result.json", dict(machine=machine, prices=prices, process=clock, worker=worker, science=actual,
          images=media, owners=owners, owner_roles_sha256=canonical_digest(detail["selected_rows"]),
          geography=geography, original_control_receipt=EARLIER, newly_paid_raw_refinement_calls=0,
          resumed_price_sha256=SEALED_PRICE if price_from else None))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("run", "worker"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--price-from", type=Path)
    args = cli.parse_args()
    if args.mode == "worker":
        work(args.root)
    else:
        run(args.root, args.price_from)
