"""Build a numerics-only source distribution for the standalone cavity executable."""

import argparse
import ast
import gzip
import hashlib
import io
import json
import tarfile
from collections import deque
from importlib.util import resolve_name
from pathlib import Path, PurePosixPath

ENTRY = "tools.pipeline_eval.variants.v5_direct_lifetime"
# The deployed executable needs only these operations from the four mixed-purpose modules.
FUNCTIONS = {
    "tools.pipeline_eval.variants.v5_core": (
        "cold_node",
        "ranked_initial_nodes",
        "fit_initial_nodes",
        "initial_selection",
        "scan_context",
    ),
    "tools.pipeline_eval.variants.orbit_projector": (
        "KERNEL",
        "FLAGS",
        "compile_kernel",
        "Stencil",
        "prepare",
        "Projector",
    ),
    "leo.application.localization_v3": (
        "prepare_initial_sky",
        "prepare_phase_history",
        "prepare_native_scan",
    ),
    "leo.application.localization_v3_engine": ("_json_value", "_prepared_values"),
}
# The executable imports concrete submodules under these four package roots.
# Their platform-wide registries pull in the database, scanner and plotting code.
FACADES = {"leo.operations", "leo.contracts", "leo.analysis.research", "leo.application"}
NATIVE_SOURCES = {
    "leo/analysis/localization_v4/native_bound.c",
    "tools/pipeline_eval/variants/orbit_projector.c",
}


def names_in_import(node):
    return {a.asname or a.name.split(".")[0] for a in node.names}


def select_definitions(source, required):
    tree = ast.parse(source)
    keep = []
    for node in tree.body:
        name = getattr(node, "name", None)
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = getattr(node.targets[0], "id", None)
        if name in required:
            keep.append((name, node))
    if {name for name, _ in keep} != set(required):
        raise ValueError("standalone cavity definitions differ from the declared entry")
    needed = {n.id for _, node in keep for n in ast.walk(node) if isinstance(n, ast.Name)}
    imports = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and (getattr(node, "module", "") == "__future__" or needed & names_in_import(node))
    ]
    lines = source.splitlines(keepends=True)
    blocks = []
    for node in sorted(imports + [n for _, n in keep], key=lambda n: n.lineno):
        first = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", ()))])
        blocks.append("".join(lines[first - 1 : node.end_lineno]).rstrip())
    return "\n\n".join(blocks) + "\n"


def module_id(path):
    if path.endswith("/__init__.py"):
        return path[:-12].replace("/", ".")
    if path.endswith(".py"):
        return path[:-3].replace("/", ".")
    if path.endswith(".so") and ".cpython-" in path:
        return path.split(".cpython-")[0].replace("/", ".")
    return None


def source_closure(files, entry=ENTRY):
    modules = {module: name for name in files if (module := module_id(name))}
    pending = deque([entry])
    selected = {}
    while pending:
        module = pending.popleft()
        name = modules[module]
        if name in selected:
            continue
        parts = module.split(".")
        pending.extend(p for i in range(1, len(parts)) if (p := ".".join(parts[:i])) in modules)
        raw = files[name]
        if not name.endswith(".py"):
            selected[name] = raw
            continue
        source = raw.decode()
        if module in FUNCTIONS:
            source = select_definitions(source, FUNCTIONS[module])
        if module in FACADES:
            selected[name] = b""
            continue
        selected[name] = source.encode()
        package = module if name.endswith("/__init__.py") else module.rpartition(".")[0]
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                if any(a.name in FACADES for a in node.names):
                    raise ValueError(f"{module} uses a full platform package")
                pending.extend(a.name for a in node.names if a.name in modules)
            if not isinstance(node, ast.ImportFrom):
                continue
            base = resolve_name("." * node.level + (node.module or ""), package)
            if base in modules:
                pending.append(base)
            for alias in node.names:
                child = base + "." + alias.name
                if child in modules:
                    if child in FACADES:
                        raise ValueError(f"{module} requests the full {child} package")
                    pending.append(child)
                elif base in FACADES:
                    raise ValueError(f"{module} requests the omitted export {base}.{alias.name}")
    for filename in NATIVE_SOURCES:
        selected[filename] = files[filename]
    return dict(sorted(selected.items()))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_bundle(archive, manifest):
    verified = {}
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            name = member.name
            path = PurePosixPath(name)
            if (
                not member.isfile()
                or path.is_absolute()
                or ".." in path.parts
                or name != str(path)
                or name in verified
                or name not in manifest
            ):
                raise ValueError(f"unexpected source bundle member {name!r}")
            data = source.extractfile(member).read()
            if digest(data) != manifest[name]:
                raise ValueError(f"source digest mismatch for {name}")
            verified[name] = data
    if set(verified) != set(manifest):
        raise ValueError("source bundle is incomplete")
    return verified


def packed(files):
    out = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for name, data in sorted(files.items()):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return out.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    if arguments.output.resolve().is_relative_to("/mnt/qnap01"):
        parser.error("the receiver archive requires a writable local output path")
    manifest = json.loads(arguments.manifest.read_bytes())
    subset = source_closure(read_bundle(arguments.archive, manifest["files"]))
    with arguments.output.open("xb") as output:
        output.write(packed(subset))
