"""Verified read-only source receipts with local append-only research writes."""

import hashlib
import json
from pathlib import Path

from leo.application.regional_position_runner import json_value
from leo.contracts.digests import canonical_digest


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(json_value(value), stream, indent=2, allow_nan=False)
        stream.write("\n")


class Overlay:
    def __init__(
        self,
        directory,
        protocol_digest,
        source_root,
        source_receipts,
        *,
        compatible=False,
        verify_coarse=None,
        coarse_alias_prefix=None,
    ):
        self.directory = Path(directory)
        self.protocol_digest = protocol_digest
        self.source_root = Path(source_root)
        self.source_receipts = source_receipts
        self.compatible = compatible
        self.verify_coarse = verify_coarse
        self.coarse_alias_prefix = coarse_alias_prefix
        self.aliases = {}
        self.verified = set()
        self.source_hits = 0

    def path(self, key):
        return self.directory / (canonical_digest({"key": key})[7:] + ".json")

    def get(self, key):
        path = self.path(key)
        if path.exists():
            row = read(path)
            assert row["key"] == key and row["protocol_sha256"] == self.protocol_digest
            assert canonical_digest(row["value"]) == row["value_sha256"]
            return row["value"]
        if not self.compatible:
            return None
        source_key = key
        if source_key not in self.source_receipts and self.coarse_alias_prefix is not None:
            suffix = key.removeprefix("b7-shared:")
            if key.startswith("b7-shared:point:") and suffix.count(":") == 2:
                source_key = self.coarse_alias_prefix + ":" + suffix
        if source_key not in self.source_receipts:
            return None
        entry = self.source_receipts[source_key]
        source_path = self.source_root / entry["file"]
        assert hashlib.sha256(source_path.read_bytes()).hexdigest() == entry["file_sha256"]
        value = read(source_path)
        assert canonical_digest(value) == entry["value_sha256"]
        is_coarse = bool(
            value.get("result") and "bootstrap" in value["result"] and "fits" in value["result"]
        )
        if source_key != key and not is_coarse:
            return None
        if is_coarse and source_key not in self.verified:
            assert self.verify_coarse is not None
            self.verify_coarse(value["result"])
            self.verified.add(source_key)
        if source_key != key:
            self.aliases[key] = dict(
                source_key=source_key,
                value_sha256=entry["value_sha256"],
                coarse_objective_verified=True,
            )
        self.source_hits += 1
        return value

    def put(self, key, value):
        path = self.path(key)
        receipt = dict(
            key=key,
            protocol_sha256=self.protocol_digest,
            value=json_value(value),
            value_sha256=canonical_digest(json_value(value)),
        )
        if path.exists():
            assert read(path) == receipt
        else:
            write(path, receipt)


def claim_slice(directory, phase, protocol_digest, *, maximum=6):
    """A started invocation counts even if its process crashes; never resets."""
    if phase not in ("baseline", "candidate"):
        raise ValueError("Unknown pilot phase")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    existing = sorted(directory.glob(f"{phase}-*.started.json"))
    for path in existing:
        assert read(path)["protocol_sha256"] == protocol_digest
    if len(existing) >= maximum:
        return None
    index = len(existing) + 1
    write(
        directory / f"{phase}-{index:02d}.started.json",
        dict(protocol_sha256=protocol_digest, phase=phase, slice=index),
    )
    return index
