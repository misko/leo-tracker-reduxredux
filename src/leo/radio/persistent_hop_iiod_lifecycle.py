"""Narrow no-flash iiOD lifecycle port owned by acquisition composition."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

PERSISTENT_HOP_IIOD_BINARY_RELATIVE_PATH = Path("runtime/scanner-iiod/iiod")
PERSISTENT_HOP_IIOD_KNOWN_HOSTS_CREDENTIAL = "scanner-iiod-ssh-known-hosts"
PERSISTENT_HOP_IIOD_PASSWORD_CREDENTIAL = "scanner-iiod-ssh-password"


@dataclass(frozen=True, slots=True)
class PersistentHopIiodLifecycleConfiguration:
    """Exact immutable inputs for one radio-local, volatile iiOD lifetime."""

    radio_id: str
    expected_serial: str
    host: str
    port: int
    binary_path: Path
    known_hosts_path: Path
    password_path: Path


class PersistentHopIiodLifecycle(Protocol):
    """Own and attest one alternate iiOD process without persistent radio writes.

    Construction must be side-effect free. ``enter_and_attest`` may copy only
    the configured immutable bundle into volatile radio storage, must reject a
    pre-existing listener, and returns only after identity and hop capabilities
    are attested. Entry is transactional and owns cleanup if it raises.
    ``exit_and_verify`` is called exactly once only after successful entry; it
    stops only the owned process and verifies alternate-port closure and the
    health of the untouched stock iiOD endpoint.
    """

    def enter_and_attest(self) -> None: ...

    def exit_and_verify(self) -> None: ...
