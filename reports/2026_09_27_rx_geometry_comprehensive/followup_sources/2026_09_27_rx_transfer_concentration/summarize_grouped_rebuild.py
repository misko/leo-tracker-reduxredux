"""Require and independently check the full six-recording development cohort."""
import hashlib
import json
import math
from pathlib import Path
from verify_grouped_rebuild import verify

HERE=Path(__file__).resolve().parent


def main():
    fixed=HERE.parent/'2026_09_27_roof_location_geometry/topology_frequency_fixedpoint.json'
    sessions=sorted(json.loads(fixed.read_text())['final_tracks'])
    shards=[];hashes={}
    for sid in sessions:
        path=HERE/f'grouped-rebuild-{sid}.json';raw=path.read_bytes();d=json.loads(raw)
        if d['session_id']!=sid:raise ValueError('session changed')
        verify(d)
        for name,expected in d['code_hashes'].items():
            if 'sha256:'+hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=expected:raise ValueError('code changed')
        shards.append(d);hashes[path.name]=hashlib.sha256(raw).hexdigest()
    if len(shards)!=6 or sum(len(s['records'])//2+len(s['unsupported']) for s in shards)!=344:
        raise ValueError('cohort mismatch')
    results={}
    for direction in ('X_to_Y','Y_to_X'):
        rows=[r for s in shards for r in s['records'] if r['direction']==direction]
        total=sum(r['weight_seconds'] for r in rows)
        modes={}
        for mode in ('normal','reversed','null'):
            per={s['session_id']:s['summary'][direction][mode] for s in shards}
            modes[mode]={'occupied_second_weighted_gain':math.fsum(r['weight_seconds']*r['controls'][mode]['gain'] for r in rows)/total,
                'equal_recording_gain':math.fsum(per.values())/6,'recordings_improving':sum(v>1e-10 for v in per.values()),'per_recording':per}
        results[direction]={'tracks':len(rows),'held_observations':sum(r['held_count'] for r in rows),'weight_seconds':total,'modes':modes}
    output={'scope':'Conditional randomized-block development replay; not fully nested validation or geographic resolution.',
        'supported_tracks':sum(len(s['records'])//2 for s in shards),'unsupported_tracks':sum(len(s['unsupported']) for s in shards),
        'source_sha256':hashes,'results':results,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'verifier_sha256':hashlib.sha256((HERE/'verify_grouped_rebuild.py').read_bytes()).hexdigest()}
    with (HERE/'grouped-rebuild-summary.json').open('x') as stream:json.dump(output,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(output,indent=2))


if __name__=='__main__':main()
