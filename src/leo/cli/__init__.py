"""Public CLI composition and typed result boundary.

Imports stay lazy so a saved-input CLI can run without optional radio drivers.
"""

from importlib import import_module
from typing import Any

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


def __getattr__(name: str) -> Any:
    modules = {
        "create_cli": "leo.cli.app",
        "main": "leo.cli.app",
        "AcquisitionCliBackend": "leo.cli.backend",
        "CliBackendError": "leo.cli.backend",
        "CliSettings": "leo.cli.composition",
        "CompositionHooks": "leo.cli.composition",
        "LocalAcquisitionBackend": "leo.cli.composition",
        "configured_backend_factory": "leo.cli.composition",
        "CommandResultV1": "leo.cli.models",
        "ExitCode": "leo.cli.models",
    }
    try:
        module = import_module(modules[name])
    except KeyError as error:
        raise AttributeError(name) from error
    return getattr(module, name)
