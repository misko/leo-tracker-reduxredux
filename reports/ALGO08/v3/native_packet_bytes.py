"""Prototype a canonical detection snapshot and verified immutable readback."""

from dataclasses import dataclass, field
from hashlib import sha256
import json


@dataclass(frozen=True)
class NativePacketBytes:
    """Own encoded bytes, with no references to mutable detection dictionaries."""

    canonical: bytes
    sha256: str = field(init=False)

    def __post_init__(self):
        if type(self.canonical) is not bytes:
            raise TypeError("Expected owned immutable canonical bytes")
        object.__setattr__(self, "sha256", "sha256:" + sha256(self.canonical).hexdigest())

    @classmethod
    def capture(cls, packet, encode):
        """Take a snapshot with the released canonical encoder."""
        return cls(encode(packet))

    def verified_readback(self, path):
        """Preserve the durable read and require exact equality before reusing its digest."""
        persisted = path.read_bytes()
        if persisted != self.canonical:
            raise ValueError("Immutable detector bytes differ from the sealed handoff")
        return persisted, self.sha256

    def load_verified(self, path):
        persisted, digest = self.verified_readback(path)
        return json.loads(persisted), digest
