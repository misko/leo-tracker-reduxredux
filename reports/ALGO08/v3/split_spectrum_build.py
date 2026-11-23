"""Relink the frozen 12 ms receiver with a fractional spectrum trace tap."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

from .directed_verifier_trial import replace_once
from .eight_ms_primary_trial import PRODUCTION_SHORT
from .mixed_aperture_receiver import verified

HERE = Path(__file__).resolve().parent
SHORT = Path("/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2")
BUILD_SHA = "99f912ef6c1cd57f13b081408a8cececc9bb3ea2384c517bef70f7eb34bfcfac"
VERIFY_C = Path("/var/tmp/leo-short-signed-02/short/portable_verifier.c")
VERIFY_SHA = "4cceaa68fe8d7f93608d1d07f585e2bc5c68955a22619d989052d6cde2e70def"
STENCIL_SHA = "8b2f4162d9637991e45b3e47eea28aadd9ff254bee02389569be69180f064a63"
EXACT = Path("/tmp/leo-algo08v2-2x-bench/receiver-fractional-exact-v1/build.json")
EXACT_SHA = "5566ddd22345982e1b7673c7d65a8ce5799ce8229275365e1e6e237ab3f0e86d"


def overlay(source):
    for original, instrumented in (
        ("static double glrt_spectrum_details(",
         '#include "split_spectrum_tap.inc"\n\nstatic double glrt_spectrum_details('),
        ("    double spectra[short_size] = {0}, ceiling = 0;",
         "    double spectra[short_size] = {0}, ceiling = 0;\n"
         "    double halves[2][short_size], half_ceiling[2] = {0};\n"
         "    const int capture = split_fractional;\n"
         "    if (capture) memset(halves, 0, sizeof(halves));"),
        ("        ceiling += row*row;",
         "        ceiling += row*row;\n"
         "        if (capture) half_ceiling[frame % 2] += row*row;"),
        ("            spectra[k] += re*re + im*im;",
         "            const double power = re*re + im*im;\n"
         "            spectra[k] += power;\n"
         "            if (capture) halves[frame % 2][k] += power;"),
        ("    if (ceiling == 0) return 0;",
         "    if (ceiling == 0) {\n"
         "        if (capture) split_finish(w, frames, halves, half_ceiling);\n"
         "        return 0;\n    }"),
        ("    if (gap) *gap = (best - second) / ceiling;",
         "    if (gap) *gap = (best - second) / ceiling;\n"
         "    if (capture) split_finish(w, frames, halves, half_ceiling);"),
        ("        if (glrt(w, epoch, freq, out->offset_samples, &out->fractional_exact, &out->fractional_control,\n"
         "                 &out->fractional_residual_hz, &out->flags, allow_phase_free)) return -1;",
         "        split_fractional = 1;\n"
         "        int status = glrt(w, epoch, freq, out->offset_samples, &out->fractional_exact,\n"
         "                          &out->fractional_control, &out->fractional_residual_hz,\n"
         "                          &out->flags, allow_phase_free);\n"
         "        split_fractional = 0;\n"
         "        if (status) return -1;"),
        ("    return 0;\n}\n\nint portable_verifier_glrt(",
         "    split_trace.seen = 1;\n"
         "    split_trace.flags = out->flags;\n"
         "    return 0;\n}\n\nint portable_verifier_glrt("),
    ):
        source = replace_once(source, original, instrumented)
    return source


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def build(out):
    out.mkdir()
    release = json.loads(verified(EXACT, EXACT_SHA))
    short = json.loads(verified(SHORT / "build-receipt.json", BUILD_SHA))
    control = SHORT / "short-primary.so"
    verified(control, PRODUCTION_SHORT)
    original = verified(VERIFY_C, VERIFY_SHA).decode()
    source = out / "portable_verifier.c"
    source.write_text(overlay(original))
    tap = out / "split_spectrum_tap.inc"
    shutil.copyfile(HERE / tap.name, tap)
    stencil = out / "receiver_stencil_verify.inc"
    stencil.write_bytes(verified(VERIFY_C.with_name(stencil.name), STENCIL_SHA))
    obj = out / "portable_verifier.o"
    binary = out / "split-spectrum.so"
    compile_unit = [*release["commands"][-2][:-4], "-c", str(source), "-o", str(obj)]
    link, objects = [], {}
    for item in short["relink"][:-1]:
        if item.endswith(".o"):
            path = Path(item)
            if path.name != "two_carrier_receiver.o":
                verified(path, short["short_object_sha256"][path.name])
            objects[path.name] = digest(path)
            if path.name == obj.name:
                item = str(obj)
        link.append(item)
    link.append(str(binary))
    rebuilt = out / "stock-relinked.so"
    reference_link = [*short["relink"][:-1], str(rebuilt)]
    for command in (reference_link, compile_unit, link):
        subprocess.run(command, cwd=release["cwd"], check=True, timeout=25)
    verified(rebuilt, PRODUCTION_SHORT)
    receipt = dict(
        binary=str(binary), binary_sha256=digest(binary),
        control=str(control), control_sha256=PRODUCTION_SHORT,
        compile=compile_unit, relink=link, reference_link=reference_link,
        cwd=release["cwd"], original_sha256=VERIFY_SHA,
        stencil_sha256=STENCIL_SHA,
        source_sha256=digest(source), tap_sha256=digest(tap), release_sha256=EXACT_SHA,
        short_build_sha256=BUILD_SHA, objects=objects,
    )
    (out / "build.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    build(parser.parse_args().out.resolve())
