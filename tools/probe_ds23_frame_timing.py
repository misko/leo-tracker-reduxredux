"""Radio-frame timing versus causal range: diagnostic, never a position input."""

import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from probe_ds23_height import context,OUT
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_refined_curve_position import proposed_delta
from remeasure_ds23_rx2_cohort import selected_points,OUT as MEASURED
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.sky.frames import geodetic_to_ecef_km

FRAME_US=1e6/750


def clock_segments(times,arrival_seconds,range_km,maximum_gap_s=10.):
    t,arrival,rho=map(lambda x:np.asarray(x,float),(times,arrival_seconds,range_km))
    if t.shape!=arrival.shape or t.shape!=rho.shape or t.ndim!=1 or not all(np.isfinite(a).all() for a in (t,arrival,rho)) or np.any(np.diff(t)<=0):
        raise ValueError('finite matching ordered timing and range samples required')
    wrapped=(arrival-rho/299792.458)*1e6
    wrapped=(wrapped+FRAME_US/2)%FRAME_US-FRAME_US/2
    boundaries=np.r_[0,np.flatnonzero(np.diff(t)>maximum_gap_s)+1,len(t)];result=[]
    for start,stop in zip(boundaries[:-1],boundaries[1:],strict=True):
        if stop-start<4:continue
        x=t[start:stop];y=np.unwrap(wrapped[start:stop]*2*np.pi/FRAME_US)*FRAME_US/(2*np.pi)
        z=(x-x.mean())/max(1.,float(np.ptp(x)));a=np.column_stack((np.ones(len(x)),z))
        coefficient=np.linalg.lstsq(a,y,rcond=None)[0];residual=y-a@coefficient
        result.append(dict(start_index=int(start),stop_index=int(stop),time_s=x,unwrapped_clock_us=y,
            affine_residual_us=residual,RMS_us=float(np.sqrt(np.mean(residual**2))),
            clock_rate_ppm=float(coefficient[1]/max(1.,float(np.ptp(x)))),
            maximum_affine_step_us=float(max(abs(np.diff(residual)))),
            frame_alias_period_us=FRAME_US,unwrap_is_nearest_neighbor_with_10s_gap_splits=True))
    return result


def arrival_time(point,source,document):
    fs=source['sample_rate_hz']
    origin=(document['clock_anchor']['sample_counter'] if 'source' in document
            else source['timing']['session_start_device_sample_counter'])
    peak=point['peak']
    counter=point['visit_start_counter']-origin+round(point['probe_start_ms']*fs/1000)
    return (counter+peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples'])/fs


def run(case):
    directory=OUT/'frame_timing';directory.mkdir(exist_ok=True)
    if (directory/(case+'.json')).exists():raise FileExistsError('preserve diagnostic result')
    scan,node,keep,powers,means,model,noise,baseline=context(case,'archived')
    record=baseline['c0'];x=np.array(record['endpoint_east_north_km'])
    p=make_problem(scan,node,keep,'c0',np.array(record['phase_reference']),powers,means,model['multiplier'],model['nu'])
    c=p.calculate(x);phase=p.state(x)['phases'][p.labels]
    document=read(SOURCE/case/'tracking.json');source,points=selected_points(document,[scan.tracks[i] for i in p.members])
    lookup={point['observation_id']:point for point in points};refined={r['point']['observation_id']:r for r in read(MEASURED/(case+'_refined.json'))['rows']}
    observer=geodetic_to_ecef_km(*latlon(x),0.);start=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)
    rows=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        track=scan.tracks[i];active=keep[sl]
        if active.sum()<4:continue
        ids=np.array(track['observation_ids'])[active];arrivals=np.array([arrival_time(lookup[oid],source,document) for oid in ids])
        local=p.labels.index(row['candidate_index']);labels=np.full(len(ids),local,int)
        position,velocity=paired_phase_states(p.sky,arrivals,labels,phase)
        if row['candidate_index'] in p.supported:
            supported=p.supported.index(row['candidate_index'])
            expanded=(labels[:,None]*3+np.arange(3)).ravel()
            dp,_=paired_phase_states(p.mode_bank,np.repeat(arrivals,3),expanded,np.repeat(phase,3))
            position+=np.einsum('nmc,m->nc',dp.reshape(-1,3,3),c['coefficient'][start+3*supported:start+3*supported+3])
        rho=np.linalg.norm(position-observer,axis=1)
        offsets=np.array([refined[oid]['joint_CFO_epoch_rate']['offset_samples']/source['sample_rate_hz']
                          if oid in refined and proposed_delta(refined[oid],'joint_CFO_epoch_rate')[1]=='refined' else 0. for oid in ids])
        # Correct the small range change between the archived and refined epoch.
        direction=(position-observer)/rho[:,None];rho_new=rho+np.sum(direction*velocity,axis=1)*offsets
        rows.append(dict(track=track['key'],receiver=track['receiver'],channel=track['channel'],
            norad=row['candidate_norad'],observation_ids=ids,arrival_time_s=arrivals,range_km=rho,
            archived=clock_segments(arrivals,arrivals,rho),
            refined_epoch=clock_segments(arrivals+offsets,arrivals+offsets,rho_new),
            refined_epoch_points=int(np.count_nonzero(offsets))))
    write(directory/(case+'.json'),dict(case=case,tracks=rows,RF_endpoint_east_north_km=x,
        source_sha256=sha(Path(__file__)),tracking_sha256=sha(SOURCE/case/'tracking.json'),
        no_GPS_used=True,no_clock_timing_applied_to_position=True,
        no_IQ_read_or_new_RF=True,only_original_active_curved_observations=True,
        range_is_at_arrival_time_using_CFO_fitted_causal_phase_and_physical_modes=True,
        light_time_and_transmitter_clock_compensation_not_modeled=True,
        short_gaps_do_not_prove_correct_integer_frame_unwrap=True))
    fig,axes=plt.subplots(2,2,figsize=(14,8),sharex=True,constrained_layout=True)
    families=sorted({r['norad'] for r in rows});colors={j:plt.get_cmap('tab20')(k%20) for k,j in enumerate(families)}
    for row in rows:
        ax=axes[row['receiver']-1,int(row['channel']>4)]
        for segment in row['refined_epoch']:
            ax.plot(segment['time_s'],segment['affine_residual_us'],'.-',color=colors[row['norad']],lw=.6,ms=3)
    for k,ax in enumerate(axes.flat):
        ax.axhline(0,color='black',lw=.6);ax.set(title=f'RX{k//2+1} / '+('high' if k%2 else 'low')+' band',
            xlabel='Scan time (s)',ylabel='Affine-removed clock residual (microseconds)');ax.grid(alpha=.2)
    fig.suptitle(case+' · independent timing diagnostic · colors are RF-nominated satellite families\nFrame arrival minus causal propagation delay; each gap-split curve gets its own affine clock')
    fig.savefig(directory/(case+'.png'),dpi=155);plt.close(fig)
    all_segments=[s for r in rows for s in r['refined_epoch']]
    print(case,'segments',len(all_segments),'median/max clock RMS us',
        np.median([s['RMS_us'] for s in all_segments]),max(s['RMS_us'] for s in all_segments),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True);run(parser.parse_args().case)
