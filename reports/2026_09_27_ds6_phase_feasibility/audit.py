"""Bounded real-data rate audit plus explicitly conditional sensitivity scenarios."""
import json, hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
manifest=json.loads((ROOT/'2026_09_27_ds6_roof/manifest.json').read_text())
members={r['session_id'] for r in manifest['captures']}
rows=[];sources={}
for path in sorted((ROOT/'2026_09_27_latest_ten_phase').glob('scan-fw-*.json')):
    d=json.loads(path.read_text())
    if d.get('session_id') not in members: continue
    sources[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    for row in d.get('rows',[]):
        if not row.get('both_qualified'):continue
        a,b=row['modes'];wrap=lambda x: np.angle(np.exp(1j*x))
        err=wrap((b['evaluation']['phase_rad']-a['evaluation']['phase_rad'])-(b['train']['phase_rad']-a['train']['phase_rad']))
        rows.append(dict(session_id=d['session_id'],visit=row['visit'],start_ms=row['start_ms'],differential_rate_hz=b['frequency_hz']-a['frequency_hz'],split_disagreement_deg=float(np.degrees(err))))
assert len(rows)==482 and len(sources)==10
c=299792458.; B=.08; f=12.7e9; distance=500e3; speed=10e3
# For each source |du/dt| <= speed/range and ||du/dx|| <= 1/range.
# Summing magnitudes gives an optimistic upper bound for a two-source DD.
rate_bound=2*f*B/c*speed/distance
phase_per_km_deg=360*2*f*B/c*1000/distance
rates=np.abs([r['differential_rate_hz'] for r in rows])
split_rms=np.sqrt(np.mean(np.square([r['split_disagreement_deg'] for r in rows])))
# A toy zero-slope five-pilot experiment diagnoses short-window rate uncertainty.
# Noise levels below are a scenario sweep, not a calibration to the real data.
rng=np.random.default_rng(2026092707);times=(np.arange(5)-2)/750
toy=[]
for sigma in [1.,3.,6.,10.]:
    phases=rng.normal(0,np.radians(sigma),(20000,2,5))
    slopes=np.sum(phases*times,axis=-1)/np.sum(times**2)/(2*np.pi)
    delta=slopes[:,1]-slopes[:,0]
    analytic=np.sqrt(2)*np.radians(sigma)/np.sqrt(np.sum(times**2))/(2*np.pi)
    assert abs(np.std(delta)/analytic-1)<.03
    toy.append(dict(per_pilot_noise_deg=sigma,rate_std_hz=float(np.std(delta)),median_abs_rate_hz=float(np.median(abs(delta)))))
# Finite differences independently check the geometric derivative upper bound.
sat=np.array([0.,0.,distance]);baseline=np.array([B,0.,0.]);eps=1.
phase=lambda x: 2*np.pi*f/c*np.dot(baseline,(sat-x)/np.linalg.norm(sat-x))
derivative=(phase(np.array([eps,0,0]))-phase(np.array([-eps,0,0])))/(2*eps)
assert np.isclose(abs(derivative),2*np.pi*f*B/(c*distance),rtol=1e-8)
summary=dict(status='sub_km_not_demonstrated',ds6_recordings=43,cached_phase_recordings=10,qualified_pair_windows=len(rows),qualified_pair_dwells=len({(r['session_id'],r['visit']) for r in rows}),median_abs_differential_rate_hz=float(np.median(rates)),split_disagreement_rms_deg=float(split_rms),scenario=dict(baseline_m=B,rf_hz=f,min_slant_range_m=distance,max_relative_speed_m_s=speed,maximum_DD_rate_hz=rate_bound,maximum_DD_phase_change_per_km_deg=phase_per_km_deg),windows_below_scenario_rate_bound=int(sum(rates<=rate_bound)),toy_zero_slope=toy,input_sha256=sources,seed=2026092707)
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(HERE/'window-rate-audit.json').write_text(json.dumps(rows,indent=2)+'\n')
fig,axes=plt.subplots(1,2,figsize=(12,4.5))
axes[0].hist(rates,bins=np.geomspace(.01,1000,40));axes[0].axvline(rate_bound,color='red',label='Conditional geometric bound');axes[0].set(xscale='log',xlabel='Absolute fitted DD rate (Hz)',ylabel='Qualified windows',title='Real DS6 subset: short-window rates');axes[0].legend()
ranges=np.linspace(300,2000,200)
axes[1].plot(ranges,360*2*f*B/c*1000/(ranges*1000));axes[1].set(xlabel='Assumed minimum slant range (km)',ylabel='Upper bound: DD phase change per 1 km (degrees)',title='Optimistic geometric sensitivity, 80 mm / 12.7 GHz');axes[1].grid(alpha=.3)
fig.tight_layout();fig.savefig(HERE/'phase-feasibility.png',dpi=160);plt.close(fig)
print(json.dumps(summary,indent=2))
