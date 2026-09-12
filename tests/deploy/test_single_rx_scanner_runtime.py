"""The shipped single-RX provider is bound to exact reviewed build bytes."""

import json
import runpy
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_single_rx_scanner_runtime_provenance_is_exact(tmp_path):
    checks = runpy.run_path(str(ROOT / "deploy/scripts/validate-published-release"))
    destination = tmp_path / "runtime/scanner-iiod"
    destination.mkdir(parents=True)
    for name in ("iiod", "provenance.json"):
        shutil.copyfile(ROOT / "runtime/scanner-iiod" / name, destination / name)
    (destination / "iiod").chmod(0o550)
    provenance = destination / "provenance.json"
    provenance.chmod(0o440)
    checks["validate_scanner_iiod_provenance"](tmp_path)
    assert b"iio,buffer-persistent-hop-single-rx-10m" in (destination / "iiod").read_bytes()
    document = json.loads(provenance.read_text())
    assert document["source"]["head"] == "26310f8a5079f9eb6ed25e3000e018da33550b9b"
    document["artifact"]["sha256"] = "0" * 64
    provenance.chmod(0o640)
    provenance.write_text(json.dumps(document))
    provenance.chmod(0o440)
    with pytest.raises(ValueError, match="reviewed artifact"):
        checks["validate_scanner_iiod_provenance"](tmp_path)
