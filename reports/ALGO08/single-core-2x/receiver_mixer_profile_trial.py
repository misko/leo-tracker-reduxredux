"""Train matched floating receiver variants at zero and nonzero mixer centers."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import receiver_compiler_trial as compiler
from receiver_eligibility_trial import load
from receiver_resident_cancel_trial import paired
from tools.pipeline_eval.qualification import waveform_site_model as waveform
from tools.pipeline_eval.variants.experimental import (
    receiver_build, receiver_carrier_eligibility, receiver_phase_packed_build, receiver_resident_cancel,
)
from tools.pipeline_eval.variants.experimental.receiver_benchmark import (
    Receiver, digest, read_archive, read_simulated_prefix,
)
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical


def mixer_centers(index):
    return 0., (-100_000. if index % 2 == 0 else 100_000.)


def train(binary, assets):
    frames = waveform.pulse_bank()
    outputs = []
    for index, (edge, record) in enumerate(compiler.training_rows()):
        iq = waveform.iq(record, dict(sample_rate_truth_hz=waveform.RATE), frames[edge])
        pilot = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
        if pilot.shape != (133413,):
            raise ValueError("Unexpected training asset")
        detector = Receiver(binary, pilot)
        try:
            for center in mixer_centers(index):
                for lane in (0, 1):
                    factors, _, _ = detector.timed(iq, lane, center)
                    outputs.append(dict(edge=edge, lane=lane, center_hz=center, count=len(factors)))
        finally:
            detector.close()
    return outputs


def freeze(work, assets, eligibility, eligibility_manifest):
    originals = load(eligibility, eligibility_manifest)
    work.mkdir()
    process = compiler.subprocess
    training_script = str(Path(compiler.__file__).resolve())

    def run(command, **kwargs):
        if command[1:3] == [training_script, "train"]:
            command = [command[0], str(Path(__file__).resolve()), *command[2:]]
        return process.run(command, **kwargs)

    native = receiver_build.build
    phase = receiver_phase_packed_build.overlay(native)
    combined = receiver_carrier_eligibility.overlay(receiver_resident_cancel.overlay(phase))
    builds = {}
    driver = SimpleNamespace(run=run, check_output=process.check_output, PIPE=process.PIPE)
    with patch.object(compiler, "subprocess", driver):
        for name, function in (("balanced-reference", phase), ("balanced-combined", combined)):
            def build(output, **recipe):
                if output.name == "control.so":
                    return native(output, **recipe)
                return function(output, **recipe)

            with patch.object(receiver_build, "build", build):
                builds[name] = compiler.build(work / name, assets, integer_fir=False)
    return dict(
        originals={name: dict(path=str(originals[name].resolve()), sha256=digest(originals[name].read_bytes()))
                   for name in ("reference", "combined")},
        builds=builds, training_source_sha256=digest(Path(__file__).read_bytes()),
        base_training_source_sha256=digest(Path(compiler.__file__).read_bytes()),
    )


def verified(work, manifest):
    spec = json.loads(manifest.read_bytes())
    paths = {name: (Path(row["path"]), row["sha256"]) for name, row in spec["originals"].items()}
    for name, build in spec["builds"].items():
        paths[name] = work / name / "use.so", build["library_sha256"]
    if any(digest(path.read_bytes()) != expected for path, expected in paths.values()):
        raise ValueError("One of the frozen mixer profile variants changed")
    return {name: path for name, (path, _) in paths.items()}


def evaluate(work, manifest, assets, binding, weak, panel):
    paths = verified(work, manifest)
    physical = list(read_physical(binding, Path("/srv/bulk"), 128))
    mixed = []
    for index, (row, iq) in enumerate(read_archive(weak, 18)):
        offset = (-1 if index % 2 else 1) * 50_000
        acq = row["acquisition"]
        mixed.append((dict(row, acquisition=dict(acq, actual_if_center_hz=acq["actual_if_center_hz"] + offset)), iq))
    groups = {"chronological": physical, "mixed_center": mixed}
    for row, iq in read_simulated_prefix(panel, 40):
        groups.setdefault(row["case"], []).append((row, iq))
    return {
        key: dict(
            single_setting=paired(rows, assets, (paths["reference"], paths["combined"]), repeats=3),
            mix_trained=paired(rows, assets, (paths["balanced-reference"], paths["balanced-combined"]), repeats=3),
            direct_vs_lead=paired(rows, assets, (paths["reference"], paths["balanced-combined"]), repeats=3),
        )
        for key, rows in groups.items()
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for handler, fields in (
        (train, ("binary", "assets")),
        (freeze, ("work", "assets", "eligibility", "eligibility_manifest")),
        (evaluate, ("work", "manifest", "assets", "binding", "weak", "panel")),
    ):
        command = commands.add_parser(handler.__name__)
        command.set_defaults(handler=handler)
        for field in fields:
            command.add_argument(field, type=Path)
    args = vars(parser.parse_args())
    handler = args.pop("handler")
    args.pop("action")
    print(json.dumps(handler(**args), indent=2, allow_nan=False))
