"""Freeze paired covariance PGO and check short generated and public inputs."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import receiver_compiler_trial as compiler
import receiver_mixer_profile_trial as mixer_profile
from receiver_resident_cancel_trial import paired
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.pipeline_eval.qualification.two_carrier_injections import mix, unit_wave
from tools.pipeline_eval.variants.experimental import (
    receiver_build, receiver_carrier_eligibility, receiver_mode_pair_build,
    receiver_phase_packed_build, receiver_resident_cancel,
)
from tools.pipeline_eval.variants.experimental.receiver_benchmark import digest, read_simulated_prefix


REFERENCE_SHA256 = "678d8a24ae727cc65442436955c4e9718354ada4e103db24c362d3d9b727ff9d"
PUBLIC_VISITS = 16


def freeze(work, assets, reference):
    if digest(reference.read_bytes()) != REFERENCE_SHA256:
        raise ValueError("Expected the frozen balanced floating receiver")
    work.mkdir()
    native = receiver_build.build
    balanced = receiver_carrier_eligibility.overlay(
        receiver_resident_cancel.overlay(receiver_phase_packed_build.overlay(native)),
    )
    covariance = receiver_mode_pair_build.overlay(balanced)
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
            ("candidate", covariance, False), ("reference-profile", balanced, True),
            ("candidate-profile", covariance, True),
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


def generated():
    rng = np.random.default_rng(28741)
    for index, (edge, sign) in enumerate((("lower", -1), ("upper", 1))):
        template = qin_edge_pilot_frame(30_000_000, edge)
        for repeat, center in enumerate((0., 87_500. * sign)):
            seed = 8341 + index * 50 + repeat
            a, _ = unit_wave(template, 1267 + 6001 * repeat, sign * 291_350., seed, False)
            b, _ = unit_wave(template, 11501 + 3681 * repeat, -sign * 372_450., seed + 1, False)
            c, _ = unit_wave(template, 2133 + 6001 * repeat, sign * 178_250., seed + 2, False)
            noise = rng.integers(-300, 301, size=(200000, 2, 2), dtype="<i2")
            iq, clipped_a = mix(noise, 0, [(a, 12), (b, 4)])
            if repeat:
                iq, clipped_b = mix(iq, 1, [(c, 9)])
            else:
                clipped_b = 0
            if clipped_a or clipped_b:
                raise ValueError("Unexpected generated signal clipping")
            key = f"generated:{edge}:{repeat}"
            row = dict(
                key=key, case=key, edge=edge, sha256=digest(iq.tobytes()),
                target=dict(rf_center_hz=center, lnb_lo_hz=0., channel=1),
                acquisition=dict(actual_if_center_hz=0., sample_start=0),
            )
            yield row, iq


def evaluate(work, manifest, assets, panel):
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
    groups = defaultdict(list)
    for row, iq in read_simulated_prefix(panel, PUBLIC_VISITS):
        groups[row["case"]].append((row, iq))
    groups["generated"] = list(generated())
    results = {name: paired(rows, assets, (reference, paths["candidate"]), repeats=9 if name == "generated" else 5)
               for name, rows in groups.items()}
    profile = paired([item for rows in groups.values() for item in rows], assets,
                     (paths["reference-profile"], paths["candidate-profile"]), repeats=3)
    return dict(groups=results, profile=profile)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for handler, fields in (
        (freeze, ("work", "assets", "reference")),
        (evaluate, ("work", "manifest", "assets", "panel")),
    ):
        command = commands.add_parser(handler.__name__)
        command.set_defaults(handler=handler)
        for field in fields:
            command.add_argument(field, type=Path)
    args = vars(parser.parse_args())
    handler = args.pop("handler")
    args.pop("action")
    print(json.dumps(handler(**args), indent=2, allow_nan=False))
