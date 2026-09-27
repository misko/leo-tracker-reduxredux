"""Physical delayed-waveform oracle, independent of extraction's FFT shifter."""
from pathlib import Path
import json
import numpy as np
from leo.analysis.starlink.templates import qin_edge_pilot_symbols,edge_frequencies_hz
from joint_phase_run import geometry
from joint_mode_audit import design
from joint_phase import extract

HERE=Path(__file__).resolve().parent
OUT=HERE/'quality-quadrature'
C=299792458.
RATE=1e7

def continuous_pilot(times,epoch,delay):
    # Continuous-time evaluation from symbols and tones, with no sampled
    # template interpolation or FFT fractional-shift function.
    local=times-epoch-delay;symbol=np.floor(local/4.4e-6).astype(int);valid=(symbol>=2)&(symbol<302)
    out=np.zeros(len(times),complex);codes=qin_edge_pilot_symbols('lower');freq=edge_frequencies_hz('lower')
    u=local[valid]-symbol[valid]*4.4e-6-(2/15)*1e-6
    out[valid]=np.sum(codes[symbol[valid]-2]*np.exp(2j*np.pi*u[:,None]*freq[None,:]),axis=1)/np.sqrt(8)
    return out

def case(baseline,start_ms,shared_frequency=False,geometric_rates_hz=(0.,0.)):
    start=round(start_ms*1e4);stop=start+70000;t=np.arange(start,stop)/RATE
    cfo=np.array([-120000.,240000.]);rf=11.2e9+cfo;projection=np.array([.2,-.3]);lo=678123.45
    designs=[[],[]];controls=[[],[]];iq=np.zeros((70000,2),complex)
    for mode,epoch in enumerate([100.,4200.]):
        pair=[dict(integer_epoch_sample=epoch,fractional_epoch_offset_samples=0.)]*2;g=geometry(pair,'lower',start,stop)
        frame_times=(g['frame_starts']+g['frame_fractional_offsets_samples'])/RATE
        for rx in (0,1):
            designs[rx].append(design(g,'lower',cfo[mode]+rx*lo,start,stop));controls[rx].append(design(g,'lower',cfo[mode]+rx*lo,start,stop,True))
            delay=-rx*baseline*projection[mode]/C-rx*geometric_rates_hz[mode]*(t-(start+stop)/(2*RATE))/rf[mode]
            envelope=sum(continuous_pilot(t,frame,delay)*np.exp(1j*(.3*j+.2*mode)) for j,frame in enumerate(frame_times))
            iq[:,rx]+=envelope*np.exp(2j*np.pi*(cfo[mode]+rx*lo)*t-2j*np.pi*rf[mode]*delay+1j*rx*(.7+2*np.pi*75*t))
    result=extract(designs,controls,iq,shared_frequency=shared_frequency)
    measured=result['modes'][1]['evaluation']['phase_rad']-result['modes'][0]['evaluation']['phase_rad']
    expected=2*np.pi*baseline*(rf[1]*projection[1]-rf[0]*projection[0])/C
    error=float(np.angle(np.exp(1j*(measured-expected))))
    return dict(baseline_m=baseline,start_ms=start_ms,shared_frequency=shared_frequency,geometric_rates_hz=list(geometric_rates_hz),expected_wrapped_phase_rad=float(np.angle(np.exp(1j*expected))),measured_wrapped_phase_rad=float(np.angle(np.exp(1j*measured))),error_rad=error,both_qualified=result['both_qualified'],residual_frequency_hz=[r['frequency_hz'] for r in result['modes']],R=[r['evaluation']['R'] for r in result['modes']])

def main():
    OUT.mkdir(exist_ok=True);rows=[case(b,s) for b in (0.,.3,.6) for s in (0,63)]
    (OUT/'physical-phase-audit.json').write_text(json.dumps(dict(protocol='Two continuous-time pilot sources, physical RF propagation phase and envelope delay, independent TX frame phases, shared 678123.45Hz LO difference and additional75Hz residual. Extractor still uses its sampled/FFT templates. No noise, multipath or unknown hardware response; synthetic sign/reference check only.',cases=rows,max_absolute_error_rad=max(abs(r['error_rad']) for r in rows)),indent=2)+'\n');print(json.dumps(rows,indent=2))

if __name__=='__main__':main()
