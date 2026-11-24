"""Extract detached, independently signed visits from a staged original Zstd prefix."""

import argparse
from gzip import decompress
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
from time import perf_counter, process_time

import zstandard

from leo.contracts.multirate_window_recording import ShortWindowIndexV2, ShortWindowManifestV2


HERE = Path(__file__).resolve().parent
CASES = {
    "DS30-0163": ("first-member-0163-idle.json.gz",
                  "e6dfabaf402fd84179fe69d5f971a906258dd3446456cacc018a6cccff57a6a9"),
    "DS30-0419": ("first-member-0419-idle.json",
                  "1ce2f2e896c0dfba19cc750937cf9eac06664da036ea5a502be32f4c30113ffd"),
}


def digest(body):
    return "sha256:" + sha256(body).hexdigest()


def checked(body, expected):
    if digest(body)[7:] != expected.removeprefix("sha256:"):
        raise ValueError("Frozen bytes do not match their expected digest")
    return body


def local_member(root, path, length):
    if (root.parent != Path("/tmp") or root.resolve(strict=True) != root or path.resolve(strict=True) != path
            or not path.is_relative_to(root)):
        raise ValueError("Refusing a non-enrolled path or symlink")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_dev != root.stat().st_dev or info.st_size != length:
            raise ValueError("Changed staged member geometry")
        body = stream.read(length + 1)
    if len(body) != length:
        raise ValueError("Changed read extent")
    return body


def partial_decode(encoded, decoded_limit):
    dec = zstandard.ZstdDecompressor().decompressobj()
    raw = bytearray()
    for off in range(0, len(encoded), 1024**2):
        raw.extend(dec.decompress(encoded[off:off + 1024**2]))
        if len(raw) > decoded_limit or dec.eof or dec.unused_data:
            raise ValueError("Expected one incomplete original frame within its signed decoded extent")
    witness = dict(encoded_bytes_supplied=len(encoded), encoded_tail_unused_bytes=len(dec.unused_data),
                   encoded_unconsumed_tail_bytes=len(dec.unconsumed_tail), frame_eof=dec.eof,
                   decoded_bytes=len(raw), decoded_sha256=digest(raw))
    return raw, witness


def confirm_decode(encoded, raw):
    check = subprocess.run(["/usr/bin/zstd", "-q", "-d", "-c"], input=encoded, capture_output=True,
                           timeout=10, check=False)
    if (check.returncode != 1 or b"premature end" not in check.stderr.lower()
            or check.stdout != raw):
        raise ValueError("Independent decoder did not emit the same incomplete data")
    return dict(argv=["/usr/bin/zstd", "-q", "-d", "-c"], exit=check.returncode,
                error=check.stderr.decode(), decoded_bytes=len(check.stdout), decoded_sha256=digest(check.stdout))


def read_index(index, manifest, chunk):
    receiver_ids = tuple(manifest.receiver_ids)
    if receiver_ids != (0, 1) or manifest.sample_rate_hz != 10_000_000:
        raise ValueError("The signed format is not the enrolled dual-radio format")
    targets = {target["target_id"]: target for target in manifest.configuration["targets"]}
    lines = index.splitlines()
    if len(lines) != chunk["window_count"] or len(lines) != 64 or len(targets) != len(manifest.configuration["targets"]):
        raise ValueError("The signed member inventory changed")
    offset, previous_end, generation = 0, None, None
    result = []
    for number, line in enumerate(lines):
        row = ShortWindowIndexV2.model_validate_json(line)
        acquisition = row.acquisition
        if generation is None:
            generation = acquisition["generation"]
        if (row.sequence != number or acquisition["global_visit"] != number
                or type(generation) is not int or acquisition["generation"] != generation
                or (previous_end is not None and acquisition["sample_start"] < previous_end)
                or acquisition["sample_end"] < acquisition["sample_start"]
                or row.payload_offset_bytes != offset or row.receiver_count != len(receiver_ids)
                or row.payload_bytes != row.sample_count * row.receiver_count * 4
                or row.sample_count > manifest.sample_rate_hz // 50 or row.target_id not in targets):
            raise ValueError("The complete signed index failed original chronology or byte geometry")
        previous_end = acquisition["sample_end"]
        result.append(dict(sequence=number, signed_row=json.loads(line), decoded_offset_bytes=offset,
                           decoded_bytes=row.payload_bytes, sha256=row.iq_sha256, receiver_ids=list(receiver_ids),
                           target=targets[row.target_id]))
        offset += row.payload_bytes
    if offset != chunk["uncompressed_bytes"]:
        raise ValueError("The complete signed index differs from the original decoded extent")
    return result


def complete_prefix(raw, rows):
    end = 0
    attested = []
    for row in rows:
        start, length = row["decoded_offset_bytes"], row["decoded_bytes"]
        if start != end or length < 0:
            raise ValueError("Signed visits must cover one contiguous decoded extent")
        if start + length > len(raw):
            return attested, end, dict(sequence=row["sequence"], expected_bytes=length,
                                       emitted_bytes=len(raw) - start, reason="incomplete_decoded_visit")
        if digest(memoryview(raw)[start:start + length]) != row["sha256"]:
            raise ValueError(f"Signed IQ digest mismatch at visit {row['sequence']}")
        attested.append(row)
        end += length
    raise ValueError("Unexpected complete signed member in an incomplete-frame study")


def sealed_stage(case):
    filename, pin = CASES[case]
    report = (HERE / "measurements" / filename).read_bytes()
    body = decompress(report) if filename.endswith(".gz") else report
    attestation = json.loads(checked(body, pin))
    stage = attestation["stage"]
    base = Path(f"/tmp/leo-v3-{case[-4:]}-first-idle-stage01")
    stored = json.loads(checked(local_member(base, base / "stage.json", (base / "stage.json").stat().st_size),
                                attestation["stage_sha256"]))
    cp_file = base / "checkpoint.json"
    checkpoint = json.loads(checked(local_member(base, cp_file, cp_file.stat().st_size),
                                    attestation["checkpoint_sha256"]))
    chunk = stage["member"]
    extent = Path(checkpoint["relative"])
    folder = Path(stage["stage"])
    actual = base / extent
    pin = attestation["verified_partial_sha256"]
    count = attestation["verified_partial_bytes"]
    if (stored != stage or stage["case"] != case or stage["complete"]
            or actual != folder / chunk["payload_relative_path"] or len(extent.parts) != 2
            or not 0 < count == stage["payload_bytes"] < chunk["compressed_bytes"]
            or dict(checkpoint["prefixes"]).get(count) != pin or checkpoint["sha256"] != chunk["compressed_sha256"]
            or checkpoint["size"] != chunk["compressed_bytes"] or checkpoint["source_identity"][2] != checkpoint["size"]):
        raise ValueError("Frozen checkpoint and member disagree")
    manifest_path = folder / "manifest.json"
    manifest_len = manifest_path.stat().st_size
    if not 0 < manifest_len <= 256_000 or not 0 < chunk["index_bytes"] <= 2_000_000:
        raise ValueError("Unexpected sidecar extent")
    manifest_bytes = checked(local_member(base, manifest_path, manifest_len), stage["manifest_sha256"])
    manifest = ShortWindowManifestV2.model_validate_json(manifest_bytes)
    if (manifest.session_id != folder.name or json.loads(manifest_bytes)["chunks"][0] != chunk
            or chunk["chunk_index"] != 0 or chunk["first_sequence"] != 0):
        raise ValueError("Manifest no longer binds the exact original member")
    index_path = folder / chunk["index_relative_path"]
    index = checked(local_member(base, index_path, chunk["index_bytes"]), chunk["index_sha256"])
    if attestation["original_metadata_body_hashes"] != {
            "manifest.json": digest(manifest_bytes), index_path.name: digest(index)}:
        raise ValueError("Earlier independent sidecar verification differs")
    rows = read_index(index, manifest, chunk)
    return stage, manifest, rows, checked(local_member(base, actual, count), pin)


def extract(case, output):
    start, cpu_start = perf_counter(), process_time()
    stage, manifest, rows, encoded = sealed_stage(case)
    authority_clock = perf_counter() - start
    raw, primary = partial_decode(encoded, stage["member"]["uncompressed_bytes"])
    base_clock = perf_counter() - start
    alternate = confirm_decode(encoded, raw)
    verified, extent, stop = complete_prefix(raw, rows)
    if not verified or len(raw) >= stage["member"]["uncompressed_bytes"]:
        raise ValueError("No bounded, complete original visits were emitted")
    first = verified[0]["signed_row"]["acquisition"]
    clock_anchor = json.loads(first["retune_receipt"])["utc_clock_bracket"]
    if clock_anchor is None or clock_anchor["sample_counter"] != first["sample_start"]:
        raise ValueError("The first signed acquisition lacks its own clock anchor")
    output.mkdir(mode=0o700)
    destination = output / "verified.ci16"
    with destination.open("xb") as stream:
        if stream.write(memoryview(raw)[:extent]) != extent:
            raise OSError("Short write on the detached visit byte extent")
    receipt = dict(
        schema="leo.research.detached-original-prefix-visits.v1", case=case,
        original_session=stage["original_session"], original_inventory_sha256="sha256:" + stage["inventory_sha256"],
        original_raw_authority=stage["raw_authority"], manifest_sha256=stage["manifest_sha256"],
        index_sha256=stage["member"]["index_sha256"], encoded_prefix_sha256=digest(encoded),
        encoded_prefix_bytes=len(encoded), original_encoded_bytes=stage["member"]["compressed_bytes"],
        original_encoded_sha256=stage["member"]["compressed_sha256"], original_issued=stage["member"]["window_count"],
        clock_anchor=clock_anchor, receiver_ids=list(manifest.receiver_ids), sample_rate_hz=manifest.sample_rate_hz,
        windows=verified, verified_file=dict(name=destination.name, bytes=extent, sha256=digest(memoryview(raw)[:extent])),
        stop=stop, trailing_decoded_bytes=len(raw) - extent, trailing_decoded_sha256=digest(memoryview(raw)[extent:]),
        decoders=dict(primary=primary, independent=alternate, python_zstandard=zstandard.__version__),
        clocks=dict(authority_wall_s=authority_clock, through_first_decode_wall_s=base_clock,
                    overall_wall_s=perf_counter()-start, controller_cpu_s=process_time()-cpu_start),
        complete_compressed_sha_verified=False, frame_checksum_verified=False, normal_acquisition_contract=False,
        recording_acceptance=False, original_backing_payload_reads=0)
    with (output / "visits.json").open("x") as stream:
        json.dump(receipt, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
    return dict(case=case, visits=len(verified), bytes=extent, next_visit=stop["sequence"],
                witness_sha256=digest((output / "visits.json").read_bytes()))


def launch(output):
    if output.parent != Path("/tmp") or output.exists() or output.is_symlink():
        raise ValueError("Require a fresh private /tmp output")
    mounts = subprocess.check_output(["findmnt", "-n", "-o", "FSTYPE", "-T", "/tmp"], text=True)
    if mounts.strip() != "tmpfs":
        raise ValueError("The two local staging paths and detached output require tmpfs")
    output.mkdir(mode=0o700)
    for case in CASES:
        print(json.dumps(extract(case, output / case), sort_keys=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    launch(parser.parse_args().output)
