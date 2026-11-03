"""Seal the scalar state predictor before validation scoring."""
import json
from pathlib import Path
import numpy as np
from states import digest
from model import fit
HERE=Path(__file__).resolve().parent


def main():
    sources={str(p):digest(p) for p in (Path(__file__),HERE/'model.py',HERE/'PROTOCOL.md')};rows=[]
    for i in range(8):
        p=HERE/f'center-{i:02d}.json';doc=json.loads(p.read_text());sources[str(p)]=digest(p)
        for q,h in doc['sources'].items():assert digest(q)==h,q
        rp=p.with_suffix('.receipt.json');receipt=json.loads(rp.read_text());assert receipt['exit_code']==0 and digest(p.with_suffix('.log'))==receipt['log_sha256'];sources[str(rp)]=digest(rp)
        rows.extend(r for r in doc['rows'] if r['split']=='training')
    result=fit(np.array([r['previous_revision'] for r in rows]),np.array([r['next_revision'] for r in rows]))
    result.update(cases=len(rows),physical_objects=len({r['norad'] for r in rows}),sources=sources,validation_used=False,radio_data_used=False)
    with (HERE/'calibration.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!='sources'},indent=2))


if __name__=='__main__':main()
