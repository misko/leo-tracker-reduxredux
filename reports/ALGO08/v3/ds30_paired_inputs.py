"""Bind the full signed DS30 roster and one original paired request at a time."""

import csv
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "reports/2026_11_20_ds30_fast/dataset"
MANIFEST = "sha256:a4ce879975be0593f1adeb7c106f31660c6c423f17e2c7858985244530dc0eb8"
UNITS = "sha256:3423d9b489f2d9d731e3f2c7b58e67f6dd8510fc40396ba414161476597bb10f"
AUDIT = "sha256:87e6c389cc4dccafb204ada3def360343514d283d65418ee3211817d9a57b5c5"
FIRST100 = "sha256:8535781f2ed67016fe42c6ff820f503e9876c1b0f356f3cf2d9c1b6e8d216aa2"
BULK = Path("/srv/bulk")
ORIGINAL = BULK / "leo-dev/ds30-full-20261121"
SMOKE = ("DS30-0107", "DS30-0049")
ARMS = ("installed", "successor")
CALIBRATIONS = ("c0", "fitted_c")
SEED = "DS30-charted-original-v1"


def encode(document):
    return json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def digest(body):
    return "sha256:" + sha256(body).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def checked(path, expected):
    body = path.read_bytes()
    if digest(body) != "sha256:" + expected.removeprefix("sha256:"):
        raise ValueError(f"Sealed bytes changed: {path}")
    return body


def publish(path, body, *, replace=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
            if replace:
                os.replace(temporary, path)
            else:
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    if path.read_bytes() != body:
                        raise ValueError(f"Immutable campaign ledger changed: {path}") from None
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            temporary.unlink(missing_ok=True)


def write(path, document):
    publish(path, encode(document) + b"\n")


def historical_membership(path):
    rows = list(csv.DictReader(checked(path, FIRST100).decode().splitlines()))
    labels = {row["case"] for row in rows}
    if len(labels) != 100 or any(not re.fullmatch(r"DS30-\d{4}", tag) for tag in labels):
        raise ValueError("Historical first-100 CSV must identify exactly 100 DS30 cases")
    return labels


def assignments(members, units, first100):
    if units["manifest_sha256"] != MANIFEST:
        raise ValueError("Evaluation units refer to another dataset revision")
    names = dict(zip(units["dataset_labels"], units["case_ids"], strict=True))
    labels = {row["dataset_label"] for row in members}
    if (set(names) != labels or len(names) != len(members) or len(set(names.values())) != len(names)
            or not first100 <= labels):
        raise ValueError("Unmatched DS30 labels, signed units or historical membership")
    ordered = sorted(members, key=lambda row: digest(encode([SEED, row["case_id"], row["raw_recording"]["identity_sha256"]])))
    results = []
    for index, member in enumerate(ordered):
        label = member["dataset_label"]
        if not re.fullmatch(r"DS30-\d{4}", label) or names[label] != member["case_id"]:
            raise ValueError("Signed case identity differs from its evaluation unit")
        results.append(dict(case=label, case_id=member["case_id"], assigned_rank=index + 1,
                            order=list(ARMS if index % 2 == 0 else reversed(ARMS)),
                            recording_state=member["recording_state"], window_count=member["window_count"],
                            recording=member["raw_recording"]["root"], raw_identity_sha256=member["raw_recording"]["identity_sha256"],
                            manifest_raw_authority_sha256=member["raw_authority_digest"], historical_first100=label in first100))
    if len({row["raw_identity_sha256"] for row in results}) != len(results):
        raise ValueError("Duplicate acquisition identity in the signed roster")
    return results


def load_cohort():
    body = gzip.decompress((DATA / "manifest.json.gz").read_bytes())
    if digest(body) != MANIFEST:
        raise ValueError("The full DS30 accession changed")
    members = json.loads(body)["members"]
    units = json.loads(checked(DATA / "evaluation-units.json", UNITS))
    audit = json.loads(checked(ROOT / "reports/2026_11_21_ds30_full/input-audit.json", AUDIT))
    if (len(members) != 455 or sum(r["recording_state"] == "complete" for r in members) != 411
            or set(audit["bindings"]) != set(units["dataset_labels"])):
        raise ValueError("Missing signed full-cohort custody")
    return members, units, audit["bindings"]


def member_file(path, size):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size != size:
        raise ValueError(f"Signed original file size/type differs: {path}")


def historical_input(row, member, historical, region):
    """Inspect enrolled paths only. The worker later authenticates their waveform bytes."""
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    case = row["case"]
    recording = Path(row["recording"])
    if recording.resolve(strict=True) != recording or recording.name != member["recording_id"]:
        raise ValueError("The actual source is outside the enrolled original recording")
    binding = json.loads(checked(ORIGINAL / "bindings" / (case + ".json"), historical["binding_sha256"]))
    old = binding["case"]
    request = json.loads(checked(BULK / old["request"]["path"], old["request"]["sha256"]))
    archive = ORIGINAL / "snapshot/inputs" / case / "tle"
    cutoff = binding["orbit_cutoff_ns"]
    raw = member["raw_recording"]
    manifests = {Path(r["path"]): r["sha256"] for r in raw["segments"]}
    earlier = {BULK / r["path"]: "sha256:" + r["sha256"].removeprefix("sha256:")
               for r in old["recording"]["segments"]}
    if (old["id"] != case or old["valid_visits"] != historical["usable_visits"] or manifests != earlier
            or old["recording"]["window_count"] != member["window_count"] or raw["integrity_errors"]
            or request["role"] != "baseline" or request["job"]["evaluation_reference"] is not None
            or request["job"]["tle_root"] != str(archive) or request["job"]["identity"]["session_id"] != old["session_id"]
            or request["job"]["search_center"] != region["center"] or request["job"]["screen_center"] != region["screen_center"]
            or old["regions"] != [{"id": "original", "center": region["center"]}] or region["width_km"] != 25.0
            or not 0 < cutoff <= member["captured_utc_ns"]):
        raise ValueError("Historical causal inputs or original offer disagree with the accession")
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    snapshots = {v.path.name: v.sha256 for v in refs}
    if (not refs or snapshots != request["causal_snapshots"] or len(refs) != binding["orbit_count"]
            or any(item.collected_utc_ns >= cutoff for item in refs)):
        raise ValueError("Original causal catalogue membership changed")
    for manifest, expected in manifests.items():
        if manifest.parent.parent != recording or manifest.resolve(strict=True) != manifest:
            raise ValueError("Exact manifest path left its enrolled recording")
        checked(manifest, expected)
    for item in raw["chunks"]:
        manifest, payload, index = (Path(item[k]) for k in ("segment_manifest", "payload_path", "index_path"))
        if manifest not in manifests or payload != manifest.parent / item["payload_relative_path"] or index != manifest.parent / item["index_relative_path"]:
            raise ValueError("A member path leaves its signed segment")
        member_file(payload, item["compressed_bytes"])
        member_file(index, item["index_bytes"])
    return dict(archive=str(archive), offered_region=region, expected_admitted=old["valid_visits"],
                historical_binding_sha256=historical["binding_sha256"], expected=dict(recording=str(recording),
                   session_id=old["session_id"], raw_authority_sha256=old["raw_authority"],
                   window_count=row["window_count"], causal_cutoff_utc_ns=cutoff, archive_sha256=canonical_digest(snapshots)))
