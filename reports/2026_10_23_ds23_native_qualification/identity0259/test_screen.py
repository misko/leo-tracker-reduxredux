import numpy as np
from screen import shortlist,qualify

def test_pool_keeps_original_and_excludes_invisible():
    assert shortlist(np.array([4.,np.inf,1.,3.]),1,2)==[1,2,3]

def test_physical_and_fixed_radio_gates_both_required():
    r=dict(qualified=True,fixed_radio_checks=[dict(compatible=True)])
    assert qualify(r)
    r['fixed_radio_checks'][0]['compatible']=False
    assert not qualify(r)
    r.update(qualified=False,fixed_radio_checks=[dict(compatible=True)])
    assert not qualify(r)

def test_archived_screens_have_matched_candidate_pools_and_valid_gates():
    import json
    from pathlib import Path
    for suffix in ['001','002','005','006','007']:
        d=json.loads((Path(__file__).parent/(suffix+'.json')).read_text())
        assert d['status']=='complete' and d['all_element_epochs_and_collections_causal']
        assert d['catalogue_count']==1338
        pools=[{c['candidate_index'] for c in r['candidates']} for r in d['rows']]
        assert all(pool==set(d['candidate_pool']) for pool in pools)
        assert {(r['location'],r['arm']) for r in d['rows']}=={(l,a) for l in ['graph_parent','native_RF_endpoint'] for a in ['c0','fitted_c']}
        for row in d['rows']:
            for c in row['candidates']:
                if c['physical_and_residual_qualified']:
                    assert abs(c['phase_s'])<=15 and c['minimum_elevation_deg']>=0 and c['phase_change_s']<=.01
                    assert all(v['compatible'] for v in c['fixed_radio_checks'])
