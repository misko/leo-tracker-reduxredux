"""Custody, status and the normal saved worker for the enrolled DS30-0218 case."""

import argparse
import json
import os
from pathlib import Path
from shutil import copyfile
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from masked_cfo_saved import entry, saved, signed  # noqa: E402


CASE = "DS30-0218"
CAMPAIGN = saved.CAMPAIGN
PLAN = "9deecea6ce5237d01d277370f57b2666f3b84ab96bba72fe0b668c7701d0fc99"
IDENTITY = "sha256:9b08c27dfd179fcfa112d19bc6c4b1f10b3efd3f948005a8a298dc9b927866c9"
KNOWN = Path("/dev/shm/leo-v3-cfo-epoch-0019-saved01")
KNOWN_AUTHORITY = "fb8ddad37edcde83527e0a2ab913a0f02d1dd3950a313a841b7d9d82355e6628"
KNOWN_NATIVE = "1acd2fcf8104fe990eaf40c82848e723de2da0c74f1ac1f29f59c659442d8d0d"
DONORS = tuple(Path("/dev/shm")/name for name in (
    "leo-v3-cfo-epoch-0086-saved01", "leo-v3-unseen-saved-0255-result01",
    "leo-v3-nomination-handoff-0289-local01", "leo-v3-held-shrink-0274-stage02/stage",
    "leo-v3-cfo-epoch-0049-saved01",
))
SCHEDULE = ["full", *(["short_primary"]*7)]


def experiment(*, probe):
    return SimpleNamespace(stem="masked-cfo-next-original", source=Path(__file__).name, joint=not probe,
                           ledger="edits", ledger_digest="edit_sha256", priority="idle",
                           transfer_sources=("held_cfo_features.py", "masked_cfo_saved.py"))


def enrollment(root):
    plan = saved.document(root/"plan.json", PLAN)
    by_case = {row["case"]:row for row in plan["cases"]}
    order = [*plan["smoke"], *(row["case"] for row in plan["cases"] if row["case"] not in plan["smoke"])]
    if order[64] != CASE or by_case[CASE]["raw_identity_sha256"] != IDENTITY:
        raise ValueError("The frozen original rank-65 identity changed")
    return by_case[CASE]


def status(root=CAMPAIGN):
    case = enrollment(root)
    rows = [json.loads(line) for line in (root/"rows.jsonl").read_bytes().splitlines()
            if CASE.encode() in line]
    if {row["algorithm"] for row in rows} != {"installed", "successor"} or len(rows) != 2 or any(
            row["case_id"] != case["case_id"] or row["assigned_rank"] != case["assigned_rank"] for row in rows):
        raise ValueError("The official export does not bind both original rank-65 roles")
    path = root/"cases"/CASE/"pair.json"
    pair = saved.document(path) if path.is_file() else None
    verified = bool(pair and pair.get("verified_pair") and pair.get("state") == "observed_pair")
    return dict(case=CASE, execution_rank=65, assigned_rank=case["assigned_rank"], physical_identity=IDENTITY,
                event_path=str(path), verified_pair=verified,
                roles={r["algorithm"]: {k:r.get(k) for k in ("outcome","admission_state","attempt","attempt_result_sha256")}
                       for r in rows})


def causal_view(files, cutoff, expected, required):
    names = sorted(name for name in files if int(name.split("-", 1)[0]) < cutoff)
    if not required <= set(names):
        raise ValueError(f"Resident catalogue is missing {len(required-set(names))} observed causal body names")
    views = []
    for left in range(len(names)):
        window = {}
        for name in names[left:]:
            window[name] = name.split("-", 1)[1].removesuffix(".tle")
            if required <= window.keys() and signed.canonical(window) == expected:
                views.append(dict(window))
    if len(views) != 1:
        raise ValueError("The complete signed causal catalogue is absent or ambiguous in the resident donor metadata")
    return views[0]


def private_files(stages):
    fsid = os.statvfs("/dev/shm").f_fsid
    files = {}
    for stage in stages:
        pool = stage/"tle/archive/space-track"
        if not pool.exists():
            continue
        if pool.resolve() != pool or not pool.is_relative_to("/dev/shm") or os.statvfs(pool).f_fsid != fsid:
            raise ValueError("Catalogue donors must be direct resident tmpfs copies")
        for body in pool.iterdir():
            if body.suffix == ".tle" and not body.is_symlink() and body.is_file():
                files.setdefault(body.name, body)
    return files


def checked_schedule(publication, native):
    raw = saved.document(publication/"unified-short-bootstrap.json")
    recipe = raw["held_anchor_route"]["receiver_recipe"]
    if (recipe["rule"] != SCHEDULE or recipe["streams"] != ["edge","channel","actual_rf_hz"]
            or raw["receiver_audit"]["recording_authority"] != native["source"]["raw_recording_authority_digest"]):
        raise ValueError("Expected the authenticated original one-in-eight sparse candidate")


def make_cell(root, stage, case, native_path, pin, authority, refs, *, enabled, probe, original=None):
    native = saved.document(native_path, pin)
    source = native["source"]
    if (authority["raw_authority_sha256"] != source["raw_recording_authority_digest"]
            or authority["inventory_sha256"] != source["input_manifest_sha256"]
            or authority["session_id"] != source["session_id"]):
        raise ValueError("The saved cell changed original recording or inventory custody")
    root.mkdir(mode=0o700)
    packet = root/"derived-native.json"
    copyfile(native_path, packet)
    packet.chmod(0o400)
    saved.document(packet, pin)
    admission = saved.write(root/"admission.json", dict(case=case, native_pin=pin.removeprefix("sha256:"),
        authority_pin=saved.identifier(stage/"authority.json")))
    research = experiment(probe=probe)
    plan = saved.write(root/"plan.json", dict(
        case=case, enabled=enabled, probe=probe, stage=str(stage), references=refs, admission_sha256=admission,
        protocol=saved.protocol(research), worker=saved.identifier(Path(saved.__file__)), sources=saved.source_pins(research),
        original_native_sha256=pin if pin.startswith("sha256:") else "sha256:"+pin,
        original_archive=authority["archive_sha256"], installed_native_sha256=None, original=original,
        change=dict(recipe_sha256=native["provenance"]["detector_sha256"], edits=[],
                    derived_native_sha256=pin if pin.startswith("sha256:") else "sha256:"+pin,
                    recipe=dict(sparse_native_sha256=pin if pin.startswith("sha256:") else "sha256:"+pin,
                                edit_sha256=signed.canonical([]))),
    ))
    return plan


def prepare_probe(root):
    authority = saved.document(KNOWN/"authority.json", KNOWN_AUTHORITY)
    view = saved.document(KNOWN/"catalogue.json")
    if signed.canonical({name:row["sha256"] for name,row in view.items()}) != authority["archive_sha256"]:
        raise ValueError("The known handoff has a different signed causal catalogue")
    return make_cell(root, KNOWN, "DS30-0019", KNOWN/"native.json", KNOWN_NATIVE, authority, len(view),
                     enabled=True, probe=True)


def prepare_field(root):
    state = status()
    if not state["verified_pair"]:
        raise ValueError("The two original DS30-0218 results are not yet officially verified")
    case = CAMPAIGN/"cases"/CASE
    pair = saved.document(case/"pair.json")
    authority = saved.document(case/"authority.json", pair["authority_sha256"])
    result_root = case/"successor"/f"attempt-{pair['generation']:06d}"
    result = saved.document(result_root/"result.json", pair["attempt_result_sha256"]["successor"])
    if result["raw_identity"] != authority or result["outcome"] not in ("complete","withheld") or result["process"]["exit_code"]:
        raise ValueError("The original successor did not seal an otherwise eligible scientific terminal")
    publication = result_root/"publication"
    witness_path = publication/"exact-named-raw-witness.json"
    witness = saved.document(witness_path) if witness_path.is_file() else {}
    files = private_files(DONORS)
    view = causal_view(files, authority["causal_cutoff_utc_ns"], authority["archive_sha256"],
                       set(witness.get("ports", {}).get("verified_tle", ())))
    saved.require_resident([files[name] for name in view])
    if any(saved.identifier(files[name]) != digest for name, digest in view.items()):
        raise ValueError("A local resident causal body failed signed verification")
    native, = (publication/"fast-scan-automatic-work").glob("*/detections.json")
    packet = saved.document(native, result["native_sha256"])
    checked_schedule(publication, packet)
    inventory = publication/"fast-scan-inputs"/(authority["session_id"]+".json")
    request = saved.document(case/"input.json")
    offer = KNOWN/"offer.json"
    if saved.document(offer, authority["region_sha256"]) != request["offered_region"]:
        raise ValueError("No exact signed local copy of the original offered region")
    saved.document(inventory, authority["inventory_sha256"])
    root.mkdir(mode=0o700)
    stage = root/"stage"
    out = stage/"tle/archive/space-track"
    out.mkdir(parents=True)
    for name in view:
        os.link(files[name], out/name)
    for source, name in [(offer,"offer.json"), (inventory,"inventory.json"), (case/"authority.json","authority.json")]:
        copyfile(source, stage/name)
        (stage/name).chmod(0o400)
    saved.write(stage/"catalogue.json", view)
    original = dict(raw_attempt_sha256=pair["attempt_result_sha256"]["successor"],
                    verified_field_pair_sha256=saved.identifier(case/"pair.json"),
                    raw_outcome=result["outcome"], original_witness=saved.identifier(witness_path) if witness else None)
    return {name:make_cell(root/name, stage, CASE, native, result["native_sha256"], authority, len(view),
                           enabled=enabled, probe=False, original=original)
            for name,enabled in (("ordinary",False),("corrected",True))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("status","prepare-probe","prepare-field","graph-probe","ordinary","corrected"))
    parser.add_argument("root", type=Path, nargs="?")
    parser.add_argument("--pin")
    parser.add_argument("--lease-fd", type=int)
    args = parser.parse_args()
    if args.mode == "status":
        print(json.dumps(status()))
    else:
        sys.addaudithook(saved.deny_backing)
        if args.root is None or args.root.resolve() != args.root or not args.root.is_relative_to("/dev/shm"):
            parser.error("The saved stage must use a private direct tmpfs path")
        if args.mode == "prepare-probe":
            print(prepare_probe(args.root))
        elif args.mode == "prepare-field":
            print(json.dumps(prepare_field(args.root)))
        else:
            entry(args.root, args.pin, experiment, mode=args.mode, fd=args.lease_fd)
