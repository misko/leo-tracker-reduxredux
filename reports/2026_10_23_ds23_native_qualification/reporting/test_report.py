import csv
import pytest
import report

def loaded():
    protocol=report.read(report.ROOT/'protocol.json')
    frozen={c:report.read(report.FROZEN/'raw'/c/'result.json') for c in protocol['available']}
    new={c:report.read(report.ROOT/'raw'/c/'result.json') for c in protocol['eligible_cases']+protocol['controls']}
    return protocol,frozen,new

def test_incomplete_execution_and_false_acceptance_rejected():
    p,f,n=loaded()
    missing=dict(n);missing.pop(next(iter(missing)))
    with pytest.raises(ValueError):report.validate(p,missing)
    failed=dict(n);case=next(iter(failed));failed[case]=dict(failed[case],status='execution_failure')
    with pytest.raises(ValueError):report.validate(p,failed)
    failed[case]=dict(n[case],candidate_accepted=n[case]['status']!='accepted')
    with pytest.raises(ValueError):report.validate(p,failed)

def test_positions_and_coverage_match_frozen_reporting_numerically():
    p,f,n=loaded();old=list(csv.DictReader((report.FROZEN/'tables/positions.csv').open()))
    formats={r['case']:r['cohort'] for r in old};rows=report.build(p,f,n,formats)
    index={(r['case'],r['method'],r['arm']):r for r in rows}
    for r in old:
        if r['method'] not in ('reference','ordinary') or r['case'] not in f:continue
        x=index[r['case'],'prior_ordinary' if r['method']=='ordinary' else 'reference',r['arm']]
        assert x['error_km']==float(r['error_km'])
        assert x['associated_unique']==int(r['associated_points'])
    for case in set(p['available'])-set(p['eligible_cases']):
        for arm in report.ARMS:
            x=index[case,'prior_ordinary',arm]
            for method in ('disable_rescue','one_pass'):
                assert index[case,method,arm]['error_km']==x['error_km']
                assert index[case,method,arm]['associated_unique']==x['associated_unique']

def test_control_views_and_eligible_views_are_exact_contract():
    f={'reference':object(),'final':object()};n={'policy_final':object(),'disable_rescue_final':object()}
    assert report.views('control',f,n,False)['one_pass'] is f['final']
    assert report.views('eligible',f,n,True)['one_pass'] is n['policy_final']
    assert report.views('eligible',f,n,True)['disable_rescue'] is n['disable_rescue_final']

def test_all381_outside_eligibility_reuse_exact_endpoints_and_ID_vectors():
    p,f,n=loaded();outside=set(p['available'])-set(p['eligible_cases'])
    assert len(outside)==381
    for case in outside:
        vv=report.views(case,f[case],n.get(case),False)
        for method in ('disable_rescue','one_pass'):
            assert vv[method] is f[case]['final']
            for arm in report.ARMS:
                assert vv[method]['arms'][arm]['endpoint_latlon']==f[case]['final']['arms'][arm]['endpoint_latlon']
                assert vv[method]['coverage'][arm]==f[case]['final']['coverage'][arm]

def test_every_frozen_protocol_input_hash_matches_current_bytes():
    p=report.read(report.ROOT/'protocol.json')
    assert p['input_hashes']
    for path,expected in p['input_hashes'].items():
        assert report.digest(report.Path(path))==expected
