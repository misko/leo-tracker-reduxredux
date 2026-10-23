"""RF-selected whole newly added path exclusion diagnostic, no GPS inference."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run_solver as s
import numpy as np
import signal,time
from leo.analysis.research.retained_track_likelihood import profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
OUT=Path(__file__).resolve().parent
KEY='GRAPH_PATH_persistent5s_005'
def diagnostics(d,kind,arm,saved):
    p=s.exp.paths.build(d,kind,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km']);c=p.calculate(x)
    j=next(i for i,e in enumerate(d['entries']) if e['component']==KEY)
    e=d['entries'][j];t=d['scan'].tracks[e['track_index']];sl=p.linear_slices[j]
    raw=c['linear_raw_prediction_residual_hz'][sl]
    terms=profile(raw,np.zeros(len(raw)),*d['scan'].white[e['track_index']],bias_sigma=300.)
    innovations=terms['innovations'][0];noise=batch_noise_screen(innovations[None,:],t['times'])
    allids={o['observation_id']:o for o in d['observations']}
    return dict(component=KEY,norad=e['norad'],candidate_index=e['candidate_index'],receiver=t['receiver'],channel=t['channel'],rf_hz=t['rf_hz'],
        times_s=t['times'],points=e['points'],observation_ids=e['observation_ids'],alias=e['alias'],
        raw_measured_cfo_hz=[allids[o]['measured_cfo_hz'] for o in e['observation_ids']],
        canonical_track_values_hz=t['values'],raw_prediction_residual_hz=raw,centered_raw_prediction_residual_hz=raw-raw.mean(),
        gate_profile_innovations_hz=innovations,
        profile_metrics={k:v for k,v in terms.items() if k not in ['innovations']},noise_statistics=noise,
        thresholds=dict(profile_rms_hz=450,abs_profile_bias_hz=3000,alias_distance=.5,min_elevation_deg=0,
            mean_z=3,slope_z=3,quadratic_bic_gain=10,maximum_step_z=4,abs_lag1_acf=4/np.sqrt(len(raw))),
        full_mask_endpoint=s.snapshot(p,x,d['entries']))
def main():
    protocol=dict(case='DS23-0365',removed_new_path=KEY,selection='sole RF lag1 gate failure in both arms; no GPS selection',
        original_curved_mask_unchanged=True,original_predictive_entries_unchanged=True,
        ablation='remove exactly one whole newly added native path; retain every other native path and original observation',
        arms=['c0','fitted_c'],fit='existing ordinary cold [0,0], zero phases, 5x48 Gauss Newton',seconds_cap_per_arm=180,
        interpretation='diagnostic ablation only; no production adoption or gate relaxation')
    s.write(OUT/'protocol.json',protocol)
    d,kind,primary,frozen,selected=s.setup('DS23-0365');prior=s.read(s.OUT/'DS23-0365.json')
    reduced=dict(d,entries=[e for e in d['entries'] if e['component']!=KEY]);assert len(reduced['entries'])==len(d['entries'])-1
    assert not any(e['component']==KEY for e in frozen['ordinary_graph']['entries'])
    removed=next(e for e in d['entries'] if e['component']==KEY)
    original_ids=set().union(*(set(c['accepted_observation_ids']) for c in frozen['ordinary_graph']['coverage'].values()))
    assert not set(removed['observation_ids'])&original_ids
    result=dict(protocol=protocol,path_endpoint_diagnostics={},ablation={},removed_entry=removed,
        remaining_entries=reduced['entries'],original_parent_coverage=frozen['ordinary_graph']['coverage'])
    for arm in protocol['arms']:
        result['path_endpoint_diagnostics'][arm]={fit['solver']:diagnostics(d,kind,arm,fit['summary']) for fit in prior['fits'] if fit['arm']==arm}
    s.write(OUT/'results.json',result)
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180 second fit cap')))
    for arm in protocol['arms']:
        signal.alarm(180);start=time.monotonic()
        try:
            fitted=s.exp.ordinary(reduced,kind,arm)
            coverage=s.exp.paths.coverage(reduced,kind,arm,fitted)
            preserved=set(frozen['ordinary_graph']['coverage'][arm]['accepted_observation_ids'])<=set(coverage['accepted_observation_ids'])
            fitted['qualified']=bool(s.qualifies(fitted) and preserved)
            result['ablation'][arm]=dict(summary=fitted,coverage=coverage,original_parent_ids_preserved=preserved,
                common_full_mask_endpoint=diagnostics(d,kind,arm,fitted),seconds=time.monotonic()-start)
        except TimeoutError as exc:result['ablation'][arm]=dict(status='timeout',error=str(exc))
        finally:signal.alarm(0)
        s.write(OUT/'results.json',result)
        print(arm,result['ablation'][arm].get('summary',{}).get('minimum_gate_slack'),flush=True)
if __name__=='__main__':main()
