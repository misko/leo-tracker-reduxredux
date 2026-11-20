"""Build the sealed standalone C receiver and isolated Qin tile kernel."""

import argparse
import os
import subprocess
from hashlib import sha256
from pathlib import Path

from ..__main__ import ROOT, local_output, save_json
from .portable_verifier_run import BUILD_FLAGS, KERNEL, SOURCES, TARGETS, VARIANTS

REVISION = "234490f2b"
CLI = Path(__file__).with_name("portable_coarse_cli.c")
COARSE = VARIANTS / "portable_coarse.c"
TILES = VARIANTS / "c_coarse_tiles.h"
VERIFY_SOURCES = SOURCES[1:]
SOURCE_PATHS = tuple(
    path.relative_to(ROOT)
    for path in (
        CLI,
        COARSE,
        *VERIFY_SOURCES,
        *(
            VARIANTS / name
            for name in (
                "portable_coarse.h",
                "portable_coarse_qin.h",
                "portable_fine.h",
                "portable_verifier.h",
            )
        ),
        KERNEL / "native_presence/fft.h",
    )
)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"sealed source overlay no longer has one match for {old!r}")
    return source.replace(old, new)


def overlay(source, *, pairs_only=False):
    start = source.index("static void phase_pairs(" if pairs_only else "static void rotations(")
    end = source.index("static void grid(")
    source = source[:start] + '#include "c_coarse_tiles.h"\n\n' + source[end:]
    if pairs_only:
        return "#define C_COARSE_TILES_PAIR_ONLY\n" + replace_once(
            source,
            "            fold(w,family,count,limit,p,size,row,real,imag);",
            "            fold_tiles(w,family,count,limit,p,size,row,w->xr,w->xi,real,imag);",
        )
    source = replace_once(
        source,
        "    float real[tones][tile], imag[tones][tile];\n",
        "    TileCarriers carriers;\n    tile_carriers(&carriers);\n",
    )
    source = replace_once(
        source,
        "        ToneRow seed[taps], undo, tail, amp;\n"
        "        rotations(center+residual[f],seed,&undo,&tail,&amp);\n",
        "",
    )
    start = source.index("        for (unsigned p=0; p<limit; p+=tile)")
    end = source.index("        for (unsigned e=0; e<epochs; ++e)", start)
    return (
        source[:start]
        + "        tile_row(w,&carriers,family,count,limit,center+residual[f],row);\n"
        + source[end:]
    )


def snapshot(folder):
    folder.mkdir()
    sources = {}
    for rel in SOURCE_PATHS:
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        data = subprocess.check_output(["git", "show", f"{REVISION}:{rel}"], cwd=ROOT)
        path.write_bytes(data)
        sources[str(rel)] = digest(path)
    base = (folder / COARSE.relative_to(ROOT)).read_text()
    for name, pairs_only in (("tiles", False), ("pairs", True)):
        tuned = folder / COARSE.with_stem(f"c_coarse_tiles_{name}").relative_to(ROOT)
        tuned.write_text(overlay(base, pairs_only=pairs_only))
        sources[str(tuned.relative_to(folder))] = digest(tuned)
    (folder / TILES.relative_to(ROOT)).write_bytes(TILES.read_bytes())
    sources[str(TILES.relative_to(ROOT))] = digest(TILES)
    return sources


def compile_binary(folder, sources, target, version, *, profile=False, shared=False):
    cc, arch, _, _ = TARGETS[target]
    arch = ("-march=x86-64-v3",) if target == "x86" else arch
    flags = list(BUILD_FLAGS)
    kernel = COARSE if version == "incumbent" else COARSE.with_stem(f"c_coarse_tiles_{version}")
    files = (CLI, kernel, *VERIFY_SOURCES)
    name = "detector"
    if profile:
        flags += ["-pg", "-g"]
    if shared:
        flags.remove("-static")
        flags += ["-shared", "-fPIC"]
        files = (kernel,)
        name += ".so"
    folder.mkdir(parents=True)
    binary = folder / name
    command = [
        cc,
        *flags,
        *arch,
        "-I",
        sources / KERNEL.relative_to(ROOT) / "native_presence",
        *(sources / path.relative_to(ROOT) for path in files),
        "-lm",
        "-o",
        binary,
    ]
    subprocess.run(
        command, cwd=folder, env=os.environ | {"TMPDIR": str(folder)}, check=True, timeout=45
    )
    if not shared and b"INTERP" in subprocess.check_output(["readelf", "-l", binary]):
        raise ValueError("standalone detector acquired a dynamic runtime dependency")
    sections = {}
    for line in subprocess.check_output(["size", "-A", binary], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] in {".text", ".rodata", ".data", ".bss"}:
            sections[parts[0]] = int(parts[1])
    return {
        "command": [str(part) for part in command],
        "sha256": digest(binary),
        "file_bytes": binary.stat().st_size,
        "sections": sections,
        "tool": subprocess.check_output([cc, "--version"], text=True).splitlines()[0],
    }


def build(work, targets):
    work.mkdir()
    sources = work / "source"
    lock = {"revision": REVISION, "sources": snapshot(sources), "builds": {}}
    for target in targets:
        lock["builds"][target] = {}
        for version in ("incumbent", "tiles", "pairs"):
            out = work / target / version
            lock["builds"][target][version] = compile_binary(out, sources, target, version)
    for version in ("incumbent", "tiles", "pairs"):
        for name, kw in (("profile", {"profile": True}), ("grid", {"shared": True})):
            out = work / name / version
            lock["builds"].setdefault(name, {})[version] = compile_binary(
                out, sources, "x86", version, **kw
            )
    save_json(work / "build-lock.json", lock)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--targets", nargs="+", choices=tuple(TARGETS), default=["x86"])
    args = parser.parse_args()
    build(args.work, args.targets)
