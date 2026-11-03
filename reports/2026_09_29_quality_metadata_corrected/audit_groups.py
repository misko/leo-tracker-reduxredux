import collections
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    rows=[]
    for ds in ('DS7','DS8','DS9'):
        path=HERE/f'{ds}.json'
        data=json.loads(path.read_text())
        groups=collections.defaultdict(list)
        for p in data['rows']:
            groups[p['source_group_id']].append(p)
        shared=[v for v in groups.values() if len({x['track_id'] for x in v})>1]
        alternatives=[v for v in shared if len({x['candidate_id'] for x in v})>1]
        assert all(len({x['training'] for x in v})==1 for v in groups.values())
        rows.append(dict(dataset=ds,observations=len(data['rows']),source_groups=len(groups),multi_track_groups=len(shared),distinct_candidate_multi_track_groups=len(alternatives),observations_in_distinct_candidate_multi_track_groups=sum(len(v) for v in alternatives),maximum_group_multiplicity=max(map(len,groups.values())),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),groups=[dict(source_group_id=v[0]['source_group_id'],observations=[dict(track_id=x['track_id'],index=x['index'],candidate_id=x['candidate_id'],candidate_rank=x['candidate_rank'],training=x['training']) for x in v]) for v in alternatives]))
    with (HERE/'group-overlap.json').open('x') as out:
        json.dump(dict(rows=rows),out,indent=2)
    print([{k:v for k,v in r.items() if k!='groups'} for r in rows])


if __name__=='__main__':
    main()
