import hashlib

import pytest

from tools.pipeline_eval.qualification import freeze_publication as bundle
from tools.pipeline_eval.qualification.paired_publication import verify_sources


def test_freeze_copies_release_and_only_selected_research_modules(tmp_path):
    release, checkout, output = [tmp_path / name for name in ("release", "checkout", "output")]
    (release / "tools").mkdir(parents=True)
    (release / "tools/deployed.py").write_text("production")
    selected = [bundle.ENTRY, bundle.LAUNCHER, bundle.VARIANTS / "experimental/receiver_ingress.py"]
    for path in selected:
        (checkout / path).parent.mkdir(parents=True, exist_ok=True)
        (checkout / path).write_text(str(path))
    binary = tmp_path / "detector.so"
    binary.write_bytes(b"reviewed")
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="reviewed build"):
        bundle.freeze(checkout, output, binary, "wrong", "stock", "compressed-buffer", release)
    assert not output.exists()
    spec = bundle.freeze(checkout, output, binary, digest, "stock", "compressed-buffer", release)
    (checkout / bundle.ENTRY).write_text("edited after freeze")
    verify_sources(output / bundle.LAUNCHER, spec["sources"])
    assert (output / "receiver.so").read_bytes() == b"reviewed"
    assert (output / "tools/deployed.py").read_text() == "production"
    assert set(spec["sources"]) == {str(p) for p in selected}
    with pytest.raises(FileExistsError):
        bundle.freeze(checkout, output, binary, digest, "stock", "compressed-buffer", release)
