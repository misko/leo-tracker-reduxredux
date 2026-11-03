"""Select active-curve simultaneous IQ pairs before new RF outcomes or GPS."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from itertools import combinations
from pathlib import Path
import signal
import time
import numpy as np

from ds23_differential_information import covariance_gain,differential_gradient
from ds23_phase_measurement_design import local_design
from ds23_frequency_events import make_event_problem
from inventory_ds23_active_differential_pairs import matching_curve,OUT
from probe_ds23_same_probe_curves import lanes,SOURCE
from probe_ds23_sign_carrier_position import context_signed
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.retained_track_likelihood import PERIOD

BULK=Path('/srv/bulk/leo/research/ds23-differential-information-20261022')


def one(case):
    target=BULK/(case+'_selection.json')
    if target.exists():return read(target)
    start=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120second metadata target-selection cap')));signal.alarm(120)
    try:
        scan,node,mask,powers,means,hyper,entries,signed,source=context_signed(case)
        endpoint=np.array(signed['policy_arms']['c0']['endpoint_east_north_km'])
        p=make_event_problem(scan,node,mask,'c0',np.array(signed['policy_arms']['c0']['phase_reference']),powers,means,hyper,[])
        p.design_powers=powers;design=local_design(p,endpoint);c=p.calculate(endpoint)
        active=[(k,p.scan.tracks[i]) for k,(i,sl) in enumerate(zip(p.members,p.slices,strict=True)) if np.any(mask[sl])]
        document=read(SOURCE/case/'tracking.json');source_doc=document.get('source',document)
        candidates=[]
        for lane in lanes(case):
            rx,ch,rf=lane['lane'];curves=[(k,t) for k,t in active if (t['receiver'],t['channel'])==(rx,ch) and abs(t['rf_hz']-rf)<=10]
            if len(curves)<2:continue
            by_probe={}
            for peak in lane['candidates']:
                if peak['margin']<.1:continue
                matches=[(k,t,m) for k,t in curves if (m:=matching_curve(t,peak['time_s'],peak['cfo_hz'])) is not None]
                if len(matches)!=1:continue
                k,t,m=matches[0];by_probe.setdefault(peak['probe'],[]).append((peak,k,t,m))
            for pi,peaks in by_probe.items():
                for first,second in combinations(peaks,2):
                    a,ka,ta,ma=first;b,kb,tb,mb=second
                    if ka==kb or p.rows[ka]['candidate_index']==p.rows[kb]['candidate_index']:continue
                    separation=abs((a['cfo_hz']-b['cfo_hz']+PERIOD/2)%PERIOD-PERIOD/2)
                    if separation<5000 or abs(a['epoch']-b['epoch'])/lane['sample_rate_hz']<2e-6:continue
                    probe=source_doc['probes'][pi]
                    if source_doc['probe_ms']!=20 or probe['probe_start_ms']!=0:continue
                    candidates.append(dict(case=case,group=case+f'_RX{rx}_CH{ch}',probe=pi,time_s=a['time_s'],lane=lane['lane'],
                        visit_index=probe['visit_index'],sample_counter=probe['valid_start_counter'],native_receiver_id=probe['receiver_id'],edge=probe['edge'],
                        first=a,second=b,first_lifted_value=a['cfo_hz']+round((ma['polynomial_value_hz']-a['cfo_hz'])/PERIOD)*PERIOD,
                        second_lifted_value=b['cfo_hz']+round((mb['polynomial_value_hz']-b['cfo_hz'])/PERIOD)*PERIOD,
                        curve_rows=[ka,kb],curve_components=[ta['key'],tb['key']],
                        proposed_norads=[p.rows[ka]['candidate_norad'],p.rows[kb]['candidate_norad']],
                        minimum_native_margin=min(a['margin'],b['margin'])))
        # Bounded information screening, after native support and unique-owner
        # checks. No newly estimated RF or geographic error enters this rank.
        candidates=sorted(candidates,key=lambda r:(-r['minimum_native_margin'],r['probe'],r['curve_rows']))[:96]
        for candidate in candidates:
            h=differential_gradient(p,candidate['curve_rows'],candidate['time_s'],candidate['lane'][2],endpoint,c['coefficient'])
            candidate['physical_information_gradient']=h
        covariance=np.array(design['covariance']);selected=[];used=set()
        for _ in range(min(3,len(candidates))):
            remaining=[r for r in candidates if r['visit_index'] not in used]
            if not remaining:break
            ranked=[(covariance_gain(covariance,r['physical_information_gradient'],20.),r) for r in remaining]
            gain,choice=max(ranked,key=lambda x:x[0]['gain_km2'])
            if gain['gain_km2']<=0:break
            covariance=gain['covariance'];used.add(choice['visit_index'])
            selected.append(dict(choice,paired_index=len(selected),assumed_design_sigma_hz=20.,expected_position_variance_gain_km2=gain['gain_km2']))
        result=dict(case=case,status='complete',eligible_after_native_and_curved_ownership=len(candidates),selected=selected,
            design_position_rms_SD_km=design['position_rms_SD_km'],predicted_position_rms_SD_km=float(np.sqrt(np.trace(covariance[:2,:2]))),
            tracking_sha256=sha(SOURCE/case/'tracking.json'),signed_incumbent_sha256=sha(source),
            information_approximation_conditional_not_accuracy_or_measured_RF_precision=True,
            no_new_IQ_or_GPS_or_future_TLE_read_for_selection=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-start;write(target,result)
    print(case,result['status'],len(result.get('selected',[])),result.get('error'),flush=True);return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    old=read(OUT/'inventory_protocol.json');cases=old['cases']
    protocol=dict(cases=cases,pilot_cases=cases[:3],maximum_per_case=3,maximum_information_screened_per_case=96,
        unique_curved_ownership_not_verified_satellite_identity=True,minimum_native_margin=.1,
        minimum_epoch_separation_us=2.,minimum_alias_aware_CFO_separation_hz=5000.,
        no_extrapolation=True,one_selected_pair_per_physical_visit=True,design_sigma_hz=20.,
        design_sigma_hypothetical_actual_RF_must_qualify=True,
        workers=8,per_case_seconds=120,no_new_RF_or_GPS_or_following_TLE=True,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_differential_information.py',ROOT/'tools/inventory_ds23_active_differential_pairs.py']})
    path=OUT/'target_selection_protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('information target-selection protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,c) for c in cases])]
    write(OUT/'target_selection.json',dict(rows=rows,all_terminal=True,
        selected_probes=sum(len(r.get('selected',[])) for r in rows),
        cases_with_targets=sum(bool(r.get('selected')) for r in rows),
        no_real_position_change=True,original69probe_inventory_preserved=True))


if __name__=='__main__':main()
