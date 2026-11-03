"""Postfit residual transfer by receiver, band and family on all 20 scans."""

import argparse
import itertools
from pathlib import Path
import numpy as np

from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,make_problem
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_18_ds23_learned_residuals'


def nearest_pairs(left,right,tolerance=.5):
    """Nearest-distance-first pairs, with no repeated observation."""
    left,right=np.asarray(left,float),np.asarray(right,float)
    if left.ndim!=1 or right.ndim!=1 or not np.isfinite(left).all() or not np.isfinite(right).all() or not np.isfinite(tolerance) or tolerance<0:
        raise ValueError('finite one-dimensional times and nonnegative tolerance required')
    distance=abs(left[:,None]-right[None,:]);ii,jj=np.where(distance<=tolerance)
    order=np.lexsort((jj,ii,distance[ii,jj]));used_left=set();used_right=set();a=[];b=[]
    for k in order:
        i,j=int(ii[k]),int(jj[k])
        if i in used_left or j in used_right:continue
        used_left.add(i);used_right.add(j);a.append(i);b.append(j)
    return np.array(a,int),np.array(b,int)


def run(case):
    scan=final_scan(case);original=read(SOURCE/case/'result.json')
    source=read(LEARNED/(case+'.json'));primary=source['results']['mean_and_distribution']
    assert not source['GPS_used'];keep=np.array(primary['mask'],bool);node=original['final_node']
    model=source['hyperparameters_from_pre_RF_TLE_only']
    base=problem(scan,node,'c0',keep);_,receipts=phase_widths(scan,base.labels)
    means=forecast_phase_mean(receipts,model['shrinkage'])
    weights=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    tracks=[];pairs=[];groups=[];replay=[]
    for arm in ('c0','fitted_c'):
        record=primary['arms'][arm];reference=np.zeros(len(means))
        for h in record['history']:
            p=make_problem(scan,node,keep,arm,reference,weights,means,model['multiplier'],model['nu'])
            xy=np.array(h['fit']['parameters']);reference=np.clip(p.state(xy)['phases'][p.labels],-15,15)
        c=p.calculate(xy);replay.append(float(p.residual(xy)@p.residual(xy)-record['score']))
        residual=c['conditional_residual_hz'];local=[]
        for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
            active=keep[sl]
            if not active.any():continue
            track=scan.tracks[i];t=track['times'][active];r=residual[sl][active];s=p.point_noise[sl][active]
            centered=t-t.mean();norm=float(centered@centered)
            data=dict(case=case,arm=arm,component=row['component'],norad=int(scan.norads[row['candidate_index']]),
                receiver=track['receiver'],band=int(track['channel']>4),channel=track['channel'],points=len(r),
                time_s=t,residual_hz=r,noise_hz=s,RMS_hz=float(np.sqrt(np.mean(r*r))),mean_hz=float(r.mean()),
                slope_hz_s=float(centered@r/norm) if norm else None,noise_precision=float(c['noise_precision'][k]),
                standardized_RMS=float(np.sqrt(np.mean((r/s)**2))))
            tracks.append(data);local.append(data)
        for rx in (1,2):
            for band in (0,1):
                selected=[r for r in local if r['receiver']==rx and r['band']==band]
                if not selected:continue
                values=np.concatenate([r['residual_hz'] for r in selected]);noise=np.concatenate([r['noise_hz'] for r in selected])
                groups.append(dict(case=case,arm=arm,receiver=rx,band=band,points=len(values),tracks=len(selected),
                    families=len({r['norad'] for r in selected}),RMS_hz=float(np.sqrt(np.mean(values**2))),
                    standardized_RMS=float(np.sqrt(np.mean((values/noise)**2))),median_noise_hz=float(np.median(noise))))
        for a,b in itertools.combinations(local,2):
            ia,ib=nearest_pairs(a['time_s'],b['time_s'])
            if len(ia)<6:continue
            aa,bb=np.asarray(a['residual_hz'])[ia],np.asarray(b['residual_hz'])[ib]
            if min(np.std(aa),np.std(bb))<=0:continue
            pairs.append(dict(case=case,arm=arm,left=a['component'],right=b['component'],pairs=len(ia),
                same_receiver=a['receiver']==b['receiver'],same_band=a['band']==b['band'],
                same_family=a['norad']==b['norad'],correlation=float(np.corrcoef(aa,bb)[0,1])))
    assert max(abs(np.array(replay)))<1e-6
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+'.json'),dict(case=case,tracks=tracks,pairs=pairs,groups=groups,replay_loss_differences=replay,
        GPS_used=False,source_sha256=sha(Path(__file__)),prior_input_sha256=sha(LEARNED/(case+'.json')),
        correlations_descriptive_and_conditioned_on_joint_fit=True,
        overlapping_track_pairs_are_not_independent_tests=True,matching_tolerance_s=.5,minimum_pairs=6))
    print(case,'tracks',len(tracks),'pairs',len(pairs),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
