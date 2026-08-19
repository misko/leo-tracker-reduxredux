"""Public CLI composition and typed result boundary."""

from leo.cli.app import create_cli, main
from leo.cli.backend import AcquisitionCliBackend, CliBackendError
from leo.cli.composition import (
    CliSettings,
    CompositionHooks,
    LocalAcquisitionBackend,
    configured_backend_factory,
)
from leo.cli.models import CommandResultV1, ExitCode

__all__ = [
    "AcquisitionCliBackend",
    "CliBackendError",
    "CliSettings",
    "CommandResultV1",
    "CompositionHooks",
    "ExitCode",
    "LocalAcquisitionBackend",
    "configured_backend_factory",
    "create_cli",
    "main",
]
