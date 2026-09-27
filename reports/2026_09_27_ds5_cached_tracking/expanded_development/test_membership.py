import importlib.util
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('expanded_development_replay',HERE/'replay.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)


def test_membership_is_fixed_exposed_development_and_truth_stays_unknown():
    rows=module.membership()
    assert len(rows)==64
    assert {r['session_id'] for r in rows}=={'scan-fw-1a0e881391ba1d2f','scan-fw-3ec1c634e1f48f77'}
    for rate in (2500000,5000000):
        visits=[r['visit_index'] for r in rows if r['rate_hz']==rate]
        assert visits==list(range(min(visits),min(visits)+32))
    for row in rows:
        case=module.descriptor(row)
        assert row['split']=='dev' and case.split=='development'
        assert case.activity_policy=='recorded_unknown' and case.expected_active is None
        assert all(not truth.constructed_negative and not truth.pilots for truth in case.receivers)
