"""Replay one original all-20 DS30-0008 packet and one measured prefix splice."""

import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
from prefix_transfer_0419 import ARMS, BASE, PINS, checked, lane_rows, metadata, observation_id, overlap, read, signed_member, verified_owner_rows, write


PFX = Path("/tmp/leo-v3-original-dense-intake-result01")
INTAKE = "add31a04da733a4c4cdaa87b613c8f8832aabb8c37aa55d278045c227f85cde6"
SELECTOR = ("9e9c5b2503b95c09c1e7fdd42fa5add20a54ba59d32d3ff04d48fe49ff49d8ca",
            "2b86595e0d092af97149261a5649eb1784e951acd639af7963c4075f56058012")
RELEASED = Path("/tmp/ds30-v2-stage-all-6cdbac/DS30-0008")
PAIR = "b2a0a7b73a245731ae2c21bdb3e44664a402397bb65cad6c42b66c8e2989b919"
DENSE = Path("/dev/shm/leo-held-anchor-selected-dense-01")
DENSE_REQUEST = "8abec0e2f60def947cd03883662611c3fcfdbd5f255eb0ba60e8306085abf502"
ORDER = ("full-20", "measured-prefix")
PROTOCOL = HERE / "0008-prefix-transfer-protocol.md"
LABEL = "authenticated saved all-20 DS30-0008 with measured original first-member 20/8 prefix"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def prefix(output):
    from continued_cfo_trial import rebinding
    from empty_bootstrap import bind_native
    from leo.contracts.digests import canonical_digest

    score = json.loads(checked(PFX/"result.json", INTAKE))
    bind = score["binding"]
    inv = bind["inventory"]
    entries = inv["segments"]
    if (score["case"] != "DS30-0008" or not score["qualified"] or score["position_solve"]
            or bind["stop"] != 64 or len(entries) != 1 or canonical_digest(inv) != bind["digest"]):
        raise ValueError("The sealed original dense receiver scope differs")
    original = dict(entries[0], path=str(Path(inv["original_recording"]) / Path(entries[0]["path"]).name),
                    scope="segment-00000000", windows=512)
    witness = signed_member(Path(entries[0]["path"]), dict(segments=[original]))
    if inv["prefix_members"] != [witness["member"]]:
        raise ValueError("The raw scope is not the first signed original member")
    hashes = [row["iq_sha256"] for row in witness["visits"]]
    raw = canonical_digest([bind["digest"], hashes])
    packets, parents = {}, []
    for number, pin in enumerate(SELECTOR, 1):
        selection = json.loads(checked(PFX/f"{number}-first_use-held-anchor-route.json", pin))
        row = score["pairs"][number-1]
        for mode, iq in (("named", "stock_iq"), ("first_use", "first_use_iq")):
            folder = PFX/f"{number}-{mode}"
            worker = read(folder/"worker.json")
            native = json.loads(checked(folder/worker["native"], row[mode]["source"]["native"]))
            view, source = native["source"], row[mode]["source"]
            if (source["raw_authority"] != raw or view["raw_recording_authority_digest"] != raw
                    or worker[iq] != hashes or canonical_digest(view["probes"]) != source["ordered_probes"]
                    or row[mode]["process"]["exit_code"] != 0 or (mode in packets and packets[mode] != native)):
                raise ValueError("Detector pair changed raw authority, order, process scope or repeatability")
            bind_native(native, bind["session"], bind["digest"], source["detector"][7:], expected=source["native"])
            packets[mode] = native
        mixed = packets["first_use"]
        recipe = selection["receiver_recipe"]
        parent = {key: value for key, value in recipe.items() if key != "held_native_8ms"}
        if (selection["choice"]["route"] != "unfiltered" or selection["refinement_calls"] != 0
                or selection["native_sha256"] != row["first_use"]["source"]["native"]
                or selection["observed"] != selection["selected"] or parent["aperture_samples"] != [200_000, 80_000]
                or canonical_digest(parent) != selection["parent_detector_sha256"]
                or canonical_digest(rebinding(mixed, mixed["source"]["probes"], parent)) != selection["parent_native_sha256"]):
            raise ValueError("Unable to reverse the unfiltered provenance exactly to the measured pre-selector packet")
        parents.append(dict(native=row["first_use"]["source"]["native"], parent_native=selection["parent_native_sha256"],
                            named_native=row["named"]["source"]["native"], selector=pin))
    write(output, dict(witness=witness, prefix_inventory=inv, prefix_authority=raw, intake=INTAKE,
                       parents=parents, native=packets, protocol=digest(PROTOCOL)))


def inputs(bundle):
    from continued_cfo_trial import rebinding
    from cropped_physical_iq_gate import AUTHORITY, DETECTOR, INVENTORY, SOURCE, SOURCE_SHA256
    from empty_bootstrap import bind_native
    from leo.contracts.digests import canonical_digest
    from nomination_handoff_0255_publication import remediation_pins

    full = json.loads(checked(SOURCE, SOURCE_SHA256))
    pair = json.loads(checked(RELEASED/"pair.json", PAIR))
    original = json.loads(checked(DENSE/"request.json", DENSE_REQUEST))
    admitted = json.loads(checked(BASE/"admission.json", PINS["admission.json"]))
    template = json.loads(checked(BASE/"request.json", PINS["request.json"]))
    pins = remediation_pins()
    source = full["source"]
    session = source["session_id"]
    inventory_file = RELEASED/"candidate/fast-scan-inputs"/(session + ".json")
    inventory = json.loads(checked(inventory_file, INVENTORY))
    if (bundle["protocol"] != digest(PROTOCOL) or bundle["intake"] != INTAKE or pins != admitted["source_pins"]
            or bundle["witness"]["segment"] != inventory["segments"][0]
            or bundle["prefix_inventory"]["original_inventory_sha256"] != INVENTORY
            or source["raw_recording_authority_digest"] != AUTHORITY or pair["runs"]["candidate"]["raw_authority"] != AUTHORITY
            or original["archive"]["snapshots_sha256"] != pair["archive"]["snapshots_sha256"]
            or original["cutoff_utc_ns"] != full["clock_anchor"]["before"]["realtime_ns"]
            or pair["recording"] != original["recording"]):
        raise ValueError("The frozen full 20 ms input, region, archive or route cannot be composed")
    bind_native(full, session, INVENTORY, DETECTOR[7:], expected="sha256:"+SOURCE_SHA256)
    stock, mixed = (bundle["native"][mode] for mode in ("named", "first_use"))
    before = [row for row in source["probes"] if row["visit_index"] < 64]
    if (before != stock["source"]["probes"] or list(map(metadata, before)) != list(map(metadata, mixed["source"]["probes"]))
            or full["clock_anchor"] != bundle["witness"]["visits"][0]["clock_anchor"]):
        raise ValueError("The independent installed prefix did not reproduce the full original rows exactly")
    empty = {mode: {arm: {} for arm in ARMS} for mode in ("installed", "routed")}
    audit, rows = overlap(full, stock, mixed, bundle["witness"], empty)
    if rows is None or not audit["changes"]:
        raise ValueError("No changed measured prefix is eligible for the frozen solve")
    recipe = dict(policy="original first 64 issued visits measured 20/8; original installed 20 ms suffix",
                  full_native="sha256:"+SOURCE_SHA256, full_detector=DETECTOR, prefix_parents=bundle["parents"],
                  protocol=bundle["protocol"], prefix_authority=bundle["prefix_authority"], intake=INTAKE)
    hybrid = rebinding(full, rows, recipe)
    bind_native(hybrid, session, INVENTORY, canonical_digest(recipe)[7:])
    req = template | dict(case="DS30-0008 prefix development", session=session, inventory=INVENTORY,
          raw_authority=AUTHORITY, issued=inventory["window_count"], admitted=full["provenance"]["processed_windows"],
          recording=pair["recording"], offer_file=original["offer"], offer_sha256=original["offer_sha256"],
          manifests=[[str(Path(row["path"])/"manifest.json"), row["manifest_digest"]] for row in inventory["segments"]],
          causal_cutoff_utc_ns=original["cutoff_utc_ns"], original_archive=pair["archive"],
          local_archive=dict(original["archive"], snapshots=original["archive"]["records"]))
    offer = json.loads(checked(Path(req["offer_file"]), req["offer_sha256"]))
    if offer != pair["runs"]["candidate"]["receipt"]["region"]:
        raise ValueError("The supplied full-recording region changed")
    return req, inventory_file, {ORDER[0]: full, ORDER[1]: hybrid}, recipe, pins, audit, original, pair


def resident(path):
    mount = next((p for p in (Path("/dev/shm"), Path("/tmp")) if path.is_relative_to(p)), None)
    if mount is None or path.resolve(strict=True) != path or path.stat().st_dev != mount.stat().st_dev:
        raise ValueError(f"Need a direct RAM path for {path}")
    return path


def launch(root, bundle, pin):
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from cropped_physical_iq_gate import SOURCE, SOURCE_SHA256
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE, clock, now
    from exact_named_route import checked_catalogue
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import immutable_json
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident as cache

    begin = now()
    if root.exists() or resident(root.parent) != Path("/tmp"):
        raise ValueError("Need a new private /tmp root")
    machine = host()
    req, inventory, packets, recipe, sources, audit, original, _ = inputs(json.loads(checked(bundle, pin)))
    libs = json.loads(checked(BASE/"job.json", PINS["job.json"]))["binding"]["packets"]
    offer = Path(req["offer_file"])
    archive = req["local_archive"]["root"]
    common = {str(inventory): req["inventory"].removeprefix("sha256:"), str(offer): req["offer_sha256"]}
    common.update({path: libs[path] for path in req["local_libraries"].values()})
    for path, value in common.items():
        checked(Path(path), value)
    _, refs = checked_catalogue(dict(archive=archive), req, TleArchiveReader, canonical_digest, resident=resident)
    availability = cache([str(ref.path) for ref in refs])
    if availability["members"] != len(refs) or availability["bytes"] != original["archive"]["bytes"]:
        raise ValueError("Original causal view was not observed resident")
    root.mkdir(mode=0o700)
    for name in (*ORDER, "fonts", "tmp"):
        (root/name).mkdir()
    font = "fontlist-v3.11.0.json"
    (root/"fonts"/font).write_bytes(checked(BASE/"fonts"/font,
             "3ec97e620a1fa0115bbbdaefd3ddd47382fd0aed525281d7f1fc88a8614f282a"))
    hybrid = root/"hybrid-native.json"
    immutable_json(hybrid, packets[ORDER[1]])
    recorded = {ORDER[0]: (SOURCE, SOURCE_SHA256), ORDER[1]: (hybrid, canonical_digest(packets[ORDER[1]])[7:])}
    commands, receiver = {}, {}
    for mode in ORDER:
        folder = root/mode
        target = folder/"routed"
        target.mkdir()
        source, native_pin = recorded[mode]
        packet = json.loads(checked(source, native_pin))
        receiver[mode] = packet["provenance"]["detector_sha256"]
        request = folder/"request.json"
        write(request, dict(req, native_file=str(source), native_sha256=native_pin))
        pinned = common | {str(request): digest(request), str(source): native_pin}
        bound = dict(case=req["case"], stage=str(root), archive=archive, request=str(request), inventory=str(inventory),
                     issued=req["issued"], admitted=req["admitted"], portable=None, packets=pinned, sources=sources)
        job = folder/"job.json"
        write(job, dict(binding=bound, original_archive=req["original_archive"]))
        job_pin = digest(job)
        with patch("exact_named_route.resident_path", resident):
            load_job(job, job_pin)
        write(folder/"admission.json", dict(source_pins=sources, job_sha256=job_pin))
        write(target/"binding.json", dict(input=bound))
        commands[mode] = ["/usr/bin/timeout", "--kill-after=2s", "150s", str(RELEASE/"venv/bin/python"),
                          "-IB", __file__, "worker", str(folder), "--pin", job_pin, "--mode", mode]
    write(root/"admission.json", dict(setup=clock(begin), source_pins=sources, adapter=digest(Path(__file__)),
          recipe=recipe, receiver=receiver, protocol=digest(PROTOCOL), archive=availability, bundle=str(bundle),
          bundle_sha256=pin, machine=machine, commands=commands, waveform_reads=0, portable=None))
    write(root/"overlap-before-publication.json", audit)
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    for mode in ORDER:
        folder = root/mode
        timing = measure(commands[mode], env, folder/"candidate")
        write(folder/"clock.json", timing)
        if timing["exit_code"] != 0:
            break
    write(root/"prediction-seal.json", output_seal(root))


def worker(folder, pin, mode):
    from empty_bootstrap import RELEASE, checked as secure

    sys.path.insert(0, str(RELEASE/"src"))
    import exact_named_route as exact
    import prospective_0316_solver as saved
    from history_risk_weak_physical import deny_original
    from leo.contracts.digests import canonical_digest
    from nomination_handoff_0255_publication import worker as frozen

    sys.addaudithook(deny_original)
    admission = read(folder.parent/"admission.json")
    if (admission["adapter"] != digest(Path(__file__)) or admission["protocol"] != digest(PROTOCOL)
            or admission["receiver"][ORDER[1]] != canonical_digest(admission["recipe"])):
        raise ValueError("Saved wrapper or derived detector recipe changed")
    port = read(folder/"admission.json")
    job = json.loads(secure(folder/"job.json", pin))
    target = folder/"routed"
    if port["job_sha256"] != pin or job["binding"] != read(target/"binding.json")["input"] or mode != folder.name:
        raise ValueError("The original sealed worker binding changed")
    saved_entry = saved.worker
    if mode == ORDER[1]:
        saved_entry = partial(saved_entry, detector=admission["receiver"][mode][7:], input_description=LABEL)
    # Only forward the existing receiver argument and admit direct /tmp paths. The installed validator runs normally.
    with (patch.object(exact, "resident_path", resident),
          patch.object(exact, "exact_ports", partial(exact.exact_ports, resident=resident)),
          patch.object(saved, "worker", saved_entry)):
        frozen(folder/"job.json", pin, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prefix", "launch", "worker", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--pin")
    parser.add_argument("--mode", choices=ORDER)
    args = parser.parse_args()
    if args.operation == "prefix":
        prefix(args.root)
    elif args.operation == "launch":
        launch(args.root, args.bundle, args.pin)
    elif args.operation == "worker":
        worker(args.root, args.pin, args.mode)
    else:
        from prefix_transfer_0008_score import score

        score(args.root)


if __name__ == "__main__":
    main()
