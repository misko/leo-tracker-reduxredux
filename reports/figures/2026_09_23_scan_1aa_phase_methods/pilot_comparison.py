"""Compare pilot variants against frame-matched scalar phase with training-only offset."""
import json
from pathlib import Path
import numpy as np
from leo.analysis.starlink.adaptive_dual_rx_phase import fit_linear_phasor
ROOT=Path('/tmp/phase-1aa-review')
doc=json.loads((ROOT/'comparison.json').read_text());out=[]
def wrap(x):return np.angle(np.exp(1j*np.asarray(x)))
for visit in doc['visits']:
    if visit['state']!='replayed':continue
    model=visit['broadband']['model'];rate=visit['sample_rate_hz'];prod=visit['production_relative_phase']
    times=np.asarray(prod['scalar_time_s']);unwrapped=np.unwrap(prod['scalar_phase_rad'])
    def carrier(sample):
        dt=(np.asarray(sample)-model['reference_sample'])/rate
        return 2*np.pi*(model['relative_cfo_hz']*dt+.5*model['relative_cfo_rate_hz_s']*dt**2)
    for method in ('principal','branch_lifted','offset_authority','shared_residual','refined_shared'):
        rows=[]
        for p in visit['pilot_variants']:
            if p['method']!=method:continue
            obs=p['observation'];frames=p['support_start_s']+np.asarray(obs['receivers'][0]['frame_starts'])/rate
            if min(frames)<min(times) or max(frames)>max(times):continue
            left=np.array([complex(z['real'],z['imag']) for z in obs['receivers'][0]['frame_phasors']])
            right=np.array([complex(z['real'],z['imag']) for z in obs['receivers'][1]['frame_phasors']])
            weights=np.sqrt(abs(left)*abs(right));center=p['time_s']
            basef=model['relative_cfo_hz']+model['relative_cfo_rate_hz_s']*(center-model['reference_sample']/rate)
            phasors=np.exp(1j*(np.interp(frames,times,unwrapped)+carrier(frames*rate)-carrier(center*rate)-2*np.pi*basef*(frames-center)))
            _,phase,strength=fit_linear_phasor(phasors,frames,weights,center)
            rows.append(dict(time_s=center,support_start_s=p['support_start_s'],support_end_s=p['support_end_s'],
                             native_pilot_rad=p['residual_phase_rad'],scalar_matched_rad=phase,
                             difference_rad=float(wrap(p['residual_phase_rad']-phase)),resultant=p['resultant']))
        train=[r for r in rows if r['support_end_s']<=.06];held=[r for r in rows if r['support_start_s']>=.06]
        offset=float(np.angle(np.mean(np.exp(1j*np.array([r['difference_rad'] for r in train]))))) if train else None
        rms=None
        if offset is not None:
            for row in rows:row['aligned_discrepancy_deg']=float(np.degrees(wrap(row['difference_rad']-offset)))
            if held:rms=float(np.sqrt(np.mean([r['aligned_discrepancy_deg']**2 for r in held])))
        if method=='refined_shared' and rms is not None:
            assert np.isclose(rms,prod['pilot_held_rms_deg'],atol=1e-4),(visit['visit'],rms,prod['pilot_held_rms_deg'])
        out.append(dict(visit=visit['visit'],method=method,training_count=len(train),held_count=len(held),
                        training_offset_rad=offset,held_rms_deg=rms,rows=rows))
(ROOT/'pilot-method-comparison.json').write_text(json.dumps(out,indent=2)+'\n')
for v in (544,569,1642,1659,1667,2138,1464):
    print(v,{r['method']:None if r['held_rms_deg'] is None else round(r['held_rms_deg'],2) for r in out if r['visit']==v})
