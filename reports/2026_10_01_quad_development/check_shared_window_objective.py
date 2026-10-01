"""Fixed-state complete-window directional derivative checks; no optimization."""
import json
from pathlib import Path
import time
import numpy as np
from run_window import prepare_window
from run_constituent_pair import save,digest,verify_sources
from shared_visibility_port import SharedVisibilityPort
from shared_window_objective import WindowObjective

HERE=Path(__file__).resolve().parent


def main():
    cases=[('DS9-B01-S1','independent-v2/DS9-B01'),('DS10-B01-D1','independent-v2/DS10-B01'),
           ('DS11-B01-Q','independent-v2/DS11-B01'),('DS11-B03-D2','constituent-pair-v3/DS11-B03-D2')]
    rows=[];inputs={};rng=np.random.default_rng(402)
    for unit,directory in cases:
        begun=time.monotonic();path=HERE/directory/(unit+'.json')
        assert digest(path)==path.with_suffix('.sha256').read_text().strip()
        receipt=json.loads(path.read_text());verify_sources(receipt['source_sha256']);verify_sources(receipt['inputs']);inputs[str(path)]=digest(path)
        binding,scans,columns,precision,original=prepare_window(unit)
        assert receipt['binding']==binding and receipt['inputs']=={k:v for s,_,_ in scans for k,v in s.inputs.items()}
        ports=[SharedVisibilityPort(p.local,.1) for p in original]
        model=WindowObjective(ports,[p.columns for p in original],precision)
        state=np.asarray(receipt['best']['mean']);value,g,labels=model.evaluate(state)
        directions=[np.eye(1,len(state),i)[0] for i in [0,1]]
        for _ in range(3):
            d=rng.normal(size=len(state));d[:2]=0;d/=np.linalg.norm(d);directions.append(d)
        checks=[]
        for index,direction in enumerate(directions):
            for h in [.0005,.0001]:
                vp=model.evaluate(state+h*direction,labels,False)[0]
                vm=model.evaluate(state-h*direction,labels,False)[0]
                numeric=(vp-vm)/(2*h);analytic=float(g@direction);error=abs(numeric-analytic)
                assert error<.002,(unit,index,h,error)
                checks.append(dict(direction=index,step=h,analytic=analytic,numeric=numeric,error=error))
        row=dict(unit=unit,size=binding['size'],tracks=len(ports),dimensions=len(state),objective=value,
            gradient_norm=float(np.linalg.norm(g)),checks=checks,seconds=time.monotonic()-begun)
        rows.append(row);print(json.dumps(dict(unit=unit,max_error=max(c['error'] for c in checks),seconds=row['seconds'])),flush=True)
    save(HERE/'shared-window-objective-check-v1.json',dict(rows=rows,input_sha256=inputs,
        source_sha256={str(p):digest(p) for p in [Path(__file__).resolve(),HERE/'shared_window_objective.py',HERE/'shared_visibility_port.py']},
        qualification='Fixed saved states, newly selected hard labels frozen for perturbations, width0.1deg. Full objective including Gaussian priors. Five directions/two steps perwindow; not exhaustive coordinate audit, no optimization or geographic scoring.'))


if __name__=='__main__':main()
