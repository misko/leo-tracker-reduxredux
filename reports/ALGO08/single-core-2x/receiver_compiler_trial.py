"""Build and exercise a GCC branch-profiled Q15 receiver using site-free training signals."""
import argparse
from contextlib import contextmanager, nullcontext
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.qualification import waveform_site_model as waveform
from tools.pipeline_eval.variants.experimental import receiver_build, receiver_residual_build
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver

Q15_SHA256 = "8982c1b6cadbe80659f9f7cf8456746472d0f693c2dd363bd4e9a282adaf83e0"
DUAL_Q15_SHA256 = "c34c55748bd9b5feac6f1736e27acb78b4a1caa97f0d13a50b604cffd61d2d70"


def training_rows():
    """Cover both CFO signs and pilot edges, a noise lane, and a weak and strong pilot."""
    for edge in ("lower", "upper"):
        for index, cfo in enumerate((-675_000, -225_000, 225_000, 675_000)):
            plant = dict(epoch=713 + 2719 * index, period=40_000 / 3, actual_cfo_hz=cfo,
                         slope_hz_s=(-1) ** index * 3700, amplitude=1600)
            second = dict(plant, amplitude=400, actual_cfo_hz=-cfo) if index % 2 else None
            yield edge, dict(sample_seed=37 + index, tone_hz=130_000, tone_amplitude=170,
                             planted=[plant, second])


def train(binary, assets, dual=False):
    frames = waveform.pulse_bank()
    outputs = []
    for edge, record in training_rows():
        samples = waveform.iq(record, dict(sample_rate_truth_hz=waveform.RATE), frames[edge])
        pilot = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
        if pilot.shape != (133413,):
            raise ValueError("unexpected pilot asset length")
        receiver = Receiver(binary, pilot)
        try:
            entries = {"full": receiver.run}
            if dual:
                primary = receiver.lib.cancellation_primary_factors
                primary.argtypes, primary.restype = receiver.run.argtypes, receiver.run.restype
                entries["primary"] = primary
            for entry, kernel in entries.items():
                receiver.run = kernel
                for lane in (0, 1):
                    factors, _, _ = receiver.timed(samples, lane, 0)
                    outputs.append(dict(edge=edge, lane=lane, entry=entry, count=len(factors)))
        finally:
            receiver.close()
    return outputs


@contextmanager
def dual_source():
    original = Path.read_text

    def read_source(path, *args, **kwargs):
        text = original(path, *args, **kwargs)
        if path == receiver_residual_build.TWO_CARRIER_SOURCE:
            return receiver_residual_build.optional_residual(text)
        return text

    with patch.object(Path, "read_text", read_source):
        yield


def build(work, assets, dual=False):
    work = work.resolve()
    work.mkdir(exist_ok=False)
    stage, profiles = work / "objects", work / "profiles"
    stage.mkdir()
    profiles.mkdir()
    recipe = dict(pack_stencil=True, batch_refine=True, fractional_batch=True, integer_fir=True)
    control = work / "control.so"
    reference_digest = DUAL_Q15_SHA256 if dual else Q15_SHA256
    with dual_source() if dual else nullcontext():
        receiver_build.build(control, **recipe)
    if hashlib.sha256(control.read_bytes()).hexdigest() != reference_digest:
        raise ValueError("ordinary compiler did not reproduce the frozen Q15 reference")
    for mode in ("generate", "use"):
        binary = work / f"{mode}.so"

        def compile_with_feedback(command, **kwargs):
            flags = [f"-fprofile-{mode}={profiles}", "-fno-profile-values"]
            if mode == "use":
                flags.extend(["-Werror=missing-profile", "-Werror=coverage-mismatch"])
            return subprocess.run([command[0], *flags, *command[1:]], **kwargs)

        # GCC keys coverage by the object path. Keep names fixed across both compilations.
        with (patch.object(receiver_build, "TemporaryDirectory", lambda **_: nullcontext(stage)),
              patch.object(receiver_build, "subprocess", SimpleNamespace(run=compile_with_feedback)),
              dual_source() if dual else nullcontext()):
            receiver_build.build(binary, **recipe)
        if mode == "generate":
            # GCC flushes its per-translation-unit counters when the training process exits.
            command = [sys.executable, str(Path(__file__).resolve()), "train", str(binary), str(assets.resolve())]
            if dual:
                command.append("--dual")
            proc = subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE)
            training = json.loads(proc.stdout)
            counters = {p.stem for p in profiles.rglob("*.gcda")}
            if not counters or counters != {p.stem for p in stage.glob("*.o")}:
                raise RuntimeError("training counters do not cover all compiled objects")
    return dict(compiler=subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
                control_sha256=reference_digest, counted_objects=sorted(counters), training=training,
                library_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "train"))
    parser.add_argument("target", type=Path)
    parser.add_argument("assets", type=Path)
    parser.add_argument("--dual", action="store_true")
    args = parser.parse_args()
    result = (build if args.action == "build" else train)(args.target, args.assets, args.dual)
    print(json.dumps(result, indent=2))
