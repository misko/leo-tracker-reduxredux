"""Audit split support using saved provenance only; no new model scores."""
import collections
import hashlib
import json
from pathlib import Path
from grouped_split import randomized_groups

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_27_roof_balanced_confirmation'


def main():
    sessions=[]
    for path in sorted(SOURCE.glob('association-transfer-scan-fw-*.json')):
        raw=path.read_bytes();shard=json.loads(raw);rows=[]
        for track in shard['tracks']:
            rows.extend({**r,'track_id':track['track_id']} for r in track['split']['observation_assignments'])
        split=randomized_groups(rows,shard['held_session'])
        labels={(o['track_id'],o['observation_id']):g['partition'] for g in split['groups'] for o in g['observations']}
        counts=collections.defaultdict(collections.Counter)
        for r in rows:counts[r['track_id']][labels[r['track_id'],r['observation_id']]]+=1
        supported=[tid for tid,c in counts.items() if c['train']>=3 and c['A']>=1 and c['B']>=1]
        old_counts=collections.Counter((bool(r['training']),labels[r['track_id'],r['observation_id']]) for r in rows)
        sessions.append({'session_id':shard['held_session'],'source_sha256':hashlib.sha256(raw).hexdigest(),
            'tracks':len(counts),'supported_min_train3_A1_B1':len(supported),
            'partition_group_counts':dict(collections.Counter(g['partition'] for g in split['groups'])),
            'track_counts':dict(counts),'old_training_to_new_partition':{str(k):v for k,v in old_counts.items()},
            'split':split})
    if len(sessions)!=6 or sum(s['tracks'] for s in sessions)!=344:raise ValueError('cohort mismatch')
    out={'scope':'Feasibility only, existing six calibration recordings; no new validation scores. Whole-session grouping of 10-second blocks joined by raw overlap, opportunities and pairs.',
         'grouping_code_sha256':hashlib.sha256((HERE/'grouped_split.py').read_bytes()).hexdigest(),
         'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'sessions':sessions}
    with (HERE/'grouped-feasibility.json').open('x') as stream:json.dump(out,stream,indent=2);stream.write('\n')
    for s in sessions:print(s['session_id'],s['supported_min_train3_A1_B1'],s['tracks'],s['partition_group_counts'],s['old_training_to_new_partition'])


if __name__=='__main__':main()
