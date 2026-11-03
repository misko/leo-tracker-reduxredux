"""All-causal-catalogue frequency plus held-family reception identity proposals.

Frequency screening conditions on the current RF-only calibration and omits
orbit shape modes; its scores are proposals only. Full cold position fits and
unchanged gates are required before any association can be adopted.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np
from ds23_reception_identity import train,scores
from ds23_reception_ratio import beam_contrast,cross_validate
from ds23_family_screen import screen_family
from ds23_frequency_events import make_event_problem
from ds23_causal_phase_location import adjust_means
from probe_ds23_causal_phase_mean import forecast_phase_mean
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_sign_carrier_position import context_signed
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency
from leo.analysis.research.orbit_phase_geometry import phase_shifted_states
from leo.sky.frames import geodetic_to_ecef_km,ecef_to_enu_matrix,look_angles

OUT=ROOT/'reports/2026_10_21_ds23_reception_identity'
BULK=Path('/srv/bulk/leo/research/ds23-reception-identity-20261021')
SOURCE=ROOT/'reports/2026_10_21_ds23_reception_anchor_ratio/evaluation.json'


def one(case):
    target=BULK/(case+'.json')
    if target.exists():return read(target)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('120 second reception identity screen cap exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    try:
        rf=next(r for r in read(SOURCE)['rows'] if r['case']==case)
        scan,node,mask,powers,old_means,hyper,entries,signed,binding=context_signed(case)
        old=signed['policy_arms']['c0'];x=np.asarray(old['endpoint_east_north_km'])
        p=make_event_problem(scan,node,mask,'c0',np.asarray(old['phase_reference']),powers,old_means,hyper,[])
        state=p.state(x)
        all_labels=list(range(len(scan.norads)));widths,receipts=phase_widths(scan,all_labels)
        means=forecast_phase_mean(receipts,hyper['shrinkage'])
        if signed['accepted']:means=adjust_means(means,receipts,hyper,signed['selection'])
        widths=np.asarray(widths)*hyper['multiplier'];means=np.asarray(means)
        np.testing.assert_allclose(means[p.labels],old_means,rtol=0,atol=1e-12)
        frequency,elevation,derivative=phase_linear_frequency(scan.geometry,*latlon(x))
        blocks=[];controls=[]
        for family in sorted({r['norad'] for r in rf['family_band_medians']}):
            training=[r for r in rf['family_band_medians'] if r['norad']!=family]
            held=[r for r in rf['family_band_medians'] if r['norad']==family]
            if any(sum(r['band']==b for r in training)<2 for b in {r['band'] for r in held}):continue
            model=train(training,family);null=train(training,family,direction=False)
            nested=cross_validate(training)
            controls.append(dict(norad=family,held_direction_score=float(scores(model,held)[0]),
                held_band_only_score=float(scores(null,held)[0]),training_qualified=nested['qualified']))
            if not nested['qualified']:continue
            original=int(np.flatnonzero(scan.norads==family)[0]);curves=[];members=[]
            for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
                if row['candidate_index']!=original or not mask[sl].any():continue
                t=scan.tracks[i];use=mask[sl];index=scan.index[i][use];q=t['rf_hz']/11.5e9
                observed=t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][t['receiver']-1]
                curves.append(dict(observed=observed[use],predicted=q*(frequency[:,index]+derivative[:,index]*means[:,None]),
                    derivative=q*derivative[:,index],sigma=p.point_noise[sl][use],power=powers[k],visible=elevation[:,index].min(axis=1)>=0))
                members.append(k)
            if not curves:continue
            screen=screen_family(curves,widths)
            phases=means+screen['phase_correction_s']
            eligible=np.flatnonzero(np.isfinite(screen['cost']) & (abs(phases)<=15))
            if original not in eligible:continue
            bank=dict(time_s=scan.sky['time_s'],position_km=scan.sky['position_km'][eligible],velocity_km_s=scan.sky['velocity_km_s'][eligible])
            features=[]
            for r in held:
                points=[v for v in rf['paired_points'] if v['norad']==family and v['band']==r['band']]
                pos,vel=phase_shifted_states(bank,np.array([v['time_s'] for v in points]),phases[eligible])
                az,el,_,_=look_angles(pos,vel,geodetic_to_ecef_km(*latlon(x),0.),ecef_to_enu_matrix(*latlon(x)))
                features.append(np.median(beam_contrast(az,el),axis=1))
            reception=scores(model,held,np.column_stack(features));radio=screen['cost'][eligible]
            combined=radio+reception;original_local=int(np.flatnonzero(eligible==original)[0])
            def record(local):
                j=int(eligible[local]);return dict(candidate_index=j,norad=int(scan.norads[j]),frequency_proposal_score=float(radio[local]),
                    reception_score=float(reception[local]),combined_proposal_score=float(combined[local]),phase_s=float(phases[j]),
                    aliases=[int(a[j]) for a in screen['aliases']],band_features=np.column_stack(features)[local])
            rf_order=np.argsort(radio);order=np.argsort(combined)
            np.savez_compressed(BULK/(case+'_'+str(family)+'_scores.npz'),candidate_index=eligible,radio=radio,reception=reception,phase_s=phases[eligible])
            blocks.append(dict(original_norad=family,original_index=original,original=record(original_local),
                row_indices=members,points=sum(len(r['observed']) for r in curves),held_rows=held,reception_model=model,
                nested_training_validation=nested,original_frequency_rank=int(np.flatnonzero(rf_order==original_local)[0])+1,
                original_combined_rank=int(np.flatnonzero(order==original_local)[0])+1,
                frequency_top=[record(k) for k in rf_order[:8]],combined_top=[record(k) for k in order[:8]],
                candidate_count=len(scan.norads),visible_phase_valid_candidates=len(eligible),held_family_never_trains_antenna=True))
        result=dict(case=case,status='complete',blocks=blocks,predictive_controls=controls,RF_position_km=x,
            signed_incumbent_path=str(binding.relative_to(ROOT)),signed_incumbent_sha256=sha(binding),
            no_GPS_or_post_scan_TLE_or_new_RF_used=True,no_original_labels_or_position_estimates_changed=True,
            conditional_frequency_proposals_omit_shape_modes_and_are_not_identity_probabilities=True)
    except Exception as exc:result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(target,result);print(case,result['status'],len(result.get('blocks',[])),result.get('error'),flush=True);return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    cases=sorted(r['case'] for r in read(SOURCE)['rows'] if r['status']=='complete' and 'held_family_SSE_fractional_improvement' in r['validation'])
    protocol=dict(cases=cases,workers=4,per_case_seconds=120,source_evaluation_sha256=sha(SOURCE),
        minimum_train_families=4,qualification='other families only: original leave-family-out SSE gain>20percent and consistent slope sign',
        logit_ratio_independent_noise_SD=1.,logit_ratio_shared_family_SD=1.,coefficient_prior_SD=10.,
        frequency_proposals='all causal candidates; one phase per family plus300Hz fragment constants; original RF-only calibration',
        original_observations_masks_and_gates_unchanged=True,source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_reception_identity.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen reception identity protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=4) as pool:rows=[f.result() for f in as_completed([pool.submit(one,c) for c in cases])]
    controls=[v for r in rows for v in r.get('predictive_controls',[])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,failures=[r for r in rows if r['status']!='complete'],
        held_family_controls=len(controls),held_direction_score=sum(r['held_direction_score'] for r in controls),
        held_band_only_score=sum(r['held_band_only_score'] for r in controls),
        no_satellite_replacement_or_position_gain_adopted=True,protocol_sha256=sha(path)))


if __name__=='__main__':main()
