"""Local geometric phase sensitivity on existing DS6 observation schedules."""
import hashlib
import importlib.util
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.sky.frames import geodetic_to_ecef_km

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('pair_run',ROOT/'2026_09_27_ds6_pair_proposals/run.py')
pair=importlib.util.module_from_spec(spec);spec.loader.exec_module(pair)


def phase(position,lat,lon,rf):
    observer=geodetic_to_ecef_km(lat,lon,0)
    direction=position-observer
    direction/=np.linalg.norm(direction,axis=-1,keepdims=True)
    east=np.array([-np.sin(np.radians(lon)),np.cos(np.radians(lon)),0.])
    return 2*np.pi*.08*rf/299792458.*((direction[1]-direction[0])@east)


def gradient(position,lat,lon,rf,step_km):
    # Coordinate perturbations define local east/north distance at the base point.
    dl=np.degrees(step_km/6371.0088)
    de=dl/np.cos(np.radians(lat))
    return np.column_stack([(phase(position,lat,lon+de,rf)-phase(position,lat,lon-de,rf))/(2*step_km),
                            (phase(position,lat+dl,lon,rf)-phase(position,lat-dl,lon,rf))/(2*step_km)])


def remove_offsets(design):
    return design-design.mean(axis=0,keepdims=True)


def information(designs):
    s=np.linalg.svd(np.concatenate(designs),compute_uv=False)
    return dict(singular_values_rad_per_km=s.tolist(),
                weak_axis_sigma_km_at_1deg=float(np.radians(1)/s[-1]),
                phase_sigma_deg_for_1km_weak_axis=float(np.degrees(s[-1])))


def main():
    inputs={name:ROOT/'2026_09_27_ds6_pair_proposals'/name for name in ['full-results.json','protocol.json']}
    full=json.loads(inputs['full-results.json'].read_text());protocol=json.loads(inputs['protocol.json'].read_text())
    lat,lon=protocol['observer_from_other_scan_cfo']
    source_path=ROOT/'2026_09_27_ds6_differential_cfo/results.json'
    source=json.loads(source_path.read_text());inputs['differential_results']=source_path
    for scan in source['scans']:
        sid=scan['session_id'];inputs[sid]=ROOT/'2026_09_27_ds6_common_rate_validation'/(sid+'-plan.json')
    frozen=dict(source_hashes={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in inputs.items()},
        observer=[lat,lon],step_km=.1,check_step_km=.01,
        candidate_selection='CFO MAP pair independently at each of the 11 frozen timing hypotheses; no phase or reference position selects identities',
        noise_model='Illustrative independent equal-variance local Gaussian phase errors; offsets profiled per group; not an empirical precision estimate',
        scope='Optimistic local geometry diagnostic with fixed identities, timing, altitude and nominal baseline; no location fit')
    (HERE/'protocol.json').write_text(json.dumps(frozen,indent=2)+'\n')
    rows=[];fig,axes=plt.subplots(1,2,figsize=(12,4.8));max_error=0.
    for si,(scan,fullscan) in enumerate(zip(source['scans'],full['scans'])):
        assert scan['session_id']==fullscan['session_id']
        sid=scan['session_id'];plan=json.loads(inputs[sid].read_text());cat=pair.u.load_catalogue(plan)
        lookup={int(n):i for i,n in enumerate(cat.satellite_numbers)};tracks={t['track_id']:t for t in plan['tracks']}
        hypotheses=[]
        for ti,tau in enumerate(protocol['timing_s']):
            designs=[];training=[];raw=[];groups=[]
            for group,fg in zip(scan['groups'],fullscan['groups']):
                assert group['group']==fg['group']
                choice=fg['maxima'][ti];assert choice['time_s']==tau
                indices=np.array([lookup[n] for n in choice['pair']]);obs=group['phase_observations']
                times=np.array([o['time_s'] for o in obs]);mask=np.array([o['train'] for o in obs])
                p,_,valid=propagate_candidate_states(cat,indices,plan['start_utc_ns'],times,np.array([tau]))
                np.testing.assert_array_equal(valid,indices)
                rf=tracks[group['track_ids'][0]]['rf_hz'];g=gradient(p[:,0],lat,lon,rf,.1)
                small=gradient(p[:,0],lat,lon,rf,.01);error=float(np.max(np.abs(g-small)));max_error=max(max_error,error)
                centered=remove_offsets(g);designs.append(centered);training.append(remove_offsets(g[mask]));raw.append(g)
                groups.append(dict(group=group['group'],pair=choice['pair'],times_s=times.tolist(),training_mask=mask.tolist(),
                    phase_rad=phase(p[:,0],lat,lon,rf).tolist(),gradient_rad_per_km=g.tolist(),centered_gradient_rad_per_km=centered.tolist(),
                    rms_phase_change_deg_per_1km=np.degrees(np.sqrt(np.mean(centered**2,axis=0))).tolist(),finite_difference_error=error))
            hypotheses.append(dict(timing_s=tau,groups=groups,all_visits=information(designs),training_visits=information(training),
                                   calibrated_offsets=information(raw)))
        rows.append(dict(session_id=sid,hypotheses=hypotheses))
        ax=axes[si]
        for key,label in [('calibrated_offsets','Offsets known'),('all_visits','Offsets unknown, all 4 visits'),('training_visits','Offsets unknown, 2 training visits')]:
            ax.semilogy(protocol['timing_s'],[r[key]['weak_axis_sigma_km_at_1deg'] for r in hypotheses],marker='o',label=label)
        ax.axhline(1,color='k',ls='--',lw=1);ax.set_title(sid[-8:]);ax.set_xlabel('Assumed scan timing offset (s)');ax.set_ylabel('Weak-axis 1σ distance at 1° phase noise (km)');ax.legend(fontsize=8)
    fig.suptitle('DS6 local phase sensitivity: identities and timing assumed known\nIllustrative Gaussian precision; not a measured position error')
    fig.tight_layout();fig.savefig(HERE/'sensitivity.png',dpi=180);plt.close(fig)
    result=dict(complete=True,protocol_sha256=hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest(),
                max_finite_difference_error_rad_per_km=max_error,scans=rows)
    (HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    for row in rows:
        print(row['session_id'])
        for key in ['calibrated_offsets','all_visits','training_visits']:
            vals=[r[key]['weak_axis_sigma_km_at_1deg'] for r in row['hypotheses']]
            req=[r[key]['phase_sigma_deg_for_1km_weak_axis'] for r in row['hypotheses']]
            print(key,'1deg noise km range',min(vals),max(vals),'required deg',min(req),max(req))
    print('finite difference error',max_error)


if __name__=='__main__':main()
