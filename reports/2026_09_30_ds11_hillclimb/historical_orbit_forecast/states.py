"""Propagate three historical elements at a common prediction instant."""
import hashlib
import inspect
import json
from pathlib import Path
import sys
import time
import numpy as np
from leo.sky.propagation import parse_element_sets
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
HERE=Path(__file__).resolve().parent


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(ordinal):
    started=time.monotonic();path=HERE/'inventory.json';doc=json.loads(path.read_text())
    for p,h in doc['sources'].items():assert digest(p)==h,p
    window=doc['windows'][ordinal];cases=window['cases'];values={}
    assert cases
    for kind in ('old','current','later'):
        text=''.join(f"0 {c[kind]['name']}\n{c[kind]['first_line']}\n{c[kind]['second_line']}\n" for c in cases)
        catalogue=parse_element_sets(text);assert list(catalogue.satellite_numbers)==[c['norad'] for c in cases]
        p,v,valid=propagate_candidate_states(catalogue,range(len(cases)),window['center_utc_ns'],np.array([0.]),np.array([0.]))
        np.testing.assert_array_equal(valid,np.arange(len(cases)))
        values[kind]=np.column_stack((p[:,0,0],v[:,0,0]))
    rows=[dict(norad=c['norad'],split=c['split'],previous_revision=(values['current'][i]-values['old'][i]).tolist(),next_revision=(values['later'][i]-values['current'][i]).tolist(),current_epoch_age_s=(window['center_utc_ns']-c['current']['epoch'])/1e9,previous_epoch_gap_s=(c['current']['epoch']-c['old']['epoch'])/1e9,next_epoch_gap_s=(c['later']['epoch']-c['current']['epoch'])/1e9) for i,c in enumerate(cases)]
    paths=[Path(__file__),HERE/'PROTOCOL.md',path,Path(inspect.getfile(parse_element_sets)),Path(inspect.getfile(propagate_candidate_states))]
    result=dict(ordinal=ordinal,center_utc_ns=window['center_utc_ns'],rows=rows,sources={str(p):digest(p) for p in paths},elapsed_s=time.monotonic()-started,reference_proxy=True)
    with (HERE/f'states-{ordinal:02d}.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(ordinal=ordinal,cases=len(rows),elapsed_s=result['elapsed_s'])),flush=True)


if __name__=='__main__':main(int(sys.argv[1]))
