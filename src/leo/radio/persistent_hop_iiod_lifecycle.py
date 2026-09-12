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
    bundle_manifest_path: Path | None = None


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


def attach_iiod_failure_diagnostics(
    lifecycle: PersistentHopIiodLifecycle, primary: BaseException
) -> None:
    """Read the optional diagnostic port before cleanup; always preserve failure.

    Advisory exception notes do not replace capture or restoration receipts.
    Missing/failed diagnostics cannot prevent the mandatory cleanup attempt.
    """
    read = getattr(lifecycle, "diagnostic_tail", None)
    if not callable(read):
        primary.add_note("alternate iiOD diagnostic tail unavailable: provider lacks support")
        return
    try:
        tail = read()
        if not isinstance(tail, str) or len(tail) > 8192:
            raise ValueError("invalid bounded daemon diagnostic text")
    except BaseException as error:
        primary.add_note(
            f"alternate iiOD diagnostic tail unavailable: {type(error).__name__}: "
            f"{str(error)[:512]}"
        )
    else:
        primary.add_note("alternate iiOD advisory daemon log tail:\n" + (tail or "<empty>"))
