"""Descriptive paired causal revision densities in one dependent archive group.

No independent validation, tuning, RF data, GPS or position fit is claimed.
All mode scales/bases and both priors use only pre-issuance TLE versions.
"""
import copy
import json
from pathlib import Path
import signal
import tempfile
import time
from types import SimpleNamespace
import numpy as np
from age_covariance import POLICY,base,project_pair,select_pairs,sha

ROOT=Path(__file__).resolve().parent


def gaussian_score(a,covariance):
    sign,volume=np.linalg.slogdet(covariance)
    if sign<=0:raise ValueError('Nonpositive covariance')
    return float(a@np.linalg.solve(covariance,a)+volume+len(a)*np.log(2*np.pi))


def prior_covariance(coefficients,details):
    energy=sum(r['phase_removed_state_energy_km2'] for r in details)
    residual=sum(r['projection_residual_energy_km2'] for r in details)
    represented=1-residual/max(energy,1e-30)
    if represented<.5:return np.eye(3),dict(status='identity_fallback',represented_energy_fraction=represented)
    covariance,summary=base.shrunk_covariance(coefficients)
    return covariance,dict(summary,status='ready',represented_energy_fraction=represented)


def evaluate(record,forecast):
    from sgp4.api import Satrec
    from analyze_dsx01_fixed_site import ecef_states
    from build_dsx01_orbit_modes import build_modes
    from leo.sky.propagation import ElementSetCatalogue
    z=json.loads(Path(record['input_path']).read_text());native=Path(z['native_path'])
    raw=json.loads((native.parent/'causal_phase_history'/(native.name+'.json')).read_text())
    family=forecast['family'];issue=forecast['issuance_utc_ns'];target=forecast['target_epoch_utc_ns']
    versions=raw['past_versions'][str(family)]
    older=next(r for r in versions if base.element_sha(r['lines'])==forecast['older_element_sha256'])
    held=next(r for r in versions if base.element_sha(r['lines'])==forecast['held_newer_element_sha256'])
    past=[r for r in versions if r['collected_utc_ns']<=issue and r['epoch']<=issue]
    assert held['collected_utc_ns']>issue and held['epoch']>=issue
    assert all(base.element_sha(r['lines'])!=forecast['held_newer_element_sha256'] for r in past)
    prefix=copy.deepcopy(raw);prefix['cutoff_utc_ns']=prefix['origin_utc_ns']=issue
    prefix['sources']=[s for s in raw['sources'] if s['collected_utc_ns']<=issue]
    prefix['past_versions']={str(family):past}
    nominal=dict(lines=older['lines'],provenance=dict(element_epoch_utc_ns=older['epoch'],
        collected_utc_ns=issue,snapshot_digest='sha256:'+older['snapshot_sha256']))
    pairs,info=select_pairs(prefix,nominal,issue,issue,family,forecast['horizon_hours'])
    history,history_info=base.validate_and_select(prefix,nominal,issue,issue,family)
    assert len(pairs)>=2 and len(history)>=3
    previous=max((r for r in past if r['epoch']<older['epoch']-1_000_000_000),key=lambda r:r['epoch'])
    timestamps=[r['time_s'] for r in json.loads((native/'observations.json').read_text())]
    duration=max(timestamps)-min(timestamps)
    origin=target-int(150e9);knots=np.arange(-180.,481.)
    sat=Satrec.twoline2rv(*older['lines'])
    cat=ElementSetCatalogue((str(family),),(family,),(sat,))
    p,v,valid=ecef_states(cat,origin,knots)
    if not valid.all():raise ValueError('Known forecast orbit propagation failed')
    with tempfile.TemporaryDirectory(prefix='density_runtime_',dir=ROOT) as temporary:
        previous_path=Path(temporary)/'previous.tle'
        previous_path.write_text('\n'.join(previous['lines'])+'\n')
        scan=SimpleNamespace(case=record['case'],norads=np.array([family]),elements={str(family):nominal},
            sky=dict(time_s=knots,position_km=p,velocity_km_s=v),
            receipt=dict(origin_utc_ns=origin,cutoff_utc_ns=issue,previous_tle_sha256=sha(previous_path)),
            previous_tle_path=previous_path)
        mode_bank,mode_metadata=build_modes(scan,[0],[0],'physical')
        scales=[mode_metadata[0][k] for k in ['mean_motion_sigma_rev_day','inclination_sigma_deg','raan_sigma_deg']]
        times=np.array([150-duration/2,150.,150+duration/2])
        try:
            a,details=base.project_disagreements(scan,0,mode_bank,nominal,history,times)
            old_covariance,old_info=prior_covariance(a,details['historical_projection'])
        except ValueError as exc:old_covariance,old_info=np.eye(3),dict(status='identity_fallback',reason=str(exc))
        try:
            projected=[project_pair(pair,duration,scales) for pair in pairs]
            age_covariance,age_info=prior_covariance([r[0] for r in projected],[r[1] for r in projected])
        except ValueError as exc:age_covariance,age_info=np.eye(3),dict(status='identity_fallback',reason=str(exc))
        # Freeze preprocessing before the held newer element enters the score.
        preprocessing=dict(issuance_utc_ns=issue,forecast_target_epoch_utc_ns=target,
            physical_SD=scales,current_mode_metadata=mode_metadata[0],
            known_elements=[dict(sha256=base.element_sha(r['lines']),epoch_utc_ns=r['epoch'],
                collected_utc_ns=r['collected_utc_ns']) for r in past],
            older_nominal_element_sha256=base.element_sha(older['lines']),
            previous_element_sha256=base.element_sha(previous['lines']),
            oldB_covariance=old_covariance.tolist(),age2_covariance=age_covariance.tolist())
        assert all(r['collected_utc_ns']<=issue and r['epoch_utc_ns']<=issue for r in preprocessing['known_elements'])
        assert all(r['sha256']!=forecast['held_newer_element_sha256'] for r in preprocessing['known_elements'])
        innovation,held_details=base.project_disagreements(scan,0,mode_bank,nominal,[held],times)
    a=innovation[0]
    scores={name:gaussian_score(a,covariance) for name,covariance in
        [('identity',np.eye(3)),('oldB',old_covariance),('Age2',age_covariance)]}
    return dict(forecast,status='complete',scores_negative_twice_log_density=scores,
        age2_gain_over_identity=scores['identity']-scores['Age2'],age2_gain_over_oldB=scores['oldB']-scores['Age2'],
        coefficient_innovation=a.tolist(),held_represented_energy_fraction=held_details['represented_energy_fraction'],
        oldB_prior=old_info,Age2_prior=age_info,preprocessing=preprocessing,
        score_units='normalized density of the three standardized coefficients conditional on known forecast basis; residual outside that subspace reported separately')


def main():
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120-second auxiliary diagnostic cap')))
    signal.alarm(120);began=time.monotonic()
    support_path=ROOT/'archive_validation_support.json';support=json.loads(support_path.read_text())
    roster_path=ROOT.parent/'evaluation/rf_roster.json'
    records={r['case']:r for r in json.loads(roster_path.read_text())['cases']}
    selected=[r for r in support['forecasts'] if r['age2_and_oldB_prefix_supported']]
    rows=[]
    for forecast in selected:
        try:rows.append(evaluate(records[forecast['case']],forecast))
        except (ValueError,KeyError,OSError) as exc:rows.append(dict(forecast,status='failed',reason=str(exc)))
    signal.alarm(0)
    complete=[r for r in rows if r['status']=='complete']
    packet=dict(status='descriptive_one_dependent_group',independent_holdout_validation=False,
        no_calibration_or_threshold_selection=True,no_RF_or_GPS_or_position_fit=True,
        source_sha256=sha(Path(__file__)),scientific_module_sha256=sha(ROOT/'age_covariance.py'),
        support_inventory_sha256=sha(support_path),roster_sha256=sha(roster_path),
        forecast_count=len(selected),completed=len(complete),failed=len(rows)-len(complete),
        shared_snapshot_connected_groups=support['shared_snapshot_connected_groups'],rows=rows,
        wall_seconds=time.monotonic()-began,
        age2_vs_oldB=dict(sum_normalized_density_gain=float(sum(r['age2_gain_over_oldB'] for r in complete)),
            wins=sum(r['age2_gain_over_oldB']>0 for r in complete)),
        limitation='Dependent descriptive paired forecasts; no probability calibration, independent validation or localization conclusion')
    (ROOT/'causal_density_diagnostic.json').write_text(json.dumps(packet,indent=2,allow_nan=False,default=lambda v:v.tolist() if hasattr(v,'tolist') else str(v))+'\n')
    print(json.dumps({k:v for k,v in packet.items() if k!='rows'},indent=2))


if __name__=='__main__':main()
