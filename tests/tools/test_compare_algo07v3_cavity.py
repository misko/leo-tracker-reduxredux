from copy import deepcopy

import pytest
from check_algo07v3_scan_likelihood import fingerprint
from compare_algo07v3_cavity import compare


def test_cavity_archive_comparison_checks_all_scientific_fields_and_trials():
    nominations = dict(status='complete', families=[dict(score=1.)], seconds=10.)
    position = dict(status='complete', trials=[dict(paired_valid=False, loss=2.)],
                    nomination_sha256='operational binding', seconds=20.)
    candidate = dict(cavity_nominations=fingerprint({k:v for k,v in nominations.items()
                                                    if k != 'seconds'}),
                     cavity_policy=fingerprint({k:v for k,v in position.items()
                                                if k not in ('seconds', 'nomination_sha256')}))
    assert compare(nominations, position, candidate)['exact']
    changed = deepcopy(position)
    changed['trials'][0]['paired_valid'] = True
    with pytest.raises(ValueError, match='differs'):
        compare(nominations, changed, candidate)
    changed = deepcopy(nominations)
    changed['families'][0]['seconds'] = 1.
    with pytest.raises(ValueError, match='Fields differ'):
        compare(changed, position, candidate)
