import copy
import json

import pytest
from pydantic import ValidationError

from leo.contracts.scanner_glrt_publication import ScannerGlrtPublicationV1
from leo.scanner.glrt_publication import validate_glrt_capture_binding
from tests.scanner.glrt_publication_fixtures import make_capture, make_publication


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_publication_preserves_uint64_fraction_and_independent_completion(tmp_path, rate):
    _, capture = make_capture(tmp_path, rate=rate)
    publication = make_publication(capture)
    validate_glrt_capture_binding(
        publication, capture.manifest.receipt, input_manifest_sha256=capture.manifest_sha256
    )
    raw = publication.model_dump_json()
    assert ScannerGlrtPublicationV1.model_validate_json(raw) == publication
    row = json.loads(raw)["evidence"]["results"][0]
    assert row["valid_start"] == str(publication.evidence.results[0].valid_start)
    assert int(row["valid_start"]) > 2**53
    assert row["fractional_offset_samples"] == 0.375
    assert (
        publication.evidence.delivery_complete and not publication.evidence.classification_complete
    )


@pytest.mark.parametrize(
    "change", ["session", "manifest", "wire_session", "interval", "edge", "inventory", "visit"]
)
def test_binding_rejects_another_capture_or_source_geometry(tmp_path, change):
    _, capture = make_capture(tmp_path)
    document = make_publication(capture).model_dump()
    if change == "session":
        document["session_id"] = "another-session"
    elif change == "manifest":
        document["input_manifest_sha256"] = "sha256:" + "c" * 64
    elif change == "wire_session":
        document["evidence"]["session"] += 1
    elif change == "inventory":
        document["evidence"].update(expected_results=2, delivery_complete=False)
    elif change == "visit":
        document["evidence"]["results"][0]["visit"] = 1
        document["evidence"]["delivery_complete"] = False
    elif change == "interval":
        for field in (
            "valid_start",
            "valid_end",
            "search_start",
            "search_end",
            "confirmation_start",
            "confirmation_end",
            "epoch_sample_counter",
        ):
            document["evidence"]["results"][0][field] += 1
    else:
        document["evidence"]["results"][0]["edge"] = "upper"
    publication = ScannerGlrtPublicationV1.model_validate(document)
    with pytest.raises(ValueError):
        validate_glrt_capture_binding(
            publication, capture.manifest.receipt, input_manifest_sha256=capture.manifest_sha256
        )


def test_invalid_or_unqualified_evidence_cannot_become_a_positive(tmp_path):
    _, capture = make_capture(tmp_path)
    source = make_publication(capture).model_dump()
    changes = (
        {"evidence": None},
        {"algorithm_sha256": "c" * 64},
        {"algorithm_sha256": "0" * 64},
        {"unexpected": True},
    )
    for change in changes:
        with pytest.raises(ValidationError):
            ScannerGlrtPublicationV1.model_validate(source | change)
    document = copy.deepcopy(source)
    document["evidence"]["results"][0].update(verdict="starlink", reason="complete")
    with pytest.raises(ValidationError):
        ScannerGlrtPublicationV1.model_validate(document)
    failed = ScannerGlrtPublicationV1.model_validate(
        source | {"evidence": None, "error": "no peer"}
    )
    assert failed.evidence is None and failed.error == "no peer"


@pytest.mark.parametrize("verdict", ["starlink", "no_signal"])
def test_positive_profile_is_checked_before_publication_or_presentation(tmp_path, verdict):
    _, capture = make_capture(tmp_path)
    document = make_publication(capture).model_dump()
    document["evidence"].update(mode="positive-only-v1", classification_complete=True)
    document["evidence"]["results"][0].update(verdict=verdict, reason="complete")
    # The existing extensible persisted contract is not changed. Its new
    # application profile is checked separately at the capture binding boundary.
    publication = ScannerGlrtPublicationV1.model_validate(document)
    if verdict == "no_signal":
        with pytest.raises(ValueError, match="cannot assert signal absence"):
            validate_glrt_capture_binding(
                publication, capture.manifest.receipt, input_manifest_sha256=capture.manifest_sha256
            )
    else:
        validate_glrt_capture_binding(
            publication, capture.manifest.receipt, input_manifest_sha256=capture.manifest_sha256
        )
