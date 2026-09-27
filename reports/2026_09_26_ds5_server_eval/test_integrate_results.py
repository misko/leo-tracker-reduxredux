import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location(
    'ds5_integrate', Path(__file__).with_name('integrate_results.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_unsupported_cases_remain_in_denominator_and_dual_rx_cost_is_summed():
    cases = [dict(case_id='a', split='holdout', origin='real_ds5', rate_hz=2500000,
                  session_id='s', visit_index=0, source_start_counter=100,
                  source_end_counter_exclusive=300100),
             dict(case_id='b', split='holdout', origin='real_ds5', rate_hz=10000000,
                  session_id='t', visit_index=0, source_start_counter=200,
                  source_end_counter_exclusive=1200200)]
    rows = [dict(case_id='a', rx=rx, variant='baseline_blind_512', rate_hz=2500000,
                 representative={'candidates': []}, timing_median={'wall_ms': 10})
            for rx in range(2)]
    result = module.integrate(cases, {'split': 'holdout', 'rows': rows}, 'search')
    baseline = result['methods']['baseline_blind_512']
    assert baseline['arrival_replay']['median_service_ms'] == 20
    assert baseline['arrival_replay']['unknown_visits'] == 1
    assert baseline['by_origin_and_rate']['real_ds5:10000000']['reference_unknown_cases'] == 2
    with pytest.raises(ValueError, match='duplicate'):
        module.integrate(cases, {'split': 'holdout', 'rows': rows + rows}, 'search')
