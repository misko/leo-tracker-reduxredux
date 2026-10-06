"""Digest-scoped immutable numerical stage checkpoints on local storage."""

import json
from contextlib import contextmanager
from pathlib import Path

from pydantic import TypeAdapter

from leo.contracts.digests import Sha256Digest, canonical_digest, canonical_json_bytes
from leo.storage.adaptive_hop_analysis import _publish, _read
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStore


class RegionalCheckpointStore:
    """The binding covers capture, evidence, ephemeris, configuration and code.

    One writer lease should enclose a runner slice. Each completed stage is
    immutable and independently checksummed, so a retry never consumes torn data.
    """

    def __init__(self, root: Path, session_id: str, binding_sha256: str):
        TypeAdapter(Sha256Digest).validate_python(binding_sha256)
        self.session_id = session_id
        self.binding_sha256 = binding_sha256
        self._store = AdaptiveTlePositionStore(root, read_only=False)
        self._store.namespace = "scanner-regional-position-work-v1"

    @contextmanager
    def _directory(self, *, create=False):
        # Production workers own this one pre-created namespace, not bulk_root.
        # Keep changing input/configuration bindings below the session directory.
        with self._store._directory(self.session_id, create=create) as session:
            directory = session.child(self.binding_sha256[7:], create=create)
            try:
                yield directory
            finally:
                directory.close()

    def writer(self):
        return self._store.writer(self.session_id)

    def _name(self, key):
        if not isinstance(key, str) or not key or len(key) > 1024:
            raise ValueError("invalid checkpoint key")
        return canonical_digest({"key": key})[7:] + ".json"

    def get(self, key: str) -> dict | None:
        name = self._name(key)
        try:
            with self._directory() as directory:
                raw = _read(directory, name, 16 * 1024 * 1024)
        except FileNotFoundError:
            return None
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return None
            raise
        envelope = json.loads(raw)
        if (
            not isinstance(envelope, dict)
            or envelope.get("key") != key
            or envelope.get("binding_sha256") != self.binding_sha256
            or not isinstance(envelope.get("value"), dict)
            or canonical_digest(envelope["value"]) != envelope.get("value_sha256")
        ):
            raise ValueError("regional checkpoint failed verification")
        if canonical_json_bytes(envelope) != raw:
            raise ValueError("regional checkpoint encoding differs")
        return envelope["value"]

    def put(self, key: str, value: dict) -> None:
        name = self._name(key)
        raw = canonical_json_bytes(
            {
                "key": key,
                "binding_sha256": self.binding_sha256,
                "value": value,
                "value_sha256": canonical_digest(value),
            }
        )
        with self._directory(create=True) as directory:
            try:
                existing = _read(directory, name, 16 * 1024 * 1024)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                if existing != raw:
                    raise ValueError("immutable regional checkpoint conflict")
                return
            _publish(directory, name, raw, 16 * 1024 * 1024)
