"""Verify catalogue access and portable coverage using only sealed field receipts."""

import argparse
import json
import re
import struct
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns


ROOT = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
BUILD_PIN = "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"
RUNTIME_PIN = "6d69fd4436cb772c63cb018f776179fc8c1349763d9c8db1e77b887ca5cea807"
PAIRS = {
    "DS30-0354": (
        "9194135470701604bf3aeb2ee3d1fd8a0d1f5390dda039cea71d0b954939a0be",
        "6066ba3a39d5be60eb74c0e13db7c51a9dfff5f8af8ed00c132e98f047cde86a",
    ),
    "DS30-0010": (
        "5352551fef1d03855fdffc6c713741969aba2a1c5a1e1f21e7d9621e34495ccc",
        "a06684b304d71f1c8567b09da37bb9515a5240dd949fb42f13c0782023ae89f7",
    ),
}
SNAPSHOT = re.compile(r"([1-9][0-9]*)-([0-9a-f]{64})\.tle")
INDEX_MAGIC = b"LEOTLE-I\x01"
INDEX_HEADER = struct.Struct("<II")
INDEX_BODY = struct.Struct("<32sI")
INDEX_RECORD_BYTES = struct.calcsize("<Iq")


def tagged(value):
    return "sha256:" + value.removeprefix("sha256:")


def document_digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return tagged(sha256(payload).hexdigest())


def local_bytes(root, path):
    if (not path.is_relative_to(root) or path.resolve(strict=True) != path
            or path.stat().st_dev != root.stat().st_dev or path.name.endswith((".tle", ".ci16.zst"))):
        raise ValueError(f"Expected a direct local NVMe receipt or index: {path}")
    return path.read_bytes()


def checked(root, path, expected):
    data = local_bytes(root, path)
    if tagged(sha256(data).hexdigest()) != tagged(expected):
        raise ValueError(f"Receipt digest changed: {path.name}")
    return data


def index_bodies(data):
    """Read only the pinned portable format's declared digest and row roster."""
    if not data.startswith(INDEX_MAGIC) or not len(INDEX_MAGIC) + INDEX_HEADER.size <= len(data) <= 24 << 20:
        raise ValueError("Invalid portable index extent or version")
    heading, declared = INDEX_HEADER.unpack_from(data, len(INDEX_MAGIC))
    cursor = len(INDEX_MAGIC) + INDEX_HEADER.size + heading
    if not 0 < heading <= 4096 or cursor > len(data):
        raise ValueError("Invalid portable index compatibility header")
    roster, previous = {}, b""
    for _ in range(declared):
        if len(data) - cursor < INDEX_BODY.size:
            raise ValueError("Truncated portable index digest descriptor")
        digest, count = INDEX_BODY.unpack_from(data, cursor)
        cursor += INDEX_BODY.size + count * INDEX_RECORD_BYTES
        if digest <= previous or not 0 < count <= 100_000 or cursor > len(data):
            raise ValueError("Invalid ordered portable index descriptor")
        roster[digest.hex()] = count
        previous = digest
    if cursor != len(data):
        raise ValueError("Unexpected portable index trailing bytes")
    return roster


def read_coverage(verified, archive_sha, cutoff, artifact):
    roster = {}
    for name, total in verified.items():
        parsed = SNAPSHOT.fullmatch(name)
        if parsed is None or int(parsed[1]) >= cutoff or type(total) is not int or total <= 0:
            raise ValueError("Invalid, future or unverified catalogue reference in the witness")
        roster[name] = parsed[2]
    unique = set(roster.values())
    used = unique & artifact.keys()
    return dict(opened_references=len(roster), opened_unique_bodies=len(unique), verified_bytes=sum(verified.values()),
                observed_roster_sha256=document_digest(roster),
                observed_roster_is_complete=document_digest(roster) == archive_sha,
                index_digest_overlap=len(used), index_row_overlap=sum(artifact[k] for k in used),
                catalogue_bytes_available_from_index=False)


def argument_value(argv, flag):
    if argv.count(flag) != 1 or argv[-1] == flag:
        raise ValueError(f"Expected one enrolled option {flag}")
    return argv[argv.index(flag) + 1]


def audit_case(root, case, artifact, portable):
    pair_pin, witness_pin = PAIRS[case]
    folder = root / "cases" / case
    pair = json.loads(checked(root, folder / "pair.json", pair_pin))
    authority = json.loads(checked(root, folder / "authority.json", pair["authority_sha256"]))
    if not pair["verified_pair"] or pair["generation"] != 1 or set(pair["attempt_result_sha256"]) != {"installed", "successor"}:
        raise ValueError("Expected both verified generation-one field arms")
    attempts, launches = {}, {}
    for role, pin in pair["attempt_result_sha256"].items():
        attempt = folder / role / "attempt-000001"
        attempts[role] = json.loads(checked(root, attempt / "result.json", pin))
        launches[role] = json.loads(local_bytes(root, attempt / "launch.json"))
    candidate = folder / "successor" / "attempt-000001" / "publication"
    capture = json.loads(local_bytes(root, candidate / "unified-short-bootstrap.json"))
    release = json.loads(local_bytes(root, candidate / "algo08v3-successor-release.json"))
    witness = json.loads(checked(root, candidate / "exact-named-raw-witness.json", witness_pin))
    archive = capture["archive_root"]
    if (release["build_sha256"] != tagged(BUILD_PIN) or release["archive_sha256"] != authority["archive_sha256"]
            or release["authority_sha256"] != pair["authority_sha256"]
            or release["terminal_sha256"] != attempts["successor"]["evidence"]["receipt"]["terminal_sha256"]
            or capture["causal_cutoff_utc_ns"] != authority["causal_cutoff_utc_ns"]
            or capture["solver_recipe"]["archive_sha256"] != authority["archive_sha256"]
            or argument_value(launches["successor"]["command"], "--build-sha256") != tagged(BUILD_PIN)
            or any(result["outcome"] != "complete" or result["raw_identity"] != authority
                   or argument_value(launches[role]["command"], "--archive") != archive
                   for role, result in attempts.items())):
        raise ValueError("The two field runs and their catalogue authority disagree")
    ports = witness["ports"]
    transfer, = ports["portable"]["transfers"]
    attempt, = ports["portable"]["attempts"]
    values = read_coverage(ports["verified_tle"], authority["archive_sha256"], authority["causal_cutoff_utc_ns"], artifact)
    counts = transfer["counts"]
    if (transfer["sha256"] != tagged(portable["sha256"]) or transfer["file"] != portable["path"]
            or values["verified_bytes"] != attempt["verified_bytes"]
            or values["opened_unique_bodies"] != attempt["bodies"]
            or values["index_digest_overlap"] != counts["sidecar_hit_bodies"]
            or values["index_row_overlap"] != counts["sidecar_hit_rows"]
            or values["opened_unique_bodies"] != counts["sidecar_hit_bodies"] + counts["cold_bodies"]
            or counts["invalid_bodies"]):
        raise ValueError("The durable portable index and actual verified-read witness disagree")
    return values | dict(case=case, archive_argument=archive, enrolled_archive_sha256=authority["archive_sha256"],
                         causal_cutoff_utc_ns=authority["causal_cutoff_utc_ns"], actual_verified_reads=attempt["verified_reads"],
                         portable_transfer=transfer, field_pair_sha256=pair_pin, field_witness_sha256=witness_pin,
                         strict_parser_counters={role: result["evidence"]["receipt"]["tle_records"]
                                                 for role, result in attempts.items()})


def verify(root):
    frozen = root / "frozen-build"
    build = json.loads(checked(root, frozen / "build.json", BUILD_PIN))
    manifest = json.loads(checked(root, frozen / "runtime-manifest.json", RUNTIME_PIN))
    portable = build["native"]["--portable-orbit-index"]
    durable = frozen / "files" / portable["path"].lstrip("/")
    pin = manifest["artifacts"][portable["path"]]
    if frozen / pin["path"] != durable or tagged(pin["sha256"]) != tagged(portable["sha256"]):
        raise ValueError("The portable index pin differs from the durable receipt")
    data = checked(root, durable, pin["sha256"])
    bodies = index_bodies(data)
    return dict(build_sha256=BUILD_PIN, accepted_manifest_assets=sorted(manifest["artifacts"]),
                portable_index_sha256=pin["sha256"], portable_artifact_bytes=len(data),
                portable_artifact_bodies=len(bodies), portable_artifact_rows=sum(bodies.values()),
                cases={case: audit_case(root, case, bodies, portable) for case in PAIRS},
                saved_tle_body_opens=0, waveform_opens=0, solver_children=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    wall, cpu = perf_counter_ns(), process_time_ns()
    result = verify(ROOT)
    result["verification_readout"] = dict(wall_ns=perf_counter_ns() - wall, cpu_ns=process_time_ns() - cpu)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
