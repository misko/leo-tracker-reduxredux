"""Cold paired position checks of the five closest reception-screen challengers.

Selection uses frozen RF scores only. Original evidence, gates and nuisance
priors remain intact. The auxiliary reception score is conditional on a model
trained on the other original families, not a calibrated joint identity odds.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np
from ds23_reception_identity import scores
from ds23_reception_ratio import beam_contrast
from ds23_symmetric_family_code import replace_whole_family,family_code,observed_labels
from ds23_frequency_events import make_event_problem,attach_event_predictive
from ds23_causal_phase_location import adjust_means
from probe_ds23_frequency_events import refit,cached
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_reception_identity import OUT as SCREEN,SOURCE
from probe_ds23_causal_phase_mean import forecast_phase_mean
from investigate_ds23_adaptive_failures import phase_widths
from prototype_dsx01_continuous_position import latlon
from run_ds23_combined_recovery_full import ARMS,valid
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid,phase_shifted_states
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.sky.frames import geodetic_to_ecef_km,ecef_to_enu_matrix,look_angles

OUT=ROOT/'reports/2026_10_21_ds23_reception_identity_position'
BULK=Path('/srv/bulk/leo/research/ds23-reception-identity-position-20261021')


def prepare():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    offers=[]
    for case in read(SCREEN/'evaluation.json')['rows']:
        for block in case.get('blocks',[]):
            candidate=next((r for r in block['combined_top'] if r['norad']!=block['original_norad']),None)
            if candidate:
                offers.append(dict(case=case['case'],block=block,candidate=candidate,
                    proposal_gain=block['original']['combined_proposal_score']-candidate['combined_proposal_score']))
    selected=[];used=set()
    for offer in sorted(offers,key=lambda r:(-r['proposal_gain'],r['case'],r['block']['original_norad'])):
        if offer['case'] in used:continue
        selected.append(offer);used.add(offer['case'])
        if len(selected)==5:break
    protocol=dict(offers=selected,workers=2,per_case_seconds=180,
        selection='five distinct scans with closest nonincumbent combined RF plus reception proposal, before position accuracy is read',
        only_current_other_curved_families_train_reception=True,
        no_GPS_or_post_scan_TLE_or_new_RF_or_cross_scan_position_prior=True,
        all_original_points_masks_noise_priors_retained=True,original_residual_gates_unchanged=True,
        cold_start_km=[0,0],regional_width_km=25,phase_rounds=5,position_iterations=48,
        matched_c0_fitted_c=True,selection_score='full RF bound plus symmetric family code plus conditional reception score; both arms gain>2log6 and original paired gates',
        source_evaluation_sha256=sha(SCREEN/'evaluation.json'),
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_reception_identity.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('reception position protocol changed')
    if not path.exists():write(path,protocol)
    return protocol


def reception_score(scan,points,held,model,candidate,phase,position):
    bank=dict(time_s=scan.sky['time_s'],position_km=scan.sky['position_km'][[candidate]],velocity_km_s=scan.sky['velocity_km_s'][[candidate]])
    features=[]
    for row in held:
        times=np.array([r['time_s'] for r in points if r['band']==row['band']])
        pos,vel=phase_shifted_states(bank,times,np.array([phase]))
        az,el,_,_=look_angles(pos,vel,geodetic_to_ecef_km(*latlon(position),0.),ecef_to_enu_matrix(*latlon(position)))
        features.append(float(np.median(beam_contrast(az,el))))
    return float(scores(model,held,np.array([features]))[0])


def one(offer):
    case=offer['case'];path=BULK/(case+'.json')
    if path.exists():return read(path)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('180 second reception position cap exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(180)
    try:
        block=offer['block'];candidate=offer['candidate'];j=candidate['candidate_index'];original=block['original_index']
        scan,node,mask,powers,means,hyper,entries,signed,binding=context_signed(case)
        old=signed['policy_arms'];x=np.asarray(old['c0']['endpoint_east_north_km'])
        p=make_event_problem(scan,node,mask,'c0',np.asarray(old['c0']['phase_reference']),powers,means,hyper,[])
        state=p.state(x);alias={}
        bank=dict(time_s=scan.sky['time_s'],position_km=scan.sky['position_km'][[j]],velocity_km_s=scan.sky['velocity_km_s'][[j]])
        for kind,k,index in ([('curve',k,i) for k,(r,i) in enumerate(zip(p.rows,p.members,strict=True)) if r['candidate_index']==original]
                +[('linear',k,r['track_index']) for k,r in enumerate(entries) if r['candidate_index']==original]):
            t=scan.tracks[index];q=t['rf_hz']/11.5e9
            f,_=phase_frequency_grid(bank,t['times'],*latlon(x),phase_seconds=candidate['phase_s'])
            y=t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[index]@state['smooth'][t['receiver']-1]
            alias[kind,k]=int(np.rint(np.mean(q*f[0]-y)/PERIOD))
        changed,predictive=replace_whole_family(node,entries,original,j,candidate['norad'],alias)
        labels=sorted({r['candidate_index'] for r in changed['seed']['rows']})
        _,receipts=phase_widths(scan,labels);newmeans=forecast_phase_mean(receipts,hyper['shrinkage'])
        if signed['accepted']:newmeans=adjust_means(newmeans,receipts,hyper,signed['selection'])
        arms={a:refit(scan,changed,mask,a,powers,newmeans,hyper,[],predictive) for a in ARMS}
        code=family_code(len(scan.norads),observed_labels(node,entries,mask,p.slices))
        newcode=family_code(len(scan.norads),observed_labels(changed,predictive,mask,p.slices))
        rf=next(r for r in read(SOURCE)['rows'] if r['case']==case)
        points=[r for r in rf['paired_points'] if r['norad']==block['original_norad']]
        details={};replays={}
        for arm in ARMS:
            before=old[arm];after=arms[arm]
            baseline=cached(attach_event_predictive(make_event_problem(scan,node,mask,arm,np.asarray(before['phase_reference']),powers,means,hyper,[]),entries,powers))
            difference=baseline.calculate(np.asarray(before['endpoint_east_north_km']))['negative_twice_elbo']-before['negative_twice_elbo']
            if abs(difference)>1e-6:raise ValueError('signed incumbent likelihood replay failed')
            replays[arm]=float(difference)
            left=reception_score(scan,points,block['held_rows'],block['reception_model'],original,before['state']['phases'][original],before['endpoint_east_north_km'])
            right=reception_score(scan,points,block['held_rows'],block['reception_model'],j,after['state']['phases'][j],after['endpoint_east_north_km'])
            details[arm]=dict(incumbent_reception_score=left,candidate_reception_score=right,
                frequency_bound_gain=before['negative_twice_elbo']-after['negative_twice_elbo'],
                auxiliary_reception_gain=left-right,
                coded_combined_gain=before['negative_twice_elbo']+code+left-after['negative_twice_elbo']-newcode-right)
        paired=valid(arms);accepted=bool(paired and all(r['coded_combined_gain']>2*np.log(6) for r in details.values()))
        result=dict(case=case,status='complete',offer=offer,arms=arms,paired_valid=paired,accepted=accepted,
            policy_arms=arms if accepted else old,incumbent_arms=old,score_details=details,
            original_code=code,new_code=newcode,new_means_s=newmeans,original_mask=mask,
            candidate_node=changed,candidate_entries=predictive,incumbent_replay_differences=replays,
            signed_incumbent_path=str(binding.relative_to(ROOT)),signed_incumbent_sha256=sha(binding),
            no_GPS_or_future_TLE_or_new_RF_or_point_removal=True,
            linear_points_never_update_receiver_calibration=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(path,result)
    print(case,result['status'],'valid',result.get('paired_valid'),'accepted',result.get('accepted'),result.get('error'),flush=True)
    return result


def main():
    protocol=prepare()
    with ProcessPoolExecutor(max_workers=2) as pool:rows=[f.result() for f in as_completed([pool.submit(one,o) for o in protocol['offers']])]
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,failures=[r for r in rows if r['status']!='complete'],protocol_sha256=sha(OUT/'protocol.json')))


if __name__=='__main__':main()
