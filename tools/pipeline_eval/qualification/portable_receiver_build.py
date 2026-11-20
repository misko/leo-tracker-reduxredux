"""Build the relocatable stock-wide saved-IQ receiver from released project sources."""

import argparse
import ast
import importlib.util
import shutil
from pathlib import Path

from .. import cavity_runtime, whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import capture_release, full_v5_check, portable_receiver, recording_to_v5
from . import whole_memory_chain_worker as bounded
from .full_v5_check import _sha

STOCK = "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66"
SEEDS = (
    "leo.analysis.starlink.native_short_window",
    "leo.analysis.starlink.templates",
    "leo.contracts.fast_scan_native",
    "leo.scanner.fast_scan_analysis",
    "leo.storage.fast_scan",
    "leo.storage.short_window",
)
OUT_OF_SCOPE = ("leo.api", "leo.cli", "leo.radio.iio", "leo.catalog", "leo.qualification")


def resolve(root, name):
    path = root.joinpath(*name.split("."))
    for variant in (path / "__init__.py", path.with_suffix(".py")):
        if variant.is_file():
            return variant
    return None


def closure(root):
    pending = list(SEEDS)
    included = {}
    while pending:
        name = pending.pop()
        if any(name == prefix or name.startswith(prefix + ".") for prefix in OUT_OF_SCOPE):
            continue
        asset = resolve(root, name)
        if asset is None or name in included:
            continue
        included[name] = asset
        package = name if asset.name == "__init__.py" else name.rpartition(".")[0]
        if "." in name:
            pending.append(name.rpartition(".")[0])
        for node in ast.walk(ast.parse(asset.read_bytes())):
            if isinstance(node, ast.Import):
                pending.extend(
                    alias.name for alias in node.names if alias.name.split(".")[0] == "leo"
                )
            elif isinstance(node, ast.ImportFrom):
                module = (
                    importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                    if node.level
                    else node.module
                )
                if module and module.split(".")[0] == "leo":
                    pending.extend([module, *(module + "." + alias.name for alias in node.names)])
    return sorted(set(included.values()))


def definitions(module, names):
    path = Path(module.__file__)
    source = path.read_text()
    nodes = {
        node.name: ast.get_source_segment(source, node)
        for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }
    return "\n\n".join(nodes[name] for name in names)


def bridge():
    stream = definitions(recording_to_v5, ("stream_range",))
    original = (
        'if manifest.name != "manifest.json" or not manifest.is_relative_to(\n'
        '                (BULK / "leo/fast-scan-recordings").resolve()\n'
        "            ):"
    )
    if stream.count(original) != 1:
        raise ValueError("the archived replay reader's confinement port changed")
    stream = stream.replace(original, 'if manifest.name != "manifest.json":')
    # The caller path is pinned by the external manifest and checked again by
    # the original FastSegmentSource. Historical benchmark globals are omitted.
    source = [
        """from hashlib import sha256, file_digest
from pathlib import Path
from types import SimpleNamespace
import json, os, stat, sys, tempfile, time

BULK = Path("/")
BLOCK = 128 * 1024
DETECTORS = ("ordinary",)
""",
        f"MARGIN_GATE = {full_v5_check.MARGIN_GATE!r}",
        definitions(capture_release, ("inventory_digest",)),
        """def producer(_case, capture):
    return SimpleNamespace(root=Path(__file__).resolve().parent,
                           input_manifest_sha256=capture["input_manifest_sha256"])

def _bind_producer(_case, producer, _policy):
    # The standalone entry authenticates all source and library leaves itself.
    if producer.root != Path(__file__).resolve().parent:
        raise ValueError("capture reader is outside the verified bundle")

def _sha(path):
    with Path(path).open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()

capture_release = SimpleNamespace(producer=producer, inventory_digest=inventory_digest)
""",
        definitions(full_v5_check, ("factor_candidate", "_from_native", "_probe")),
        definitions(bounded, ("AuthenticatedMember",)),
        definitions(recording_to_v5, ("encoded", "digest", "native_document", "save")),
        stream,
    ]
    return "\n\n".join(source) + "\n"


def build(out, detector, source):
    files = closure(source)
    if out.exists() or out.is_relative_to("/mnt/qnap01"):
        raise ValueError("choose a new writable package directory")
    library = whole_iq.checked(detector, STOCK)
    out.mkdir(parents=True, exist_ok=False)
    for path in files:
        dest = out / "capture" / path.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    (out / "capture/native_bridge.py").write_text(bridge())
    shutil.copyfile(portable_receiver.__file__, out / "receive.py")
    shutil.copyfile(library, out / "stock-wide.so")
    receiver = cavity_runtime.install(out / "position", profile="phase-release")
    manifest = receiver / "native/manifest.json"
    template = whole_iq.read(manifest)
    for name in ("binary", "source", "wrapper"):
        template[name] = str(Path(template[name]).relative_to(receiver))
    template["provider"]["path"] = "SciPy provider resolved at runtime"
    template.pop("command", None)
    save_json(manifest, template)
    pins = {
        str(p.relative_to(out)): _sha(p)
        for p in sorted(out.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }
    sources = (capture_release, full_v5_check, recording_to_v5, bounded, cavity_runtime)
    save_json(
        out / "files.json",
        dict(
            schema="leo-portable-receiver/v1",
            files=pins,
            capture_sources=len(files),
            adapted_sources={
                str(Path(x.__file__).relative_to(ROOT)): _sha(Path(x.__file__)) for x in sources
            },
        ),
    )
    return pins


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, required=True)
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=ROOT / "src")
    args = parser.parse_args()
    print(len(build(args.out, args.stock, args.source)), "authenticated application files")
