"""Benchmark all retained candidate CFO integrals without position fitting."""
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.special import logsumexp
from model import integrate

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
sys.path.insert(0,str(HERE.parents[2]/'tools'))
import ds7_fast_baseline_adapter as fast


def main():
    started=time.monotonic();oracle_path=HILL/'offset_integral_sensitivity/outcome.json';oracle=json.loads(oracle_path.read_text())
    sources=dict(oracle['sources'])
    for p,h in sources.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h
    lookup={(r['index'],r['track_id']):r for r in oracle['rows']}
    base=HILL.parent/'2026_09_30_ds11_single10';plan=json.loads((base/'plan.json').read_text());rows=[];scans=[]
    for index in (0,16):
        doc=fast.load_documents(dict(config=plan['config'],inputs=[plan['inputs'][index]]))[0]
        x=np.array(json.loads((base/f'runs/{index:02d}_iid.json').read_text())['selected']['x'])
        geometry=fast.Stationary(doc,plan['config']);totals={str(n):dict(score=0.,gradient=np.zeros(3),integration_s=0.) for n in (32,64)}
        for track in doc['tracks']:
            mask=track['mask'];prediction,visible=geometry.prediction(track,x)
            residual=(track['y'][None,:]-prediction)[:,mask]
            _,_,audits,offset=fast.profile(track['y'][None,:]-prediction,mask);assert all(a['converged'] for a in audits)
            jac=[]
            for axis,step in enumerate((1e-4,1e-4,1e-5)):
                d=np.eye(3)[axis]*step
                jac.append((geometry.prediction(track,x+d)[0][:,mask]-geometry.prediction(track,x-d)[0][:,mask])/(2*step))
            jac=np.stack(jac,axis=2);results={}
            for order in (32,64):
                start=time.monotonic();out=[integrate(r,j,float(b),order) for r,j,b in zip(residual,jac,offset)]
                totals[str(order)]['integration_s']+=time.monotonic()-start
                values=np.array([v['value'] for v in out]);gradients=np.array([v['gradient'] for v in out]);assert np.isfinite(values).all() and np.isfinite(gradients).all()
                logvalues=np.where(visible,values,-np.inf);normal=logsumexp(logvalues);weights=np.exp(logvalues-normal)
                totals[str(order)]['score']+=float(normal-np.log(track['catalogue_size']))
                totals[str(order)]['gradient']+=weights@gradients
                results[str(order)]=out
            row=dict(index=index,track_id=track['track_id'],candidates=len(offset),results=results,
                     value_difference=max(abs(a['value']-b['value']) for a,b in zip(results['32'],results['64'])),
                     gradient_difference=max(float(np.max(abs(np.array(a['gradient'])-b['gradient']))) for a,b in zip(results['32'],results['64'])))
            if (index,track['track_id']) in lookup:
                o=lookup[index,track['track_id']];slot=int(np.argmax(np.where(visible,fast.profile(track['y'][None,:]-prediction,mask)[0],-np.inf)))
                v=results['64'][slot]
                row['oracle_value_difference']=abs(v['value']-o['vector']['value'])
                row['oracle_gradient_difference']=float(np.max(abs(np.array(v['gradient'])-o['vector']['gradient'])))
            rows.append(row)
        for value in totals.values():value['gradient']=value['gradient'].tolist()
        scans.append(dict(index=index,orders=totals))
    summary=dict(tracks=len(rows),candidates=sum(r['candidates'] for r in rows),
                 maximum_value_difference=max(r['value_difference'] for r in rows),
                 maximum_gradient_difference=max(r['gradient_difference'] for r in rows),
                 oracle_cases=sum('oracle_value_difference' in r for r in rows),
                 maximum_oracle_value_difference=max(r.get('oracle_value_difference',0.) for r in rows),
                 maximum_oracle_gradient_difference=max(r.get('oracle_gradient_difference',0.) for r in rows))
    summary['numerical_gate_pass']=summary['oracle_cases']==24 and summary['maximum_value_difference']<1e-6 and summary['maximum_gradient_difference']<1e-3 and summary['maximum_oracle_value_difference']<1e-6 and summary['maximum_oracle_gradient_difference']<1e-3
    for p in (oracle_path,Path(__file__),HERE/'model.py',HERE/'test_model.py',HERE/'PROTOCOL.md'):
        sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(summary=summary,scans=scans,rows=rows,sources=sources,position_fits=0,reference_used=False,elapsed_s=time.monotonic()-started)
    with (HERE/'outcome.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(summary=summary,scans=scans,elapsed_s=result['elapsed_s']),indent=2))


if __name__=='__main__':main()
