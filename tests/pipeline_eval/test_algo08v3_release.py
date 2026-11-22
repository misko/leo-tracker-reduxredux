from hashlib import sha256
import json
from pathlib import Path
import runpy

import pytest


RUN = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/run"


def test_release_relocates_only_digest_bound_libraries_and_rejects_edits(tmp_path):
    launcher = runpy.run_path(str(RUN))
    libs = launcher["LIBRARIES"]
    pins = {}
    spec = dict(sources=pins, schedule="all", curved_design=True)
    for name in (*libs, "detector"):
        path = tmp_path / (name + ".so")
        path.write_bytes(name.encode())
        digest = sha256(path.read_bytes()).hexdigest()
        pins[path.name] = digest
        frozen_path = "/original/build/" + path.name
        if name == "detector":
            spec.update(detector=frozen_path, detector_sha256=digest)
        else:
            spec[name] = dict(library=frozen_path, sha256=digest)
    (tmp_path / "spec.json").write_text(json.dumps(spec))
    fingerprint = sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    relocated = launcher["checked_spec"](tmp_path, fingerprint)
    assert relocated["detector"] == str(tmp_path / "detector.so")
    assert all(relocated[k]["library"] == str(tmp_path / (k + ".so")) for k in libs)
    assert relocated["sources"] == pins and relocated["curved_design"] and relocated["schedule"] == "all"
    with pytest.raises(ValueError, match="specification changed"):
        launcher["checked_spec"](tmp_path, "0" * 64)
    (tmp_path / "detector.so").write_bytes(b"changed")
    with pytest.raises(ValueError, match="file changed"):
        launcher["checked_spec"](tmp_path, fingerprint)


def test_release_help_and_version_do_not_require_a_gauss_installation(capsys):
    launcher = runpy.run_path(str(RUN))
    for flags, expected in ((["--help"], "--region"), (["--version"], "ALGO08v3 sha256:6cdbac")):
        with pytest.raises(SystemExit) as stopped:
            launcher["main"](flags)
        assert stopped.value.code == 0 and expected in " ".join(capsys.readouterr().out.split())
