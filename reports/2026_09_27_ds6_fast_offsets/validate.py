"""Compare batched solver with sealed pooled scalar-offset results."""
import importlib.util
import json
import time
from pathlib import Path
import numpy as np
from solver import fit
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('audit',ROOT/'2026_09_27_ds6_pooled_offset_audit/run.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


def run():
    start=time.monotonic();source=ROOT/'2026_09_27_ds6_pooled_offset_audit/results.json';prior=json.loads(source.read_text());assert prior['complete'];p=json.loads((source.parent/'protocol.json').read_text());parent=json.loads((ROOT/'2026_09_27_ds6_fresh_joint43/protocol.json').read_text());x=p['x'];rows=[];solve_seconds=0.;fallbacks=0
    for si,s in enumerate(prior['scans']):
        model,_,banks=audit.fresh.load_model(s['session_id'],parent['center']);point=np.array([x[0],x[1],x[si+2]]);exact=banks(np.array([point[2]]));evaluation=model.evaluate(point,False,exact_banks=exact);old={t['track_id']:t for t in s['tracks']};tracks=[]
        for t,pred in zip(model.tracks,evaluation['predictions']):
            candidates=old[t['track_id']]['candidates'];ids=exact[t['track_id']][2];indices=[int(np.flatnonzero(ids==c['candidate_index'])[0]) for c in candidates];res=t['y'][None,:]-pred[indices];started=time.monotonic();offset,info=fit(res[:,t['mask']]);solve_seconds+=time.monotonic()-started;fallbacks+=info['fallbacks'];gains=[];shifts=[]
            for row,o,c in zip(res,offset,candidates):
                score,_=audit.score(row,t['mask'],o);gains.append(score-c['new_train']);shifts.append(float(o-c['new_offset_hz']))
            tracks.append(dict(track_id=t['track_id'],score_differences=gains,offset_differences_hz=shifts,**info))
        rows.append(dict(session_id=s['session_id'],tracks=tracks));print(s['session_id'],round(time.monotonic()-start,1),flush=True)
    (HERE/'validation.json').write_text(json.dumps(dict(complete=True,source_sha256=audit.fresh.digest(source),solver_sha256=audit.fresh.digest(HERE/'solver.py'),scans=rows,solve_seconds=solve_seconds,fallbacks=fallbacks,elapsed_s=time.monotonic()-start),indent=2)+'\n')


if __name__=='__main__':run()
