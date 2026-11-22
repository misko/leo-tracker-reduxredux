"""Rebuild packed cancellation with just the pre-PGO delay-product arithmetic."""

import argparse
import json
import subprocess
from hashlib import sha256
from pathlib import Path

from tools.pipeline_eval.variants.experimental.receiver_build import HERE, PINNED

RECIPE_SHA = "ebb16041dda446e67951cb4342e0d0a7c369e393b3780915ad46f2ce10821eb4"
INPUT_SHA = "88b4f3ba6479b287cd581c604afa796992a2e6c7cbd34761d176f24500123f03"
PACKED_SHA = "c7d370eef755ba71c225bf91992d94d79c6b2a886eea434ae6555179f2c9e316"
SOURCE_SHA = "d014fe0670ff7a926bbd302ada1f4d021fe2f488f91b32dae8b4fe1634a07f1c"
HEADERS = {
    "receiver_simd.inc": "3672b6f8b1aa8683783371553fcae2de2e2069dcf1642622e2fefbaff9e076a8",
    "receiver_refine_batch.h": "70a0474cb13fb01ae64e2f15aba1a8c8a9c3f0d667d3df284b295de622dd03bd",
    "receiver_refine_batch.inc": "700626f50e8c66d52e4076e0ab3821a691de566f849796ab365a913d3cf3cce8",
}
PILOT = "pilot_cancel.o"
DELAY = "delay_product_kernel.o"


def digest(path, expected=None):
    value = sha256(path.read_bytes()).hexdigest()
    if expected is not None and value != expected:
        raise ValueError(f"Unexpected saved bytes: {path}")
    return value


def compiler_inputs(recipe, archive, cancellation):
    args = recipe["args"]
    first_source = next(i for i, value in enumerate(args) if value.endswith(".c"))
    objects = {Path(value).with_suffix(".o").name: archive / Path(value).with_suffix(".o").name
               for value in args[first_source:] if value.endswith(".c")}
    if PILOT not in objects or DELAY not in objects:
        raise ValueError("Expected both the signed cancellation and the delay-product objects")
    objects[PILOT] = cancellation / PILOT
    flags = [arg for arg in args[:first_source] if arg not in ("-shared", "-Wl,--gc-sections")]
    return flags, objects


def build(output, archive, cancellation):
    recipe_file = PINNED / "build.json"
    digest(recipe_file, RECIPE_SHA)
    for name, expected in HEADERS.items():
        digest(HERE / name, expected)
    recipe = json.loads(recipe_file.read_bytes())
    compiler = recipe["cc"]
    flags, original = compiler_inputs(recipe, archive, cancellation)
    source = original[DELAY].with_suffix(".c")
    digest(source, SOURCE_SHA)
    digest(original[PILOT], PACKED_SHA)
    digest(cancellation / "use.so", INPUT_SHA)
    output.mkdir()

    def link(path, objects):
        cmd = [compiler, "-shared", "-Wl,--gc-sections", *objects.values(),
               "-lfftw3f", "-pthread", "-lm", "-o", path]
        subprocess.run(cmd, cwd=PINNED, check=True)
        return [str(item) for item in cmd]

    original_link = link(output / "packed.so", original)
    digest(output / "packed.so", INPUT_SHA)
    candidate = original.copy()
    candidate[DELAY] = output / DELAY
    compile_cmd = [compiler, *flags, "-I", PINNED / "tools/pipeline_eval/variants", "-I", HERE,
                   "-c", source, "-o", candidate[DELAY]]
    subprocess.run(compile_cmd, cwd=PINNED, check=True)
    corrected = output / "restored.so"
    corrected_link = link(corrected, candidate)
    compiler_version = subprocess.check_output([compiler, "--version"], text=True).splitlines()[0]
    result = dict(compiler=compiler_version,
                  compiler_cwd=str(PINNED), source_sha256=SOURCE_SHA, headers=HEADERS,
                  packed_sha256=INPUT_SHA, corrected_sha256=digest(corrected),
                  original_link=original_link, compile=[str(item) for item in compile_cmd],
                  corrected_link=corrected_link,
                  original_objects={name: digest(path) for name, path in original.items()},
                  corrected_objects={name: digest(path) for name, path in candidate.items()})
    (output / "build.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "archive", "cancellation"):
        parser.add_argument(name, type=lambda value: Path(value).resolve())
    args = parser.parse_args()
    build(args.output, args.archive, args.cancellation)


if __name__ == "__main__":
    main()
