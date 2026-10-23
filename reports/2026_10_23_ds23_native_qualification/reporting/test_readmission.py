import json
from pathlib import Path

def test_frozen_readmission_is_fit_exclusion_not_blacklist():
    d=json.loads((Path(__file__).parent/'readmission_audit.json').read_text())
    rows={(r['case'],r['arm']):r for r in d['rows']}
    assert d['status']=='complete'
    for r in rows.values():
        assert r['coverage_exact_replay'] and r['excluded_from_fitting']
        assert r['remaining_fit_ID_overlap']==0 and r['parent_ID_overlap']==0 and r['parent_IDs_lost']==0
    assert rows['DS23-0232','fitted_c']['coverage_readmitted']==9
    assert rows['DS23-0232','c0']['coverage_readmitted']==0
    assert rows['DS23-0365','c0']['coverage_readmitted']==rows['DS23-0365','fitted_c']['coverage_readmitted']==0
    assert rows['DS23-0232','c0']['original_family_candidate']['noise']['quadratic_bic_gain']>10
    assert rows['DS23-0232','fitted_c']['original_family_candidate']['noise']['quadratic_bic_gain']<10

def test_strict_ledger_is_derived_reporting_only_and_removes_exact_nine():
    d=json.loads((Path(__file__).parent/'readmission_audit.json').read_text())
    s={r['arm']:r for r in d['strict_exclusion_sensitivity']}
    assert s['c0']['strict_exclusion_ledger_unique_IDs']==769010
    assert s['fitted_c']['strict_exclusion_ledger_unique_IDs']==768677
    assert s['fitted_c']['frozen_unique_IDs']-s['fitted_c']['strict_exclusion_ledger_unique_IDs']==9
    assert all(r['positions_unchanged'] and r['derived_reporting_only'] for r in s.values())
