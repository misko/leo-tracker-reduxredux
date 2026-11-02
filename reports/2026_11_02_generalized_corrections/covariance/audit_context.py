"""Exact actual-model feature invariance audit; no position fitting/evaluation."""
import argparse
import json
from pathlib import Path

import numpy as np

from algo07_science import engine as e
from causal_covariance import candidate_context,sha

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]


def audit(case):
    rows=json.loads((REPO/'reports/2026_11_02_algo07_top10_outliers/run_manifest.json').read_text())['rows']
    row=next(r for r in rows if r['case']==case)
    prior=json.loads((REPO/'reports/2026_11_02_family_reliability/population/cases'/case/'result.json').read_text())
    root=Path(row['input_path']).parent.parent
    e.configure(root,ROOT/'context_test');e.ROOTS[case[:4]]=root
    d,z,replay=e.load_case(case)
    family=prior['selected_family']
    dd,receipt=candidate_context(d,z,dict(case=case,selected_family=family))
    checks={}
    if receipt['applied']:
        for arm,(base,x) in d['problems'].items():
            p,_=e.build(dd,z,arm,base.reference)
            old,new=base.calculate(x),p.calculate(x)
            assert old['features'].shape==new['features'].shape
            first=base.hardware.shape[1]+base.smooth.shape[1]+len(base.labels)
            local=base.supported.index(next(j for j in base.labels if int(d['scan'].norads[j])==family))
            indexes=np.arange(first+3*local,first+3*local+3)
            unrelated=np.ones(old['features'].shape[1],bool);unrelated[indexes]=False
            diff=float(np.max(abs(old['features'][:,unrelated]-new['features'][:,unrelated])))
            assert diff==0
            for name in ['values','keep','phase_sigma','reference','hardware','smooth','constants']:
                assert np.array_equal(getattr(base,name),getattr(p,name)),name
            assert base.alias==p.alias
            checks[arm]=dict(unrelated_feature_max_difference=diff,changed_columns=indexes.tolist(),
                            all_other_arrays_exact=True,feature_count=new['features'].shape[1])
    else:
        assert dd is d
        checks['fallback_is_same_context']=True
    output=dict(case=case,receipt=receipt,replay=replay,checks=checks,position_fit_performed=False,
        evaluation_coordinate_read=False,source_sha256=sha(ROOT/'causal_covariance.py'))
    (ROOT/('context_audit-'+case+'.json')).write_text(json.dumps(output,default=lambda v:v.tolist() if hasattr(v,'tolist') else v,indent=2)+'\n')
    print(case,receipt['status'],receipt.get('reason'),checks)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',default='DS26-0309');audit(p.parse_args().case)
