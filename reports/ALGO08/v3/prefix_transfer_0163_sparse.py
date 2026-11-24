"""Publish a saved original DS30-0163 packet with genuine first-member selections."""

import argparse
from functools import partial
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

from ds30_0163_composed_saved import TRANSFER_0163 as CASE, donor_sources
from prefix_transfer_0419 import ARMS, checked, lane_key, metadata, prefix_scope, read, signed_member, write
from prefix_transfer_0008 import digest


PROTOCOL = HERE / "0163-sparse-prefix-hybrid-protocol.md"
PAIR = Path("/tmp/leo-v3-0163-resumed-member-pair02")
PINS = {
    "result.json": "e70870dfa1832a1511a5109e20b7a576bc690024b0b5484ff30c0e23c2b405f9",
    "binding.json": "332607cbb9d30a8ffeb406a23b50c4419d77f6ec7c04c5cdb0668c139ef09931",
    "integrated-held-anchor-route.json": "c68eb6ecfedfc770e8d4f02327e15b759d757346f10d41d93ed6bb46fae82238",
    "integrated/detections.json": "8631fad91d1b9555baf22f752d2679d123244066d3e77100ba7bd6be5ac0945c",
    "named/fast-scan-automatic-work/algo08-v2-3c930ea608338c1f278e7879f165e57b/detections.json":
        "0a517f46e394b59649030dd836717c8bf18cb075eae8fcc48a1ad9c68cc946ce",
}
CLEAN = Path("/dev/shm/leo-v3-0163-composed-saved-result01")
CLEAN_PIN = "e08d702e92753fe2bc274c39f742815cc23b8be74415b3476a13b3b7bfac4573"
RESTORE = (61, 0, 6)
MODES = ("hybrid", "restore-singleton")
LABELS = dict(zip(MODES, (
    "saved original DS30-0163 all-20 with actual sparse 20/8 selections on first signed member",
    "saved DS30-0163 measured prefix hybrid restoring one original installed singleton",
), strict=True))


def ready_directory(root, mode):
    return root.with_name(f"{root.name}-{mode}-ready")


def measured_rows(full, named, measured):
    prefix = [row for row in full if row["visit_index"] < 64]
    if prefix != named or list(map(metadata, named)) != list(map(metadata, measured)):
        raise ValueError("Prefix order, installed factors, or original lane metadata disagree")
    replacement = {lane_key(row): row for row in measured}
    if len(replacement) != len(measured):
        raise ValueError("Expected one measured selection per signed lane")
    hybrid = [replacement.get(lane_key(row), row) for row in full]
    original, = [row for row in named if (*lane_key(row), row["channel"]) == RESTORE]
    changed = replacement[lane_key(original)]
    if len(original["candidates"]) != 1 or original == changed:
        raise ValueError("The original installed singleton must be unique and actually changed")
    restored = [original if lane_key(row) == lane_key(original) else row for row in hybrid]
    return hybrid, restored


def custody(bound, req):
    from continued_cfo_trial import rebinding
    from empty_bootstrap import bind_native
    from leo.contracts.digests import canonical_digest as canonical

    prior, binding, selector, measured, named = map(lambda name: json.loads(checked(PAIR/name, PINS[name])), PINS)
    source, = binding["scopes"].values()
    full = json.loads(checked(Path(req["native_file"]), req["native_sha256"]))
    inventory = json.loads(checked(Path(bound["inventory"]), req["inventory"]))
    witness = signed_member(Path(binding["source"]), inventory)
    measured_iq = [row["iq_sha256"] for row in witness["visits"]]
    raw, sparse = prior["authority"], selector["receiver_recipe"]
    prefix_inventory = source["inventory"]
    prefix_cutoff = binding["original"]["cutoff_utc_ns"]
    prefix_recipe = {key: value for key, value in sparse.items() if key != "held_native_8ms"}
    if (not prior["qualified"] or prior["solver_workers"] or prior["backing_waveform_reads"]
            or binding != prior["input"] or binding["iq"] != measured_iq
            or prefix_inventory["prefix_members"] != [witness["member"]]
            or prefix_inventory["original_inventory_sha256"] != req["inventory"]
            or canonical(prefix_inventory) != source["digest"] or canonical([source["digest"], measured_iq]) != raw
            or prefix_cutoff != req["causal_cutoff_utc_ns"]
            or binding["original"]["archive"]["snapshots_sha256"] != req["original_archive"]["snapshots_sha256"]
            or binding["original"]["offer"] != req["offer_file"]
            or binding["original"]["parent_native"] != req["native_file"]
            or "--sparse8-primary" not in binding["candidate_options"]
            or selector["choice"]["route"] != "unfiltered" or selector["refinement_calls"] != 0
            or selector["selected"] != selector["observed"] or sparse["aperture_samples"] != [200000, 80000]
            or canonical(sparse) != selector["detector_recipe_sha256"]
            or canonical(prefix_recipe) != selector["parent_detector_sha256"]
            or canonical(rebinding(measured, measured["source"]["probes"], prefix_recipe)) != selector["parent_native_sha256"]
            or full["source"]["raw_recording_authority_digest"] != req["raw_authority"]
            or full["clock_anchor"] != witness["visits"][0]["clock_anchor"]):
        raise ValueError("The acquired first member, original holdout or sparse detector provenance changed")
    full_detector = full["provenance"]["detector_sha256"]
    bind_native(full, req["session"], req["inventory"], full_detector[7:], expected="sha256:"+req["native_sha256"])
    for mode, packet in (("named", named), ("integrated", measured)):
        observed = prior["result"][mode]
        detector = packet["provenance"]["detector_sha256"]
        if (observed["clock"]["exit_code"] or (observed["issued"], observed["admitted"]) != (64, 55)
                or packet["source"]["raw_recording_authority_digest"] != raw
                or (mode == "named" and detector != full_detector)
                or (mode == "integrated" and (detector != selector["detector_recipe_sha256"]
                    or observed["packet_sha256"] != selector["native_sha256"]))):
            raise ValueError("The recorded native pair changed its authenticated receiver scope")
        bind_native(packet, source["session"], source["digest"], detector[7:], expected=observed["packet_sha256"])
    views, _ = prefix_scope(full, named, measured, witness)
    excluded = views["archived"][1]
    if any(view[1] != excluded for view in views.values()) or len(excluded) != 9:
        raise ValueError("Original exclusion positions or evidence changed")
    before, after = named["source"]["probes"], measured["source"]["probes"]
    primary, restored = measured_rows(full["source"]["probes"], before, after)
    recipe = dict(policy=LABELS["hybrid"], full_native="sha256:"+req["native_sha256"], full_detector=full_detector,
                  original_member_witness=witness["member"], measured_authority=raw, measured_native=selector["native_sha256"],
                  installed_member=prior["result"]["named"]["packet_sha256"], protocol=digest(PROTOCOL), parent_receipts=PINS)
    first = rebinding(full, primary, recipe)
    second = rebinding(full, restored, dict(recipe, policy=LABELS["restore-singleton"],
                                          hybrid_parent=canonical(first), restoration=list(RESTORE)))
    restored_id = next(lane_key(row) for row in before if (*lane_key(row), row["channel"]) == RESTORE)
    audit = dict(signed_index=witness["member"], admitted_lanes=len(before), issued_prefix=64, excluded=sorted(excluded),
                 changed_lanes=[lane_key(a) for a,b in zip(before, after, strict=True) if a != b],
                 empty_original=sum(not r["candidates"] for r in before), empty_measured=sum(not r["candidates"] for r in after),
                 singleton_lane=restored_id, singleton_comparison=[
                     next(row for row in lanes if lane_key(row) == restored_id) for lanes in (before, after)])
    return dict(zip(MODES, (first, second), strict=True)), audit


def clean_control():
    from clean_saved_0169_trial import output_seal
    from ds30_0163_composed_saved import read as saved_read

    clean = json.loads(checked(CLEAN/"result.json", CLEAN_PIN))
    seal = CLEAN/"prediction-seal.json"
    if not clean["qualified"] or clean["prediction_sha256"] != digest(seal) or saved_read(seal) != output_seal(CLEAN):
        raise ValueError("Require the complete unchanged matched clean all-20 publication")
    return clean


def prepare(root):
    from clean_saved_publication import load_job
    from combined_successor_0289 import admitted_libraries
    from empty_bootstrap import RELEASE, clock, now
    from exact_named_route import checked_catalogue, resident_path
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import immutable_json
    from reports.ALGO08.v3.ds30_0163_combined import pinned_sources, ready
    from visit_frame_raw_0016 import resident

    begin = now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh direct RAM output")
    stat = os.statvfs(root.parent)
    if stat.f_frsize * stat.f_bavail < 128 * 1024**2:
        raise ValueError("Insufficient tmpfs headroom for the two bounded results")
    original = ready(check_assignment=False)
    clean = clean_control()["admission"]
    extra, _ = donor_sources()
    pins, libraries = pinned_sources(), admitted_libraries()
    if clean["job_sha256"] != CASE.job_pin or pins != clean["sources"] or libraries != clean["libraries"] or any(
            clean[key] != value for key, value in extra.items()):
        raise ValueError("The original composed algorithm or source binding changed")
    bound, req = load_job(CASE.ready/"job.json", CASE.job_pin)
    _, refs = checked_catalogue(bound, req, TleArchiveReader, canonical_digest)
    availability = resident([*(ref.path for ref in refs), *map(Path, bound["packets"]), *map(Path, libraries)])
    packets, audit = custody(bound, req)
    if any(ready_directory(root, mode).exists() for mode in MODES):
        raise ValueError("Use fresh research ready envelopes")
    root.mkdir(mode=0o700)
    write(root/"overlap.json", audit)
    for mode, packet in packets.items():
        directory = root/mode
        directory.mkdir()
        for leaf in ("routed", "fonts", "tmp"):
            (directory/leaf).mkdir()
        for font in (CASE.ready/"fonts").glob("fontlist-*.json"):
            os.link(font, directory/"fonts"/font.name)
        native = directory/"native.json"
        immutable_json(native, packet)
        native_pin = digest(native)
        request = directory/"request.json"
        write(request, dict(req, native_file=str(native), native_sha256=native_pin))
        updated = dict(bound, request=str(request), stage=str(directory), packets=bound["packets"] | {
            str(request): digest(request), str(native): native_pin})
        envelope = ready_directory(root, mode)
        envelope.mkdir(mode=0o700)
        job = envelope/"job.json"
        write(job, dict(binding=updated, original_archive=req["original_archive"]))
        job_pin = digest(job)
        load_job(job, job_pin)
        ready_file = envelope/"admission.json"
        write(ready_file, original | dict(job_sha256=job_pin, original_job_sha256=CASE.job_pin, mode=mode))
        write(directory/"routed/binding.json", {"input": updated})
        command = ["/usr/bin/timeout", "--kill-after=2s", "60s", str(RELEASE/"venv/bin/python"), "-IB",
                   str(Path(__file__)), "worker", str(root), mode]
        write(directory/"admission.json", {key: clean[key] for key in ("protocol_sha256", "machine", "installed_release")}
              | extra | dict(sources=pins, libraries=libraries, job_sha256=job_pin, ready_sha256=digest(ready_file),
              detector=packet["provenance"]["detector_sha256"][7:], adapter=digest(Path(__file__)), protocol=digest(PROTOCOL),
              native_sha256=native_pin, mode=mode, command=command))
    write(root/"pre-fit-seal.json", dict(admission={mode: digest(root/mode/"admission.json") for mode in MODES},
          clock=clock(begin), inputs=PINS, control=CLEAN_PIN, overlap_sha256=digest(root/"overlap.json"),
          resident=availability, no_waveform=True))


def worker(root, mode):
    import ds30_0359_composed_saved as composed
    import prospective_0316_solver as saved
    directory = root/mode
    envelope = ready_directory(root, mode)
    seal, book = read(root/"pre-fit-seal.json"), read(directory/"admission.json")
    if (seal["admission"][mode] != digest(directory/"admission.json") or book["adapter"] != digest(Path(__file__))
            or book["protocol"] != digest(PROTOCOL) or book["ready_sha256"] != digest(envelope/"admission.json")
            or book["mode"] != mode or seal["control"] != CLEAN_PIN):
        raise ValueError("The intervention differs from the frozen signed saved boundary")

    with (patch.multiple(composed, READY=envelope, READY_PIN=book["ready_sha256"], JOB_PIN=book["job_sha256"]),
          patch.object(saved, "worker", partial(saved.worker, detector=book["detector"], input_description=LABELS[mode]))):
        composed.worker(directory)


def launch(root, mode):
    from clean_saved_0169_trial import output_seal
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    directory = root/mode
    if (directory/"routed/clock.json").exists():
        raise ValueError("Each frozen numerical variant may run once")
    if mode == MODES[1]:
        first = read(root/MODES[0]/"result.json")
        if (not first["qualified"] or not first["endpoint_or_owner_change"]
                or first["prediction_sha256"] != digest(root/MODES[0]/"prediction-seal.json")):
            raise ValueError("Singleton recovery requires a verified and changed first hybrid")
    env = environment(directory) | {"TMPDIR": str(directory/"tmp"), "XDG_CACHE_HOME": str(directory/"tmp")}
    command = read(directory/"admission.json")["command"]
    write(directory/"routed/clock.json", measure(command, env, directory/"routed/candidate"))
    write(directory/"prediction-seal.json", output_seal(directory))


def score(root, mode):
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import inspect, owner_delta
    from tools.pipeline_eval.scoring import distance_km
    from unseen_saved_holdout_score import REFERENCE_PIN

    directory = root/mode
    seal = directory/"prediction-seal.json"
    book, clock = (read(directory/path) for path in ("admission.json", "routed/clock.json"))
    result = dict(mode=mode, process=clock, qualified=False, prediction_sha256=digest(seal), parent=CLEAN_PIN)
    if read(seal) != output_seal(directory):
        raise ValueError("Unexpected change to the sealed publication")
    if clock["exit_code"]:
        write(directory/"result.json", result)
        return
    bound, request = load_job(ready_directory(root, mode)/"job.json", book["job_sha256"])
    target = directory/"routed/candidate"
    receipt = read(target/"worker.json")["receipt"]
    current = inspect(target, mode, receipt, clock, request, native_sha=book["native_sha256"], windows=bound["issued"],
                      admitted=bound["admitted"], audit_name="worker.json", detector=book["detector"], input_description=LABELS[mode])
    control = clean_control()
    reference = subprocess.check_output(["git", "-c", f"safe.directory={HERE.parents[2]}", "-C", str(HERE.parents[2]), "show",
                                         "2d0ad2dfd:reports/2026_11_21_ds30_full/reference-audit.json"])
    from hashlib import sha256
    if sha256(reference).hexdigest() != REFERENCE_PIN:
        raise ValueError("The independent reference changed")
    truth, = (row["reference"] for row in json.loads(reference)["cases"] if row["dataset_label"] == CASE.case
              and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    coordinates = (truth["latitude_deg"], truth["longitude_deg"])
    telemetry = read(directory/"composition.json")
    grid = FastStandardAnalysisStore(target).position_grid(receipt["run_id"])
    peers = dict(all20=control["candidate"])
    if mode == MODES[1]:
        peers["hybrid"] = read(root/MODES[0]/"result.json")["candidate"]
    candidate_arms = current["science"]["arms"]
    def compare(peer):
        terminal = peer["science"]["arms"]
        return {arm: dict(endpoint_change=candidate_arms[arm]["latlon"] != terminal[arm]["latlon"],
                          movement_m=1000*distance_km(terminal[arm]["latlon"], candidate_arms[arm]["latlon"]),
                          error_m=1000*distance_km(coordinates, candidate_arms[arm]["latlon"]),
                          prior_error_m=1000*distance_km(coordinates, terminal[arm]["latlon"]),
                          rf_rms_hz=candidate_arms[arm]["rf_rms_hz"], prior_rf_rms_hz=terminal[arm]["rf_rms_hz"],
                          owners=owner_delta(peer["selected_rows"][arm], current["selected_rows"][arm])) for arm in ARMS}

    comparisons = {name: compare(peer) for name, peer in peers.items()}
    differs = any(row["endpoint_change"] or not row["owners"]["identical_ordered_rows"] for row in comparisons["all20"].values())
    checks = dict(both_fixes=set(candidate_arms) == set(ARMS) and all(row["latlon"] for row in candidate_arms.values()),
                  original_offer=current["terminal"]["region"] == control["candidate"]["terminal"]["region"],
                  complete_grid=grid["complete"] and grid["evaluated_points"] == 179,
                  both_sidecars=set(current["sidecars"]) == {"path", "grid"}, eight_pngs=len(current["figures"]) == 8,
                  native_png=telemetry["native_png"]["native"] == 8 and telemetry["native_png"]["fallback"] == 0)
    write(directory/"result.json", result | dict(qualified=all(checks.values()), checks=checks, candidate=current,
          reference_pin=REFERENCE_PIN, comparisons=comparisons, endpoint_or_owner_change=differs, telemetry=telemetry,
          previous_clean_clock=control["process"], pre_fit_seal_sha256=digest(root/"pre-fit-seal.json")))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "launch", "worker", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("mode", nargs="?", choices=MODES)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.root)
    else:
        {"launch": launch, "worker": worker, "score": score}[args.action](args.root, args.mode)
