"""Real-data zero-height parity only: no fitting or altitude selection."""
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from model import Model,physical,SOURCE

HERE=Path(__file__).resolve().parent;HILL=HERE.parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    started=time.monotonic();base=HILL.parent/'2026_09_30_ds11_single10'
    pp=base/'plan.json';plan=json.loads(pp.read_text());fast=physical.fast
    sources={str(p):digest(p) for p in (pp,Path(__file__),HERE/'model.py',SOURCE,HERE/'test_model.py',HERE/'PROTOCOL.md')}
    original_profile=fast.baseline.profile
    fast.baseline.profile=fast.profile
    rows=[]
    try:
        for index in (0,16):
            p=base/f'runs/{index:02d}_iid.json';control=json.loads(p.read_text())['selected'];sources[str(p)]=digest(p)
            entry=plan['inputs'][index]
            for artifact in entry['artifacts']:
                assert digest(artifact['path'])==artifact['sha256'].removeprefix('sha256:')
                sources[artifact['path']]=digest(artifact['path'])
            doc=fast.load_documents(dict(config=plan['config'],inputs=[entry]))[0]
            m=Model(doc,plan['config'],0);original=fast.Stationary(doc,plan['config']);x=np.array(control['x'])
            a=m.evaluate(x);score,grad=original.evaluate(x,True)
            prediction=max(float(np.max(abs(m.prediction(t,x)[0]-original.prediction(t,x)[0]))) for t in doc['tracks'])
            fd=[]
            for axis,step in enumerate((1e-3,1e-3,1e-4)):
                d=np.eye(3)[axis]*step
                fd.append((m.evaluate(x+d,False)['score']-m.evaluate(x-d,False)['score'])/(2*step))
            row=dict(index=index,prediction_parity_hz=prediction,score_parity=abs(score-a['score']),
                     stored_score_parity=abs(control['score']-a['score']),gradient_parity=float(np.max(abs(grad-a['gradient']))),
                     finite_difference_error=float(np.max(abs(a['gradient']-fd))))
            assert prediction==0 and row['score_parity']<1e-8 and row['stored_score_parity']<1e-6 and row['gradient_parity']<1e-6 and row['finite_difference_error']<.02,row
            rows.append(row)
    finally:fast.baseline.profile=original_profile
    result=dict(passed=True,rows=rows,sources=sources,position_fits=0,antenna_altitude_selected=False,
                causal_position_improvement_established=False,elapsed_s=time.monotonic()-started)
    with (HERE/'preflight.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!='sources'},indent=2))


if __name__=='__main__':main()
