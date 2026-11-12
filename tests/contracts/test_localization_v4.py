import pytest

from leo.contracts import localization_v3, localization_v4
from leo.contracts.digests import canonical_digest
from tests.localization_v4_fixture import evidence_fixture


def test_native_evidence_preserves_shared_scientific_checks_and_owns_version():
    evidence, _ = evidence_fixture()
    assert localization_v4.validate_evidence(evidence) is evidence
    with pytest.raises(ValueError):
        localization_v3.validate_evidence(evidence)
    evidence["selected"]["owners"]["c0"]["a"] = 12345
    with pytest.raises(ValueError):
        localization_v4.validate_evidence(evidence)


@pytest.mark.parametrize("failure", [
    "algorithm", "manifest_digest", "source_digest", "provider", "counts", "duplicate_pid",
])
def test_native_evidence_rejects_provenance_or_activation_misbinding(failure):
    evidence, _ = evidence_fixture()
    provenance = evidence["provenance"]
    backend = provenance["native_backend"]
    if failure == "algorithm":
        provenance["algorithm"] = localization_v3.MODEL
    elif failure == "manifest_digest":
        backend["manifest_sha256"] = "sha256:" + "0" * 64
    elif failure == "source_digest":
        backend["manifest"]["source_sha256"] = "wrong"
        backend["manifest_sha256"] = canonical_digest(backend["manifest"])
    elif failure == "provider":
        backend["receipts"][0]["provider"] = dict(threads=8)
    elif failure == "counts":
        backend["receipts"][0]["counts"]["activated"] = 7
    else:
        backend["receipts"].append(backend["receipts"][0])
    with pytest.raises(ValueError):
        localization_v4.validate_evidence(evidence)
