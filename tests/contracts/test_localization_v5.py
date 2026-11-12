import pytest

from leo.contracts import localization_v3, localization_v4, localization_v5
from leo.contracts.digests import canonical_digest
from tests.localization_v5_fixture import evidence_fixture


def test_v5_outer_model_preserves_v4_native_backend_and_scientific_checks():
    evidence, _ = evidence_fixture()
    assert localization_v5.validate_evidence(evidence) is evidence
    backend = evidence['provenance']['native_backend']
    assert backend['manifest']['algorithm'] == localization_v4.MODEL
    assert {r['algorithm'] for r in backend['receipts']} == {localization_v4.MODEL}
    for contract in (localization_v3, localization_v4):
        with pytest.raises(ValueError):
            contract.validate_evidence(evidence)
    evidence['selected']['owners']['c0']['a'] = 12345
    with pytest.raises(ValueError):
        localization_v5.validate_evidence(evidence)


@pytest.mark.parametrize('failure', ['policy', 'algorithm', 'manifest', 'receipt'])
def test_v5_rejects_misbound_policy_outer_algorithm_or_native_identity(failure):
    evidence, _ = evidence_fixture()
    provenance = evidence['provenance']
    backend = provenance['native_backend']
    if failure == 'policy':
        provenance['initial_control_policy'] = 'other'
    elif failure == 'algorithm':
        provenance['algorithm'] = localization_v4.MODEL
    elif failure == 'manifest':
        backend['manifest']['algorithm'] = localization_v5.MODEL
        backend['manifest_sha256'] = canonical_digest(backend['manifest'])
    else:
        backend['receipts'][0]['algorithm'] = localization_v5.MODEL
    with pytest.raises(ValueError):
        localization_v5.validate_evidence(evidence)
