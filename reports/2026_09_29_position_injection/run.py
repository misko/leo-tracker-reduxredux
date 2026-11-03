import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
import numpy as np
from inject import shifted_track

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main(ds):
    started=time.monotonic()
    helper_path=HERE.parent/'2026_09_29_receiver_holdout/run.py'
    spec=importlib.util.spec_from_file_location('receiver_helper',helper_path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    source=HERE.parent/'2026_09_29_source_consistent_n8/manifest.json'
    plan=json.loads(source.read_text());items=[s for s in plan['scans'] if s['real_dataset']==ds]
    prior_path=HERE.parent/f'2026_09_29_time_balanced_scans/grid_{ds}_balanced_0.json'
    old=json.loads(prior_path.read_text())['selected'];assert old['qualified']
    paths=[source,prior_path,helper_path,HERE/'run.py',HERE/'inject.py',HERE/'PROTOCOL.md',
           ROOT/'tools/ds7_fast_baseline_adapter.py',ROOT/'tools/ds7_baseline_adapter.py',
           HERE.parent/'2026_09_29_unassociated_trend/trend_mixture.py',
           HERE.parent/'2026_09_29_frequency_contrast/contrast_position.py']
    for item in items:
        for artifact in item['input']['artifacts']:
            p=Path(artifact['path']);assert 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()==artifact['sha256'];paths.append(p)
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=[s['input'] for s in items]))
    def model(dd):return helper.TrendMixturePosition(dd,plan['config'],helper.baseline.Stationary,.2)
    original=model(docs);x=np.array(old['x']);scored=original.evaluate(x,gradient=False,held=True)
    assert abs(scored['score']-old['score'])<1e-7
    metadata={(r['session_id'],r['track_id']):r for r in scored['rows']}
    result=[]
    for name,shift in [('east',[1.,0.]),('north',[0.,1.])]:
        target=x.copy();target[:2]+=shift
        injected=[];ledger=[];audit=0.
        for i,d in enumerate(docs):
            tracks=[]
            for t in d['tracks']:
                row=metadata[d['session_id'],t['track_id']]
                k=int(np.argmax(row['weights_given_signal']))
                before,v0=original.models[i].prediction(t,[x[0],x[1],x[i+2]])
                after,v1=original.models[i].prediction(t,[target[0],target[1],target[i+2]])
                assert np.array_equal(v0,v1)
                moved=shifted_track(t,before,after,k)
                discrepancy=float(np.max(abs((moved['y']-after[k])-(t['y']-before[k]))))
                audit=max(audit,discrepancy);assert discrepancy<1e-7
                np.testing.assert_array_equal(shifted_track(t,before,before,k)['y'],t['y'])
                tracks.append(moved)
                ledger.append(dict(session_id=d['session_id'],track_id=t['track_id'],candidate_index=k,signal_responsibility=row['signal_responsibility'],conditional_probability=row['weights_given_signal'][k]))
            injected.append(dict(d,tracks=tracks))
        m=model(injected)
        starts=[dict(helper.fit_model(m,initial),initial=initial.tolist()) for initial in [x,target]]
        valid=[s for s in starts if s['qualified']];best=max(valid,key=lambda s:s['score']) if valid else None
        entry=dict(direction=name,injected_shift_km=shift,residual_preservation_max_hz=audit,ledger=ledger,starts=starts,selected=best)
        if best:
            recovered=np.array(best['x'])-x
            final=m.evaluate(best['x'],gradient=False,held=True)
            new={(r['session_id'],r['track_id']):int(np.argmax(r['weights_given_signal'])) for r in final['rows']}
            entry.update(recovered_shift_km=recovered[:2].tolist(),shift_recovery_error_m=float(np.linalg.norm(recovered[:2]-shift)*1000),max_timing_change_s=float(max(abs(recovered[2:]))),candidate_changes=sum(new[r['session_id'],r['track_id']]!=r['candidate_index'] for r in ledger))
        result.append(entry)
    with (HERE/f'{ds}.json').open('x') as out:
        json.dump(dict(dataset=ds,baseline=old,results=result,elapsed_seconds=time.monotonic()-started,hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}),out,indent=2,allow_nan=False)
    print(ds,[(r['direction'],r.get('shift_recovery_error_m')) for r in result],time.monotonic()-started,flush=True)


if __name__=='__main__':main(sys.argv[1])
