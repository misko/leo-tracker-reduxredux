import importlib.util
from pathlib import Path
import numpy as np
from refit_selected import Corrected


def test_correction_matches_direct_selected_scores_and_held_isolation():
    path=Path(__file__).resolve().parent.parent/'2026_09_27_ds6_height_sensitivity/test_height.py'
    spec=importlib.util.spec_from_file_location('height_synthetic_fixture',path)
    module=importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0,str(path.parent));spec.loader.exec_module(module)
    base=module.synthetic_base();x=np.zeros(3)
    empty=Corrected(base,[]).evaluate(x);old=base.evaluate(x,False)
    assert empty['train']==old['train'] and empty['held']==old['held']
    corrected=Corrected(base,['one']);value=corrected.evaluate(x)
    from solver import scores
    t=base.tracks[0];a,b,audits=scores(t['y'][None,:]-old['predictions'][0],t['mask'])
    np.testing.assert_allclose(value['train'],a[0],atol=1e-9)
    np.testing.assert_allclose(value['held'],b[0]-a[0],atol=1e-9)
    t['y']=t['y']+np.where(t['mask'],0,1e6)
    assert corrected.evaluate(x)['train']==value['train']


def test_frozen_refit_outputs_and_selection():
    import json
    from refit_selected import HERE,digest
    p=json.loads((HERE/'refit-protocol.json').read_text())
    assert p['source_sha256']==digest(HERE/'refit_selected.py')
    assert p['solver_sha256']==digest(HERE/'solver.py')
    for s in p['sessions']:
        r=json.loads((HERE/f'{s}-refit.json').read_text())
        assert r['complete'] and r['protocol_sha256']==digest(HERE/'refit-protocol.json')
        assert r['selected_tracks']==p['selected'][s]
        assert r['best']==max(r['runs'],key=lambda v:v['train'])
        assert r['best']['train']>=r['baseline_corrected']['train']-1e-3
        assert r['exact']['max_offset_gradient']<1e-7
        assert abs(r['exact']['train']-r['best']['train'])<1.
