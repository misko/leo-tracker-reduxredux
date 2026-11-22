from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from tools import algo08_scan
from tools.pipeline_eval.qualification import experimental_publication
from tools.pipeline_eval.variants.experimental import residual_receiver


def test_conditional_publications_have_two_reviewed_native_pins():
    for digest in (
        "1b4c43dc1f2edc64ead9c4b9c0f4d724f79f623e04a13f40812a1d4bb40345a5",
        "c34c55748bd9b5feac6f1736e27acb78b4a1caa97f0d13a50b604cffd61d2d70",
    ):
        residual_receiver.require_native_pin(digest)
    with pytest.raises(ValueError, match="reviewed native detector"):
        residual_receiver.require_native_pin("0" * 64)


@pytest.fixture
def q15_config(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    offer = tmp_path / "region.json"
    offer.write_text(json.dumps(dict(center=[12, 20], width_km=25)))
    args = SimpleNamespace(recording=tmp_path / "recording", archive=tmp_path / "tle",
                           region=offer, bulk_root=output)
    payload = b"reviewed Q15 native library"
    detector = tmp_path / "receiver.so"
    detector.write_bytes(payload)
    digest = sha256(payload).hexdigest()
    monkeypatch.setattr(residual_receiver, "Q15_DETECTOR_SHA256", digest)
    spec = dict(detector=str(detector), detector_sha256=digest, solver="stock",
                schedule="conditional-residual")
    return args, spec, detector


def test_launcher_passes_verified_q15_bytes_and_pin_to_conditional_acquisition(q15_config, monkeypatch):
    args, spec, detector = q15_config
    original_pins = dict(algo08_scan.PINS)

    def analyze(recording, root, assets, archive, offer):
        assert recording == args.recording and root == args.bulk_root and archive == args.archive
        assert offer.center == (12., 20.)
        private_binary = assets / "cancellation-factors.so"
        assert not private_binary.is_symlink()
        assert private_binary.read_bytes() == detector.read_bytes()
        assert algo08_scan.PINS["cancellation-factors.so"] == spec["detector_sha256"]
        assert isinstance(algo08_scan.detector.__self__, residual_receiver.ResidualReceiver)
        return {"decision": "complete"}

    monkeypatch.setattr(algo08_scan, "analyze", analyze)
    monkeypatch.setattr(residual_receiver.ResidualReceiver, "receipt", lambda self: {"factor_calls": 4})
    assert experimental_publication.run(args, spec) == {
        "decision": "complete", "conditional_residual": {"factor_calls": 4},
    }
    assert algo08_scan.PINS == original_pins


@pytest.mark.parametrize("payload", [b"tampered detector", b"reviewed legacy native library"])
def test_launcher_rejects_bytes_that_do_not_match_selected_q15_pin(q15_config, monkeypatch, payload):
    args, spec, detector = q15_config
    legacy = sha256(b"reviewed legacy native library").hexdigest()
    monkeypatch.setattr(residual_receiver, "DETECTOR_SHA256", legacy)
    detector.write_bytes(payload)
    monkeypatch.setattr(algo08_scan, "analyze", lambda *_: pytest.fail("loaded incorrect detector bytes"))

    with pytest.raises(ValueError, match="Conditional detector differs from its reviewed build"):
        experimental_publication.run(args, spec)
