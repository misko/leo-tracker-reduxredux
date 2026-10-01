"""Bind operator-reported pose to saved adaptive captures through the IQ store.

Companion metadata preserves sealed IQ contracts. It does not alter tracking
priors or claim a measured RF baseline. No RF acquisition is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ReceiverDirection(ClosedModel):
    connector_label: Literal["RX1", "RX2"]
    receiver_id: Literal[0, 1]
    mapping_status: Literal["provisional", "verified"]
    azimuth_deg: Annotated[float, Field(ge=0, lt=360)]
    elevation_deg: Annotated[float, Field(ge=-90, le=90)] | None


class CapturePoseAuthority(ClosedModel):
    schema_version: Literal[1]
    revision: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]+$")]
    station_id: str
    radio_id: str
    radio_serial: str
    valid_from_utc_ns: Annotated[int, Field(gt=0)]
    valid_until_utc_ns: Annotated[int, Field(gt=0)]
    time_evidence: str
    latitude_deg: Annotated[float, Field(ge=-90, le=90)]
    longitude_deg: Annotated[float, Field(ge=-180, le=180)]
    altitude_m: float | None
    altitude_datum: Literal["WGS84-ellipsoid", "mean-sea-level"] | None
    position_evidence: str
    azimuth_reference: Literal["geographic-north-assumed", "geographic-north", "magnetic-north"]
    receivers: tuple[ReceiverDirection, ReceiverDirection]
    orientation_evidence: str
    fixture_part_id: str
    fixture_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    fixture_evidence: str
    nominal_mount_separation_m: Annotated[float, Field(gt=0)]
    nominal_outward_tilt_deg: Annotated[float, Field(ge=0, le=90)]
    phase_center_baseline_enu_m: tuple[float, float, float] | None

    @model_validator(mode="after")
    def consistent(self):
        if self.valid_until_utc_ns <= self.valid_from_utc_ns:
            raise ValueError("empty pose validity interval")
        if tuple(r.receiver_id for r in self.receivers) != (0, 1):
            raise ValueError("pose requires ordered distinct RX0/RX1")
        if len({r.connector_label for r in self.receivers}) != 2:
            raise ValueError("connector labels must be distinct")
        if (self.altitude_m is None) != (self.altitude_datum is None):
            raise ValueError("altitude requires its datum")
        return self


def canonical(document: dict) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def bind(session, authority: CapturePoseAuthority) -> dict | None:
    """Use capture UTC brackets, never publication/file times, for eligibility."""
    manifest = session.manifest
    receipt = manifest.receipt
    if (receipt.radio_id, receipt.radio_serial) != (authority.radio_id, authority.radio_serial):
        return None
    if tuple(receipt.plan.geometry.receiver_ids) != (0, 1):
        return None
    timing = manifest.timing
    if timing is None or not timing.qualified:
        return None
    start = timing.first_sample_earliest_utc_ns
    end = timing.terminal_realtime_ns
    if not authority.valid_from_utc_ns <= start <= end < authority.valid_until_utc_ns:
        return None
    pose = authority.model_dump(mode="json")
    content = {
        "schema_version": 1,
        "session_id": session.session_id,
        "manifest_sha256": session.manifest_sha256,
        "capture_start_earliest_utc_ns": start,
        "capture_end_utc_ns": end,
        "pose_authority": pose,
        "pose_authority_digest": digest(canonical(pose)),
    }
    return {**content, "binding_digest": digest(canonical(content))}


def publish(root: Path, document: dict) -> bool:
    """Publish one immutable companion; retries verify exact existing content."""
    import re
    import tempfile

    session_id = document["session_id"]
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", session_id) is None:
        raise ValueError("unsafe session ID")
    if root.resolve().is_relative_to("/mnt/qnap01"):
        raise ValueError("QNAP is read-only")
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{session_id}.json"
    payload = canonical(document) + b"\n"
    if target.exists():
        if target.read_bytes() != payload:
            raise ValueError(f"existing pose binding differs: {session_id}")
        return False
    descriptor, temporary = tempfile.mkstemp(prefix=".pose-", dir=root)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o640)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != payload:
                raise ValueError(f"concurrent pose binding differs: {session_id}") from None
            return False
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return True
    finally:
        os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--authority-sha256", required=True)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--session-id", action="append")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = args.authority.read_bytes()
    if digest(payload) != args.authority_sha256:
        raise ValueError("authority file digest mismatch")
    authority = CapturePoseAuthority.model_validate_json(payload)
    # Runtime uses the installed acquisition release's narrow, read-only store.
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    output = args.output_root / authority.revision
    counts = {"eligible": 0, "created": 0, "unchanged": 0, "excluded": 0}
    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    try:
        candidates = args.session_id or [
            session_id
            for _, captured, radio_id, session_id in store.tracking_metadata_index()
            if radio_id == authority.radio_id and captured >= authority.valid_from_utc_ns
        ]
        for session_id in candidates:
            document = bind(store.inspect(session_id), authority)
            if document is None:
                counts["excluded"] += 1
                continue
            counts["eligible"] += 1
            if args.write:
                created = publish(output, document)
                counts["created" if created else "unchanged"] += 1
    finally:
        store.close()
    print(json.dumps({"revision": authority.revision, "output": str(output), **counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
