#!/usr/bin/env python3
"""Inventory and freeze causal DS7 orbital products without reading reference data.

The input is the reference-free DS7 plan.  Archived bytes are accessed only
through ``TleArchiveReader``.  A product may use a snapshot only when its
collector timestamp is strictly before the capture's earliest possible start.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sgp4.alpha5 import from_alpha5

from leo.operations.tle_archive import PROVIDERS, TleArchiveReader, TleSnapshotRef
from leo.sky.propagation import ELEMENT_LINE_LENGTH, element_line_checksum

SCHEMA = "ds7-causal-orbit-inventory/v1"
PRODUCT_SCHEMA = "ds7-causal-orbit-product/v1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class ElementRecord:
    name: str
    catalog_number: int
    epoch_utc_ns: int
    line1: str
    line2: str
    source: TleSnapshotRef

    @property
    def element_sha256(self) -> str:
        body = f"{self.line1}\n{self.line2}\n".encode("ascii")
        return "sha256:" + hashlib.sha256(body).hexdigest()


def _raw_records(payload: str, snapshot: TleSnapshotRef) -> tuple[ElementRecord, ...]:
    """Return structurally validated records while retaining exact source lines."""

    lines = [line.rstrip() for line in payload.splitlines() if line.strip()]
    records: list[ElementRecord] = []
    index = 0
    while index < len(lines):
        name = ""
        if not lines[index].startswith(("1 ", "2 ")):
            name = lines[index][2:].strip() if lines[index].startswith("0 ") else lines[index]
            index += 1
        one, two = lines[index], lines[index + 1]
        if (
            len(one) != ELEMENT_LINE_LENGTH
            or len(two) != ELEMENT_LINE_LENGTH
            or not one.startswith("1 ")
            or not two.startswith("2 ")
            or one[2:7] != two[2:7]
            or not one[68].isdigit()
            or not two[68].isdigit()
            or int(one[68]) != element_line_checksum(one)
            or int(two[68]) != element_line_checksum(two)
        ):
            raise ValueError("invalid element record in digest-verified snapshot")
        year = int(one[18:20])
        year += 1900 if year >= 57 else 2000
        day = Decimal(one[20:32])
        whole_day = int(day)
        fraction_ns = int((day - whole_day) * Decimal(86_400_000_000_000))
        epoch = datetime(year, 1, 1, tzinfo=UTC) + timedelta(days=whole_day - 1)
        epoch_ns = int(epoch.timestamp()) * 1_000_000_000 + fraction_ns
        number = int(from_alpha5(one[2:7]))
        records.append(
            ElementRecord(name or f"CATALOG-{number}", number, epoch_ns, one, two, snapshot)
        )
        index += 2
    if not records:
        raise ValueError("empty element snapshot")
    return tuple(records)


def _snapshot_receipt(snapshot: TleSnapshotRef, capture_start_ns: int) -> dict[str, object]:
    return {
        "provider": snapshot.provider,
        "collected_utc_ns": snapshot.collected_utc_ns,
        "sha256": snapshot.digest,
        "byte_size": snapshot.byte_size,
        "collection_lead_s": (capture_start_ns - snapshot.collected_utc_ns) / 1e9,
    }


def newest_per_object(
    reader: TleArchiveReader, snapshots: Sequence[TleSnapshotRef]
) -> tuple[dict[int, ElementRecord], int]:
    """Select each object's newest epoch from strictly causal archived bytes.

    Equal epochs prefer the later collection and then digest, making replay
    deterministic.  Collector time establishes byte causality.  Future-dated
    epochs are counted for audit but remain eligible because a causal provider
    product can legitimately publish a predicted epoch.
    """

    selected: dict[int, ElementRecord] = {}
    future_dated = 0
    for snapshot in snapshots:
        for record in _raw_records(reader.read(snapshot), snapshot):
            if record.epoch_utc_ns > snapshot.collected_utc_ns:
                future_dated += 1
            old = selected.get(record.catalog_number)
            key = (record.epoch_utc_ns, snapshot.collected_utc_ns, snapshot.sha256)
            if old is None or key > (
                old.epoch_utc_ns,
                old.source.collected_utc_ns,
                old.source.sha256,
            ):
                selected[record.catalog_number] = record
    return selected, future_dated


def _write_product(path: Path, records: dict[int, ElementRecord]) -> dict[str, object]:
    body = "".join(
        f"0 {item.name}\n{item.line1}\n{item.line2}\n"
        for item in (records[number] for number in sorted(records))
    ).encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    sources = Counter(item.source.digest for item in records.values())
    members = [
        {
            "catalog_number": item.catalog_number,
            "element_epoch_utc_ns": item.epoch_utc_ns,
            "element_sha256": item.element_sha256,
            "source_snapshot_sha256": item.source.digest,
        }
        for item in (records[number] for number in sorted(records))
    ]
    return {
        "schema": PRODUCT_SCHEMA,
        "path": str(path),
        "sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
        "byte_size": len(body),
        "object_count": len(records),
        "member_index_sha256": _digest(members),
        "contributing_snapshot_count": len(sources),
        "contributing_snapshot_sha256": [
            {"sha256": key, "selected_object_count": sources[key]} for key in sorted(sources)
        ],
    }


def build_inventory(
    plan: dict[str, object],
    reader: TleArchiveReader,
    output: Path,
    emit_count: int,
    product_root: Path | None = None,
) -> dict[str, object]:
    captures = plan.get("captures")
    if not isinstance(captures, list) or not captures:
        raise ValueError("plan has no captures")
    ordered = sorted(captures, key=lambda row: (row["capture_start_utc_ns"], row["session_id"]))
    rows: list[dict[str, object]] = []
    all_snapshots = reader.list_snapshots()
    provider_snapshots = {
        provider: tuple(item for item in all_snapshots if item.provider == provider)
        for provider in PROVIDERS
    }
    provider_cursor = {provider: 0 for provider in PROVIDERS}
    provider_selected: dict[str, dict[int, ElementRecord]] = {
        provider: {} for provider in PROVIDERS
    }
    provider_future = {provider: 0 for provider in PROVIDERS}
    parsed_by_digest: dict[str, tuple[ElementRecord, ...]] = {}

    def records_for(snapshot: TleSnapshotRef) -> tuple[ElementRecord, ...]:
        cached = parsed_by_digest.get(snapshot.digest)
        if cached is None:
            cached = _raw_records(reader.read(snapshot), snapshot)
            parsed_by_digest[snapshot.digest] = cached
        if cached[0].source == snapshot:
            return cached
        return tuple(
            ElementRecord(
                item.name,
                item.catalog_number,
                item.epoch_utc_ns,
                item.line1,
                item.line2,
                snapshot,
            )
            for item in cached
        )

    for capture_index, capture in enumerate(ordered):
        cutoff = int(capture["capture_start_earliest_utc_ns"])
        products: list[dict[str, object]] = []
        for provider in PROVIDERS:
            snapshots = provider_snapshots[provider]
            cursor = provider_cursor[provider]
            selected = provider_selected[provider]
            while cursor < len(snapshots) and snapshots[cursor].collected_utc_ns < cutoff:
                snapshot = snapshots[cursor]
                for record in records_for(snapshot):
                    if record.epoch_utc_ns > snapshot.collected_utc_ns:
                        provider_future[provider] += 1
                    old = selected.get(record.catalog_number)
                    key = (record.epoch_utc_ns, snapshot.collected_utc_ns, snapshot.sha256)
                    if old is None or key > (
                        old.epoch_utc_ns,
                        old.source.collected_utc_ns,
                        old.source.sha256,
                    ):
                        selected[record.catalog_number] = record
                cursor += 1
            provider_cursor[provider] = cursor
            causal = snapshots[:cursor]
            if not causal:
                products.append(
                    {
                        "provider": provider,
                        "state": "unavailable",
                        "reason": "no archived snapshot collected before capture",
                    }
                )
                continue
            latest = causal[-1]
            latest_records = records_for(latest)
            composite = selected
            product: dict[str, object] = {
                "provider": provider,
                "state": "ready",
                "product_class": "public_gp_3le",
                "causality_cutoff": "collected_utc_ns < capture_start_earliest_utc_ns",
                "causal_snapshot_count": len(causal),
                "latest_snapshot": {
                    **_snapshot_receipt(latest, cutoff),
                    "object_count": len(latest_records),
                    "maximum_element_epoch_utc_ns": max(
                        item.epoch_utc_ns for item in latest_records
                    ),
                },
                "newest_per_object": {
                    "selection": "maximum element epoch; tie later collection then digest",
                    "object_count": len(composite),
                    "observed_future_dated_record_count": provider_future[provider],
                },
            }
            if capture_index < emit_count:
                root = product_root if product_root is not None else output / "products"
                destination = root / provider / f"{capture['session_id']}.tle"
                product["newest_per_object"].update(_write_product(destination, composite))
            products.append(product)
        rows.append(
            {
                "session_id": capture["session_id"],
                "manifest_sha256": capture["manifest_sha256"],
                "capture_start_utc_ns": capture["capture_start_utc_ns"],
                "capture_start_earliest_utc_ns": cutoff,
                "products": products,
            }
        )
    document: dict[str, object] = {
        "schema": SCHEMA,
        "dataset_id": plan.get("dataset_id"),
        "dataset_sha256": plan.get("dataset_sha256"),
        "plan_content_sha256": plan.get("content_sha256"),
        "reference_policy": "reference-free plan only; no pose or score inputs read",
        "selection_policy": (
            "strict collector-time causality at earliest capture-start bracket; "
            "newest element per catalog object"
        ),
        "archive_semantics": {
            "space-track": "public Space-Track GP query, archived by local collector",
            "huggingface": "third-party latest-Starlink TLE mirror, archived by local collector",
            "supgp": "unavailable: no SupGP archive/provider exists in the public archive port",
            "provider_ephemeris": (
                "unavailable: no provider ephemeris archive/provider exists in the "
                "public archive port"
            ),
        },
        "emitted_product_capture_count": min(emit_count, len(rows)),
        "captures": rows,
    }
    document["content_sha256"] = _digest(document)
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--product-root", type=Path)
    parser.add_argument("--emit-count", type=int, default=8)
    args = parser.parse_args(argv)
    if args.emit_count < 0:
        parser.error("--emit-count must be non-negative")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    result = build_inventory(
        plan,
        TleArchiveReader(args.archive_root),
        args.output,
        args.emit_count,
        args.product_root,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    inventory = args.output / "inventory.json"
    inventory.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"inventory": str(inventory), "content_sha256": result["content_sha256"]},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
