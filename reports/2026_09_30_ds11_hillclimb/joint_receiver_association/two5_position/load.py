"""Load an unchanged estimator with newly bound family0/1 transfer evidence."""
import inspect
import numpy as np
from common import HERE,PARENT,JOBS,base,read,digest,fast,bindings,verify_sources
from whole_source_fast import WholeSourcePosition


def seeds(original):
    if original is not None and original['qualified']:
        return [np.array(original['x']),np.zeros(3)]
    return [np.zeros(3),np.array([0.,0.,2.])]


def load(cohort,index,arm):
    family=next(f for c,i,f in JOBS if (c,i)==(cohort,index))
    pp=base(cohort)/'plan.json';plan=read(pp);entry=plan['inputs'][index]
    bp=HERE/f'input-{cohort}-{index:02d}.json';bound=read(bp);verify_sources(bound)
    cp=PARENT/f'acquisition_calibration/fit-{family}.json';cal=read(cp);verify_sources(cal)
    tp=PARENT/'extra_donors/transfer-summary.json';transfer=read(tp);verify_sources(transfer)
    assert transfer['families'][str(family)]['passed']
    assert all(a['selected']['qualified'] for a in cal['arms'].values())
    assert digest(cp)==transfer['sources'][str(cp)]
    doc=fast.load_documents(dict(config=plan['config'],inputs=[entry]))[0]
    paths={}
    for a in entry['artifacts']:
        assert digest(a['path'])==a['sha256'].removeprefix('sha256:')
        paths[a['path']]=digest(a['path'])
    obs=next(a['path'] for a in entry['artifacts'] if a['kind']=='observations')
    bank=next(a['path'] for a in entry['artifacts'] if a['kind']=='candidates' and a['path'].endswith('.npz'))
    mp=next(a['path'] for a in entry['artifacts'] if a['kind']=='candidates' and a['path'].endswith('.json'))
    manifest=read(mp)
    ip=PARENT.parent/'source_balance/catalogue_identities.json' if cohort=='original' else base(cohort)/'catalogue_identities.json'
    ids=read(ip)['scans'][str(index)]
    assert ids['bank_sha256']==digest(bank) and ids['manifest_sha256']==digest(mp) and ids['observation_sha256']==digest(obs)
    assert ids['session_id']==entry['session_id']
    assert all(s['collected_utc_ns']<doc['start_utc_ns'] for s in manifest['provider_sources'])
    assert cal['sample_rate_hz']==doc['sample_rate_hz'] and sorted({t['rf_hz'] for t in doc['tracks']})==cal['frequencies']
    with np.load(bank,allow_pickle=False) as data:
        for t in manifest['tracks']:np.testing.assert_array_equal(data[f"candidate_ids_{t['index']}"],ids['tracks'][t['track_id']]['candidate_ids'])
    op=base(cohort)/f'runs/{index:02d}_iid.json';original=read(op)['selected']
    sources=bindings([pp,bp,cp,tp,ip,op,HERE/'PROTOCOL.md',HERE/'common.py',HERE/'load.py',
                      *[PARENT/p for p in ('whole_source_fast.py','whole_source_position.py','source_partition_fast.py','source_partition.py','joint_position.py','position_run.py','doppler_pilot.py')],inspect.getfile(fast),inspect.getfile(fast.baseline)])
    sources.update(paths)
    return WholeSourcePosition(doc,plan['config'],bound,cal,arm),seeds(original),original,sources
