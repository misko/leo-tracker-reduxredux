"""Reference-free finite-difference sensitivity of the rejected pair; no refit."""
import json
from pathlib import Path
import numpy as np
from run_window import prepare_window
from run_constituent_pair import save,digest,verify_sources

HERE=Path(__file__).resolve().parent


def main():
    unit='DS11-B03-D2';directory=HERE/'constituent-pair-v3'/unit
    path=directory/(unit+'.json');audit_path=directory/'evaluation.json'
    for p in [path,audit_path]:assert digest(p)==p.with_suffix('.sha256').read_text().strip()
    receipt=json.loads(path.read_text());audit=json.loads(audit_path.read_text())['rows'][0]
    assert not audit['accepted'] and audit['receipt_sha256']==digest(path)
    verify_sources(receipt['source_sha256']);verify_sources(receipt['inputs'])
    binding,scans,columns,precision,ports=prepare_window(unit)
    assert receipt['binding']==binding and receipt['columns']==[c.tolist() for c in columns]
    assert receipt['inputs']=={k:v for scan,_,_ in scans for k,v in scan.inputs.items()}
    state=np.asarray(receipt['best']['mean']);assigned=receipt['best']['associations']
    assert assigned==[int(np.argmax(p.score_all(state))) for p in ports]
    active={0,1,*np.flatnonzero(state).tolist()};gradient=precision*state;score_gradients=[]
    for p,i in zip(ports,assigned,strict=True):
        g=np.zeros(len(state))
        if i<p.candidate_count:
            pred=p.predict_selected(state,i);assert pred.eligible
            residual=p.observation-pred.mean;solved=np.linalg.solve(pred.covariance,residual)
            weight=(4+len(residual))/(4+float(residual@solved));g=weight*pred.jacobian.T@solved
            active.update(np.flatnonzero(np.any(pred.jacobian!=0,axis=0)).tolist())
        gradient-=g;score_gradients.append(g)
    def objective(x):return float(.5*(precision*x)@x-sum(p.score_selected(x,i) for p,i in zip(ports,assigned)))
    active=sorted(active);finite=[]
    for index in active:
        shift=np.zeros(len(state));shift[index]=.0005
        finite.append((objective(state+shift)-objective(state-shift))/.001)
    errors=np.abs(np.asarray(finite)-gradient[active]);worst=int(active[int(np.argmax(errors))])
    curves=[]
    for step in [.001,.0005,.0001,.00001,.000001]:
        shift=np.zeros(len(state));shift[worst]=step
        contributions=[]
        for index,(p,i,g) in enumerate(zip(ports,assigned,score_gradients,strict=True)):
            minus=p.score_selected(state-shift,i);plus=p.score_selected(state+shift,i)
            numeric=(plus-minus)/(2*step)
            contributions.append(dict(track=index,assignment=i,background=i>=p.candidate_count,
                observation_ids=list(p.observation_ids),score_minus=float(minus),score_plus=float(plus),
                score_derivative=float(numeric),analytic_score_derivative=float(g[worst]),
                disagreement=float(abs(numeric-g[worst]))))
        numeric=(objective(state+shift)-objective(state-shift))/(2*step)
        curves.append(dict(step=step,numeric_objective_derivative=numeric,analytic_objective_derivative=float(gradient[worst]),
            disagreement=float(abs(numeric-gradient[worst])),tracks=sorted(contributions,key=lambda r:r['disagreement'],reverse=True)[:5]))
    memberships=[dict(scan=binding['scans'][j],local_column=int(np.flatnonzero(c==worst)[0])) for j,c in enumerate(columns) if worst in c]
    save(HERE/'pair-gradient-diagnostic-v1.json',dict(unit=unit,worst_global_column=worst,memberships=memberships,
        reproduced_maximum_error=float(errors.max()),curves=curves,
        input_sha256={str(path):digest(path),str(audit_path):digest(audit_path)},source_sha256=digest(__file__),
        qualification='Fixed saved state and assignments, no optimization or geographic reference. Step sensitivity is diagnostic only; does not replace the original audit.'))
    print(json.dumps(dict(worst_column=worst,memberships=memberships,curves=curves),indent=2),flush=True)


if __name__=='__main__':main()
