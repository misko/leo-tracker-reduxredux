#!/usr/bin/env python3
"""Build the CLI's small metadata snapshot from frozen membership authorities.

Only explicitly registered authorities are read; analysis-run manifests are not
dataset membership. No IQ is opened. Archived parts and optional raw recording
metadata are checksum-verified. Missing metadata stays unknown.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from leo.cli.datasets import DatasetCatalogue, DatasetSummary

ARCHIVE = "reports/2026_10_18_dataset_manifest_archive"
# (dataset ID, revision, current, authority). Add new frozen cohorts here.
EXTRA_AUTHORITIES = (
    ("DS24", "1", False, "reports/2026_10_23_ds24_fast10m/manifest.json"),
    ("DS24", "2", True, "reports/2026_10_24_ds24_extension/membership-summary.json"),
    ("DS25", "1", True, "reports/2026_10_24_ds25_adaptive/dataset/manifest.json.gz"),
    ("DS26", "1", True, "reports/2026_10_30_ds26_all_new_recordings/membership-summary.json"),
    ("DS27", "1", True, "reports/2026_10_31_ds27_algo04_review/dataset/manifest.json.gz"),
    (
        "DS28",
        "1",
        False,
        "reports/2026_11_01_ds28_revision2/dataset/previous-revision-manifest.json",
    ),
    ("DS28", "2", True, "reports/2026_11_01_ds28_revision2/dataset/membership-summary.json"),
)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def capture_documents(member: dict):
    """Visit only acquisition metadata; never restoration or analysis settings."""
    yield member
    for key in ("document", "manifest", "configuration", "timing", "receipt", "plan", "geometry"):
        value = member.get(key)
        if isinstance(value, dict):
            yield from capture_documents(value)
    raw = member.get("raw_recording", {})
    for segment in raw.get("segments", []):
        yield from capture_documents(segment)


def scan_metadata(member: dict) -> tuple[str, int | None]:
    documents = list(capture_documents(member))
    kinds = {
        str(doc.get(key, "")) for doc in documents for key in ("recording_format", "kind", "mode")
    }
    mode = "unknown"
    if kinds & {"fast", "short_window_iq_recording"}:
        mode = "fast"
    elif kinds & {"adaptive", "starlink_adaptive_hop_iq", "starlink_adaptive_hop_plan"}:
        mode = "adaptive"
    elif kinds & {
        "hop",
        "starlink_hop_iq",
        "starlink_persistent_hop_iq",
        "starlink_hop_plan",
        "starlink_persistent_hop_plan",
    }:
        mode = "hop"
    else:
        identifier = member.get("recording_id", member.get("session_id", ""))
        if identifier.startswith(("fast8-", "fast-")):
            mode = "fast"
        elif identifier.startswith(("scan-fw-", "scan-hop-")):
            # Session family identifies hopping, not the adaptive policy.
            mode = "hop"
    rates = {doc["sample_rate_hz"] for doc in documents if doc.get("sample_rate_hz") is not None}
    if any(type(rate) is not int or rate <= 0 for rate in rates):
        raise ValueError("invalid acquisition sample rate")
    if len(rates) > 1:
        raise ValueError("conflicting acquisition sample rates in one recording")
    return mode, next(iter(rates), None)


def summarise(
    document: dict,
    *,
    dataset: str,
    revision: str = "1",
    current: bool = True,
    sources: list[dict] | None = None,
    resolve_metadata=None,
) -> DatasetSummary:
    notes = []
    if dataset == "DS1":
        # Nested views and case groups overlap. Count each acquisition once.
        ids = {session for group in document["groups"] for session in group["session_ids"]}
        members = [{"session_id": session} for session in sorted(ids)]
    elif dataset == "DSX01":
        # Regions overlap in five complete scans; they are not fifteen scans.
        ids = {region["source_id"] for region in document["regions"]}
        if len(ids) != document["recording_count"]:
            raise ValueError("DSX01 region sources disagree with recording_count")
        members = [{"recording_id": name, "mode": "fast"} for name in sorted(ids)]
        notes.append("Counts complete source scans, not overlapping challenge regions.")
    else:
        members = next(
            (
                document[key]
                for key in ("members", "captures", "sessions")
                if isinstance(document.get(key), list)
            ),
            None,
        )
        if members is None:
            raise ValueError(f"{dataset}: no recognized membership array")
        # Early inventories retain explicitly excluded candidates in captures.
        members = [member for member in members if member.get("admission_status") != "excluded"]
    identifiers = [
        member.get("recording_id", member.get("session_id", member.get("case_id")))
        for member in members
    ]
    if None in identifiers or len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{dataset}: missing or duplicate recording identities")
    buckets = Counter()
    unresolved_metadata = 0
    for member in members:
        mode, rate = scan_metadata(member)
        if resolve_metadata is not None and (rate is None or mode in ("hop", "unknown")):
            extra = resolve_metadata(member)
            if extra is not None:
                mode, rate = scan_metadata({**member, "document": extra})
            else:
                unresolved_metadata += 1
        buckets[mode, rate] += 1
    counts = document.get("counts", {})
    for key in ("members", "recordings", "sessions", "admitted"):
        if key in counts and counts[key] != len(members):
            raise ValueError(f"{dataset}: declared {key} count disagrees with membership")
    for kind in ("fast", "adaptive"):
        key = kind + "_recordings"
        if key in counts and counts[key] != sum(
            n for (mode, _), n in buckets.items() if mode == kind
        ):
            raise ValueError(f"{dataset}: {key} disagrees with classified acquisition metadata")
    if unresolved_metadata:
        notes.append(
            f"{unresolved_metadata} members lack accessible checksum-bound capture metadata."
        )
    if any(mode == "hop" for mode, _ in buckets):
        notes.append(
            "Legacy hop identities do not establish whether an adaptive policy was active."
        )
    return DatasetSummary.model_validate(
        {
            "dataset": dataset,
            "revision": revision,
            "current": current,
            "scans": len(members),
            "breakdown": [
                {"scan_type": mode, "sample_rate_hz": rate, "scans": n}
                for (mode, rate), n in sorted(
                    buckets.items(),
                    key=lambda pair: (pair[0][0], pair[0][1] is None, pair[0][1] or 0),
                )
            ],
            "sources": sources or [],
            "notes": notes,
        }
    )


class AuthorityReader:
    def __init__(self, repo: Path, source_roots: list[Path]):
        self.repo = repo
        self.source_roots = [repo, *source_roots]

    def read(self, relative: str) -> bytes:
        for root in self.source_roots:
            path = root / relative
            if path.is_file():
                return path.read_bytes()
        result = subprocess.run(
            ["git", "show", f"HEAD:{relative}"], cwd=self.repo, capture_output=True, check=False
        )
        if result.returncode:
            raise FileNotFoundError(f"dataset authority not found: {relative}")
        return result.stdout

    def recording_metadata(self, member: dict) -> dict | None:
        segments = member.get("raw_recording", {}).get("segments", [])
        if not segments:
            return None
        # A fast acquisition's segments share capture configuration. No IQ read.
        segment = segments[0]
        if "document" in segment:
            return segment["document"]
        expected = segment.get("sha256", "").removeprefix("sha256:")
        if not expected:
            return None
        try:
            raw = Path(segment["path"]).read_bytes()
        except (OSError, KeyError):
            return None
        if sha256(raw) != expected:
            raise ValueError(f"changed capture metadata: {segment['path']}")
        value = json.loads(raw)
        return value.get("document", value.get("manifest", value))


def build_catalogue(reader: AuthorityReader, *, resolve_metadata: bool = False) -> DatasetCatalogue:
    archive = json.loads(reader.read(f"{ARCHIVE}/catalogue.json"))
    datasets = []
    resolver = reader.recording_metadata if resolve_metadata else None
    for authority in archive["authorities"]:
        name = authority["dataset"]
        if name == "DS3-inference":  # Derived inference units, not a new membership.
            continue
        streams = []
        sources = []
        for part in authority["parts"]:
            path = f"{ARCHIVE}/{part['path']}"
            raw = reader.read(path)
            if sha256(raw) != part["sha256"] or len(raw) != part["bytes"]:
                raise ValueError(f"archive part checksum/length mismatch: {path}")
            streams.append(raw)
            sources.append({"path": path, "sha256": sha256(raw)})
        raw = b"".join(streams)
        if authority["encoding"] in ("zstd", "concatenated-zstd-parts"):
            import zstandard

            with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw)) as stream:
                raw = stream.read()
        elif authority["encoding"] != "identity":
            raise ValueError("unsupported archive encoding")
        if sha256(raw) != authority["original_sha256"] or len(raw) != authority["original_bytes"]:
            raise ValueError(f"original authority checksum/length mismatch: {name}")
        datasets.append(
            summarise(json.loads(raw), dataset=name, sources=sources, resolve_metadata=resolver)
        )
        # Drop the large JSON authority before reading the next one.
        del raw, streams
    for name in ("DS14", "DS15", "DS19"):
        datasets.append(
            DatasetSummary(dataset=name, notes=["Historical membership authority unlocated."])
        )
    for name, revision, current, path in EXTRA_AUTHORITIES:
        raw = reader.read(path)
        sources = [{"path": path, "sha256": sha256(raw)}]
        if path.endswith(".gz"):
            raw = gzip.decompress(raw)
        datasets.append(
            summarise(
                json.loads(raw),
                dataset=name,
                revision=revision,
                current=current,
                sources=sources,
                resolve_metadata=resolver,
            )
        )
    return DatasetCatalogue(
        generated_utc=datetime.now(UTC).isoformat(timespec="seconds"), datasets=datasets
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-root", type=Path, action="append", default=[])
    parser.add_argument(
        "--resolve-recording-metadata",
        action="store_true",
        help="Read checksum-bound capture manifests for missing rates/modes; never IQ.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalogue = build_catalogue(
        AuthorityReader(args.repo, args.source_root),
        resolve_metadata=args.resolve_recording_metadata,
    )
    args.output.write_text(catalogue.model_dump_json(indent=2) + "\n")
    print(f"Wrote {len(catalogue.datasets)} dataset/revision rows to {args.output}")


if __name__ == "__main__":
    main()
