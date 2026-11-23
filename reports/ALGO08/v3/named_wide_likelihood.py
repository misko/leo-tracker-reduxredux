"""Bind the reviewed wider private likelihood to the named inference port."""

import argparse
from collections import Counter
from contextlib import contextmanager
from functools import wraps
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch


SOURCES = Path(__file__).resolve().parents[3] / "tools/pipeline_eval/variants"
IMPLEMENTATION = (Path(__file__), SOURCES / "algo08_private_width.py", SOURCES / "algo08_private_width.h")


def load_overlay():
    # The named payload does not ship the separate research compiler overlay.
    spec = importlib.util.spec_from_file_location("named_private_width", IMPLEMENTATION[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def checked_library(path, expected, overlay):
    binary = path.read_bytes()
    manifest = json.loads(path.with_name("manifest.json").read_bytes())
    binary_hash = sha256(binary).hexdigest()
    source_hash = sha256(overlay.expanded_source().encode()).hexdigest()
    if (expected != "sha256:" + binary_hash or manifest.get("binary_sha256") != binary_hash
            or manifest.get("parent_source_sha256") != overlay.SOURCE_SHA256
            or manifest.get("source_sha256") != source_hash):
        raise ValueError("Wider likelihood artifact, operator digest or source record differs")
    return binary, manifest


@contextmanager
def inference_scope(core, native_bound, widened, audit):
    original, stock_call = core.infer, native_bound.__call__
    totals = Counter()
    audit.update(inferences=0, stock_selected_packets=0)

    @wraps(original)
    def infer(*args, **kwargs):
        selected = kwargs.get("selected_evidence")
        if selected is not None:
            @wraps(selected)
            def assemble(*values, **options):
                audit["stock_selected_packets"] += 1
                with patch.object(native_bound, "__call__", stock_call):
                    return selected(*values, **options)

            kwargs["selected_evidence"] = assemble
        audit["inferences"] += 1
        with widened() as counts:
            try:
                return original(*args, **kwargs)
            finally:
                totals.update(counts)

    with patch.object(core, "infer", infer):
        try:
            yield
        finally:
            audit["counts"] = dict(totals)
            audit["attempts"] = totals["calls"]
            audit["activations"] = totals["activated"]


@contextmanager
def binding(path, expected, output, audit):
    from empty_bootstrap import clock, now
    from leo.analysis.localization_v4.native_bound import NativeBound
    from tools.pipeline_eval.variants import v5_core

    start = now()
    overlay = load_overlay()
    binary, manifest = checked_library(path, expected, overlay)
    with TemporaryDirectory(prefix=".wide-private-", dir=output) as isolated:
        directory = Path(isolated)
        private = directory / "private_width.so"
        private.write_bytes(binary)
        (directory / "manifest.json").write_text(json.dumps(manifest, allow_nan=False))
        audit.update(library_sha256=expected, source_sha256="sha256:" + manifest["source_sha256"],
                     parent_source_sha256="sha256:" + manifest["parent_source_sha256"], verification_and_copy=clock(start))
        with inference_scope(v5_core, NativeBound, lambda: overlay.expand_unsupported_layout(private), audit):
            yield


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from empty_bootstrap import load_runtime

    cli = argparse.ArgumentParser(description="Build the wider private likelihood and its source manifest")
    cli.add_argument("output", type=Path)
    options = cli.parse_args()
    load_runtime()
    print(load_overlay().build(options.output))
