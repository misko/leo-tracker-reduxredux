"""Bind the isolated two-lag, four-row timing scout to the guarded short ABI."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
PROFILE = Path("/dev/shm/leo-anchored-phase-results02/short-anchored/portable_verifier.o")
PROFILE_SHA = "68c8e294db5e6bfa6c6abf7e9d6cc9c65c8cd6fe1d9ef211fa685c81f8255e21"
ORIGINAL_SHORT = "f20605e5a4e487d13548411b0430ea262b9b9c6fba89dae973313d3d0008bb6a"
PRIOR = "96ad73cac883ece79c3831933194bdcea3d6f50ef9abfad793a1e9f226410db1"
LAYOUT = {"sample_limit": 120_000, "timing_lags": [28, 44], "carrier_rows": 4}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def checked(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Unexpected binding for {path}")
    return data


def reduced_source(source):
    import re

    changes = (("clocks = 12,", "clocks = 4,"),
               (r"(static void find_times\(.*?for \(int k = 0; k < lags; \+\+k\) \{)",
                r"\1\n        if (k != 5 && k != 6) continue;"))
    source, first = re.subn(changes[0][0], changes[0][1], source)
    source, second = re.subn(changes[1][0], changes[1][1], source, flags=re.S)
    if first != 1 or second != 1 or "points = 120000," not in source:
        raise ValueError("The frozen 12 ms timing source changed layout")
    return source


def read_pack(root, pin):
    info = json.loads(checked(root / "short-scout.json", pin))
    if (info["layout"] != LAYOUT or info["baseline_short_sha256"] != ORIGINAL_SHORT
            or info["wrapper_sha256"] != digest(Path(__file__)) or info["prior_sha256"] != PRIOR
            or info["training"]["positive"] != 12 or info["training"]["empty"] != 4):
        raise ValueError("The short timing pack does not bind the frozen scout and signed checks")
    path = (root / "short.so").resolve(strict=True)
    checked(path, info["short_sha256"])
    return info, path


@contextmanager
def activate(root, pin):
    import anchored_cfo_raw as guarded

    info, binary = read_pack(root, pin)
    verify, recipe = guarded.verified_pack, guarded.recipe

    def shorter(ordinary):
        paths = verify(ordinary)
        if guarded.LIBRARIES["short.so"] != ORIGINAL_SHORT:
            raise ValueError("The current guarded short parent differs from the frozen pack")
        return paths | {"short.so": binary}

    def bound(*args):
        actual = recipe(*args)
        return dict(actual, short_timing_scout=dict(LAYOUT, original_short_sha256=ORIGINAL_SHORT,
                    short_sha256=info["short_sha256"], source_sha256=info["reduced_source_sha256"],
                    guard_object_sha256=PROFILE_SHA, pack_sha256=pin))

    with patch.object(guarded, "verified_pack", shorter), patch.object(guarded, "recipe", bound):
        yield


def train(binary, assets, reference=None):
    from contextlib import closing
    import numpy as np

    from .timing_only_oracle import TICKS, asset_for
    from .whole_group_receiver_bound import PILOT_SHA, measure, receiver

    rng = np.random.default_rng(4841)
    samples = np.arange(200_000)
    positive = empty = same = 0
    for edge in PILOT_SHA:
        asset = asset_for(assets, edge)
        pilot = asset[4 * 13333 + 81:].view(np.complex64)
        with (closing(receiver(binary, asset, "short")) as short,
              closing(receiver(reference or binary, asset, "short")) as stock):
            for strength, center in ((80, -50000), (500, 60000), (1500, 0), (0, 0)):
                iq = rng.normal(0, 19, (len(samples), 2, 2)).astype(np.int16)
                for lane in (0, 1):
                    signed = -250000 + 381000 * lane
                    tick = 2215 + 3201 * lane
                    waveform = strength * pilot[(3 * samples - tick) % TICKS]
                    waveform *= np.exp(2j * np.pi * signed * samples * 1e-7)
                    iq[:, lane, 0] += np.rint(waveform.real).astype(np.int16)
                    iq[:, lane, 1] += np.rint(waveform.imag).astype(np.int16)
                    measured, blob, _ = measure(short, iq, lane, center)
                    if reference is not None:
                        _, before, _ = measure(stock, iq, lane, center)
                        same += blob == before
                    if strength:
                        if len(measured) != 1 or measured[0][0] != 0 or abs(measured[0][3] - signed) > 250:
                            raise ValueError("A signed training plant did not pass")
                        actual = measured[0][1] + measured[0][2]
                        if abs((actual - tick / 3 + TICKS / 6) % (TICKS / 3) - TICKS / 6) > 2:
                            raise ValueError("The signed plant moved outside the original time gate")
                        positive += 1
                    else:
                        if measured:
                            raise ValueError("A pure noise training lane acquired a factor")
                        empty += 1
    return dict(positive=positive, empty=empty, exact_matched_lanes=same)


def build(root, assets):
    from .whole_group_receiver_bound import FULL_BUILD, FULL_BUILD_SHA, SHORT_BUILD, SHORT_BUILD_SHA, SOURCE_SHA

    original = json.loads(checked(SHORT_BUILD, SHORT_BUILD_SHA))
    full = json.loads(checked(FULL_BUILD, FULL_BUILD_SHA))
    compile_flags = full["commands"][-2][:-4]
    if subprocess.check_output(["cc", "--version"], text=True).splitlines()[0] != full["compiler"]:
        raise ValueError("Compiler differs from the original native build")
    link = original["relink"]
    timing, = (value for value in link if Path(value).name == "timing_first_receiver.o")
    verifier, = (value for value in link if Path(value).name == "portable_verifier.o")
    original_source = checked(Path(timing).with_suffix(".c"), SOURCE_SHA["short"]).decode()
    checked(PROFILE, PROFILE_SHA)
    root.mkdir()
    commands = []

    def run(command):
        command = list(map(str, command))
        commands.append(command)
        subprocess.run(command, cwd=full["cwd"], check=True)

    reference = root / "ordinary-guarded.so"
    run([*(PROFILE if value == verifier else value for value in link[:-1]), reference])
    checked(reference, ORIGINAL_SHORT)
    work = root / "compile"
    feedback = work / "profile"
    feedback.mkdir(parents=True)
    source = work / "timing_first_receiver.c"
    # The archived guarded link's other objects and their flags stay byte-identical.
    source.write_text(reduced_source(original_source))
    obj = source.with_suffix(".o")
    relink = [str(obj) if value == timing else str(PROFILE) if value == verifier else value
              for value in link[1:-1] if not value.startswith("-fprofile-use") and value != "-fno-profile-values"]
    for phase in ("generate", "use"):
        binary = work / "instrumented.so" if phase == "generate" else root / "short.so"
        pgo = [f"-fprofile-{phase}={feedback}", "-fno-profile-values"]
        strict = [] if phase == "generate" else ["-Werror=missing-profile", "-Werror=coverage-mismatch"]
        run([*compile_flags, *pgo, *strict, "-c", source, "-o", obj])
        run([link[0], *pgo, *relink, binary])
        if phase == "generate":
            run([sys.executable, "-Bm", "reports.ALGO08.v3.all_visit_timing", "train", binary, assets])
    training = train(root / "short.so", assets, reference)
    info = dict(layout=LAYOUT, training=training, prior_sha256=PRIOR, wrapper_sha256=digest(Path(__file__)),
                reduced_source_sha256=digest(source), original_source_sha256=SOURCE_SHA["short"],
                short_sha256=digest(root / "short.so"), baseline_short_sha256=ORIGINAL_SHORT,
                original_build_sha256={"timing": SHORT_BUILD_SHA, "full": FULL_BUILD_SHA, "verifier": PROFILE_SHA},
                commands=commands)
    (root / "short-scout.json").write_text(json.dumps(info, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "train"))
    parser.add_argument("output", type=Path)
    parser.add_argument("assets", type=Path)
    args = parser.parse_args()
    (build if args.mode == "build" else train)(args.output.resolve(), args.assets.resolve())
