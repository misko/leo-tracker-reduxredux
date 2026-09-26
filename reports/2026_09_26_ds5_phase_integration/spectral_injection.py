"""Explicitly synthetic single-source controls at real candidate geometries."""
from pathlib import Path
import json
import numpy as np
import pilot_extract as E
from run import split,summarize,RATE
from spectral_audit import atom

HERE=Path(__file__).resolve().parent

def main():
    plan=json.loads((HERE/'long-overlap/plan.json').read_text());train,held,_=split();rng=np.random.default_rng(20261001);out=[]
    for scan in plan['scans']:
        if not scan['selected']:continue
        sid=scan['session_id'];v=scan['selected'][0];old=json.loads((HERE/'long-overlap'/(sid+'.json')).read_text())['rows'];pairs=[];geometry=[]
        for m in (0,1):
            prior=next(r for r in old if r['visit']==v['visit'] and r['start_ms']==0 and r['mode']==m)
            pair=[dict(r) for r in v['modes'][m]['seeds']];ep=[r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in pair]
            pair[1]['fractional_epoch_offset_samples']+=round((ep[0]-ep[1])/(RATE/750))*(RATE/750)
            epoch=np.mean([r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in pair]);fraction=epoch-round(epoch)
            for r in pair:r['fractional_epoch_offset_samples']+=prior['timing_offset_samples']-fraction
            pairs.append(pair);geometry.append(E.extract_candidate(np.zeros((70000,2),complex),v['edge'],pair,0,70000,[0.],train,held))
        for source in (0,1):
            signal=np.stack([atom(geometry[source],v['edge'],pairs[source][rx]['tracking_absolute_baseband_cfo_hz'],0,70000)*np.exp(.7j*rx) for rx in (0,1)],axis=1)
            power=float(np.mean(abs(signal)**2))
            for snr in (-20.,0.,20.,None):
                sigma=0 if snr is None else np.sqrt(power/10**(snr/10)/2)
                iq=signal+sigma*(rng.normal(size=signal.shape)+1j*rng.normal(size=signal.shape))
                for extracted in (0,1):
                    r=E.extract_candidate(iq,v['edge'],pairs[extracted],0,70000,[0.],train,held);s=summarize(r,r['alternatives'][0],len(train))
                    out.append(dict(session_id=sid,visit=v['visit'],source_mode=source,extracted_mode=extracted,synthetic_snr_db=snr,held_R=s['coefficients']['held']['R'],held_phase_rad=s['coefficients']['held']['phase_rad'],held_exact_control_ratios=s['held_exact_control_ratios']))
    (HERE/'spectral-audit/single-source-injections.json').write_text(json.dumps(dict(meaning='Synthetic single-mode IQ using real timing/CFO geometry, known RX1−RX0 phase 0.7 rad; SNR over complete window; null SNR means noiseless; one realization per condition, not false-alarm calibration',seed=20261001,rows=out),indent=2)+'\n')
    print(json.dumps([r for r in out if r['source_mode']!=r['extracted_mode']],indent=2))

if __name__=='__main__':main()
