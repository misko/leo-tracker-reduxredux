"""Link the archived packed scout with pre-PGO arithmetic on wrapped requests only."""

import argparse
import json
import subprocess
from pathlib import Path

from . import receiver_cfo_restore_object as restore

PGO_DELAY_SHA = "3b9ac7bf706e0b095344c3e0f682ce8a01cfdd9900703772a48c4c886b3cc48c"
REFERENCE_DELAY_SHA = "ed9074f4c3b4da84563ecc73a6854355e9288b0836f98a9a46ad3baf0cbe4b7d"
FULL_RESTORATION_SHA = "6f2cc95d835ffcff8226a925dddca9d5b03d8fe6b06c159b165ac0807b805a91"
PGO_SECTION = ".text.unlikely.delay_refine"
DISPATCH = Path(__file__).with_name("receiver_cfo_wrap_dispatch.c").resolve()


def run(cmd, *, cwd=None):
    command = [str(value) for value in cmd]
    subprocess.run(command, check=True, cwd=cwd)
    return command


def exports(library):
    rows = subprocess.check_output(["nm", "-D", "--defined-only", library], text=True).splitlines()
    return sorted(tuple(row.split()[-2:]) for row in rows)


def splice_objects(output, pgo, reference, compiler, flags, *, cwd=None):
    pgo_copy, reference_copy, dispatch = (output / name for name in
                                          ("delay_pgo.o", "delay_reference.o", "delay_dispatch.o"))
    # Bank calls retain their original PLT relocation. The strong wrapper
    # overrides the weak definition, and a private alias keeps the PGO body.
    table = subprocess.check_output(["objdump", "-t", pgo], text=True).splitlines()
    symbol, = [line.split() for line in table if line.endswith(" delay_refine") or
               line.endswith("\tdelay_refine")]
    if int(symbol[0], 16) != 0 or symbol[-3] != PGO_SECTION or symbol[1:3] != ["g", "F"]:
        raise ValueError("Expected the original refinement symbol at the pinned section start")
    commands = [
        run(["objcopy", "--weaken-symbol=delay_refine",
             f"--add-symbol=leo_pgo_delay_refine={PGO_SECTION}:0,global,function", pgo, pgo_copy]),
        run(["objcopy", "--redefine-sym=delay_refine=leo_reference_delay_refine",
             "--localize-symbol=delay_decimate", "--localize-symbol=delay_refine_bank",
             reference, reference_copy]),
        run([compiler, *flags, "-Wall", "-Wextra", "-Werror", "-c", DISPATCH, "-o", dispatch],
            cwd=cwd),
    ]
    return (pgo_copy, reference_copy, dispatch), commands


def build(output, archive, cancellation, restoration):
    recipe_file = restore.PINNED / "build.json"
    restore.digest(recipe_file, restore.RECIPE_SHA)
    recipe = json.loads(recipe_file.read_bytes())
    compiler = recipe["cc"]
    flags, objects = restore.compiler_inputs(recipe, archive, cancellation)
    reference_delay = restoration / restore.DELAY
    packed = cancellation / "use.so"
    restore.digest(packed, restore.INPUT_SHA)
    restore.digest(objects[restore.PILOT], restore.PACKED_SHA)
    restore.digest(objects[restore.DELAY], PGO_DELAY_SHA)
    restore.digest(reference_delay, REFERENCE_DELAY_SHA)
    restore.digest(restoration / "restored.so", FULL_RESTORATION_SHA)
    output.mkdir()

    def link(path, parts):
        return run([compiler, "-shared", "-Wl,--gc-sections", *parts,
                    "-lfftw3f", "-pthread", "-lm", "-o", path], cwd=restore.PINNED)

    reproducer = output / "packed.so"
    commands = [link(reproducer, objects.values())]
    restore.digest(reproducer, restore.INPUT_SHA)
    modified, splice_commands = splice_objects(output, objects[restore.DELAY], reference_delay,
                                               compiler, flags, cwd=restore.PINNED)
    commands += splice_commands
    for section in (".text.refine_batch", ".text.delay_refine_bank", ".text.hot.paired_fir"):
        dump = ["readelf", "--hex-dump", section]
        if (subprocess.check_output([*dump, objects[restore.DELAY]]) !=
                subprocess.check_output([*dump, modified[0]])):
            raise ValueError(f"Wrapped restoration changed archived PGO instructions in {section}")
    candidate = objects | {restore.DELAY: modified[0]}
    binary = output / "wrapped.so"
    commands.append(link(binary, (*candidate.values(), *modified[1:])))
    if exports(binary) != exports(reproducer):
        raise ValueError("Wrapped restoration changed the receiver's exported ABI")
    result = dict(library_sha256=restore.digest(binary), packed_sha256=restore.INPUT_SHA,
                  full_restoration_sha256=FULL_RESTORATION_SHA,
                  dispatch_sha256=restore.digest(DISPATCH),
                  original_objects={key: restore.digest(path) for key, path in objects.items()},
                  reference_delay_sha256=REFERENCE_DELAY_SHA,
                  linked_delay_objects={path.name: restore.digest(path) for path in modified},
                  cwd=str(restore.PINNED), commands=commands)
    (output / "build.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "archive", "cancellation", "restoration"):
        parser.add_argument(name, type=lambda value: Path(value).resolve())
    build(**vars(parser.parse_args()))
