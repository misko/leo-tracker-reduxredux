"""Post-result robustness audit; does not tune or replace frozen model settings."""
import json
from collections import defaultdict
import numpy as np
import model_eval as m
from prepare import HERE, digest


def shuffle_within_lanes(rows, seed):
    rng=np.random.default_rng(seed); result=[dict(r) for r in rows]; groups=defaultdict(list)
    for r in result:
        if r['split']=='holdout':
            key=(r['session_id'],r['receiver_id'],r['channel'],r['edge'],r['sample_rate_hz'])
            groups[key].append(r)
    moved=0
    for group in groups.values():
        tracks=defaultdict(list)
        for r in group:tracks[r['track_id']].append(r)
        ids=sorted(tracks); permutation=rng.permutation(ids)
        for rr in tracks.values():rr.sort(key=lambda r:r['observation_utc_ns'])
        directions={tid:[(r['east'],r['up']) for r in rr] for tid,rr in tracks.items()}
        for target, donor in zip(ids,permutation,strict=True):
            rr=tracks[target]; values=directions[donor]
            if target!=donor:moved+=1
            for r,i in zip(rr,np.rint(np.linspace(0,len(values)-1,len(rr))).astype(int),strict=True):
                r['east'],r['up']=values[i]
    return result,moved


def main():
    data=(HERE/'model_rows.json').read_bytes(); rows=json.loads(data)
    # Existing joint channel-edge encoding now also contains receiver identity.
    rich=[dict(r,channel=f"{r['receiver_id']}:{r['channel']}") for r in rows]
    result={'scope':'Additional post-result audit, no threshold/penalty selection or model tuning',
            'row_file_sha256':digest(data),
            'receiver_specific_lane_baseline':m.evaluate(rich)}
    original={outcome:(m.fit_detection_models(rows) if outcome=='detection' else m.fit_continuous_models(rows))
              for outcome in ('detection','continuous')}
    values=defaultdict(list); moved=[]
    for seed in range(20260927,20261027):
        shuffled,n=shuffle_within_lanes(rows,seed); moved.append(n)
        test=[r for r in shuffled if r['split']=='holdout']
        for outcome, fits in original.items():
            values[outcome].append(m.score_models(fits,test)['equal_track']['M1'])
    result['stratified_heldout_direction_shuffle']={
        'rule':'100 fixed seeds; shuffle whole direction trajectories only within scan, receiver, channel, edge and sample rate; fixed original fitted coefficients. Descriptive control, not a permutation p-value.',
        'replicates':100,'moved_track_count_quantiles_10_50_90':np.quantile(moved,[.1,.5,.9]).tolist(),
        **{key:{'M1_loss_quantiles_025_50_975':np.quantile(v,[.025,.5,.975]).tolist()} for key,v in values.items()}}
    (HERE/'stricter_controls.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result['receiver_specific_lane_baseline'][k]['heldout'] for k in ('detection','continuous')},indent=2))
    print(json.dumps(result['stratified_heldout_direction_shuffle'],indent=2))


if __name__=='__main__':main()
