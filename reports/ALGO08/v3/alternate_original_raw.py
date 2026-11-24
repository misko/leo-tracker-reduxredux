"""Read and verify even original compressed members with ordinary 20 ms acquisition."""

from hashlib import sha256
from inspect import getsource
from pathlib import Path
import stat
from types import SimpleNamespace


INCLUDE = "                if valid_window_support("
SKIP = ("                if w.samples is None:\n"
        "                    skipped.append(visit)\n"
        "                elif valid_window_support(")


def plan(inventory, segment_factory):
    """Match the post-temporal mask's signed member list before opening payloads."""
    entries, members, offset = {}, [], 0
    for entry in inventory["segments"]:
        source = segment_factory(entry)
        manifest = source.reader.manifest
        if (source.receiver_ids != (0, 1) or manifest.schema_version != 2 or manifest.window_ms != 20
                or manifest.sample_rate_hz != 10_000_000 or manifest.window_count != entry["windows"]):
            raise ValueError("Expected the original 20 ms stereo segment")
        segment = []
        for chunk in manifest.chunks:
            ordinal = len(members)
            first = offset + chunk.first_sequence
            span = dict(ordinal=ordinal, segment=entry["scope"], manifest=entry["manifest_digest"], first_visit=first,
                        stop_visit=first + chunk.window_count, retained=ordinal % 2 == 0,
                        **chunk.model_dump(mode="json"))
            segment.append(span)
            members.append(span)
        if not segment or segment[-1]["stop_visit"] != offset + entry["windows"]:
            raise ValueError("Original compressed member extents are incomplete")
        entries[entry["path"]] = source, segment
        offset += entry["windows"]
    if offset != inventory["window_count"] or not members:
        raise ValueError("Original member extents must account for every visit")
    return entries, members


def file_identity(path, expected_bytes, device):
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_dev != device or info.st_size != expected_bytes:
        raise ValueError(f"Signed member extent or file identity changed: {path}")
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def omitted_index(path, member, model):
    """Authenticate signed metadata for an omitted member without reading IQ."""
    with path.open("rb") as stream:
        raw = stream.read(member["index_bytes"] + 1)
    if len(raw) != member["index_bytes"] or "sha256:" + sha256(raw).hexdigest() != member["index_sha256"]:
        raise ValueError("Omitted member index differs from its signed manifest")
    offset = 0
    rows = [model.model_validate_json(line) for line in raw.splitlines()]
    if len(rows) != member["window_count"]:
        raise ValueError("Omitted member index count differs from its manifest")
    for sequence, row in enumerate(rows, member["first_sequence"]):
        if (row.sequence != sequence or row.receiver_count != 2 or row.payload_offset_bytes != offset
                or row.payload_bytes != row.sample_count * 8):
            raise ValueError("Omitted member index geometry is not consecutive stereo CI16")
        offset += row.payload_bytes
    if offset != member["uncompressed_bytes"]:
        raise ValueError("Omitted member index does not cover its attested payload extent")
    return rows


def selected_source(source, members, audit):
    from leo.contracts.multirate_window_recording import ShortWindowIndexV2

    def windows():
        folder = source.reader.path
        device = folder.stat().st_dev
        for member in members:
            indexes = folder / member["index_relative_path"]
            payload = folder / member["payload_relative_path"]
            identity = file_identity(payload, member["compressed_bytes"], device)
            index_identity = file_identity(indexes, member["index_bytes"], device)
            first = member["first_sequence"]
            keep = member["retained"]
            scans = (source.reader.windows(start_sequence=first, stop_sequence=first + member["window_count"])
                     if keep else (SimpleNamespace(index=row, samples=None)
                                   for row in omitted_index(indexes, member, ShortWindowIndexV2)))
            for window in scans:
                row = window.index
                yield SimpleNamespace(sequence=row.sequence, acquisition=row.acquisition, iq_sha256=row.iq_sha256,
                                      target=source.targets[row.target_id], samples=window.samples,
                                      sample_rate_hz=source.reader.manifest.sample_rate_hz)
            if (file_identity(payload, member["compressed_bytes"], device) != identity
                    or file_identity(indexes, member["index_bytes"], device) != index_identity):
                raise ValueError("Source changed during original-member read")
            audit["members"].append(dict(**member, payload_identity=identity, index_identity=index_identity,
                                         index_verified=True, compressed_verified=keep, decoded_chunk_verified=keep,
                                         per_window_iq_verified=keep, payload_opened=keep))

    return SimpleNamespace(reader=source.reader, receiver_ids=source.receiver_ids, radio=source.radio, windows=windows)


def preserve_stock_acquisition(scan, authority, expected_members, guard, audit):
    """Use the pinned original receiver loop, with a separate skipped-acquisition branch."""
    ordinary = scan.acquire
    body = getsource(ordinary)
    if body.count(INCLUDE) != 1:
        raise ValueError("The released acquisition dispatch did not match the reviewed source")
    compiled = compile(body.replace(INCLUDE, SKIP, 1), ordinary.__code__.co_filename, "exec")

    def acquire(session, inventory_sha, inventory, assets):
        from leo.contracts.digests import canonical_digest

        if audit or inventory_sha != authority["inventory"] or session != authority["session"]:
            raise ValueError("Expected one acquisition under the signed original inventory")
        selected, members = plan(inventory, scan.FastSegmentSource)
        if expected_members is not None and members != expected_members:
            raise ValueError("Raw member plan differs from the frozen saved mask")
        for path, (source, spans) in selected.items():
            guard.update(Path(path) / m["payload_relative_path"] for m in spans if not m["retained"])
        audit["members"] = []
        skipped = []

        def open_segment(entry):
            source, spans = selected[entry["path"]]
            return selected_source(source, spans, audit)

        namespace = dict(vars(scan), FastSegmentSource=open_segment, skipped=skipped)
        exec(compiled, namespace)
        native = namespace["acquire"](session, inventory_sha, inventory, assets)
        provenance = native["provenance"]
        if (native["source"]["raw_recording_authority_digest"] != authority["authority"]
                or native["clock_anchor"]["before"]["realtime_ns"] != authority["cutoff_utc_ns"]
                or len(audit["members"]) != len(members)):
            raise ValueError("Sampled acquire did not preserve the full attested authority")
        expected = [visit for m in members if not m["retained"] for visit in range(m["first_visit"], m["stop_visit"])]
        if skipped != expected or provenance["window_count"] != (
                len(skipped) + provenance["processed_windows"] + provenance["invalid_capture"]):
            raise ValueError("Processed, invalid and skipped visits must account for the source")
        audit.update(skipped_acquisition_windows=skipped, members_sha256=canonical_digest(members),
                     retained_compressed_bytes=sum(m["compressed_bytes"] for m in members if m["retained"]),
                     omitted_compressed_bytes=sum(m["compressed_bytes"] for m in members if not m["retained"]),
                     all_payloads_newly_verified=not bool(skipped))
        if skipped:
            provenance["research_sampling"] = {
                "kind": "raw-even-original-compressed-members", "skipped_acquisition_windows": skipped,
                "members_sha256": audit["members_sha256"], "original_inventory_sha256": inventory_sha,
                "omitted_payload_verification": "signed manifest and index attestations only", "receiver_slots": [0, 1],
            }
        return native

    return acquire


def scan_report(report, recording, run_id, native):
    result = report(recording, run_id, native)
    sampling = native["provenance"].get("research_sampling")
    if sampling is not None:
        result["counts"]["skipped_acquisition"] = len(sampling["skipped_acquisition_windows"])
        result["research_sampling"] = sampling
    if sum(result["counts"].values()) != result["window_count"]:
        raise ValueError("Raw analysis must account for every scheduled visit")
    return result
