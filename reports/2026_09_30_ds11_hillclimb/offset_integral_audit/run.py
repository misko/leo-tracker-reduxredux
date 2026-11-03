"""Check independent-error offset integrals on frozen training residuals."""
import hashlib
import json
from pathlib import Path
import sys
import time
import warnings
import numpy as np
from scipy.integrate import IntegrationWarning
from model import marginal

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
sys.path.insert(0,str(HERE.parents[2]/'tools'))
import ds7_fast_baseline_adapter as fast


def main():
    started=time.monotonic();fixed=json.loads((HILL/'cross_band_rx_fixed/outcome.json').read_text())
    sources=dict(fixed['sources'])
    for p,h in sources.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h
    base=HILL.parent/'2026_09_30_ds11_single10';plan=json.loads((base/'plan.json').read_text());rows=[]
    warnings.simplefilter('error',IntegrationWarning)
    for index in (0,16):
        document=fast.load_documents(dict(config=plan['config'],inputs=[plan['inputs'][index]]))[0]
        original=json.loads((base/f'runs/{index:02d}_iid.json').read_text())['selected']
        geometry=fast.Stationary(document,plan['config'])
        for track in sorted(document['tracks'],key=lambda t:t['track_id'])[:12]:
            prediction,visible=geometry.prediction(track,np.array(original['x']))
            residual=track['y'][None,:]-prediction
            score,_,audits,offsets=fast.profile(residual,track['mask'])
            assert all(a['converged'] for a in audits)
            slot=int(np.argmax(np.where(visible,score,-np.inf)));assert visible[slot]
            r=residual[slot,track['mask']];start=time.monotonic()
            a=marginal(r,offsets[slot],score[slot]);b=marginal(r,offsets[slot],score[slot],1e-10)
            rows.append(dict(index=index,track_id=track['track_id'],candidate_slot=slot,training_rows=len(r),
                             coarse=a,fine=b,log_discrepancy=abs(a['log_marginal']-b['log_marginal']),
                             elapsed_s=time.monotonic()-start))
    extra=[Path(__file__),HERE/'model.py',HERE/'test_model.py',HERE/'PROTOCOL.md',HILL/'cross_band_rx_fixed/outcome.json']
    for p in extra:sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    passed=len(rows)==24 and all(r['log_discrepancy']<1e-6 and max(r[k]['relative_quadrature_error'] for k in ('coarse','fine'))<1e-6 for r in rows)
    result=dict(numerical_gate_pass=passed,rows=rows,sources=sources,position_fits=0,reference_used=False,
                elapsed_s=time.monotonic()-started,
                maximum_log_discrepancy=max(r['log_discrepancy'] for r in rows),
                correction_range=[min(r['fine']['log_correction'] for r in rows),max(r['fine']['log_correction'] for r in rows)])
    with (HERE/'outcome.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','sources')},indent=2))


if __name__=='__main__':main()
