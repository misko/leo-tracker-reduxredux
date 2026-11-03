import hashlib
import importlib.util
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from core import moments,pack,density,conditional

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent


def read(p):return json.loads(p.read_text())


def main():
    started=time.monotonic();hashes={}
    pair_path=REPORTS/'2026_09_30_rx_difference_calibration/results.json'
    pairs=read(pair_path)
    for name,digest in pairs['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
        hashes[name]=digest
    features=defaultdict(list)
    for p in pairs['pairs']:
        for rx in [0,1]:features[p['dataset'],p['session_id'],p[f'track{rx}']].append(np.log(p['feature']))
    features={key:float(np.exp(np.median(values))) for key,values in features.items()}
    donor_path=REPORTS/'2026_09_29_donor_residual_transfer/plan.json';donor=read(donor_path)
    names={Path(c['source']).parent.name for c in pairs['summary']['coverage'] if c['dataset']!='DS10'}
    units=[dict(dataset=u['unit_id'].split('_')[0],unit_id=u['unit_id'],inputs=u['group']['inputs'],x=u['x'],score=u['training_score']) for u in donor['units'] if u['unit_id'] in names]
    assert len(units)==9
    ds10path=REPORTS/'2026_09_29_ds10_geographic/fits/N24_h0/result.json';ds10=read(ds10path)
    ds10plan_path=REPORTS/'2026_09_29_ds10_geographic/plan.json';ds10plan=read(ds10plan_path)
    assert donor['config']==ds10plan['config'] and ds10['selected']['qualified']
    for name,digest in ds10['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
        hashes[name]=digest
    captures={c['session_id']:c for c in ds10plan['captures']}
    inputs=[read(ds10plan_path.parent/'exports'/captures[s]['unit_id']/'validated.json')['input'] for s in ds10['sessions']]
    units.append(dict(dataset='DS10',unit_id='DS10_N24',inputs=inputs,x=ds10['selected']['x'],score=ds10['selected']['score']))
    spec=importlib.util.spec_from_file_location('budget',REPORTS/'2026_09_29_scan_budget/run.py')
    budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget);helper=budget.helper
    rows=[];coverage=[];max_audit=0.
    for unit in units:
        for entry in unit['inputs']:
            for artifact in entry['artifacts']:
                path=Path(artifact['path']);digest=hashlib.sha256(path.read_bytes()).hexdigest()
                assert 'sha256:'+digest==artifact['sha256']
                hashes[str(path)]=digest
        docs=helper.baseline.load_documents(dict(config=donor['config'],inputs=unit['inputs']))
        model=helper.TrendMixturePosition(docs,donor['config'],helper.baseline.Stationary,.2)
        x=unit['x'];scored=model.evaluate(x,gradient=False,held=True)
        assert abs(scored['score']-unit['score'])<1e-7
        reference={(r['session_id'],r['track_id']):r for r in scored['rows']}
        count=0
        for i,(doc,engine) in enumerate(zip(docs,model.models,strict=True)):
            for track in doc['tracks']:
                key=(unit['dataset'],doc['session_id'],track['track_id'])
                if key not in features:continue
                count+=1;pred,visible=engine.prediction(track,[*x[:2],x[i+2]])
                y,t,mask=track['y'],np.asarray(track['times_s']),track['mask']
                train=moments(y[mask],t[mask],pred[:,mask],visible);full=moments(y,t,pred,visible)
                training=density(pack([train]),np.log([100.]))[0][0]
                held=conditional(pack([train]),pack([full]),np.log([100.]))[0][0]
                ref=reference[doc['session_id'],track['track_id']]
                audit=max(abs(training-ref['training_log_score']),abs(held-ref['held_log_score']))
                assert audit<1e-7;max_audit=max(max_audit,audit)
                rows.append(dict(dataset=unit['dataset'],session_id=doc['session_id'],track_id=track['track_id'],rx=track['receiver_id'],feature=features[key],
                                 training=train,full=full,held_observations=int((~mask).sum()),baseline_held=float(held)))
        coverage.append(dict(unit=unit['unit_id'],tracks=len(reference),supported=count))
        print(unit['unit_id'],count,flush=True)
    assert len(rows)==len(features)
    for path in [pair_path,donor_path,ds10path,ds10plan_path,HERE/'prepare.py',HERE/'core.py',HERE/'PROTOCOL.md',HERE/'test_core.py']:
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    with (HERE/'statistics.json').open('x') as out:
        json.dump(dict(rows=rows,coverage=coverage,max_baseline_audit=max_audit,hashes=hashes,elapsed_seconds=time.monotonic()-started),out,indent=2,allow_nan=False)
    print('Complete',len(rows),'audit',max_audit,flush=True)


if __name__=='__main__':main()
