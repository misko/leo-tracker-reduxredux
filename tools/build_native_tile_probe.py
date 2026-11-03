"""Build isolated 4/8-lane probes over the pinned deployed native GLRT runtime."""

import argparse
import ast
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sysconfig
from pathlib import Path

from stage_native_glrt_runtime import digest, verify, verify_files


def transform(c_source, grid_source, python_source, lanes):
    if lanes not in (4, 8):
        raise ValueError("Probe requires 4 or 8 lanes")
    marker = "if (kernel->cfo_count == 12) {"
    if grid_source.count(marker) != 1:
        raise ValueError("Unknown native register layout")
    start = grid_source.index(marker)
    end = grid_source.index("} else {", start)
    old = grid_source[start:end]
    # Drop complete statements mentioning the unused vector groups. Each retained
    # lane keeps mul, fma/fnmadd, then add, in the original sample order.
    body = old[len(marker):]
    statements = body.split(";")
    groups = range(lanes // 4, 3)
    kept = [s for s in statements if not any(
        re.search(r"(?:real|imag)_" + str(i) + r"\b", s) for i in groups)]
    body = ";".join(kept).replace("index * 12", f"index * {lanes}")
    grid_source = (grid_source[:start] + f"if (kernel->cfo_count == {lanes}) {{"
                   + body + grid_source[end:])
    if c_source.count("cfo_count == 12") != 1:
        raise ValueError("Unknown native dispatch")
    c_source = c_source.replace("cfo_count == 12", f"cfo_count == {lanes}")
    nodes = [n for n in ast.parse(python_source).body if isinstance(n, ast.FunctionDef)
             and n.name == "_folded_anchor_score_grid_native"]
    if len(nodes) != 1:
        raise ValueError("Unknown Python grid wrapper")
    node = nodes[0]
    lines = python_source.splitlines(keepends=True)
    block = "".join(lines[node.lineno-1:node.end_lineno])
    for old, new in [("scientific_cfo_count > 12", f"scientific_cfo_count > {lanes}"),
                     ("range(0, scientific_cfo_count, 12)",
                      f"range(0, scientific_cfo_count, {lanes})"),
                     ("start : start + 12", f"start : start + {lanes}"),
                     ("12 - len(tile)", f"{lanes} - len(tile)")]:
        if block.count(old) != 1:
            raise ValueError("Unknown Python tiling layout")
        block = block.replace(old, new)
    lines[node.lineno-1:node.end_lineno] = [block]
    return c_source, grid_source, "".join(lines)


def build(base, pin, output, lanes):
    import numpy

    base, output = base.resolve(strict=True), output.resolve()
    if not output.is_relative_to("/srv/bulk/leo/research") or output.exists():
        raise ValueError("New isolated research directory required")
    manifest = verify(base, pin)
    inventory = manifest["files_sha256"]
    prefix = "src/leo/analysis/starlink/"
    names = [prefix + n for n in ("_native_acquisition.c", "_native_acquisition_grid.inc",
                                  "acquisition.py")]
    texts = transform(*[(base / n).read_text() for n in names], lanes)
    output.mkdir(parents=True)
    for name in inventory:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base / name, target)
    for name, text in zip(names, texts, strict=True):
        (output / name).write_text(text)
    extension = prefix + "_native_acquisition" + sysconfig.get_config_var("EXT_SUFFIX")
    command = [*shlex.split(sysconfig.get_config_var("CC")), "-shared", "-fPIC", "-O3",
               "-fno-math-errno", "-Wall", "-Wextra", "-I" + sysconfig.get_path("include"),
               "-I" + numpy.get_include(), str(output / names[0]),
               str(output / prefix / "fast_scan_fold.c"), "-lm", "-o", str(output / extension)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    candidate = {name: digest(output / name) for name in inventory}
    changed = sorted(n for n in inventory if inventory[n] != candidate[n])
    if changed != sorted(names + [extension]):
        raise ValueError("Unexpected file changes")
    verify(base, pin)
    verify_files(output, candidate)
    receipt = dict(base=str(base), base_pin=pin, candidate=str(output), lanes=lanes,
                   files_sha256=candidate, changes=changed, compile_command=command,
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   compiler=subprocess.check_output(command[:1] + ["--version"], text=True),
                   production_modified=False, qualification="research only")
    (output / "tile-probe.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return dict(candidate=str(output), lanes=lanes, changed=changed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--pin", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lanes", type=int, choices=(4, 8), required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.base, args.pin, args.output, args.lanes)))
