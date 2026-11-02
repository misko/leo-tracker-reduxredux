"""Actual-model feature invariance, with no position optimization or geography."""
import argparse
import json
from pathlib import Path
import numpy as np
from algo07_science import engine as e
from age_covariance import candidate_context,sha

ROOT=Path(__file__).resolve().parent


def audit(case):
    roster=json.loads((ROOT.parent/'evaluation/rf_roster.json').read_text())
    record=next(r for r in roster['cases'] if r['case']==case)
    source=Path(record['input_path']).parent.parent
    e.configure(source,ROOT/'runtime_context_audit');e.ROOTS[case[:4]]=source
    d,z,replay=e.load_case(case)
    dd,receipt=candidate_context(d,z,dict(case=case,selected_family=record['target_family']))
    checks={}
    if receipt['applied']:
        for arm,(old,x) in d['problems'].items():
            new,_=e.build(dd,z,arm,old.reference)
            first=old.hardware.shape[1]+old.smooth.shape[1]+len(old.labels)
            local=old.supported.index(next(j for j in old.labels if int(old.scan.norads[j])==record['target_family']))
            indices=np.arange(first+3*local,first+3*local+3)
            a,b=old.calculate(x),new.calculate(x)
            keep=np.ones(a['features'].shape[1],bool);keep[indices]=False
            difference=float(np.max(abs(a['features'][:,keep]-b['features'][:,keep])))
            assert difference==0
            for attr in ['values','keep','phase_sigma','reference','hardware','smooth','constants']:
                assert np.array_equal(getattr(old,attr),getattr(new,attr)),attr
            assert old.alias==new.alias
            checks[arm]=dict(only_changed_columns=indices.tolist(),unrelated_feature_max_difference=difference,
                observations_masks_aliases_receiver_phase_priors_preserved=True)
    else:assert dd is d
    packet=dict(case=case,source_sha256=sha(ROOT/'age_covariance.py'),receipt=receipt,checks=checks,
        baseline_replay=replay,no_position_fit=True,no_GPS_read=True)
    (ROOT/('context_audit-'+case+'.json')).write_text(json.dumps(packet,indent=2,default=lambda v:v.tolist() if hasattr(v,'tolist') else str(v))+'\n')
    print(case,receipt['status'],receipt.get('pair_count'),checks)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',default='FRSH-0001');audit(p.parse_args().case)
