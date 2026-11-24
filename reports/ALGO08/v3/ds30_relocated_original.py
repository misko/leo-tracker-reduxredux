"""Certify enrolled DS30 NVMe accessions now pointing to their original bulk captures."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import sys
from time import monotonic, process_time, sleep
from uuid import uuid4

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

import ds30_paired_evaluation as study
from ds30_paired_inputs import ARMS, BULK, ORIGINAL, checked, digest, encode, load_cohort, read, write
from ds30_paired_worker import run_attempt

LOGICAL = Path("/srv/postgres-nvme/fast-scan-recordings")
PHYSICAL = BULK / "leo/fast-scan-recordings"
CASES = tuple(f"DS30-{index:04d}" for index in range(447, 456))
PLAN_PIN = "sha256:9deecea6ce5237d01d277370f57b2666f3b84ab96bba72fe0b668c7701d0fc99"
NATIVE_FLAGS = ("chunk_index", "first_sequence", "window_count", "index_bytes", "index_sha256",
                "index_relative_path", "payload_relative_path", "compressed_bytes", "compressed_sha256",
                "uncompressed_bytes", "uncompressed_sha256")


def observation(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def spelling(path):
    """Accept only the known one-hop same-name archive move."""
    expected = PHYSICAL / path.name
    if (path.parent != LOGICAL or path.parent.resolve(strict=True) != LOGICAL
            or not path.is_symlink() or path.readlink() != expected
            or path.resolve(strict=True) != expected or expected.resolve(strict=True) != expected):
        raise ValueError(f"Unbound relocation: {path}")
    return expected


@contextmanager
def directory(path, *, at=None, follow=False):
    flags = os.O_RDONLY | os.O_DIRECTORY | (0 if follow else os.O_NOFOLLOW)
    fd = os.open(path, flags, dir_fd=at)
    try:
        yield fd
    finally:
        os.close(fd)


def relative(path, logical):
    parts = Path(path).relative_to(logical).parts
    if len(parts) != 2 or any(part in (".", "..") for part in parts):
        raise ValueError("A sealed member must stay under one literal segment")
    return "/".join(parts)


def regular(fd, name, limit=None, expected=None):
    """Read manifest/index bytes by no-follow dirfd; stat compressed payloads."""
    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or (limit is not None and info.st_size != limit):
        raise ValueError(f"Signed member size/type changed: {name}")
    identity = observation(info)
    if expected is None:
        return identity, None
    fd_file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    with os.fdopen(fd_file, "rb") as stream:
        if observation(os.fstat(fd_file)) != identity:
            raise ValueError(f"Opened file differs from enrolled descriptor: {name}")
        body = stream.read(info.st_size + 1)
        if observation(os.fstat(fd_file)) != identity or digest(body) != expected:
            raise ValueError(f"Signed member bytes changed: {name}")
    return identity, body


def capture(recording, logical, member, work):
    from leo.contracts.digests import canonical_digest
    from leo.contracts.short_window import ShortWindowIndexV2
    from leo.storage.fast_scan import FastScanStore

    raw = member["raw_recording"]
    observed_files = {}
    manifests, hashes, cutoff = [], [], None
    session, inventory_digest, inventory = FastScanStore(work).inventory(recording, verify_windows=False)
    signed_segments = {relative(entry["path"], logical): entry["sha256"] for entry in raw["segments"]}
    chunks = {}
    for row in raw["chunks"]:
        manifest_rel = relative(row["segment_manifest"], logical)
        if manifest_rel not in signed_segments:
            raise ValueError("The enrolled index points outside its original segment manifest")
        for field, leaf in (("payload_path", "payload_relative_path"), ("index_path", "index_relative_path")):
            if relative(row[field], logical) != str(Path(manifest_rel).parent / row[leaf]):
                raise ValueError("A sealed member no longer has its exact filename")
        chunks.setdefault(manifest_rel, []).append(row)
    with directory(logical, follow=True) as old_fd, directory(recording) as actual_fd:
        root_id = observation(os.fstat(actual_fd))
        link_id = observation(logical.lstat())
        if observation(os.fstat(old_fd)) != root_id or root_id[0] != BULK.stat().st_dev:
            raise ValueError("Accession and ordinary paths do not identify the same enrolled bulk directory")
        previous_end = None
        for entry, (manifest_rel, pin) in zip(inventory["segments"], sorted(signed_segments.items()), strict=True):
            folder, leaf = manifest_rel.split("/")
            with directory(folder, at=actual_fd) as segment_fd, directory(folder, at=old_fd) as alias_fd:
                if not os.path.samestat(os.fstat(segment_fd), os.fstat(alias_fd)):
                    raise ValueError("The exact logical and physical segment descriptors differ")
                with_manifest, content = regular(segment_fd, leaf, expected=pin)
                observed_files[manifest_rel] = with_manifest
                document = json.loads(content)
                if (entry["path"] != str(recording / folder) or entry["manifest_digest"] != pin
                        or entry["windows"] != document["window_count"] or document["schema_version"] != 2
                        or document["sample_rate_hz"] != 10_000_000 or document["receiver_ids"] != [0, 1]):
                    raise ValueError("The ordinary resolved inventory changed its signed geometry")
                for chunk, expected in zip(document["chunks"], chunks[manifest_rel], strict=True):
                    if any(chunk[key] != expected[key] for key in NATIVE_FLAGS):
                        raise ValueError("The reopened segment differs from frozen compressed or decoded authority")
                    payload, index = (expected[k] for k in ("payload_relative_path", "index_relative_path"))
                    payload_id, _ = regular(segment_fd, payload, expected["compressed_bytes"])
                    index_id, data = regular(segment_fd, index, expected["index_bytes"], expected["index_sha256"])
                    for leafname, verified in ((payload, payload_id), (index, index_id), (leaf, with_manifest)):
                        if observation(os.stat(leafname, dir_fd=alias_fd, follow_symlinks=False)) != verified:
                            raise ValueError("The enrolled alias resolves to different member bytes")
                    observed_files[str(Path(folder) / payload)] = payload_id
                    observed_files[str(Path(folder) / index)] = index_id
                    lines = data.splitlines()
                    if len(lines) != expected["window_count"]:
                        raise ValueError("The signed index lost original windows")
                    offset = 0
                    for n, line in enumerate(lines):
                        source = ShortWindowIndexV2.model_validate_json(line)
                        sample = source.acquisition
                        start, stop = sample["sample_start"], sample["sample_end"]
                        bracket = json.loads(sample["retune_receipt"]).get("utc_clock_bracket")
                        if (source.sequence != expected["first_sequence"] + n or source.receiver_count != 2
                                or source.payload_offset_bytes != offset or source.payload_bytes != 8 * source.sample_count
                                or stop - start != source.sample_count or sample["global_visit"] != len(hashes)
                                or sample["counter_authority"] != "hardware"
                                or (previous_end is not None and start < previous_end)):
                            raise ValueError("The reopened index changed signed counters or geometry")
                        if bracket is not None:
                            if hashes or cutoff is not None or bracket["sample_counter"] != start:
                                raise ValueError("The reopened index lacks its original initial clock bracket")
                            cutoff = bracket["before"]["realtime_ns"]
                        previous_end = stop
                        offset += source.payload_bytes
                        hashes.append(source.iq_sha256)
                    if offset != expected["uncompressed_bytes"]:
                        raise ValueError("The signed member does not cover its full decoded geometry")
                    manifests.append({k: expected[k] for k in NATIVE_FLAGS} | {"manifest_sha256": pin})
        if observation(os.fstat(actual_fd)) != root_id or observation(logical.lstat()) != link_id:
            raise ValueError("The original symlink or storage directory changed during metadata authentication")
    if (len(hashes) != inventory["window_count"] or len(hashes) != member["window_count"]
            or len(manifests) != len(raw["chunks"]) or cutoff is None):
        raise ValueError("Missing authenticated original recording samples")
    old_inventory = dict(inventory, segments=[dict(entry, path=str(logical / Path(entry["path"]).name))
                                             for entry in inventory["segments"]])
    old_digest = canonical_digest(old_inventory)
    return dict(roots=dict(logical=str(logical), canonical=str(recording), link_id=link_id, canonical_id=root_id),
                files=observed_files, members=manifests, ordered_window_sha256=canonical_digest(hashes),
                historic=dict(recording=str(logical), session_id="fast-" + old_digest[7:39], inventory_sha256=old_digest,
                              raw_authority_sha256=canonical_digest([old_digest, hashes])),
                reopened=dict(recording=str(recording), session_id=session, inventory_sha256=inventory_digest,
                              raw_authority_sha256=canonical_digest([inventory_digest, hashes])),
                window_count=len(hashes), causal_cutoff_utc_ns=cutoff)


def plan_document():
    return json.loads(checked(study.OUTPUT / "plan.json", PLAN_PIN))


def migrations(plan):
    rows = [row for row in plan["cases"] if Path(row["recording"]).parent == LOGICAL]
    if {row["case"] for row in rows} != set(CASES):
        raise ValueError("The exact prior NVMe roster differs from this accession")
    result = {}
    for row in rows:
        path = Path(row["recording"])
        try:
            target = spelling(path)
            observed = dict(canonical=str(target), target_device=target.stat().st_dev,
                            accession_link=observation(path.lstat()))
        except (OSError, ValueError) as error:
            observed = dict(unavailable=f"{type(error).__name__}: {error}")
        result[row["case"]] = dict(logical=str(path), assigned_rank=row["assigned_rank"], **observed)
    return result


def prove(case, destination):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    started, cpu = monotonic(), process_time()
    plan = plan_document()
    row, = (row for row in plan["cases"] if row["case"] == case)
    members, _, audit = load_cohort()
    member, = (entry for entry in members if entry["dataset_label"] == case)
    logical = Path(row["recording"])
    if (member["case_id"] != row["case_id"] or logical.name != member["recording_id"]
            or logical != Path(member["raw_recording"]["root"]) or member["raw_recording"]["integrity_errors"]):
        raise ValueError("Wrong DS30 accession")
    rebound = capture(spelling(logical), logical, member, destination.parent)
    archive = ORIGINAL / "snapshot/inputs" / case / "tle"
    prior_sha = audit[case]["binding_sha256"]
    binding = json.loads(checked(ORIGINAL / "bindings" / (case + ".json"), prior_sha))
    old = binding["case"]
    request = json.loads(checked(BULK / old["request"]["path"], old["request"]["sha256"]))
    offer_sha = plan["offered_region_sha256"]
    region = Algo08Region.parse(json.loads(checked(study.OUTPUT / "offer.json", offer_sha))).document()
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    orbit_map = {info.path.name: info.sha256 for info in refs}
    historic, cutoff = rebound["historic"], rebound["causal_cutoff_utc_ns"]
    case_manifests = {item["path"]: item["sha256"] for item in member["raw_recording"]["segments"]}
    if (historic["session_id"] != old["session_id"] or historic["raw_authority_sha256"] != old["raw_authority"]
            or case != old["id"] or old["valid_visits"] != audit[case]["usable_visits"]
            or old["recording"]["window_count"] != rebound["window_count"]
            or {str(BULK / item["path"]): "sha256:" + item["sha256"].removeprefix("sha256:")
                for item in old["recording"]["segments"]} != case_manifests
            or old["regions"] != [{"id": "original", "center": region["center"]}] or region["width_km"] != 25
            or request["role"] != "baseline" or request["job"]["evaluation_reference"] is not None
            or request["job"]["identity"]["session_id"] != historic["session_id"]
            or request["job"]["tle_root"] != str(archive) or request["job"]["search_center"] != region["center"]
            or request["job"]["screen_center"] != region["screen_center"]
            or cutoff != binding["orbit_cutoff_ns"] or cutoff > member["captured_utc_ns"]
            or orbit_map != request["causal_snapshots"] or len(refs) != binding["orbit_count"]
            or not refs or any(item.collected_utc_ns >= cutoff for item in refs)):
        raise ValueError("The reconstructed old identity, cutoff, region or signed archive differs")
    authority = rebound["reopened"] | dict(schema="algo08v3-original-request-v1", window_count=rebound["window_count"],
                    causal_cutoff_utc_ns=cutoff, archive_sha256=canonical_digest(orbit_map), region_sha256=offer_sha)
    inputs = dict(archive=str(archive), expected_admitted=old["valid_visits"], offered_region=region,
                  authority=authority, authority_sha256=digest(encode(authority) + b"\n"))
    stock_payload = study.STOCK.parent / "payload"
    release = Path(study.PYTHON).parents[2]
    stock_reader_pins = {
        str(path): digest(path.read_bytes()) for path in (
            stock_payload / "tools/pipeline_eval/qualification/experimental_publication.py",
            stock_payload / "tools/pipeline_eval/variants/experimental/paired_sha256.py",
            release / "src/leo/storage/short_window.py", release / "src/leo/storage/fast_scan.py")}
    result = rebound | dict(case=case, plan_sha256=PLAN_PIN, driver_sha256=digest(Path(__file__).read_bytes()),
        assigned_order=row["order"], historical_binding_sha256="sha256:" + prior_sha.removeprefix("sha256:"),
        accession=dict(case_id=row["case_id"], physical_content_sha256=row["raw_identity_sha256"],
                       manifest_raw_authority_sha256=row["manifest_raw_authority_sha256"]),
        inputs=inputs, recorded_migrations=migrations(plan), stock_reader_sources=stock_reader_pins,
        scope=dict(waveform_payloads_opened=0, compressed_bytes_committed=sum(item["compressed_bytes"] for item in rebound["members"]),
                   signed_index_bytes_read=sum(item["index_bytes"] for item in rebound["members"]),
                   elapsed_s=monotonic()-started, cpu_s=process_time()-cpu))
    write(destination, result)


def unchanged(proof):
    roots = proof["roots"]
    logical, canonical = Path(roots["logical"]), Path(roots["canonical"])
    if (spelling(logical) != canonical or observation(logical.lstat()) != roots["link_id"]
            or observation(canonical.stat()) != roots["canonical_id"]):
        raise ValueError("The original link or target changed after proof")
    with directory(logical, follow=True) as old, directory(canonical) as actual:
        if observation(os.fstat(old)) != observation(os.fstat(actual)):
            raise ValueError("The file identity relation no longer holds")
        for name, expected in proof["files"].items():
            folder, leaf = name.split("/")
            with directory(folder, at=actual) as segment:
                if observation(os.stat(leaf, dir_fd=segment, follow_symlinks=False)) != expected:
                    raise ValueError(f"Original file changed after the authenticated projection: {name}")


def verify_encoded_successor(output, proof):
    evidence = read(output / "legacy-original-acquisition.json")
    if evidence["authority_mode"] != "verified-once":
        raise ValueError("Expected the normal complete original-member verification")
    fields = dict(manifest_sha256="manifest_sha256", index_sha256="index_sha256", member_sha256="compressed_sha256",
                  raw_sha256="uncompressed_sha256", windows="window_count", encoded="compressed_bytes",
                  decoded="uncompressed_bytes", chunk_index="chunk_index", first_sequence="first_sequence")
    for row, expected in zip(evidence["members"], proof["members"], strict=True):
        if "complete_encoded_auth" not in row or any(row[key] != expected[field] for key, field in fields.items()):
            raise ValueError("Native encoded auth differs from the original ordered compressed roster")
    return digest((output / "legacy-original-acquisition.json").read_bytes())


def measured_pair(proof_file, pin, output):
    from tools.pipeline_eval.qualification.paired_publication import verified_v3

    proof = json.loads(checked(proof_file, pin))
    plan = plan_document()
    case = proof["case"]
    if (case != "DS30-0452" or proof["plan_sha256"] != PLAN_PIN or proof["driver_sha256"] != digest(Path(__file__).read_bytes())
            or Path(proof["roots"]["logical"]).name != Path(proof["inputs"]["authority"]["recording"]).name
            or not output.is_relative_to(study.OUTPUT / "relocation") or output.name != case
            or output.parent.resolve(strict=True) != output.parent or output.exists() and output.is_symlink()):
        raise ValueError("This isolated reopening is limited to the enrolled 0452 relocation")
    if set(os.sched_getaffinity(0)) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("Use the ordinary low priority single Gauss slot")
    if plan["stock"] != verified_v3(study.STOCK):
        raise ValueError("The installed reader changed")
    for path, value in proof["stock_reader_sources"].items():
        checked(Path(path), value)
    offer = study.OUTPUT / "offer.json"
    inputs = proof["inputs"]
    output.mkdir(exist_ok=True)
    with study.exclusive(output / "driver.lock", "a+b"), study.exclusive(study.LOCK, "rb") as lease:
        authority = output / "authority.json"
        write(authority, inputs["authority"])
        write(output / "relocation.json", dict(plan_sha256=PLAN_PIN, proof_sha256=pin, case=case,
              accession=proof["accession"], historic=proof["historic"], canonical=proof["reopened"], generation=2,
              frozen_order=proof["assigned_order"], initial_campaign_disposition=study.summary(study.OUTPUT / "cases" / case)))
        lease_id = uuid4().hex
        for arm in proof["assigned_order"]:
            if study.outcome(output, arm)[0] is not None:
                continue
            quiet, state = study.quiet_window()
            if not quiet:
                study.record(output, "deferred_storage_busy", next_arm=arm, io=state)
                return 75
            unchanged(proof)
            result = study.next_attempt(output, arm)
            run_attempt(result, plan, inputs, offer, authority, arm, lease.fileno(), lease_id, 2, state, study.storage_sample)
            unchanged(proof)
        successor, path = study.outcome(output, "successor")
        if successor["outcome"] in {"complete", "withheld"}:
            pin_acquisition = verify_encoded_successor(path.parent / "publication", proof)
            write(output / "native-encoded-auth.json", dict(successor=pin_acquisition,
                installed_contract=proof["stock_reader_sources"], both_raw_authority=proof["reopened"]["raw_authority_sha256"]))
        study.seal_pair(output, inputs, proof["assigned_order"])
    return 0


def metadata_only(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)) and os.fsdecode(args[0]).endswith(".ci16.zst"):
        raise RuntimeError("No waveform file may open in the relocation proof")


def admitted_proof(case, output):
    from guarded_stage_idle import FULL_LIMIT, QUEUE_LIMIT

    # Observe the quiet window without consuming the shared process slot.
    deadline = monotonic() + 60
    while monotonic() < deadline:
        quiet, _ = study.quiet_window()
        if quiet:
            try:
                with study.exclusive(study.LOCK, "rb"):
                    sample = study.storage_sample()
                    if all(row["in_flight"] <= QUEUE_LIMIT and row["full_avg10"] < FULL_LIMIT for row in sample.values()):
                        prove(case, output)
                        return 0
            except BlockingIOError:
                pass
        sleep(.5)
    return 75


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_subparsers(dest="action", required=True)
    check = group.add_parser("prove")
    check.add_argument("case", choices=CASES)
    check.add_argument("output", type=Path)
    solve = group.add_parser("pair")
    solve.add_argument("proof", type=Path)
    solve.add_argument("proof_sha256")
    solve.add_argument("output", type=Path)
    option = parser.parse_args()
    if option.action == "prove":
        sys.addaudithook(metadata_only)
        return admitted_proof(option.case, option.output)
    return measured_pair(option.proof, option.proof_sha256, option.output)


if __name__ == "__main__":
    sys.exit(main())
