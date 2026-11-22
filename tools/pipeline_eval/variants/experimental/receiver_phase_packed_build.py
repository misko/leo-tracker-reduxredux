"""Compose the guarded frame-relative verifier with packed fractional reads."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import receiver_build


def mixed_kernel(source):
    old = '#include "receiver_phase_free_kernel.inc"'
    packed = '#include "receiver_fractional_batch.inc"'
    source = receiver_build.replace(source, old + "\n", "")
    return receiver_build.replace(source, packed, packed + "\n"
                                  "#define correlated_fractional_mixed correlated_fractional_mixed_reference\n"
                                  + old + "\n"
                                  "#undef correlated_fractional_mixed\n"
                                  '#include "receiver_phase_packed_mixed.inc"')


def overlay(build):
    """Wrap one native build and retain its active compiler driver."""
    def composed(output, **recipe):
        compile_source = receiver_build.subprocess.run

        def compile_mixed(command, **kwargs):
            if "-c" in command:
                path = Path(command[command.index("-c") + 1])
                if path.name == "refine_bank.c":
                    path.write_text(mixed_kernel(path.read_text()))
            return compile_source(command, **kwargs)

        with patch.object(receiver_build, "subprocess", SimpleNamespace(run=compile_mixed)):
            build(output, **(recipe | dict(phase_free=True, fractional_batch=True)))

    return composed
