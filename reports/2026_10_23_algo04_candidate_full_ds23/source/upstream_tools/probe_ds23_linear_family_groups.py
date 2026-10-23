"""RF-only grouped nominations from unused linear fragments; no calibration fit."""

from concurrent.futures import ProcessPoolExecutor
from itertools import combinations
from pathlib import Path
import signal
import time

import numpy as np

import run_ds23_dbg01_iteration_007 as runner
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from ds23_family_cavity import coarse_phase_scores
from ds23_conditioned_relative_nomination import unresolved_curve_score
from ds23_temporal_predictive_recovery import calibration
from probe_ds23_family_cavity_nominations import candidate_prediction
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.retained_track_likelihood import PERIOD,profile,whitening
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'linear_family_groups'


def candidate_groups(tracks,curved,accepted,maximum_groups=24):
    eligible=[i for i,t in enumerate(tracks) if i not in curved and len(t['times'])>=8 and np.ptp(t['times'])>=6
              and not (set(t['observation_ids'])&set(accepted))]
    result=[]
    for size in [2,3]:
        for group in combinations(eligible,size):
            owners={(tracks[i]['receiver'],tracks[i]['channel']) for i in group}
            if len(owners)<2:continue
            start=min(tracks[i]['times'][0] for i in group);end=max(tracks[i]['times'][-1] for i in group)
            if end-start>60:continue
            edges=[]
            for a,b in combinations(group,2):
                gap=max(tracks[a]['times'][0],tracks[b]['times'][0])-min(tracks[a]['times'][-1],tracks[b]['times'][-1])
                if gap<=10:edges.append((a,b))
            connected={group[0]}
            for _ in group:
                for a,b in edges:
                    if a in connected or b in connected:connected.update([a,b])
            if len(connected)!=size:continue
            ids=[o for i in group for o in tracks[i]['observation_ids']]
            if len(ids)!=len(set(ids)):continue
            result.append(tuple(group))
    return sorted(result,key=lambda g:(-sum(len(tracks[i]['times']) for i in g),tuple(tracks[i]['key'] for i in g)))[:maximum_groups]


def group_data(d,p,x,indices):
    c,covariance=calibration(p,x,d['powers']);nb=p.hardware.shape[1]+p.smooth.shape[1]
    dummy=p.labels[0];entries=[dict(track_index=i,candidate_index=dummy,alias=0) for i in indices]
    view,values,sigma,groups,slices=linear_geometry(p,entries);geometry=geometry_features(view,x,0.)
    radio=geometry['features'][:,:nb];noise=sigma*np.sqrt(2);constants=np.eye(len(indices))[groups]
    covariance_base=np.diag(noise**2)+radio@covariance[:nb,:nb]@radio.T+300**2*(constants@constants.T)
    members=[dict(component=p.scan.tracks[i]['key'],track_index=i,points=len(p.scan.tracks[i]['times']),
        observation_ids=p.scan.tracks[i]['observation_ids'],receiver=p.scan.tracks[i]['receiver'],channel=p.scan.tracks[i]['channel']) for i in indices]
    return dict(p=p,coefficient=c['coefficient'],covariance=covariance,radio_width=nb,
        times=view.flat_times,values=values,q=view.q,radio=radio,noise=noise,groups=groups,
        base_covariance=covariance_base,members=members,slices=slices,
        held_owners=len({(m['receiver'],m['channel']) for m in members}),target=-1)


def residual_checks(data,result):
    nb=data['radio_width'];count=len(data['members']);coefficient=np.asarray(result['coefficient'])
    # Undo the integrator's radio update for acceptance. Satellite phase/shape
    # remains a shared prior-constrained prediction; receiver calibration is fixed.
    raw=np.asarray(result['residual_hz'])+data['radio']@(coefficient[:nb]-data['coefficient'][:nb])
    raw+=coefficient[-count:][data['groups']]
    rows=[]
    for member,sl in zip(data['members'],data['slices'],strict=True):
        times=data['times'][sl];terms=profile(raw[sl],np.zeros(len(times)),*whitening(times),bias_sigma=300.)
        noise=batch_noise_screen(terms['innovations'],times)
        compatible=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and int(terms['alias'][0])==0
                        and noise['noise_screen_pass'][0])
        rows.append(dict(component=member['component'],rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0]),
            compatible=compatible,noise={k:v[0] for k,v in noise.items()}))
    return rows


def one(case):
    started=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('240s grouped nomination cap')));signal.alarm(240)
    output=OUT/(case+'.json')
    if output.exists():raise FileExistsError('preserve grouped nomination evidence')
    groups=[]
    try:
        d=runner.engine.current_setup(case);inventory=read(runner.RAW/case/'inventory.json')['arms']
        occupied=set().union(*(set(v['accepted_observation_ids']) for v in inventory.values()))
        offered=candidate_groups(d['scan'].tracks,d['scan'].curved,occupied);arms={}
        for arm,saved in d['arms'].items():
            arms[arm]=runner.engine.baseline.build(d,arm,saved['phase_reference'])
        penalty=float(2*np.log(max(1,len(offered))*len(d['scan'].norads)*3**3))
        for indices in offered:
            saved=d['arms']['c0'];x=np.asarray(saved['endpoint_east_north_km']);data=group_data(d,arms['c0'],x,indices)
            f,e=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means'])
            plus,_=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means']+.01)
            minus,_=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means']-.01)
            coarse=coarse_phase_scores(data['values'],data['radio']@data['coefficient'][:data['radio_width']],
                f*data['q'],(plus-minus)/.02*data['q'],d['widths'],data['base_covariance'],data['groups'])
            scores=np.where(e.min(axis=1)>=0,coarse['score'],np.inf)
            pool=[int(j) for j in np.argsort(scores) if np.isfinite(scores[j])][:7];pair={}
            for arm,p in arms.items():
                xx=np.asarray(d['arms'][arm]['endpoint_east_north_km']);datum=group_data(d,p,xx,indices);dd=dict(d,x=xx)
                candidates=[]
                for j in pool:
                    r=candidate_prediction(dd,datum,j,coarse['aliases'][j]);checks=residual_checks(datum,r)
                    lifted=datum['values']+np.asarray(r['aliases'])[datum['groups']]*PERIOD
                    null=sum(unresolved_curve_score(datum['times'][sl],lifted[sl],datum['noise'][sl]) for sl in datum['slices'])
                    r.update(fixed_radio_checks=checks,all_fixed_radio_checks_pass=all(v['compatible'] for v in checks),
                        unresolved_curve_score=null,gain_vs_independent_curves=null-r['score'])
                    candidates.append(r)
                pair[arm]=sorted(candidates,key=lambda r:r['score'])
            best={a:rs[0] for a,rs in pair.items()};gaps={a:rs[1]['score']-rs[0]['score'] if len(rs)>1 else 0. for a,rs in pair.items()}
            qualified=bool(best['c0']['candidate_index']==best['fitted_c']['candidate_index'] and
                all(r['qualified'] and r['all_fixed_radio_checks_pass'] and r['gain_vs_independent_curves']>penalty and gaps[a]>2*np.log(100)
                    for a,r in best.items()))
            row=dict(track_indices=indices,members=data['members'],points=len(data['values']),arms=pair,
                candidate_score_gaps=gaps,proposal_qualified=qualified,multiplicity_penalty=penalty)
            groups.append(row);write(OUT/(case+'_checkpoint.json'),dict(case=case,groups=groups))
            print(case,'group',[m['component'].split('-RF')[0] for m in data['members']],best['c0']['norad'],qualified,flush=True)
        result=dict(case=case,status='complete',groups=groups,offered_groups=len(offered),
            no_original_calibration_or_position_changed=True,conditional_scores_not_verified_identity_probabilities=True)
    except Exception as exc:
        import traceback
        result=dict(case=case,status='failed',error=repr(exc),traceback=traceback.format_exc(),groups=groups)
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(output,result);return dict(case=case,status=result['status'],groups=len(groups))


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    record=dict(cases=read(runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        minimum_points=8,minimum_span_s=6,maximum_group_span_s=60,maximum_between_piece_gap_s=10,
        group_sizes=[2,3],distinct_receiver_channel_owners_at_least=2,maximum_groups_per_case=24,
        candidates='all available causal Starlink candidates coarsely; best7 refined with shared phase and physical shape priors',
        same_frozen_c0_candidate_pool_aliases_in_both_c_arms=True,curve_point_noise_variance_factor=2,constant_prior_sigma_hz=300,
        fixed_radio_residual_gates=True,held_points_never_update_original_calibration=True,
        qualified='same winning candidate in both arms; original residual gates with fixed radio; gain versus independent broad polynomial curves exceeds2log(groups*catalogue*27); gap to next refined candidate>2log100',
        aliases_are_discrete_RF_proposals_not_a_full_wrapped_probability=True,no_GPS_following_TLE_new_RF_or_IQ=True,
        nominations_only_no_position_adoption=True,workers=2,maximum_seconds_per_case=240)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve grouped prototype protocol')
    write(OUT/'protocol.json',record)
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,record['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=all(r['status']=='complete' for r in rows)))


if __name__=='__main__':main()
