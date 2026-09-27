"""Exact-propagation score checks at both selected full-cohort solutions."""
import importlib.util
import json
import sys
import time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
s=importlib.util.spec_from_file_location('envelope',HERE/'run.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
started=time.monotonic();fits={a:json.loads((HERE/f'all-{a}.json').read_text()) for a in ['cfo_only','phase']};assert all(r['complete'] for r in fits.values());parent=json.loads((ROOT/'2026_09_27_ds6_fresh_joint43/protocol.json').read_text());rows=[]
module=sys.modules[m.fresh.Objective.__module__];original=module.robust_scores
try:
    for i,sid in enumerate(parent['splits']['all']):
        model,_,banks=m.fresh.load_model(sid,parent['center']);row=dict(session_id=sid,arms={})
        for arm,r in fits.items():
            x=np.array([r['x'][0],r['x'][1],r['x'][i+2]]);cache=m.ProfileCache();module.robust_scores=cache.score;cache.reset();approx=model.evaluate(x,False);cache.reset();exact=model.evaluate(x,False,exact_banks=banks(np.array([x[2]])));difference=max(float(np.max(abs(a-b))) for a,b in zip(approx['predictions'],exact['predictions']))
            row['arms'][arm]=dict(train_change=exact['train']-approx['train'],held_change=exact['held']-approx['held'],maximum_prediction_error_hz=difference)
        rows.append(row)
        print('audited',len(rows),round(time.monotonic()-started,1),flush=True)
finally:module.robust_scores=original
(HERE/'propagation-audit.json').write_text(json.dumps(dict(complete=True,fit_hashes={a:m.fresh.digest(HERE/f'all-{a}.json') for a in fits},scans=rows,scope='CFO contributions at both coordinates; phase factors not repropagated here',elapsed_s=time.monotonic()-started),indent=2)+'\n')
