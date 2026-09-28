"""Verify all frozen disjoint shards and apply the protocol's progression gate."""
import hashlib
import json
import math
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_27_rx_transfer_concentration'))
from verify_grouped_rebuild import verify


def gate(results):
    checks={}
    for direction in ('X_to_Y','Y_to_X'):
        normal=results[direction]['normal'];reverse=results[direction]['reversed']
        checks[direction+'_pooled_positive']=normal['pooled_gain']>0
        checks[direction+'_equal_recording_positive']=normal['equal_recording_gain']>0
        checks[direction+'_three_recordings']=normal['recordings_improving']>=3
        checks[direction+'_beats_reversal']=normal['pooled_gain']>reverse['pooled_gain']
    return {'advance':all(checks.values()),'checks':checks}


def main():
    contract_bytes=(HERE/'contract.json').read_bytes();contract=json.loads(contract_bytes)
    for path,expected in contract['files'].items():
        if 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected:raise ValueError('frozen file changed')
    shards=[];hashes={};support={}
    for sid in contract['session_ids']:
        path=HERE/f'disjoint-{sid}.json';raw=path.read_bytes();value=json.loads(raw)
        if value['session_id']!=sid or value['contract_sha256']!='sha256:'+hashlib.sha256(contract_bytes).hexdigest():raise ValueError('contract mismatch')
        support[sid]=verify(value)
        shards.append(value);hashes[path.name]=hashlib.sha256(raw).hexdigest()
    if len(shards)!=4:raise ValueError('require all four frozen recordings')
    results={}
    for direction in ('X_to_Y','Y_to_X'):
        rows=[r for s in shards for r in s['records'] if r['direction']==direction]
        results[direction]={}
        for mode in ('normal','reversed','null'):
            per={s['session_id']:s['summary'][direction][mode] for s in shards}
            results[direction][mode]={'pooled_gain':math.fsum(r['weight_seconds']*r['controls'][mode]['gain'] for r in rows)/sum(r['weight_seconds'] for r in rows),
                'equal_recording_gain':math.fsum(per.values())/4,'recordings_improving':sum(v>1e-10 for v in per.values()),'per_recording':per}
    out={'scope':'Four-recording frozen predictive test; conditional on reconstructed tracks. Not geographic resolution.',
         'results':results,'support':support,'gate':gate(results),'shard_sha256':hashes,
         'contract_sha256':hashlib.sha256(contract_bytes).hexdigest(),'scorer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out['reporting_revision']='v2: count improvements above 1e-10 numerical tolerance; v1 counted signed null roundoff. Scores and gate unchanged.'
    with (HERE/'summary-v2.json').open('x') as stream:json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
