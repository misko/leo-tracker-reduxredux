import hashlib
import os
import runpy
import shutil
from pathlib import Path

import pytest

from tests.deploy.test_release_metadata import _published, _validate

ROOT = Path(__file__).resolve().parents[2]
POLICY = runpy.run_path(str(ROOT / "deploy/scripts/validate-host-decision-bundle"))


def bundle(release):
    target = release / "runtime/scanner-host-decision"
    shutil.copytree(ROOT / "runtime/scanner-host-decision", target)
    target.chmod(0o750)
    for path in target.iterdir():
        path.chmod(0o440)
    return target


def test_host_detector_inventory_is_sealed_into_release_metadata(tmp_path):
    release, metadata = _published(tmp_path)
    bundle(release)
    paths = POLICY["inventory"](release, expected_uid=os.getuid(), expected_gid=os.getgid())
    assert len(paths) == 4
    with pytest.raises(ValueError, match="cardinality"):
        _validate(release, metadata)
    metadata.chmod(0o640)
    with metadata.open("a") as stream:
        for path in paths:
            stream.write(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path}\n")
    metadata.chmod(0o440)
    _validate(release, metadata)


@pytest.mark.parametrize("fault", ["manifest", "binary", "mode", "extra", "symlink"])
def test_host_detector_rejects_changed_packaged_files(tmp_path, fault):
    target = bundle(tmp_path)
    if fault in ("manifest", "binary"):
        path = target / ("manifest.json" if fault == "manifest" else "decision.so")
        path.chmod(0o640)
        path.write_bytes(b"changed")
        path.chmod(0o440)
    elif fault == "mode":
        (target / "decision.so").chmod(0o660)
    elif fault == "extra":
        (target / "unexpected").write_text("extra")
    else:
        path = target / "decision.so"
        path.unlink()
        path.symlink_to(ROOT / "runtime/scanner-host-decision/decision.so")
    with pytest.raises(ValueError):
        POLICY["inventory"](tmp_path, expected_uid=os.getuid(), expected_gid=os.getgid())
