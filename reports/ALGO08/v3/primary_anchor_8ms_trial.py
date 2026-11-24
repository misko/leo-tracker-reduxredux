"""Prove the installed first rank on one physical member and time one North run."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from primary_anchor_8ms import ARTIFACT, RECIPE_FIELD, bound_library, definition, first_only


PROTOCOL = HERE/"primary-anchor-8ms-protocol.md"
PREFIX_CONTROL = Path("/dev/shm/leo-v3-eight-ms-native-prefix01/history8/scope-receipt.json")
PREFIX_CONTROL_SHA = "aa771508c98f083653bb224fd369aef0a40adc7b3c5bb75b108dd474fe0b2675"
NORTH_CONTROL = HERE/"measurements/eight-ms-native-live.json.gz"
NORTH_CONTROL_SHA = "2604afe118cebc24fa4fb0a975a439e5a6e9c2858ca4ae793dbc5b7f7afe7b9d"
SOURCES = tuple(HERE/name for name in ("primary_anchor_8ms_trial.py", "primary_anchor_8ms.py", "eight_ms_native_receiver.py",
                                      "mixed_aperture_receiver.py", "combined_raw_research.py", "unified_short_bootstrap.py"))


def pin(path):
    return sha256(path.read_bytes()).hexdigest()


def verified_rank_zero(full, first):
    return tuple(row for row in full if row[0] == 0) == first


def prefix_worker(root):
    import mixed_aperture_receiver as mixed
    from combined_raw_research import native_eight
    from continued_cfo_first_0016 import worker, write
    from eight_ms_native_live import EIGHT
    import eight_ms_native_receiver as selector
    import numpy as np
    from primary_anchor_8ms import AnchorPrimaryMixer

    trace = []
    original = AnchorPrimaryMixer.detector
    prepare = selector.prepare

    @contextmanager
    def scoped(self, method, edge, *, binary, pilot):
        with ExitStack() as scope:
            receive = scope.enter_context(original(self, method, edge, binary=binary, pilot=pilot))
            pilot_data = np.frombuffer(mixed.verified(pilot, mixed.PILOT_SHA[edge]), dtype="<f4")
            full = mixed.NativePath(binary,pilot_data,"full")
            scope.callback(full.close)
            first = first_only(mixed.NativePath(binary,pilot_data,"full"), bound_library(ARTIFACT))
            scope.callback(first.close)
            chronology = mixed.StereoSchedule(full_coverage=True)

            def audited(window):
                target, capture = window.target, window.acquisition
                _, mode = chronology.visit(edge,target,capture)
                rows = receive(window)
                center = target["rf_center_hz"]-target["lnb_lo_hz"]-capture["actual_if_center_hz"]
                for lane, row in zip(window.receiver_ids, rows, strict=True):
                    order = ((full,first) if (len(trace)//2 + lane)%2 else (first,full))
                    paid = {engine:engine.run(window.samples,lane,center) for engine in order}
                    native_full, full_time = paid[full]
                    native_first, first_time = paid[first]
                    trace.append(dict(visit=row["visit_index"], radio=lane, anchor=mode=="full",
                                      full=native_full, first=native_first, full_clock_ns=full_time,
                                      first_clock_ns=first_time, full_first=order[0] is full,
                                      exact_rank0=verified_rank_zero(native_full,native_first)))
                return rows
            yield audited

    def alternative(argv, seal):
        def observe(native, recipe, session, inventory, receipt_file):
            packet, effective, detector, route = prepare(native, recipe, session, inventory, receipt_file)
            probes = native["source"]["probes"]
            seal(packet,session,inventory,detector,recipe=effective,original=probes,acquired=probes,route=route,paid=[])

        argv[argv.index("--short-binary")+1] = str(EIGHT)
        with patch.object(selector,"prepare",observe), patch.object(AnchorPrimaryMixer,"detector",scoped):
            native_eight([*argv,"--full-anchor-primary-library",str(ARTIFACT)])

    worker("history8",root,launch_alternative=alternative)
    write(root/"lane-audit.json",trace)


def prefix(root):
    from continued_cfo_first_0016 import mapped_files, read, resident, write
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE, checked
    from primary_anchor_8ms import SOURCE_SHA256
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    control = json.loads(checked(PREFIX_CONTROL,PREFIX_CONTROL_SHA))
    checked(ARTIFACT.with_suffix(".c"),SOURCE_SHA256)
    bound_library(ARTIFACT)
    chunk, files = mapped_files()
    before = resident(files)
    root.mkdir()
    (root/"tmp").mkdir()
    command = [RELEASE/"venv/bin/python","-IB",Path(__file__),"prefix-worker",root/"candidate"]
    write(root/"binding.json", dict(machine=host(), before=before, chunk=chunk, command=list(map(str,command)),
                                    native_anchor=definition(), protocol_sha256=pin(PROTOCOL), sources={x.name:pin(x) for x in SOURCES}))
    clock = measure(command,environment(root)|{"TMPDIR":str(root/"tmp")},root/"candidate")
    write(root/"clock.json",clock)
    after = resident(files)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])
    scope = read(root/"candidate/scope-receipt.json")
    rows = read(root/"candidate/lane-audit.json")
    if (any(scope[k] != control[k] for k in ("iq","opened","prefix_inventory","original_segment_inventory"))
            or len(rows) != len(scope["original_probes"]) or any(
                (row["visit"],row["radio"]) != (p["visit_index"],p["receiver_id"])
                for row,p in zip(rows,scope["original_probes"],strict=True)) or scope["recipe"][RECIPE_FIELD] != definition()
            or scope["position_runs"]):
        raise ValueError("The one-member trial failed original source or new receiver binding")
    changes = Counter()
    for audit,before_row,after_row in zip(rows,control["original_probes"],scope["original_probes"],strict=True):
        if any(before_row[key]!=after_row[key] for key in before_row if key!="candidates"):
            raise ValueError("A native trial changed original timing or radio metadata")
        before_factor, after_factor = before_row["candidates"], after_row["candidates"]
        changes["anchor" if audit["anchor"] else "short"] += int(before_factor!=after_factor)
    clocks = {label:{kind:sum(row[key+"_clock_ns"][i] for row in rows if label=="all" or row["anchor"])/1e9
                     for key in ("full","first") for i,metric in enumerate(("cpu_s","elapsed_s")) for kind in (key+"_"+metric,)}
              for label in ("all","anchor")}
    write(root/"result.json",dict(resident_before=before,resident_after=after,clock_with_extra_audit_calls=clock,
         rank_zero_equal=sum(r["exact_rank0"] for r in rows), lanes=len(rows), rank_zero_empty=sum(not r["first"] for r in rows),
         two_scan_empty=sum(not r["full"] for r in rows), residual_without_rank0=sum(not r["first"] and bool(r["full"]) for r in rows),
         two_scan_rank1=sum(any(x[0]==1 for x in r["full"]) for r in rows),anchor_lanes=sum(r["anchor"] for r in rows),
         scoped_raw_authority=read(root/"candidate/detections.json")["source"]["raw_recording_authority_digest"],
         window_sha256=scope["iq"], changed_emitted=dict(changes),
         original_native_sha256=control["native_sha256"], native_sha256=scope["native_sha256"], native_clock=clocks,
         prior_held_choice=control["held_choice"]["choice"], current_held_choice=scope["held_choice"]["choice"],
         committed_zero_tail_calls=scope["held_choice"]["refinement_calls"], lane_audit_sha256=pin(root/"candidate/lane-audit.json"),
         admit_north=all(r["exact_rank0"] for r in rows) and not changes["short"]))


def north(root, prefix_result, primary=True):
    from combined_raw_trial import PRODUCER, checked_producer, flags
    from continued_cfo_first_0016 import read, write
    from eight_ms_native_live import EIGHT
    from joint_held_north_raw import launch
    from north_orbit_index_trial import admitted_inputs

    gate = read(prefix_result)
    if not gate["admit_north"] or gate["lanes"]!=116 or gate["committed_zero_tail_calls"]:
        raise ValueError("Exact physical rank zero is required before the one North raw trial")
    controls,census = admitted_inputs()
    checked_producer(controls["binding"]["request"]["cutoff_utc_ns"],census["72"]["body_digests"])
    bound_library(ARTIFACT)
    anchor_flags = ("--full-anchor-primary-library",str(ARTIFACT)) if primary else ()
    launch(root,continued=True,entrypoint=HERE/"combined_raw_research.py",trial_protocol=PROTOCOL,extra_sources=SOURCES,
           experiment_flags=[*flags(PRODUCER),*anchor_flags],native_eight_binary=EIGHT)
    write(root/"prefix-gate.json",dict(prefix_sha256=pin(prefix_result),gate=gate,real_anchor_helper=definition()))


def north_pair(root, prefix_result):
    from continued_cfo_first_0016 import write

    root.mkdir()
    order = ("primary-anchor","full-anchor")
    write(root/"pair.json",dict(order=order,sole_changed_option="--full-anchor-primary-library",
                               prefix_sha256=pin(prefix_result),native_anchor_helper=definition()))
    for mode in order:
        north(root/mode,prefix_result,primary=mode=="primary-anchor")


def verify(root):
    from anchor_exposure import bind
    from continued_cfo_first_0016 import read, write
    from continued_cfo_trial import rebinding
    from eight_ms_native_score import NORTH_ORIGINAL, same_images, unchanged_history
    from empty_bootstrap import checked
    from joint_held_north_raw import require_resident
    from leo.contracts.digests import canonical_digest
    from preloaded_saved_score import science
    from primary_anchor_8ms import anchor_witness
    from prospective_0316_solver import owner_delta
    from raw_cfo_north_trial import native_file
    from tools.pipeline_eval.qualification.paired_publication import evidence

    from whole_stereo_blocks import load_checked

    old = load_checked(NORTH_CONTROL,NORTH_CONTROL_SHA)
    (parent,) = Path("/dev/shm/leo-eight-ms-north/8ms/fast-scan-automatic-work").glob("*/detections.json")
    control = json.loads(checked(parent,NORTH_ORIGINAL[7:]))
    previous = anchor_witness(control)
    path = root/"containing"
    binding, clock = (read(root/name) for name in ("binding.json","clock.json"))
    request = binding["request"]
    for name,file_pin in binding["source_sha256"].items():
        checked(HERE/name,file_pin)
    cache = {stage:read(root/f"cache-{stage}.json") for stage in ("before","after")}
    for snapshots in cache.values():
        for snapshot in snapshots.values():
            require_resident(snapshot)
    bootstrap, research = (read(path/name) for name in ("unified-short-bootstrap.json","joint-research-receipt.json"))
    receipt = bootstrap["receipt"]
    selected = json.loads(checked(native_file(path),bootstrap["native_sha256"][7:]))
    bind(control,selected)
    observed = bootstrap["held_anchor_route"]
    measurements = observed["full_anchor_measurements"]
    if (clock["exit_code"] or bootstrap["raw_acquisitions"]!=1 or bootstrap["verified_handoffs"]!=1
            or bootstrap["requested_offer_sha256"]!=request["inside_offer_sha256"]
            or bootstrap["archive_root"]!=request["archive"]["root"] or bootstrap["causal_cutoff_utc_ns"]!=request["cutoff_utc_ns"]
            or bootstrap["receiver_recipe"][RECIPE_FIELD]!=definition()
            or canonical_digest(bootstrap["receiver_recipe"])!=bootstrap["detector_recipe_sha256"]
            or bootstrap["receiver_audit"]["native"]["native_calls"]!={"full":304,"short_primary":2096}
            or observed["refinement_calls"] or measurements["short_probes_sha256"]!=previous["short_probes_sha256"]
            or measurements["ordered_metadata_sha256"]!=previous["ordered_metadata_sha256"]
            or observed["parent_native_sha256"]==NORTH_ORIGINAL):
        raise ValueError("North must execute the original raw work with the bound independent first-scan anchor")
    changes = [dict(previous=before,actual=after) for before,after in zip(previous["anchors"],measurements["anchors"],strict=True) if before!=after]
    modified = { (p["visit_index"],p["receiver_id"]):p for p in measurements["anchors"] }
    proposals = [modified.get((p["visit_index"],p["receiver_id"]),p) for p in control["source"]["probes"]]
    unchanged_history(proposals,selected["source"]["probes"],observed)
    parent_recipe = dict(bootstrap["receiver_recipe"])
    parent_recipe.pop("held_native_8ms")
    if canonical_digest(rebinding(control,proposals,parent_recipe))!=observed["parent_native_sha256"]:
        raise ValueError("The actual first-scan measurements do not reconstruct the bound parent native bytes")
    common = old["scientific_seal"]
    orig = common["science"]
    stock = evidence(path,receipt,clock["started_unix_ns"],read_only=True)
    if stock["raw_authority"]!=request["authority"] or receipt["region"]!=orig["identity"]["original_offer"]:
        raise ValueError("North original authority or offer changed")
    actual = None
    if receipt["decision"]=="complete":
        actual = science(path,receipt,clock,dict(orig["identity"],native_sha256=bootstrap["native_sha256"]))
    rank,orbit = (read(root/f) for f in ("catalogue-block-rank.json","orbits-indexed.json"))
    transfer, = orbit["transfers"]
    if (not rank["requested"] or transfer["compatibility"]["fallback"] or transfer["loading"]["fallback"]
            or not transfer["counts"]["sidecar_hit_bodies"]):
        raise ValueError("The measured North process did not use the original portable option and requested rank blocks")
    write(root/"seal.json",dict(original_receipt_sha256=NORTH_CONTROL_SHA,raw=bootstrap,graph=research["early_regional"],
         solve=research["solve"],route=research["route_details"],clock=clock,cache=cache,rank=rank,orbit=orbit,
         terminal=stock,science=actual,changed_anchors=changes,old_clock=common["clock"],old_raw=common["raw"],
         old_positions=old["position_score"]["outcomes"],unchanged_short_probes=2096,
         exact_with_prior=None if actual is None else dict(arms=actual["arms"]==orig["arms"],roles=actual["roles"]==orig["roles"],
            grid_path=actual["grid_and_path"]==orig["grid_and_path"],figures=same_images(actual["images"],orig["images"])),
         owners=None if actual is None else {a:owner_delta(orig["roles"][a],actual["roles"][a]) for a in actual["roles"]}))


def score(root):
    from continued_cfo_first_0016 import read, write
    from eight_ms_held_score import geographic_reference
    from eight_ms_native_score import outcome

    seal = read(root/"seal.json")
    reference, sha = geographic_reference("north")
    actual = seal["science"]
    values = outcome(actual["arms"],actual["identity"]["original_offer"],reference) if actual else None
    write(root/"score.json",dict(seal_sha256=pin(root/"seal.json"),truth_sha256=sha,primary=values,controls=seal["old_positions"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action",required=True)
    for action in ("prefix-worker","prefix","north-pair","verify","score"):
        cli = sub.add_parser(action)
        cli.add_argument("root",type=Path)
        if action=="north-pair":
            cli.add_argument("prefix_result",type=Path)
    args = vars(parser.parse_args())
    {"prefix-worker":prefix_worker,"prefix":prefix,"north-pair":north_pair,"verify":verify,"score":score}[args.pop("action")](**args)
