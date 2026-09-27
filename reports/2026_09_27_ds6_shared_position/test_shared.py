import hashlib
import json
from pathlib import Path

import numpy as np

from run_shared import fit_joint

HERE=Path(__file__).resolve().parent


class SyntheticScan:
    def __init__(self,position,timing):
        self.target=np.array([*position,timing]);self.held_bias=0.

    def evaluate(self,x):
        return dict(train=-float(np.sum((x-self.target)**2)),held=self.held_bias+float(np.sum(x)))


def test_shared_position_recovers_common_geometry_and_independent_clocks():
    models=[SyntheticScan([1.2,-.7],t) for t in [-1.,.5,2.,-.2]]
    positions=[m.target.copy() for m in models]
    best,_=fit_joint(models,positions)
    np.testing.assert_allclose(best['x'],[1.2,-.7,-1.,.5,2.,-.2],atol=.001)
    for i,model in enumerate(models):model.held_bias=1e6*(i+1)
    changed,_=fit_joint(models,positions)
    np.testing.assert_array_equal(best['x'],changed['x'])


def test_complete_fits_preserve_membership_and_training_selection():
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert hashlib.sha256((HERE/'run_shared.py').read_bytes()).hexdigest()==protocol['source_sha256']
    for name,value in protocol['files'].items():assert hashlib.sha256((HERE.parent/name).read_bytes()).hexdigest()==value
    result=json.loads((HERE/'results.json').read_text())
    assert result['complete'] and len(result['fits'])==5
    assert result['protocol_sha256']==hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
    for row in result['fits'].values():
        assert row['included']==[s for s in protocol['sessions'] if s!=row['omitted']]
        assert row['best']==max(row['runs'],key=lambda r:r['train'])
        assert len(row['best']['x'])==2+len(row['included'])
        assert set(row['included_audits'])==set(row['included'])
        if row['omitted'] is not None:
            assert row['omitted'] not in row['included_audits']
            adaptation=row['omitted_adaptation']
            assert adaptation['selected']==max(adaptation['attempts'],key=lambda r:r['train'])
