import json

import pytest
from pydantic import ValidationError

from leo.contracts.blind_regional import (
    BlindAccountingV1,
    BlindRegionalDocumentV1,
    BlindRegionV1,
)
from leo.storage.blind_regional import NAMES, BlindRegionalStore

D = "sha256:" + "a" * 64


def document():
    return BlindRegionalDocumentV1(
        session_id="scan-one",
        input_manifest_sha256=D,
        analysis_manifest_sha256=D,
        configuration_sha256=D,
        region=BlindRegionV1(
            center_latitude_deg=39.7392,
            center_longitude_deg=-104.9903,
            width_km=9000,
            height_km=9000,
            grid_policy="50-km-v1",
            refinement_policy="nested-v1",
        ),
        causal_snapshots=(),
        accounting=BlindAccountingV1(
            saved_observation_count=0,
            eligible_observation_count=0,
            track_count=0,
            associated_track_count=0,
            excluded_count=0,
            recorded_exclusion_count=0,
        ),
        state="insufficient",
        reasons=("no eligible tracks",),
    )


def test_blind_store_round_trip_and_digest_verification(tmp_path):
    writer = BlindRegionalStore(tmp_path, read_only=False)
    images = {name: b"\x89PNG\r\n\x1a\n" + name.encode() for name in NAMES}
    writer.publish(document(), images)
    reader = BlindRegionalStore(tmp_path)
    assert reader.status("scan-one").state == "complete"
    assert reader.artifact("scan-one", "blind-position") == images["blind-position"]
    (tmp_path / "scanner-blind-regional-v1" / "scan-one" / "blind-position.png").write_bytes(b"bad")
    try:
        reader.artifact("scan-one", "blind-position")
    except ValueError as error:
        assert "digest" in str(error)
    else:
        raise AssertionError("corrupt PNG accepted")


def test_blind_store_absent_is_pending(tmp_path):
    assert BlindRegionalStore(tmp_path).status("scan-missing").state == "pending"


def test_blind_contract_rejects_site_provenance_and_nonfinite_diagnostics():
    payload = document().model_dump(mode="json")
    payload["known_position_used_for_inference"] = True
    with pytest.raises(ValidationError):
        BlindRegionalDocumentV1.model_validate(payload)

    payload = document().model_dump(mode="json")
    payload["diagnostics"] = {"objective": float("nan")}
    with pytest.raises(ValidationError, match="finite"):
        BlindRegionalDocumentV1.model_validate(payload)


def test_blind_store_rejects_corrupt_document_binding(tmp_path):
    store = BlindRegionalStore(tmp_path, read_only=False)
    images = {name: b"\x89PNG\r\n\x1a\n" + name.encode() for name in NAMES}
    store.publish(document(), images)
    path = tmp_path / "scanner-blind-regional-v1" / "scan-one" / "document.json"
    payload = json.loads(path.read_bytes())
    payload["reasons"] = ["tampered"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="document digest"):
        BlindRegionalStore(tmp_path).status("scan-one")


def test_blind_store_retries_after_interrupted_unsealed_publication(tmp_path):
    directory = tmp_path / "scanner-blind-regional-v1" / "scan-one"
    directory.mkdir(parents=True)
    (directory / "document.json").write_bytes(b"interrupted")
    (directory / ".blind-position.png.123.partial").write_bytes(b"partial")
    images = {name: b"\x89PNG\r\n\x1a\n" + name.encode() for name in NAMES}

    store = BlindRegionalStore(tmp_path, read_only=False)
    with store.writer("scan-one"):
        manifest = store.publish(document(), images)

    assert manifest.document.session_id == "scan-one"
    assert BlindRegionalStore(tmp_path).status("scan-one").state == "complete"
    assert (directory / ".blind-position.png.123.partial").read_bytes() == b"partial"
