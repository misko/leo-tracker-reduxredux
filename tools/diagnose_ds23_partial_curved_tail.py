"""Causal full-catalogue prediction for an unused suffix of an active track.

The original calibration mask remains unchanged. This is a diagnostic, not
whole-track admission of a component that already contains calibration data.
"""

from pathlib import Path

import numpy as np

import repair_ds23_iteration009_targets as repair
from ds23_family_cavity import coarse_phase_scores
from probe_ds23_family_cavity_nominations import candidate_prediction
from probe_ds23_linear_family_groups import residual_checks
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from prototype_dsx01_continuous_position import latlon
from localize_merged_track_catalogue import raw_curvature
from run_algo01_ds23_sample import read,write,sha

OUT=repair.runner.RAW/'partial_tail_diagnostic'


def unused_blocks(times,active,minimum_points=12,minimum_span_s=10):
    use=np.flatnonzero(~np.asarray(active,bool));result=[]
    for ix in np.split(use,np.flatnonzero(np.diff(use)>1)+1):
        if len(ix)>=minimum_points and np.ptp(np.asarray(times)[ix])>=minimum_span_s:result.append(ix)
    return result


def data_for(d,p,x,row,indices):
    c=p.curved_calculate(x) if d['entries'] else p.calculate(x);g=p.noise_groups[p.keep];u=c['features'][p.keep]
    weights=np.asarray(d['powers'])[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
    covariance=np.linalg.inv(np.diag(c['coefficient_prior_precision'])+u.T@(u*weights[:,None]))
    i=p.members[row];sl=p.slices[row];t=p.scan.tracks[i];indices=np.asarray(indices)
    if p.keep[sl][indices].any():raise ValueError('partial prediction contains an active calibration observation')
    nb=p.hardware.shape[1]+p.smooth.shape[1];radio=c['features'][sl,:nb][indices];noise=p.point_noise[sl][indices]*np.sqrt(2/d['powers'][row])
    native_ids=np.asarray(t['observation_ids'])[indices].tolist()
    return dict(p=p,coefficient=c['coefficient'],covariance=covariance,radio_width=nb,times=t['times'][indices],values=t['values'][indices],
        q=p.q[sl][indices],radio=radio,noise=noise,groups=np.zeros(len(indices),int),slices=[slice(0,len(indices))],
        base_covariance=np.diag(noise**2)+radio@covariance[:nb,:nb]@radio.T+300**2,
        members=[dict(component=t['key'],track_index=i,points=len(indices),receiver=t['receiver'],channel=t['channel'],observation_ids=native_ids)],
        held_owners=1,target=p.rows[row]['candidate_index'])


def main():
    repair.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve partial-tail diagnostic')
    write(OUT/'protocol.json',dict(cases=read(repair.runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        maximum_blocks_per_case=1,minimum_points=12,minimum_span_s=10,
        blocks_are_exact_contiguous_unused_runs_in_the_original_frozen_calibration_mask=True,
        no_active_calibration_observation_enters_the_held_suffix=True,
        original_position_and_radio_posterior_fixed_for_nomination=True,
        all_available_causal_catalogue_coarse_then_best7_and_original_identity=True,
        diagnosis_only_no_new_association_or_position_adopted=True,no_GPS_following_TLE_or_new_RF=True))
    rows=[]
    for case in read(OUT/'protocol.json')['cases']:
        d=repair.engine.current_setup(case);saved=d['arms']['c0'];x=np.asarray(saved['endpoint_east_north_km'])
        p=repair.engine.baseline.build(d,'c0',saved['phase_reference']);blocks=[]
        for k,i in enumerate(p.members):
            active=p.keep[p.slices[k]]
            if not active.any() or active.all():continue
            for ix in unused_blocks(p.scan.tracks[i]['times'],active):
                t=p.scan.tracks[i]
                if raw_curvature(dict(t,times=t['times'][ix],values=t['values'][ix])):blocks.append((k,ix))
        blocks.sort(key=lambda r:-len(r[1]));results=[]
        for k,ix in blocks[:1]:
            data=data_for(d,p,x,k,ix);f,e=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means'])
            plus=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means']+.01)[0]
            minus=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means']-.01)[0]
            coarse=coarse_phase_scores(data['values'],data['radio']@data['coefficient'][:data['radio_width']],data['q']*f,
                data['q']*(plus-minus)/.02,d['widths'],data['base_covariance'],data['groups'])
            scores=np.where(e.min(axis=1)>=0,coarse['score'],np.inf);pool=[int(j) for j in np.argsort(scores) if np.isfinite(scores[j])][:7]
            if data['target'] not in pool:pool.append(data['target'])
            candidates=[]
            for j in pool:
                candidate=candidate_prediction(dict(d,x=x),data,j,coarse['aliases'][j]);candidate['fixed_radio_checks']=residual_checks(data,candidate);candidates.append(candidate)
            candidates.sort(key=lambda r:r['score'])
            results.append(dict(component=p.rows[k]['component'],source_row=k,source_track_index=p.members[k],indices=ix,
                observation_ids=data['members'][0]['observation_ids'],times=data['times'],original_family=int(d['scan'].norads[data['target']]),
                points=len(ix),candidates=candidates,all_held_IDs_disjoint_from_original_calibration=True))
            print(case,'partial',len(ix),'best',[(c['norad'],c['conditional_RMS_hz']) for c in candidates[:3]],flush=True)
        write(OUT/(case+'.json'),dict(case=case,rows=results,no_GPS_position_or_association_change=True));rows.append(dict(case=case,blocks=len(results)))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
