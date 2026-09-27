"""Compare fast and scalar solvers at the 44 previously selected real tracks."""
import importlib.util
import json
import sys
import time
from pathlib import Path
import numpy as np
from fast_solver import scores
from run_full import load_model,HERE,REPORTS,digest

def main():
    path=REPORTS/'2026_09_27_ds6_stationary_offsets/solver.py'
    spec=importlib.util.spec_from_file_location('scalar_reference_solver',path);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    selection_path=REPORTS/'2026_09_27_ds6_stationary_offsets/protocol.json';selection=json.loads(selection_path.read_text())
    protocol=json.loads((HERE/'protocol.json').read_text());rows=[]
    for session,ids in selection['selected'].items():
        base,x,_=load_model(session,protocol['center']);predictions=base.evaluate(x,False)['predictions']
        for t,pred in zip(base.tracks,predictions,strict=True):
            if t['track_id'] not in ids:continue
            residual=t['y'][None,:]-pred
            start=time.perf_counter();a,b,_=old.scores(residual,t['mask']);scalar_s=time.perf_counter()-start
            start=time.perf_counter();c,d,audits=scores(residual,t['mask']);fast_s=time.perf_counter()-start
            rows.append(dict(session_id=session,track_id=t['track_id'],candidates=len(audits),scalar_s=scalar_s,fast_s=fast_s,
                max_score_difference=float(max(np.max(np.abs(a-c)),np.max(np.abs(b-d)))),all_converged=all(r['converged'] for r in audits)))
    result=dict(source_sha256=digest(Path(__file__)),scalar_sha256=digest(path),fast_sha256=digest(HERE/'fast_solver.py'),
        selection_sha256=digest(selection_path),rows=rows,tracks=len(rows),candidates=sum(r['candidates'] for r in rows),
        maximum_score_difference=max(r['max_score_difference'] for r in rows),scalar_s=sum(r['scalar_s'] for r in rows),fast_s=sum(r['fast_s'] for r in rows))
    (HERE/'fast-real-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))

if __name__=='__main__':main()
