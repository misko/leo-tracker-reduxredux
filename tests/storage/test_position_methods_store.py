import pytest

from leo.contracts.digests import canonical_digest
from leo.contracts.position_methods import (
    POSITION_METHODS,
    PositionMethodResultV1,
    PositionMethodsDocumentV1,
    PositionMethodSourceV1,
    ReferencePositionV1,
)
from leo.storage.position_methods import PositionMethodsStore

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def document() -> PositionMethodsDocumentV1:
    cohort = (
        PositionMethodSourceV1(
            session_id="scan-one",
            input_manifest_sha256=DIGEST_A,
            analysis_sha256=DIGEST_B,
            tracking_product_sha256=DIGEST_C,
        ),
    )
    return PositionMethodsDocumentV1(
        session_id="scan-one",
        input_manifest_sha256=DIGEST_A,
        configuration_sha256=DIGEST_B,
        source_rolling_cohort_sha256=canonical_digest(
            [item.model_dump(mode="json") for item in cohort]
        ),
        source_rolling_cohort=cohort,
        reference_position=ReferencePositionV1(latitude_deg=37.8, longitude_deg=-122.4),
        methods=tuple(
            PositionMethodResultV1(
                method=method,
                state="diagnostic" if index == 0 else "insufficient",
                latitude_deg=37.81 if index == 0 else None,
                longitude_deg=-122.41 if index == 0 else None,
                horizontal_error_m=1234.0 if index == 0 else None,
                diagnostics={"weights": [0.8, 0.2], "nested": {"finite": 3.0}},
                reasons=() if index == 0 else ("insufficient evidence",),
            )
            for index, method in enumerate(POSITION_METHODS)
        ),
    )


def test_store_publishes_three_immutable_digest_checked_sidecars(tmp_path):
    reader = PositionMethodsStore(tmp_path)
    assert reader.status("scan-one").state == "pending"
    assert list(tmp_path.iterdir()) == []
    writer = PositionMethodsStore(tmp_path, read_only=False)
    images = {method: b"\x89PNG\r\n\x1a\n" + method.encode() for method in POSITION_METHODS}
    with writer.writer("scan-one"):
        assert not writer.complete("scan-one")
        manifest = writer.publish(document(), images)
    assert reader.status("scan-one").manifest == manifest
    assert writer.publish(document(), images) == manifest
    assert reader.artifact("scan-one", "expanded-doppler") == images["expanded-doppler"]
    path = tmp_path / "scanner-position-methods-v1" / "scan-one" / "expanded-doppler.png"
    path.write_bytes(b"damaged")
    with pytest.raises(ValueError, match="digest differs"):
        reader.artifact("scan-one", "expanded-doppler")


def test_store_rejects_a_corrupted_machine_readable_document(tmp_path):
    writer = PositionMethodsStore(tmp_path, read_only=False)
    images = {method: b"\x89PNG\r\n\x1a\n" + method.encode() for method in POSITION_METHODS}
    writer.publish(document(), images)
    path = tmp_path / "scanner-position-methods-v1" / "scan-one" / "document.json"
    path.write_bytes(b"{}")
    with pytest.raises(ValueError, match="document digest differs"):
        PositionMethodsStore(tmp_path).status("scan-one")


def test_contract_rejects_false_cohort_binding_and_nonfinite_nested_diagnostic():
    with pytest.raises(ValueError, match="cohort digest differs"):
        PositionMethodsDocumentV1.model_validate(
            {
                **document().model_dump(),
                "source_rolling_cohort_sha256": DIGEST_A,
            }
        )
    with pytest.raises(ValueError, match="finite"):
        PositionMethodResultV1(
            method="expanded-doppler",
            state="diagnostic",
            latitude_deg=1,
            longitude_deg=2,
            diagnostics={"series": [float("nan")]},
        )


def test_traversal_qnap_and_publication_conflict_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        PositionMethodsStore(tmp_path).status("../escape")
    with pytest.raises(ValueError):
        PositionMethodsStore(__import__("pathlib").Path("/mnt/qnap01/sidecars"))
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    (unsafe / "scanner-position-methods-v1").symlink_to(
        tmp_path, target_is_directory=True
    )
    with pytest.raises(ValueError):
        PositionMethodsStore(unsafe).status("scan-one")
    writer = PositionMethodsStore(tmp_path, read_only=False)
    images = {method: b"\x89PNG\r\n\x1a\n" + method.encode() for method in POSITION_METHODS}
    writer.publish(document(), images)
    changed = dict(images)
    changed["expanded-doppler"] += b"changed"
    with pytest.raises(ValueError, match="immutable"):
        writer.publish(document(), changed)
