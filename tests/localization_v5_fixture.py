from leo.contracts import localization_v5
from tests.localization_v4_fixture import evidence_fixture as native_evidence


def evidence_fixture():
    evidence, pngs = native_evidence()
    evidence['model_version'] = localization_v5.MODEL
    evidence['provenance'].update(algorithm=localization_v5.MODEL,
        initial_control_policy=localization_v5.INITIAL_CONTROL_POLICY)
    return evidence, pngs
