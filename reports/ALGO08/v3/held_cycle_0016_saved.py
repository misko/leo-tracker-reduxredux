"""Apply the held-cycle-before-CFO selector to actual paired original 0016 detections."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

BASE = "3a2825dbf42e31fb692667957e4f2aca5bab3e87"
SOURCE_NAMES = ("held_cycle_refined.py", "unified_short_bootstrap.py", "joint_publication.py", "short_cfo_raw.py",
                "empty_family_calibration.py", "anchor_cycle_route.py", "held_anchor_route_publication.py")
MIXED = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
MIXED_SEAL = "e011f66be6db6f04473cc7be701ca30979c5af358e54f71cba9daf9b18783b6f"
REFINED = Path("/dev/shm/leo-v3-raw-cfo-0016-result03")
REFINED_SEAL = "7fd4978443af6de439cfc60d53f2660ff2fd64dd95494f3dd2877d9592563d3b"
GUARDED_PACK = Path("/dev/shm/leo-anchored-cfo-raw-pack01")
PACK_SHA = "0d590b0c7e4ffc468fb17804146362b8534d33d115d83055ae7bbc1dafd967a9"
ARMS = ("c0", "fitted_c")


def digest(data):
    return sha256(data).hexdigest()


def pinned_sources():
    from empty_bootstrap import checked

    repo = HERE.parents[2]
    sources = {}
    for name in SOURCE_NAMES:
        path = HERE/name
        body = subprocess.check_output(["git", "-c", f"safe.directory={repo}", "-C", repo, "show", f"{BASE}:{path.relative_to(repo)}"])
        sources[name] = digest(body)
        checked(path, sources[name])
    return sources


def bundle(root, seal_pin, mode):
    from empty_bootstrap import checked

    seal = json.loads(checked(root/"prediction-seal.json", seal_pin))

    def sealed(name):
        paths = [path for path in seal if path.startswith(mode+"/") and Path(path).name == name]
        (relative,) = paths or [name]
        return checked(root/relative, seal[relative])

    return sealed


def witness(original, refined, recorded_attempts):
    from held_cycle_refined import CFO, FrequencyChanges
    from mixed_aperture_receiver import FULL_RULE

    change = FrequencyChanges()
    stream_counts = Counter()
    previous_stream = None
    before_rows, after_rows = (native["source"]["probes"] for native in (original, refined))
    for index, (before, after) in enumerate(zip(before_rows, after_rows, strict=True)):
        receiver = before["receiver_id"]
        stream = (before["edge"], before["channel"], before["actual_rf_hz"])
        if (receiver != index % 2 or receiver == 1 and (stream, before["visit_index"]) != previous_stream
                or {k: v for k, v in before.items() if k != "candidates"} != {k: v for k, v in after.items() if k != "candidates"}):
            raise ValueError("The signed original stereo opportunities differ")
        previous_stream = stream, before["visit_index"]
        mode = FULL_RULE[stream_counts[stream] % len(FULL_RULE)]
        if receiver == 1:
            stream_counts[stream] += 1
        left, right = before["candidates"], after["candidates"]
        if mode == "full" or not left:
            if left != right:
                raise ValueError("Refinement changed an anchor or empty lane")
            continue
        (old,), (new,) = left, right
        if old != dict(new, **{CFO: old[CFO]}):
            raise ValueError("Refinement changed a signed factor field besides CFO")
        change.attempted += 1
        if old[CFO] != new[CFO]:
            key = before["visit_index"], receiver
            if key in change.changed:
                raise ValueError("Repeated signed receiver opportunity")
            change.changed[key] = old[CFO], new[CFO]
    if change.attempted != recorded_attempts or change.original_rows(after_rows) != before_rows:
        raise ValueError("Measured refinement witness failed to reproduce the original probes")
    return change


def timings(cpu, wall):
    return dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-wall)


def worker(root):
    import empty_bootstrap as staged

    started = process_time(), perf_counter()
    _, specification, _, publication, _ = staged.load_runtime()
    from aperture_trial import archive_identity, write
    from cumulative_grid_projection import saved_inventory_port
    from full_short_run import RECIPE_SHA, checked_recipe
    from held_cycle_refined import select_refined
    from leo.contracts.digests import canonical_digest
    from short_cfo_raw import recipe
    from short_graph_guard import prove
    from unified_short_bootstrap import Handoff, publish_active

    source = pinned_sources()
    mixed, refined = (bundle(base, pin, "candidate") for base, pin in ((MIXED, MIXED_SEAL), (REFINED, REFINED_SEAL)))
    first, second = (json.loads(item("admission.json")) for item in (mixed, refined))
    same = ("raw_authority", "recording", "session", "inventory", "cutoff_utc_ns", "archive", "offer", "offer_sha256", "manifests")
    if any(first[key] != second[key] for key in same):
        raise ValueError("The archived receiver arms do not identify the same original recording and offer")
    session, inventory = second["session"], second["inventory"]
    offer, archive = REFINED/"offer.json", REFINED/"tle"
    staged.checked(offer, second["offer_sha256"])
    if archive_identity(archive)["snapshots_sha256"] != second["archive"]["sha256"]:
        raise ValueError("Original causal archive changed")
    libs = {key: REFINED/(key+".so") for key in second["library_sha256"]}
    for key, path in libs.items():
        staged.checked(path, second["library_sha256"][key])
    control, measured = (json.loads(item("detections.json")) for item in (mixed, refined))
    boot = json.loads(refined("unified-short-bootstrap.json"))
    recipe_value = recipe(checked_recipe(), RECIPE_SHA)
    pin = canonical_digest(recipe_value)
    if boot["receiver_recipe"] != recipe_value or boot["detector_recipe_sha256"] != pin or boot["raw_acquisitions"] != 1 or boot["verified_handoffs"] != 1:
        raise ValueError("The fixed-epoch donor was not the exact signed refined raw acquisition")
    for packet, detector in ((control, RECIPE_SHA), (measured, pin[7:])):
        staged.bind_native(packet, session, inventory, detector)
        if (packet["source"]["raw_recording_authority_digest"] != second["raw_authority"]
                or packet["clock_anchor"]["before"]["realtime_ns"] != second["cutoff_utc_ns"]
                or len(packet["source"]["probes"]) != 2*second["admitted"]):
            raise ValueError("A donor does not bind the genuine observed original recording")
    audit = boot["receiver_audit"]["native"]["cfo_refinement"]["lanes"]
    begin = process_time(), perf_counter()
    changes = witness(control, measured, sum(row["counts"]["attempted"] for row in audit))
    offline = timings(*begin)
    if len(changes.changed) != sum(row["counts"]["changed"] for row in audit):
        raise ValueError("The receiver audit and observed set of CFO changes disagree")
    begin = process_time(), perf_counter()
    selected, selected_recipe, detector, detail = select_refined(measured, recipe_value, changes, session, inventory, root/"choice.json")
    selector = timings(*begin)
    original_probe_digest = canonical_digest(control["source"]["probes"])
    if detail["pre_refinement_probes_sha256"] != original_probe_digest or canonical_digest(selected_recipe) != "sha256:"+detector:
        raise ValueError("The selector did not use the genuinely measured pre-refinement probes")
    write(root/"selected-packet.json", selected)
    write(root/"selector-clock.json", dict(timing=selector, offline_witness_reconstruction=offline,
          measured_attempts=changes.attempted, measured_changes=len(changes.changed), original_probe_digest=original_probe_digest))
    proof = prove(selected, staged.RELEASE/"assets", use_time_support=True, use_curvature_extent=True)
    if proof["proven"]:
        raise ValueError("Saved positive timing comparison unexpectedly requires the empty-Graph publication route")
    target = root/"candidate"
    saved_inventory = REFINED/"candidate/fast-scan-inputs"/(session+".json")
    staged.checked(saved_inventory, inventory[7:])
    request = dict(recording=second["recording"], session=session, inventory=inventory, saved_inventory=str(saved_inventory))
    args = SimpleNamespace(recording=Path(second["recording"]), archive=archive, region=offer, output=target,
          one_pass_web_png=True, exact_graph_reuse=True, reuse_verified_png_reads=True, direct_residual_figures=True,
          direct_orbit_figures=True, named_survivor_finish=True, withhold_empty_family_calibration=True,
          geographic_library=libs["geographic"], regional_track_library=libs["regional"], frontier_block_library=libs["block"],
          grid_feature_projection_library=libs["projection"])
    handoff = Handoff(session, inventory, detector, selected)
    graph, png, layout = {}, {}, {}
    begin = process_time(), perf_counter()
    with saved_inventory_port(request):
        receipt, research = publish_active(args, publication, specification, handoff, layout, graph_audit=graph,
             png_read_audit=png, no_active_curvature_sha256=proof["curvature_extent"].get("native_sha256"))
    if handoff.calls != 1 or research["input"] != "authenticated saved mixed 20/12 ms acquisition":
        raise ValueError("Expected one authenticated metadata-only detector handoff")
    write(root/"worker.json", dict(base=BASE, sources=source, receipt=receipt, full_saved=timings(*started),
          publication=timings(*begin), graph=graph, proof=proof, png=png, layout=layout, handoff_calls=handoff.calls,
          waveform_reads=0, measured_native=canonical_digest(measured), original_native=canonical_digest(control)))


def seal(root):
    paths = [path for path in root.rglob("*") if path.is_file() and path.name != "prediction-seal.json"
             and path.relative_to(root).parts[0] not in ("fonts", "tmp")]
    return {str(path.relative_to(root)): digest(path.read_bytes()) for path in sorted(paths)}


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE, checked
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Expected fresh tmpfs outputs")
    checked(GUARDED_PACK/"pack.json", PACK_SHA)
    for name, pin in json.loads((GUARDED_PACK/"pack.json").read_bytes())["libraries"].items():
        checked(GUARDED_PACK/name, pin)
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root/name).mkdir()
    for font in (REFINED/"fonts").glob("fontlist-*.json"):
        (root/"fonts"/font.name).write_bytes(font.read_bytes())
    env = environment(root)
    env.update(TMPDIR=str(root/"tmp"), XDG_CACHE_HOME=str(root/"tmp"))
    argv = [RELEASE/"venv/bin/python", "-IB", __file__, "worker", root]
    clock = measure(argv, env, root/"candidate")
    write(root/"clock.json", dict(clock=clock, command=list(map(str, argv)), machine=machine, staged_pack_sha256=PACK_SHA))
    write(root/"prediction-seal.json", seal(root))
    if clock["exit_code"]:
        raise ValueError(clock["stderr_tail"])


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("launch", "worker"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    globals()[args.mode](args.root)
