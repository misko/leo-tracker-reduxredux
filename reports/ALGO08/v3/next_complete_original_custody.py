"""Seal the completed or partial original stage from local metadata."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]


def original_inventory(root, preflight, bound):
    from leo.contracts.digests import canonical_digest
    from next_complete_original_stage import BULK, checked_local

    original = Path(preflight["selected"]["original"])
    entries = []
    for i, segment in enumerate(bound["case"]["recording"]["segments"]):
        original_file = BULK/segment["path"]
        target = root/original.name/original_file.relative_to(original)
        if not target.is_file():
            return None, None
        body = json.loads(checked_local(target, segment["sha256"]))
        entries.append(dict(scope=f"segment-{i:08d}", path=str(original_file.parent),
                            manifest_digest="sha256:"+segment["sha256"].removeprefix("sha256:"),
                            windows=body["window_count"]))
    inv = dict(kind="fast-scan-source", schema_version=1, recording_name=original.name,
               window_count=sum(row["windows"] for row in entries), segments=entries)
    return inv, canonical_digest(inv)


def run(root, output, alternatives, *, stopped_by=None):
    from leo.contracts.digests import canonical_digest
    from next_complete_original_stage import cache_sample, emit

    preflight = json.loads((root/"preflight.json").read_bytes())
    result = json.loads((root/"result.json").read_bytes())
    files = {row["path"]: row for row in preflight["original_members"]}
    prefix_bytes, full, present = 0, 0, []
    planned = Path(result["original"])
    verified = {row["relative"]: row for row in result["verified_files"]}
    for original, row in files.items():
        local = root/planned.name/Path(original).relative_to(planned)
        if not local.is_file():
            continue
        extent = local.stat().st_size
        verified_copy = verified.get(str(local.relative_to(root)))
        if verified_copy:
            if verified_copy["length"] != row["size"] or verified_copy["sha256"] != row["sha256"] or extent != row["size"]:
                raise ValueError("The completed staging receipt and local source extent disagree")
            full += extent
        else:
            if extent >= row["size"]:
                raise ValueError("A full-size unsigned partial cannot be admitted as verified")
            prefix_bytes += extent
        present.append(dict(path=local, size=extent))
    raw = root/"control/native.json"
    offer = root/"control/offer.json"
    bound = root/"control/binding.json"
    ready = None
    if raw.is_file() and offer.is_file() and bound.is_file():
        data = json.loads(raw.read_bytes())
        inventory, pin = original_inventory(root, preflight, json.loads(bound.read_bytes()))
        if inventory is not None:
            source = data["source"]
            if (pin != source["input_manifest_sha256"] or source["session_id"] != "fast-"+pin[7:39]
                    or inventory["window_count"] != result["selected"]["visits"]):
                raise ValueError("The staged manifests do not reconstruct the original signed source identity")
            if sha256(raw.read_bytes()).hexdigest() != result["causal"]["native_sha256"]:
                raise ValueError("Original native evidence no longer matches the signed job")
            request_path = root/"control/request.json"
            request = json.loads(request_path.read_bytes())
            if (canonical_digest(request["causal_snapshots"]) != result["causal"]["archive_sha256"]
                    or sha256(request_path.read_bytes()).hexdigest() != result["causal"]["request_sha256"]
                    or sha256(offer.read_bytes()).hexdigest() != result["causal"]["offer_sha256"]):
                raise ValueError("The staged archive list or offer was changed")
            ready = dict(session=source["session_id"], input_manifest_sha256=pin,
                         raw_recording_authority_digest=source["raw_recording_authority_digest"],
                         original_source_inventory=inventory,
                         causal_cutoff_utc_ns=data["clock_anchor"]["before"]["realtime_ns"])
    active = result["completed_original_stage"] and result["complete_causal"] and ready is not None
    resident = cache_sample(present) if active else None
    if active and (resident["cached_pages"] != resident["observed_file_pages"] or full != preflight["complete_source_bytes"]):
        raise ValueError("The full source is missing either exact signed bytes or residency")
    events = [json.loads(line) for line in (root/"copy-idle-progress.jsonl").read_text().splitlines()]
    emit(output, dict(
        as_run_debug_pins={name: sha256((root/name).read_bytes()).hexdigest() for name in (
            "preflight.json", "result.json", "copy-idle-progress.jsonl")},
        enclosed=dict(preflight=preflight, result=result, alternative_passive=json.loads(alternatives.read_bytes())),
        admitted_copy_progress=events,
        deliberate_stop=stopped_by,
        partial_checkpoint=json.loads((root/"checkpoint.json").read_bytes()) if (root/"checkpoint.json").is_file() else None,
        staged_verified_original_bytes=full, staged_unsigned_prefix_bytes=prefix_bytes, final_local_residency=resident,
        signed_identity=ready, ready_raw_to_publication=bool(active),
        private_readonly_bind=dict(source=result["stage"], target=result["original"]) if active else None,
        solver_calls=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("alternatives", type=Path)
    parser.add_argument("--stopped-by")
    args = parser.parse_args()
    run(args.root, args.output, args.alternatives, stopped_by=args.stopped_by)
