from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def transfer(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import india_saved_transfer

    return india_saved_transfer


def packet(case):
    return dict(schema_version=1, source=dict(session_id=case, qualified=True, probes=[{}] * 2400),
                clock_anchor={"sample_counter": 0}, delivery_clocks=[{}] * 1200,
                provenance={"detector_sha256": "wide-glrt"})


def test_legacy_packet_reports_absent_v3_authority_without_modifying_source(transfer):
    native = packet(transfer.CASE)
    result = transfer.check_contract(native)
    assert result["probe_rows"] == 2400
    assert result["delivery_clocks"] == 1200
    assert result["source_detector_sha256"] == "wide-glrt"
    expected = ["input_manifest_sha256", "analysis_manifest_sha256", "raw_recording_authority_digest"]
    assert result["missing_raw_publication_fields"] == expected
    assert all(key not in native["source"] for key in expected)


def test_broken_or_other_saved_packet_fails_waveform_eligibility(transfer):
    with pytest.raises(ValueError, match="packet contract"):
        transfer.check_contract(packet("another-session"))
    broken = packet(transfer.CASE)
    broken["delivery_clocks"].pop()
    with pytest.raises(ValueError, match="packet contract"):
        transfer.check_contract(broken)


def test_png_validation_decodes_rgba_and_pins_original_encoded_bytes(transfer, tmp_path):
    path = tmp_path / "position.png"
    with Image.new("RGBA", (3, 5), (32, 42, 52, 128)) as pixels:
        pixels.save(path)
        decoded = transfer.decode_figures(tmp_path, ("position",))["position"]
        assert decoded["size"] == (3, 5)
        assert decoded["rgba_sha256"] == transfer.digest(pixels.tobytes())
        assert decoded["sha256"] == transfer.digest(path.read_bytes())
        pixels.convert("RGB").save(path, format="BMP")
    with pytest.raises(ValueError, match="PNG bytes"):
        transfer.decode_figures(tmp_path, ("position",))
