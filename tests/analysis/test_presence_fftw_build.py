import json
from pathlib import Path

import pytest

from tools.native_presence import build_library
from tools.presence_fftw import fftw_identity, fftw_options
from tools.qualify_native_presence import digest


def test_fftw_dependency_is_explicit_and_radio_build_has_no_desktop_rpath(tmp_path):
    with pytest.raises(ValueError, match="FFTW prefix"):
        fftw_options(tmp_path)
    (tmp_path / "include").mkdir()
    (tmp_path / "lib").mkdir()
    header, library = tmp_path / "include/fftw3.h", tmp_path / "lib/libfftw3.so"
    header.write_text("test header")
    library.write_bytes(b"test dependency, never linked")
    desktop, radio = fftw_options(tmp_path), fftw_options(tmp_path, runtime_rpath=False)
    assert desktop["cflags"] == radio["cflags"]
    assert any("rpath" in value for value in desktop["ldflags"])
    assert not any("rpath" in value for value in radio["ldflags"])
    assert fftw_identity(radio)["dependency_sha256"] == {
        str(header): digest(header),
        str(library): digest(library),
    }


def test_build_receipt_records_dependencies(tmp_path):
    dependency = tmp_path / "dependency.txt"
    dependency.write_text("frozen dependency")
    output = build_library(tmp_path / "native.so", dependencies=(dependency,))
    receipt = json.loads(Path(str(output) + ".build.json").read_text())
    assert receipt["dependencies_sha256"] == {str(dependency): digest(dependency)}
