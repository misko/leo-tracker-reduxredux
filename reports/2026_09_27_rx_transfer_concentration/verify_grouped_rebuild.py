"""Independent saved-score, partition, and binding checks for rebuild shards."""
import hashlib
import json
import math
from pathlib import Path
from conservative import blend, lse

HERE=Path(__file__).resolve().parent


def verify(value):
    if value.get('finished') is not True:raise ValueError('unfinished shard')
    labels={(o['track_id'],o['observation_id']):('X' if g['partition']=='train' else 'Y')
            for g in value['split']['groups'] for o in g['observations']}
    seen=set();per_direction={}
    for r in value['records']:
        key=(r['track_id'],r['direction'])
        if key in seen:raise ValueError('duplicate result')
        seen.add(key)
        train=r['training_observation_ids'];held=r['held_observation_ids']
        if len(train)<3 or len(held)<3 or set(train)&set(held):raise ValueError('bad partition')
        expected='X' if r['direction']=='X_to_Y' else 'Y'
        for oid in train:
            if labels[r['track_id'],oid]!=expected:raise ValueError('training labels differ')
        for oid in held:
            if labels[r['track_id'],oid]==expected:raise ValueError('held labels differ')
        if set(train)|set(held)!={oid for tid,oid in labels if tid==r['track_id']}:
            raise ValueError('missing observation')
        if len(held)!=r['held_count']:raise ValueError('held count mismatch')
        k=len(r['candidate_ids']);p=r['training_log_weights'];f=r['held_frequency_ll']
        if k!=3 or len(set(r['candidate_ids']))!=3 or len(p)!=k or len(f)!=k:raise ValueError('candidate alignment')
        u=[-math.log(k)]*k;baseline=blend(p,u,.5)
        base=-lse([a+b for a,b in zip(baseline,f)])/len(held)
        if abs(base-r['baseline_nll'])>1e-10:raise ValueError('baseline score differs')
        for mode,v in r['controls'].items():
            q=[a+b for a,b in zip(p,v['reception_ll'])];z=lse(q);q=[a-z for a in q]
            if any(abs(a-b)>1e-10 for a,b in zip(q,v['posterior_log_weights'])):raise ValueError('posterior differs')
            mixed=blend(q,u,.5);nll=-lse([a+b for a,b in zip(mixed,f)])/len(held)
            if abs(nll-v['nll'])>1e-10 or abs(base-nll-v['gain'])>1e-10:raise ValueError('RX score differs')
            check=v['quadrature']
            if not check['passed'] or check['maximum_candidate_loglik_absolute_difference']>.001:raise ValueError('quadrature failed')
            if mode=='null' and abs(v['gain'])>1e-10:raise ValueError('null failed')
        per_direction.setdefault(r['direction'],[]).append(r)
    x={tid for tid,d in seen if d=='X_to_Y'};y={tid for tid,d in seen if d=='Y_to_X'}
    if x!=y:raise ValueError('missing reciprocal result')
    unsupported={r['track_id'] for r in value['unsupported']}
    if x&unsupported or x|unsupported!={tid for tid,oid in labels}:raise ValueError('track accounting')
    for direction,rows in per_direction.items():
        for mode in ('normal','reversed','null'):
            gain=math.fsum(r['weight_seconds']*r['controls'][mode]['gain'] for r in rows)/sum(r['weight_seconds'] for r in rows)
            if abs(gain-value['summary'][direction][mode])>1e-12:raise ValueError('aggregate differs')
    return {'supported_tracks':len(x),'unsupported_tracks':len(unsupported),'summary':value['summary']}


def main():
    paths=sorted(HERE.glob('grouped-rebuild-scan-fw-*.json'))
    if not paths:raise ValueError('no outputs')
    for path in paths:
        value=json.loads(path.read_text())
        for name,expected in value['code_hashes'].items():
            if 'sha256:'+hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=expected:raise ValueError('code binding changed')
        print(value['session_id'],verify(value))


if __name__=='__main__':main()
