"""Post-outcome attribution; never modifies frozen fits or selects a new model."""
import hashlib
import json
import math
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_27_rx_transfer_concentration'))
from verify_grouped_rebuild import verify
from conservative import lse


def describe(row,reciprocal,total_weight):
    ids=row['candidate_ids'];p=row['training_log_weights'];q=row['controls']['normal']['posterior_log_weights']
    f=row['held_frequency_ll'];ra=row['controls']['normal']['reception_ll']
    best=lambda a:max(range(len(a)),key=lambda i:a[i])
    pi,qi,fi=best(p),best(q),best(f)
    other=dict(zip(reciprocal['candidate_ids'],reciprocal['profiled_cfo_hz']))
    shifts={str(cid):other[cid]-cfo for cid,cfo in zip(ids,row['profiled_cfo_hz']) if cid in other}
    maxf=max(f);held_weights=[math.exp(v-lse(f)) for v in f]
    gain=row['controls']['normal']['gain']
    return {'track_id':row['track_id'],'direction':row['direction'],'candidate_ids':ids,
        'weight_seconds':row['weight_seconds'],'held_count':row['held_count'],
        'conditioning_count':len(row['training_observation_ids']),
        'gain':gain,'weighted_contribution':row['weight_seconds']*gain/total_weight,
        'frequency_map':ids[pi],'rx_map':ids[qi],'held_best_candidate':ids[fi],
        'map_changed':pi!=qi,'held_prefers_baseline_map':fi==pi,'held_prefers_rx_map':fi==qi,
        'frequency_probabilities':[math.exp(v) for v in p],
        'rx_probabilities':[math.exp(v) for v in q],
        'held_likelihood_normalized':held_weights,
        'held_total_loglik_gaps':[v-maxf for v in f],
        'rx_loglik_gaps':[v-max(ra) for v in ra],
        'frequency_log_weights':p,'rx_log_weights':q,
        'shared_id_cfo_other_minus_this_hz':shifts,
        'same_shortlist_set':set(ids)==set(reciprocal['candidate_ids']),
        'held_best_present_in_reciprocal_shortlist':ids[fi] in reciprocal['candidate_ids'],
        'reversed_gain':row['controls']['reversed']['gain']}


def analyze(shard):
    verify(shard)
    lookup={(r['track_id'],r['direction']):r for r in shard['records']}
    output={}
    for direction,reverse in [('X_to_Y','Y_to_X'),('Y_to_X','X_to_Y')]:
        rows=[r for r in shard['records'] if r['direction']==direction]
        total=sum(r['weight_seconds'] for r in rows)
        detail=[describe(r,lookup[r['track_id'],reverse],total) for r in rows]
        contribution=math.fsum(r['weighted_contribution'] for r in detail)
        if abs(contribution-shard['summary'][direction]['normal'])>1e-12:raise ValueError('gain does not close')
        worst=sorted(detail,key=lambda r:r['weighted_contribution'])[:5]
        best=sorted(detail,key=lambda r:-r['weighted_contribution'])[:5]
        split={}
        for label,selected in [('map_changed',[r for r in detail if r['map_changed']]),
                               ('map_unchanged',[r for r in detail if not r['map_changed']])]:
            split[label]={'tracks':len(selected),'contribution':math.fsum(r['weighted_contribution'] for r in selected)}
        output[direction]={'tracks':len(detail),'gain':contribution,
            'positive_contribution':math.fsum(max(0,r['weighted_contribution']) for r in detail),
            'negative_contribution':math.fsum(min(0,r['weighted_contribution']) for r in detail),
            'split':split,'worst_five':worst,'best_five':best,
            'same_shortlist_set_count':sum(r['same_shortlist_set'] for r in detail),
            'all_tracks':detail}
    return output


def main():
    summary=json.loads((HERE/'summary-v2.json').read_text());result={}
    for name,expected in summary['shard_sha256'].items():
        raw=(HERE/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('shard changed')
        shard=json.loads(raw);result[shard['session_id']]=analyze(shard)
    out={'scope':'Post-outcome diagnostic of all four recordings; no new fitted model or validation claim. Held-best identity is not physical truth; CFO differences are not drift rates.',
         'source_sha256':summary['shard_sha256'],'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'results':result}
    with (HERE/'regression-diagnostic.json').open('x') as stream:json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    for sid,dirs in result.items():
        for direction,v in dirs.items():
            print(sid,direction,'gain',v['gain'],'MAP split',v['split'],'same shortlist',v['same_shortlist_set_count'],'/',v['tracks'])
            if direction=='X_to_Y' and v['gain']<0:
                for r in v['worst_five'][:3]:print(json.dumps(r))


if __name__=='__main__':main()
