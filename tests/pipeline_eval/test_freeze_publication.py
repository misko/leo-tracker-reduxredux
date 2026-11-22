import hashlib

import pytest

from tools.pipeline_eval.qualification import freeze_publication as bundle
from tools.pipeline_eval.qualification.paired_publication import verify_sources


@pytest.mark.parametrize(("solver", "rendering", "schedule"), [
    ("stock", "individual", "all"), ("combined-shared-discovery", "shared-orbits", "all"),
    ("shared-tables", "shared-pixels", "all"), ("track-moments", "shared-pixels", "all"),
    ("track-moments", "shared-pixels", "deferred")])
def test_freeze_copies_release_and_only_selected_research_modules(tmp_path, solver, rendering, schedule):
    release, checkout, output = [tmp_path / name for name in ("release", "checkout", "output")]
    (release / "tools").mkdir(parents=True)
    (release / "tools/deployed.py").write_text("production")
    selected = [bundle.ENTRY, bundle.LAUNCHER, bundle.VARIANTS / "experimental/receiver_ingress.py"]
    if solver != "stock":
        selected.extend(bundle.VARIANTS / name for name in (
            "algo08_causal_reuse.py", "algo08_salvage_statistics.py", "algo08_dense_discovery.py",
            "experimental/shared_orbit_figures.py"))
    if solver in ("shared-tables", "track-moments"):
        selected.extend(bundle.VARIANTS / name for name in (
            "algo08_causal_table.py", "algo08_cavity_projection.py", "algo08_salvage_bound.py"))
    if solver == "track-moments":
        selected.append(bundle.VARIANTS / "algo08_track_moments.py")
    if schedule == "deferred":
        selected.extend(bundle.VARIANTS / "experimental" / name for name in
                        ("deferred_continuation.py", "deferred_receiver.py"))
    for path in selected:
        (checkout / path).parent.mkdir(parents=True, exist_ok=True)
        (checkout / path).write_text(str(path))
    binary = tmp_path / "detector.so"
    binary.write_bytes(b"reviewed")
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="reviewed build"):
        bundle.freeze(checkout, output, binary, "wrong", "stock", "compressed-buffer", release)
    assert not output.exists()
    spec = bundle.freeze(checkout, output, binary, digest, solver, "compressed-buffer", release,
                         rendering=rendering, schedule=schedule)
    assert spec.get("rendering", "individual") == rendering
    (checkout / bundle.ENTRY).write_text("edited after freeze")
    verify_sources(output / bundle.LAUNCHER, spec["sources"])
    assert (output / "receiver.so").read_bytes() == b"reviewed"
    assert (output / "tools/deployed.py").read_text() == "production"
    assert set(spec["sources"]) == {str(p) for p in selected}
    with pytest.raises(FileExistsError):
        bundle.freeze(checkout, output, binary, digest, "stock", "compressed-buffer", release)
