import hashlib
from pathlib import Path

import pytest

from tools.pipeline_eval.qualification import freeze_publication as bundle
from tools.pipeline_eval.qualification.paired_publication import verify_sources
from tools.pipeline_eval.variants.experimental import residual_receiver


@pytest.mark.parametrize(("solver", "rendering", "schedule"), [
    ("stock", "individual", "all"), ("combined-shared-discovery", "shared-orbits", "all"),
    ("shared-tables", "shared-pixels", "all"), ("track-moments", "shared-pixels", "all"),
    ("track-moments", "shared-pixels", "deferred"),
    ("shared-tables", "raster-layout", "deferred"), ("stock", "raster-layout", "all")])
def test_freeze_copies_release_and_only_selected_research_modules(tmp_path, solver, rendering, schedule):
    release, checkout, output = [tmp_path / name for name in ("release", "checkout", "output")]
    (release / "tools").mkdir(parents=True)
    (release / "tools/deployed.py").write_text("production")
    selected = [bundle.ENTRY, bundle.LAUNCHER, bundle.VARIANTS / "experimental/receiver_ingress.py"]
    if solver != "stock":
        selected.extend(bundle.VARIANTS / name for name in (
            "algo08_causal_reuse.py", "algo08_salvage_statistics.py", "algo08_dense_discovery.py",
        ))
    if rendering != "individual":
        selected.append(bundle.VARIANTS / "experimental/shared_orbit_figures.py")
    if rendering == "raster-layout":
        selected.append(bundle.VARIANTS / "experimental/raster_layout.py")
    if solver in ("shared-tables", "track-moments"):
        selected.extend(bundle.VARIANTS / name for name in (
            "algo08_causal_table.py", "algo08_cavity_projection.py", "algo08_salvage_bound.py"))
    if solver == "track-moments":
        selected.append(bundle.VARIANTS / "algo08_track_moments.py")
    if schedule == "deferred":
        selected.extend(bundle.VARIANTS / "experimental" / name for name in
                        ("deferred_continuation.py", "deferred_receiver.py"))
        selected.append(bundle.VARIANTS / "experimental/lean_startup.py")
    startup = "lazy-exports" if schedule == "deferred" else "stock"
    for path in selected:
        (checkout / path).parent.mkdir(parents=True, exist_ok=True)
        (checkout / path).write_text(str(path))
    binary = tmp_path / "detector.so"
    binary.write_bytes(b"reviewed")
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="reviewed build"):
        bundle.freeze(checkout, output, binary, "wrong", "stock", "compressed-buffer", release)
    assert not output.exists()
    with pytest.raises(ValueError, match="publication renderer"):
        bundle.freeze(checkout, output, binary, digest, solver, "compressed-buffer", release,
                      rendering="unknown")
    assert not output.exists()
    spec = bundle.freeze(checkout, output, binary, digest, solver, "compressed-buffer", release,
                         rendering=rendering, schedule=schedule, startup=startup)
    assert spec.get("rendering", "individual") == rendering
    assert spec.get("startup", "stock") == startup
    assert "endpoint_reuse" not in spec
    assert "defer_preparation_gc" not in spec
    (checkout / bundle.ENTRY).write_text("edited after freeze")
    verify_sources(output / bundle.LAUNCHER, spec["sources"])
    assert (output / "receiver.so").read_bytes() == b"reviewed"
    assert (output / "tools/deployed.py").read_text() == "production"
    assert set(spec["sources"]) == {str(p) for p in selected}
    with pytest.raises(FileExistsError):
        bundle.freeze(checkout, output, binary, digest, "stock", "compressed-buffer", release)


@pytest.mark.parametrize("endpoint_reuse", [False, True])
def test_paired_ingress_freezer_pins_its_sources_and_binary(tmp_path, endpoint_reuse):
    release, checkout, output = [tmp_path / name for name in ("release", "checkout", "output")]
    (release / "tools").mkdir(parents=True)
    selected = [bundle.ENTRY, bundle.LAUNCHER]
    selected.extend(bundle.VARIANTS / "experimental" / name for name in
                    ("receiver_ingress.py", "paired_sha256.py", "paired_sha256.c"))
    solver = "shared-tables" if endpoint_reuse else "stock"
    if endpoint_reuse:
        selected.extend(bundle.VARIANTS / name for name in (
            "algo08_causal_reuse.py", "algo08_salvage_statistics.py",
            "algo08_dense_discovery.py", "algo08_causal_table.py", "algo08_cavity_projection.py",
            "algo08_salvage_bound.py", "algo08_endpoint_readout.py", "algo08_recovery_reuse.py",
        ))
        selected.append(bundle.VARIANTS / "experimental/preparation_gc.py")
    for path in selected:
        (checkout / path).parent.mkdir(parents=True, exist_ok=True)
        (checkout / path).write_text(str(path))
    detector, library = tmp_path / "detector.so", tmp_path / "library.so"
    detector.write_bytes(b"reviewed detector")
    library.write_bytes(b"reviewed library")
    detector_digest = hashlib.sha256(detector.read_bytes()).hexdigest()
    library_digest = hashlib.sha256(library.read_bytes()).hexdigest()

    args = (checkout, output, detector, detector_digest, solver, "paired-sha256", release)
    with pytest.raises(ValueError, match="library pin"):
        bundle.freeze(*args)
    with pytest.raises(ValueError, match="library differs"):
        bundle.freeze(*args, paired_sha256=(library, "0" * 64))
    assert not output.exists()
    spec = bundle.freeze(*args, paired_sha256=(library, library_digest), endpoint_reuse=endpoint_reuse,
                         recovery_reuse=endpoint_reuse, defer_preparation_gc=endpoint_reuse)
    assert spec["ingress"] == "paired-sha256"
    assert spec.get("endpoint_reuse", False) == endpoint_reuse
    assert spec.get("recovery_reuse", False) == endpoint_reuse
    assert spec.get("defer_preparation_gc", False) == endpoint_reuse
    copied = output / "paired-sha256.so"
    assert spec["paired_sha256"] == dict(library=str(copied), sha256=library_digest)
    assert set(spec["sources"]) == {str(path) for path in selected} | {copied.name}
    verify_sources(output / bundle.LAUNCHER, spec["sources"])
    copied.write_bytes(b"substituted")
    with pytest.raises(ValueError, match="source changed"):
        verify_sources(output / bundle.LAUNCHER, spec["sources"])


def test_freeze_conditional_residual_pins_the_reviewed_pair_of_native_entries_and_rule(
    tmp_path, monkeypatch,
):
    release, checkout, output = [tmp_path / name for name in ("release", "checkout", "output")]
    (release / "tools").mkdir(parents=True)
    rule = bundle.VARIANTS / "experimental/residual_schedule.py"
    adapter = bundle.VARIANTS / "experimental/residual_receiver.py"
    for source in (bundle.ENTRY, bundle.LAUNCHER, rule, adapter):
        (checkout / source).parent.mkdir(parents=True, exist_ok=True)
        (checkout / source).write_text(str(source))
    binary = tmp_path / "detector.so"
    binary.write_bytes(b"reviewed native full and primary API")
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    args = (checkout, output, binary, digest, "stock", "stock", release)
    with pytest.raises(ValueError, match="reviewed exact fractional"):
        bundle.freeze(*args, schedule="conditional-residual")
    monkeypatch.setattr(residual_receiver, "DETECTOR_SHA256", digest)
    with pytest.raises(ValueError, match="frozen residual schedule changed"):
        bundle.freeze(*args, schedule="conditional-residual")
    assert not output.exists()

    (checkout / rule).write_bytes(Path(residual_receiver.residual_schedule.__file__).read_bytes())
    spec = bundle.freeze(*args, schedule="conditional-residual")
    assert spec["schedule"] == "conditional-residual"
    assert spec["sources"]["receiver.so"] == digest
    assert spec["sources"][str(rule)] == residual_receiver.SCHEDULE_SHA256
    assert set(spec["sources"]) == {str(bundle.ENTRY), str(bundle.LAUNCHER), str(rule),
                                    str(adapter), "receiver.so"}
    verify_sources(output / bundle.LAUNCHER, spec["sources"])
    (output / "receiver.so").write_bytes(b"changed after freezing")
    with pytest.raises(ValueError, match="source changed"):
        verify_sources(output / bundle.LAUNCHER, spec["sources"])
