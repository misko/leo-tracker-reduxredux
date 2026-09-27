from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_reporting_fix import annotate


@pytest.mark.parametrize('outcome,ref,active,expected', [
    ('retained_associated', True, True, (True, False, False)),
    ('active_unassociated_reference', True, True, (False, True, True)),
    ('reference_miss', True, False, (False, True, False)),
    ('reference_extra', False, True, (False, False, True)),
    ('both_inactive', False, False, (False, False, False)),
])
def test_reporting_flags_preserve_scientific_outcome(outcome, ref, active, expected):
    source = dict(reference_outcome=outcome, reference_active=ref, candidate_active=active)
    result = annotate(source)
    assert tuple(result[k] for k in ('matched_reference', 'lost_reference', 'additional_or_mismatched')) == expected
    assert all(result[k] == v for k, v in source.items())
    assert len(source) == 3
