from copy import deepcopy

import pytest
from check_algo07v3_scan_likelihood import fingerprint
from compare_algo07v3_signed import FIELDS, compare


def test_archive_signed_audit_checks_every_incumbent_field_and_nested_values():
    archive = dict(status='complete', **{k: dict(value=1.) for k in FIELDS})
    candidate = dict(signed_policy={v: fingerprint(archive[k]) for k,v in FIELDS.items()})
    assert compare(archive, candidate)['exact']
    for key in FIELDS:
        changed = deepcopy(archive)
        changed[key]['value'] = 1.0000000000000002
        with pytest.raises(ValueError, match='differs'):
            compare(changed, candidate)
    archive['status'] = 'failed'
    with pytest.raises(ValueError, match='incomplete'):
        compare(archive, candidate)
