"""Freeze and measure exact block maxima in the receiver timing scout."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import receiver_compiler_trial as compiler
import receiver_mixer_profile_trial as mixer_profile
from receiver_refine_parity_trial import austin_windows
from receiver_resident_cancel_trial import austin, paired
from tools.pipeline_eval.variants.experimental import (
    receiver_build, receiver_carrier_eligibility, receiver_epoch_blocks, receiver_mode_pair_build,
    receiver_phase_packed_build, receiver_resident_cancel,
)
from tools.pipeline_eval.variants.experimental.receiver_benchmark import digest, read_archive


REFERENCE_SHA256 = "d44c60320320be8281ed6e71285f8cb50cc0e204df9fa1eef53d36c514e51128"


def freeze(work, assets, reference):
    if digest(reference.read_bytes()) != REFERENCE_SHA256:
        raise ValueError("Expected the frozen paired covariance receiver")
    work.mkdir()
    native = receiver_build.build
    phase = receiver_phase_packed_build.overlay(native)
    resident = receiver_resident_cancel.overlay(phase)
    carrier = receiver_carrier_eligibility.overlay(resident)
    modes = receiver_mode_pair_build.overlay(carrier)
    blocked = receiver_epoch_blocks.overlay(modes)
    process = compiler.subprocess
    training_source = str(Path(mixer_profile.__file__).resolve())
    original_script = str(Path(compiler.__file__).resolve())

    def run(command, **kwargs):
        if command[1:3] == [original_script, "train"]:
            command = [command[0], training_source, *command[2:]]
        return process.run(command, **kwargs)

    builds = {}
    driver = SimpleNamespace(run=run, check_output=process.check_output, PIPE=process.PIPE)
    with patch.object(compiler, "subprocess", driver):
        for name, function, profile in (
            ("candidate", blocked, False), ("reference-profile", modes, True),
            ("candidate-profile", blocked, True),
        ):
            def build(output, **recipe):
                if output.name == "control.so":
                    return native(output, **recipe)
                return function(output, profile=profile, **recipe)

            with patch.object(receiver_build, "build", build):
                builds[name] = compiler.build(work / name, assets, integer_fir=False)
    return dict(
        reference=dict(path=str(reference.resolve()), sha256=REFERENCE_SHA256), builds=builds,
        training_source_sha256=digest(Path(training_source).read_bytes()),
        base_training_source_sha256=digest(Path(original_script).read_bytes()),
    )


def evaluate(work, manifest, assets, weak, archive, source_audit, wide_reference):
    spec = json.loads(manifest.read_bytes())
    reference = Path(spec["reference"]["path"])
    if spec["reference"]["sha256"] != REFERENCE_SHA256 or digest(reference.read_bytes()) != REFERENCE_SHA256:
        raise ValueError("Frozen reference changed")
    paths = {}
    for name, build in spec["builds"].items():
        path = work / name / "use.so"
        if digest(path.read_bytes()) != build["library_sha256"]:
            raise ValueError(f"Frozen library changed: {name}")
        paths[name] = path
    binaries = (reference, paths["candidate"])
    gauss_rows = list(read_archive(weak, 18))
    field = list(austin_windows(archive, source_audit, wide_reference))
    profile = paired(gauss_rows, assets, (paths["reference-profile"], paths["candidate-profile"]),
                     repeats=3)
    return dict(
        Gauss=paired(gauss_rows, assets, binaries, repeats=5),
        Austin=austin(field, assets, binaries), Gauss_profile=profile,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for handler, fields in (
        (freeze, ("work", "assets", "reference")),
        (evaluate, ("work", "manifest", "assets", "weak", "archive", "source_audit", "wide_reference")),
    ):
        command = commands.add_parser(handler.__name__)
        command.set_defaults(handler=handler)
        for field in fields:
            command.add_argument(field, type=Path)
    args = vars(parser.parse_args())
    handler = args.pop("handler")
    args.pop("action")
    print(json.dumps(handler(**args), indent=2, allow_nan=False))
