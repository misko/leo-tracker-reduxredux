from pathlib import Path

import pytest

from tools.pipeline_eval import wide_runtime as runtime
from tools.pipeline_eval.variants import wide_kernel


def test_capsule_extracts_the_canonical_leaf_and_measured_adjacent_overlay(tmp_path):
    capsule = tmp_path / "capsule"
    manifest = runtime.unpack(runtime.CAPSULE, capsule)

    leaf = capsule / "source" / runtime.LEAF
    assert runtime.sha256(leaf) == manifest["stock"]["patched_presence_sha256"]
    assert (capsule / "source/SOURCE_LICENSE.md").is_file()
    assert (capsule / "source/kernel/provenance.json").is_file()
    assert (capsule / "overlay/wide_kernel_fractional.h").read_bytes() == (
        wide_kernel.HEADER.read_bytes()
    )

    adjacent = tmp_path / "adjacent.c"
    adjacent.write_text(wide_kernel.overlay(leaf.read_text()))
    assert runtime.sha256(adjacent) == manifest["adjacent"]["patched_presence_sha256"]


def test_modified_capsule_is_rejected_before_extracting_any_member(tmp_path):
    original = runtime.CAPSULE.read_bytes()
    corrupt = tmp_path / "capsule.zip"
    corrupt.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    target = tmp_path / "unpacked"
    with pytest.raises(ValueError, match="source capsule SHA-256"):
        runtime.unpack(corrupt, target)
    assert not target.exists()


@pytest.mark.parametrize("libdir", ("lib/x86_64-linux-gnu", "lib", "lib64"))
def test_fftw_prefix_resolves_distribution_and_local_layouts(tmp_path, monkeypatch, libdir):
    monkeypatch.setattr(
        runtime.subprocess, "check_output", lambda *args, **kw: "x86_64-linux-gnu\n"
    )
    paths = tuple(
        tmp_path / name
        for name in ("include/fftw3.h", f"{libdir}/libfftw3f.a", f"{libdir}/libfftw3.so")
    )
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    assert runtime.dependency_paths(tmp_path, "/usr/bin/gcc") == paths
    paths[-1].unlink()
    with pytest.raises(ValueError, match="FFTW development files missing"):
        runtime.dependency_paths(tmp_path, "/usr/bin/gcc")


def test_builder_guards_existing_and_read_only_output_paths(tmp_path):
    for output in (tmp_path, Path("/mnt/qnap01/wide-runtime-test-do-not-create")):
        with pytest.raises(ValueError, match="new output directory on local storage"):
            runtime.build(output, Path("/usr"))
