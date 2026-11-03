"""Exact center extraction through the propagator's required three-point grid."""
import inspect
import json
from pathlib import Path
import sys
import time
import numpy as np
from leo.sky.propagation import parse_element_sets
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from states import digest
HERE=Path(__file__).resolve().parent


def main(ordinal):
    started=time.monotonic();path=HERE/'inventory.json';doc=json.loads(path.read_text())
    for p,h in doc['sources'].items():assert digest(p)==h,p
    window=doc['windows'][ordinal];cases=window['cases'];values={}
    for kind in ('old','current','later'):
        text=''.join(f"0 {c[kind]['name']}\n{c[kind]['first_line']}\n{c[kind]['second_line']}\n" for c in cases)
        catalogue=parse_element_sets(text);assert list(catalogue.satellite_numbers)==[c['norad'] for c in cases]
        p,v,valid=propagate_candidate_states(catalogue,range(len(cases)),window['center_utc_ns'],np.array([-1.,0.,1.]),np.array([0.]))
        np.testing.assert_array_equal(valid,np.arange(len(cases)))
        values[kind]=np.column_stack((p[:,0,1],v[:,0,1]))
    rows=[dict(norad=c['norad'],split=c['split'],previous_revision=(values['current'][i]-values['old'][i]).tolist(),next_revision=(values['later'][i]-values['current'][i]).tolist(),current_epoch_age_s=(window['center_utc_ns']-c['current']['epoch'])/1e9,previous_epoch_gap_s=(c['current']['epoch']-c['old']['epoch'])/1e9,next_epoch_gap_s=(c['later']['epoch']-c['current']['epoch'])/1e9) for i,c in enumerate(cases)]
    paths=[Path(__file__),HERE/'states.py',HERE/'PROTOCOL.md',path,Path(inspect.getfile(parse_element_sets)),Path(inspect.getfile(propagate_candidate_states))]
    result=dict(ordinal=ordinal,center_utc_ns=window['center_utc_ns'],rows=rows,sources={str(p):digest(p) for p in paths},elapsed_s=time.monotonic()-started,reference_proxy=True,sampling_grid_s=[-1.,0.,1.],selected_sample=1)
    with (HERE/f'center-{ordinal:02d}.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(ordinal=ordinal,cases=len(rows),elapsed_s=result['elapsed_s'])),flush=True)


if __name__=='__main__':main(int(sys.argv[1]))
