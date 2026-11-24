"""Rebuild the exact scout with a selectable four-symbol sum and matched PGO."""

import argparse
import ctypes as ct
import json
from pathlib import Path
import runpy
import subprocess
import sys

from .cross_lag_eight_ms import BUILD_SHA, EIGHT, EIGHT_SHA, SOURCE_SHA
from .eight_ms_primary import write
from .live_stereo_0008 import original
from .mixed_aperture_receiver import INSTALLED_SHA, verified
from .mixed_aperture_trial import exports
from .scout_readout_trial import check_machine
from .verifier_pilot_support import digest
from .whole_group_receiver_bound import FULL_BUILD, FULL_BUILD_SHA, SOURCE_SHA as RELEASE_SHA


HERE = Path(__file__).resolve().parent
HELPER = HERE / "scout_gate_symbols.inc"
TRAINER = HERE.parent / "single-core-2x/receiver_mixer_profile_trial.py"
TRAINER_SHA = "c63b849fb630d33fee53d8011b1766891b7e3c9038295334275135055dc443ac"
SCALAR_START = "            for (int s = 0; s < 64; ++s) {\n"
SCALAR_STOP = "            transform(w, 64, 0);\n"


def overlay(source):
    gate = "static int gate(TimingFirst *w"
    before, after = source.split(gate, 1)
    block_start, block_stop = after.index(SCALAR_START), after.index(SCALAR_STOP)
    indent = "            "
    nested = "".join("    " + line for line in after[block_start:block_stop].splitlines(keepends=True))
    after = (after[:block_start] + indent + "if (!scout_gate_symbols_try(w->data + offset, rotation, w->scratch)) {\n"
             + nested + indent + "}\n" + after[block_stop:])
    return before + f'#include "{HELPER.name}"\n\n' + gate + after


def train(binary):
    verified(TRAINER, TRAINER_SHA)
    sys.path.insert(0, str(TRAINER.parent))
    training = runpy.run_path(str(TRAINER))["train"]
    library = ct.CDLL(str(binary))
    switch = library.scout_gate_symbols_mode
    switch.argtypes, switch.restype = [ct.c_int], ct.c_int
    reference = None
    for mode in (0, 1):
        if switch(mode) != mode:
            raise ValueError("The matched x86 profile requires both scalar and AVX2 modes")
        rows = training(binary, original.RELEASE / "assets")
        if reference is not None and rows != reference:
            raise ValueError("The site-free signed training output counts differ")
        reference = rows


def build(root):
    machine = check_machine()
    installed = original.PAYLOAD / "receiver.so"
    verified(installed, INSTALLED_SHA)
    verified(EIGHT, EIGHT_SHA)
    full = json.loads(verified(FULL_BUILD, FULL_BUILD_SHA))
    short = json.loads(verified(EIGHT.with_name("build-receipt.json"), BUILD_SHA))
    if subprocess.check_output(["cc", "--version"], text=True).splitlines()[0] != full["compiler"]:
        raise ValueError("The archived native compiler differs")
    root.mkdir()
    commands, artifacts = {}, {}
    for mode, stock, pin, link in (("full", installed, INSTALLED_SHA, full["commands"][-1]),
                                   ("short", EIGHT, EIGHT_SHA, short["relink"])):
        directory = root / mode
        directory.mkdir()
        profile = directory / "profile"
        profile.mkdir()
        commands[mode] = []

        def run(argv):
            command = list(map(str, argv))
            commands[mode].append(command)
            subprocess.run(command, cwd=full["cwd"], check=True)

        stock_relink = directory / "original.so"
        run([*link[:-1], stock_relink])
        verified(stock_relink, pin)
        old, = (Path(arg) for arg in link if Path(arg).name == "timing_first_receiver.o")
        code = old.with_suffix(".c")
        code_pin = RELEASE_SHA["full"] if mode == "full" else SOURCE_SHA
        c = directory / code.name
        c.write_text(overlay(verified(code, code_pin).decode()))
        object_file = c.with_suffix(".o")
        link_args = [object_file if arg == str(old) else arg for arg in link[1:-1]
                     if not arg.startswith("-fprofile-use=") and arg != "-fno-profile-values"]
        flags = [*full["commands"][-2][:-4], "-I", HERE]
        for phase in ("generate", "use"):
            pgo = [f"-fprofile-{phase}={profile}", "-fno-profile-values"]
            strict = ["-Werror=missing-profile", "-Werror=coverage-mismatch"] if phase == "use" else []
            binary = directory / ("scout.so" if phase == "use" else "train.so")
            run([*flags, *pgo, *strict, "-c", c, "-o", object_file])
            run([link[0], *pgo, *link_args, binary])
            if phase == "generate":
                run([sys.executable, "-Bm", "reports.ALGO08.v3.scout_gate_symbols", "train", binary])
        if exports(binary) != exports(stock) | {"scout_gate_symbols_mode"}:
            raise ValueError("The original signed receiver ABI changed")
        (feedback,) = profile.rglob("*.gcda")
        artifacts[mode] = dict(candidate=digest(binary), control=pin, original_timing=code_pin,
                               changed_timing=digest(c), feedback=digest(feedback))
    write(root / "build.json", dict(binaries=artifacts, commands=commands, machine=machine,
                                  builder_sha256=digest(Path(__file__)), helper_sha256=digest(HELPER),
                                  trainer_sha256=TRAINER_SHA))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "train"))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    (build if args.mode == "build" else train)(args.path)
