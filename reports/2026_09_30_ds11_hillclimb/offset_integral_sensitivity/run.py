"""Audit within-track CFO integration effects before geographic fitting."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np
from model import value_gradient

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
spec=importlib.util.spec_from_file_location('scalar_cfo',HILL/'offset_integral_audit/model.py')
scalar=importlib.util.module_from_spec(spec);spec.loader.exec_module(scalar)
sys.path.insert(0,str(HERE.parents[2]/'tools'))
import ds7_fast_baseline_adapter as fast


def main():
    started=time.monotonic();source=HILL/'offset_integral_audit/outcome.json';old=json.loads(source.read_text())
    sources=dict(old['sources'])
    for p,h in sources.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h
    base=HILL.parent/'2026_09_30_ds11_single10';plan=json.loads((base/'plan.json').read_text());rows=[]
    for index in (0,16):
        doc=fast.load_documents(dict(config=plan['config'],inputs=[plan['inputs'][index]]))[0]
        x=np.array(json.loads((base/f'runs/{index:02d}_iid.json').read_text())['selected']['x'])
        geometry=fast.Stationary(doc,plan['config']);tracks={t['track_id']:t for t in doc['tracks']}
        for previous in [r for r in old['rows'] if r['index']==index]:
            track=tracks[previous['track_id']];mask=track['mask']
            predictions,visible=geometry.prediction(track,x)
            scores,_,audits,offsets=fast.profile(track['y'][None,:]-predictions,mask)
            assert all(a['converged'] for a in audits)
            order=np.argsort(np.where(visible,scores,-np.inf))[::-1][:2];assert visible[order].all()
            slot=int(order[0]);assert slot==previous['candidate_slot']
            def evaluate(point,which=slot):
                p=geometry.prediction(track,point)[0][which]
                residual=track['y']-p
                score,_,checks,offset=fast.profile(residual[None,:],mask)
                assert checks[0]['converged']
                integral=scalar.marginal(residual[mask],offset[0],score[0])
                return dict(profile=float(score[0]),offset=float(offset[0]),**integral)
            nominal=evaluate(x);runner=evaluate(x,int(order[1]))
            jac=[];finite=[]
            for axis,step in enumerate((1e-4,1e-4,1e-5)):
                d=np.eye(3)[axis]*step
                jac.append((geometry.prediction(track,x+d)[0][slot,mask]-geometry.prediction(track,x-d)[0][slot,mask])/(2*step))
                finite.append((evaluate(x+d)['log_marginal']-evaluate(x-d)['log_marginal'])/(2*step))
            vector=value_gradient((track['y']-predictions[slot])[mask],np.array(jac).T,nominal['offset'],nominal['profile'])
            changes=[]
            for axis in (0,1):
                for sign in (-1,1):
                    r=evaluate(x+np.eye(3)[axis]*(sign*.1))
                    changes.append(dict(axis=axis,sign=sign,correction_change=r['log_correction']-nominal['log_correction']))
            rows.append(dict(index=index,track_id=track['track_id'],nominal=nominal,runner_up=runner,
                             original_candidate_gap=float(scores[order[0]]-scores[order[1]]),
                             marginal_candidate_gap=nominal['log_marginal']-runner['log_marginal'],
                             vector=vector,finite_gradient=finite,spatial_changes=changes,
                             value_discrepancy=abs(vector['value']-nominal['log_marginal']),
                             gradient_discrepancy=float(np.max(abs(np.array(vector['gradient'])-finite)))))
    for p in (source,Path(__file__),HERE/'model.py',HERE/'test_model.py',HERE/'PROTOCOL.md'):
        sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    summary=dict(cases=len(rows),maximum_value_discrepancy=max(r['value_discrepancy'] for r in rows),
                 maximum_gradient_discrepancy=max(r['gradient_discrepancy'] for r in rows),
                 candidate_pair_reversals=sum(r['marginal_candidate_gap']<0 for r in rows),
                 maximum_candidate_gap_change=max(abs(r['marginal_candidate_gap']-r['original_candidate_gap']) for r in rows),
                 maximum_100m_correction_change=max(abs(v['correction_change']) for r in rows for v in r['spatial_changes']),
                 median_100m_maximum_correction_change=float(np.median([max(abs(v['correction_change']) for v in r['spatial_changes']) for r in rows])))
    summary['numerical_gate_pass']=len(rows)==24 and summary['maximum_value_discrepancy']<1e-6 and summary['maximum_gradient_discrepancy']<1e-3
    result=dict(summary=summary,rows=rows,sources=sources,position_fits=0,reference_used=False,elapsed_s=time.monotonic()-started)
    with (HERE/'outcome.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(summary=summary,elapsed_s=result['elapsed_s']),indent=2))


if __name__=='__main__':main()
