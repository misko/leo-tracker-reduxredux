import importlib
import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval.qualification import recovery_reads_benchmark

SHARED = (
    "v5_composed_memory.py",
    "v5_track_projection.py",
    "v5_stream_recovery.py",
    "v5_tiled_salvage.py",
    "history_stream_prep.py",
    "prep_stream_sky.py",
    "v5_catalogue_memory.py",
    "v5_armijo_aligned_finish.py",
    "v5_armijo_finish.py",
    "v5_armijo_fit.py",
    "compact_finish.py",
    "orbit_projector.py",
    "orbit_projector.c",
    "v5_core.py",
    "v5_lean.py",
)
METHODS = {
    "v5_sparse_discovery": (),
    "v5_compact_memory_combined": ("v5_sparse_discovery.py", "v5_family_memory.py"),
    "v5_signed_context_memory": (
        "v5_compact_memory_combined.py",
        "v5_sparse_discovery.py",
        "v5_family_memory.py",
    ),
    "v5_nomination_memory": (
        "v5_signed_context_memory.py",
        "v5_compact_memory_combined.py",
        "v5_sparse_discovery.py",
        "v5_family_memory.py",
    ),
    "v5_recovery_cache_memory": (
        "v5_nomination_memory.py",
        "v5_signed_context_memory.py",
        "v5_compact_memory_combined.py",
        "v5_sparse_discovery.py",
        "v5_family_memory.py",
    ),
}


@pytest.mark.parametrize("variant,added", METHODS.items())
def test_memory_implementation_binds_every_executed_local_dependency(tmp_path, variant, added):
    variants = tmp_path / "variants"
    qualification = tmp_path / "qualification"
    variants.mkdir()
    qualification.mkdir()
    sources = [
        *(variants / name for name in (variant + ".py", *added, *SHARED)),
        qualification / "armijo_finish_phase_retry.py",
    ]
    for source in sources:
        source.write_bytes(source.name.encode())

    digest = cli.implementation_digest(variant, sources[0])
    assert digest == sha256(b"".join(source.read_bytes() for source in sources)).hexdigest()
    for source in sources:
        raw = source.read_bytes()
        source.write_bytes(raw + b" changed")
        assert cli.implementation_digest(variant, sources[0]) != digest
        source.write_bytes(raw)
    if not added:
        (variants / "v5_family_memory.py").write_bytes(b"unrelated family-only helper")
        assert cli.implementation_digest(variant, sources[0]) == digest


@pytest.mark.parametrize("variant", METHODS)
def test_memory_child_dispatches_to_the_standard_bound_worker(tmp_path, monkeypatch, variant):
    assert variant in cli.VARIANTS
    entry = importlib.import_module(cli.module_name(variant))
    request = tmp_path / "request.json"
    output = tmp_path / "output.json"
    case = {"id": "DS26-fixture", "native_path": None, "request_path": None}
    request.write_bytes(cli.encoded(case))

    def runner(received, directory):
        assert received == case and directory == tmp_path
        return dict(status="unavailable", reason="fixture", boundary=variant, metrics={})

    monkeypatch.setattr(entry, "run", runner)
    cli.child(variant, request, output, tmp_path)
    actual = json.loads(output.read_bytes())
    assert actual["result"]["boundary"] == variant
    assert actual["implementation_sha256"] == cli.implementation_digest(
        variant, Path(entry.__file__)
    )


def test_memory_registry_stays_importable_without_loading_the_corpus():
    command = (
        "import importlib, sys; "
        "from tools.pipeline_eval import __main__ as cli; "
        f"[importlib.import_module(cli.module_name(v)) for v in {tuple(METHODS)!r}]; "
        "assert 'tools.pipeline_eval.corpus' not in sys.modules; "
        "assert 'v5_family_memory' not in cli.VARIANTS"
    )
    subprocess.run([sys.executable, "-c", command], check=True, cwd=cli.ROOT)


def test_recovery_reads_fingerprints_qualified_worker_and_transitive_memory_sources(tmp_path):
    variants = tmp_path / "variants"
    qualification = tmp_path / "qualification"
    variants.mkdir()
    qualification.mkdir()
    qualification_names = (
        "recovery_reads_benchmark.py",
        "recovery_reads_worker.py",
        "nomination_memory_worker.py",
        "signed_context_memory_worker.py",
        "compact_memory_combined_worker.py",
        "composed_memory_worker.py",
        "working_memory_worker.py",
        "secant_end_to_end_worker.py",
        "armijo_finish_phase_retry.py",
    )
    variants_names = (
        "v5_recovery_reads.py",
        "v5_discovery_memory.py",
        "v5_secant_fit.py",
        "v5_recovery_cache_memory.py",
        *METHODS["v5_recovery_cache_memory"],
        *SHARED,
    )
    files = [
        *(qualification / name for name in qualification_names),
        *(variants / name for name in variants_names),
    ]
    for source in files:
        source.write_bytes(source.name.encode())
    sealed = cli.implementation_digest("v5_recovery_reads", files[0])
    for source in files:
        raw = source.read_bytes()
        source.write_bytes(raw + b" changed")
        assert cli.implementation_digest("v5_recovery_reads", files[0]) != sealed
        source.write_bytes(raw)


def test_recovery_reads_executes_the_sealed_full_worker(tmp_path, monkeypatch):
    from tools.pipeline_eval.variants import orbit_projector, v5_lean

    monkeypatch.setattr(orbit_projector, "compile_kernel", lambda path: path.touch())
    case = {"id": "fixture"}

    def runner(received, output, script, *, worker_args):
        assert received == case and output == tmp_path
        assert script.name == "recovery_reads_worker.py" and script.is_file()
        assert worker_args == (str(tmp_path / "orbit_projector.so"),)
        return dict(status="unavailable")

    monkeypatch.setattr(v5_lean, "run_bound_worker", runner)
    assert cli.module_name("v5_recovery_reads") == recovery_reads_benchmark.__name__
    assert recovery_reads_benchmark.run(case, tmp_path) == {"status": "unavailable"}
