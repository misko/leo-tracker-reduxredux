import importlib.util
import sys
from pathlib import Path
import numpy as np
from run_full import Stationary


def synthetic():
    p=Path(__file__).resolve().parent.parent/'2026_09_27_ds6_height_sensitivity/test_height.py'
    sys.path.insert(0,str(p.parent));spec=importlib.util.spec_from_file_location('stationary_geometry_fixture',p)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    base=module.synthetic_base()
    base.tracks[0]['y']+=np.sin(base.tracks[0]['t']/50)*80
    return base


def test_envelope_gradient_matches_full_profiled_objective_and_held_isolation():
    base=synthetic();model=Stationary(base);x=np.array([.6,-.8,.3]);r=model.evaluate(x,True)
    numeric=[]
    for i in range(3):
        plus=x.copy();minus=x.copy();plus[i]+=1e-3;minus[i]-=1e-3
        numeric.append((model.evaluate(plus)['train']-model.evaluate(minus)['train'])/.002)
    np.testing.assert_allclose(r['gradient'],numeric,atol=1e-5,rtol=1e-5)
    t=base.tracks[0];t['y']+=np.where(t['mask'],0.,1e6);other=model.evaluate(x,True)
    assert other['train']==r['train'];np.testing.assert_array_equal(other['gradient'],r['gradient'])


def test_complete_development_fits_and_gradient_audits():
    import json
    from run_full import HERE,REPORTS,digest
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(HERE/'run_full.py')==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    assert len(protocol['development_sessions'])==4
    for session in protocol['development_sessions']:
        r=json.loads((HERE/f'{session}.json').read_text())
        assert r['complete'] and r['protocol_sha256']==digest(HERE/'protocol.json')
        assert len(r['runs'])==3 and r['best']==max(r['runs'],key=lambda v:v['train'])
        assert r['best']['max_offset_gradient']<1e-7
        assert r['maximum_interpolation_error_hz']<.05
        assert r['maximum_gradient_difference']<.01
