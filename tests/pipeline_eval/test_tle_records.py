from pathlib import Path
from hashlib import sha256
import json
import subprocess
import sysconfig
from types import SimpleNamespace

import pytest
from sgp4 import exporter

from leo.sky import propagation
from tests.operations.test_causal_tle_catalogue import at_day
from tools.pipeline_eval.variants.experimental import tle_records
from tools.pipeline_eval.qualification import freeze_publication, experimental_publication


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    output = tmp_path_factory.mktemp("tle") / "_leo_tle_records.so"
    subprocess.run(["cc", "-shared", "-fPIC", "-O2", "-I" + sysconfig.get_path("include"),
                    str(Path(tle_records.__file__).with_suffix(".c")), "-o", str(output)], check=True)
    return output


@pytest.mark.parametrize("endings", ["\n", "\r\n"])
def test_exact_canonical_records(library, endings):
    text = (at_day(232) + at_day(234)).replace("\n", endings).rstrip("\r\n")
    expected = propagation.parse_element_set_records(text)
    with tle_records.batch_records(library) as counts:
        assert propagation.parse_element_set_records(text) == expected
    assert counts == {"catalogues": 1, "records": 2, "fallback": 0}


@pytest.mark.parametrize("prefix", ["A", "J", "P", "Z"])
def test_canonical_alpha5_matches_reference(library, prefix):
    name, *lines = at_day(232).replace("44714", prefix + "0001").splitlines()
    text = "\n".join([name, *(line[:68] + str(propagation.element_line_checksum(line)) for line in lines)])
    expected = propagation.parse_element_set_records(text)
    with tle_records.batch_records(library) as counts:
        assert propagation.parse_element_set_records(text) == expected
    assert counts["records"] == 1


def test_checksum_export_preserves_all_lines_and_restores_exporter(library):
    catalogue = propagation.parse_element_sets(at_day(232) + at_day(234))
    original = exporter.compute_checksum
    expected = [exporter.export_tle(item) for item in catalogue.satellites]
    with tle_records.batch_records(library):
        assert exporter.compute_checksum is propagation.element_line_checksum
        assert [exporter.export_tle(item) for item in catalogue.satellites] == expected
        for text in ("", "-0+987.3", "0" * 68 + "99--", "\u00e9\u0661-7"):
            assert exporter.compute_checksum(text) == original(text)
    assert exporter.compute_checksum is original


@pytest.mark.parametrize("text", [
    at_day(234).replace("0 ", "", 1), at_day(234).replace("STARLINK", "étoile"),
    at_day(234).replace("1008", "1008   "), "\n" + at_day(232),
    "\n".join(at_day(232).splitlines()[1:]),
])
def test_other_valid_formats_use_original_reader(library, text):
    expected = propagation.parse_element_set_records(text)
    with tle_records.batch_records(library) as counts:
        assert propagation.parse_element_set_records(text) == expected
    assert counts["fallback"] == 1


@pytest.mark.parametrize("text", ["", at_day(232)[:-7], at_day(232).replace("44714U", "44713U"),
                                  at_day(232).replace("53.0537", "53.0538")])
def test_errors_match_including_after_a_good_record(library, text):
    sample = (at_day(231) + text) if text else text
    with pytest.raises(propagation.ElementSetError) as expected:
        propagation.parse_element_set_records(sample)
    with tle_records.batch_records(library), pytest.raises(propagation.ElementSetError) as actual:
        propagation.parse_element_set_records(sample)
    assert str(actual.value) == str(expected.value)


def test_frozen_parser_checks_and_uses_reviewed_library(library, tmp_path, monkeypatch):
    from tools import algo08_scan

    checkout = Path(tle_records.__file__).resolve().parents[4]
    release = tmp_path / "release"
    (release / "tools").mkdir(parents=True)
    detector = tmp_path / "receiver.so"
    detector.write_bytes(b"fixture")
    args = checkout, tmp_path / "bundle", detector, sha256(detector.read_bytes()).hexdigest(), "stock", "stock", release
    with pytest.raises(ValueError, match="tle_parser library differs"):
        freeze_publication.freeze(*args, tle_parser=(library, "0" * 64))
    spec = freeze_publication.freeze(*args, tle_parser=(library, sha256(library.read_bytes()).hexdigest()))
    for name in ("tle_records.c", "tle_records.py", "_leo_tle_records.so"):
        assert any(Path(path).name == name for path in spec["sources"])

    def analyze(*_args):
        assert len(propagation.parse_element_set_records(at_day(232))) == 1
        return {"decision": "withheld"}

    monkeypatch.setattr(algo08_scan, "analyze", analyze)
    output = tmp_path / "output"
    output.mkdir()
    offer = tmp_path / "offer.json"
    offer.write_text(json.dumps(dict(center=[-22., 110.], width_km=20)))
    options = SimpleNamespace(bulk_root=output, recording=tmp_path / "capture", archive=tmp_path, region=offer)
    base = propagation.parse_element_set_records
    assert experimental_publication.run(options, spec)["tle_records"] == {"catalogues": 1, "records": 1, "fallback": 0}
    assert propagation.parse_element_set_records is base
    Path(spec["tle_parser"]["library"]).write_bytes(b"different")
    with pytest.raises(ValueError, match="tle_parser library differs"):
        experimental_publication.run(options, spec)
