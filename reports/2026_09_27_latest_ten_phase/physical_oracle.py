"""Independent continuous-time RF delay check at every replay sample rate."""
from pathlib import Path
import json
import numpy as np
from leo.analysis.starlink.templates import qin_edge_pilot_symbols,edge_frequencies_hz
from phase import designs_for,extract,wrap

def continuous(t,epoch,delay,edge):
    local=t-epoch-delay;symbol=np.floor(local/4.4e-6).astype(int);valid=(symbol>=2)&(symbol<302);out=np.zeros(len(t),complex)
    u=local[valid]-symbol[valid]*4.4e-6-(2/15)*1e-6
    out[valid]=np.sum(qin_edge_pilot_symbols(edge)[symbol[valid]-2]*np.exp(2j*np.pi*u[:,None]*edge_frequencies_hz(edge)),axis=1)/np.sqrt(8)
    return out

def case(rate,edge='upper'):
    start=round(.063*rate);n=round(.007*rate);t=np.arange(start,start+n)/rate;lo=678123.45;cfo=[-120000.,240000.];rf=11.2e9+np.array(cfo);projection=[.2,-.3];baseline=.6;epochs=[.00001,.00042]
    visit=dict(edge=edge,modes=[dict(seeds=[dict(integer_epoch_sample=round(ep*rate),fractional_epoch_offset_samples=ep*rate-round(ep*rate),cfo_hz=cfo[m]+rx*lo) for rx in (0,1)]) for m,ep in enumerate(epochs)])
    d,c=designs_for(visit,rate,start,n,[0.,0.]);iq=np.zeros((n,2),complex)
    for m,ep in enumerate(epochs):
        center=round(((start+n/2)/rate-ep)*750);frames=[ep+k/750 for k in range(center-3,center+4)]
        for rx in (0,1):
            delay=-rx*baseline*projection[m]/299792458.
            envelope=sum(continuous(t,f,delay,edge)*np.exp(1j*(.3*j+.2*m)) for j,f in enumerate(frames))
            iq[:,rx]+=envelope*np.exp(2j*np.pi*(cfo[m]+rx*lo)*t-2j*np.pi*rf[m]*delay+1j*rx*(.7+2*np.pi*75*t))
    result=extract(d,c,iq,rate);actual=result['modes'][1]['evaluation']['phase_rad']-result['modes'][0]['evaluation']['phase_rad'];expected=2*np.pi*baseline*(rf[1]*projection[1]-rf[0]*projection[0])/299792458.
    return dict(rate_hz=rate,edge=edge,error_rad=float(wrap(actual-expected)),both_qualified=result['both_qualified'])

if __name__=='__main__':
    cases=[case(r,e) for r in [2500000,5000000,7500000,10000000] for e in ['lower','upper']]
    Path(__file__).with_name('physical-oracle.json').write_text(json.dumps(dict(protocol='Synthetic continuous-time pilot tones, physical carrier and envelope delay, 0.6m baseline, independent frame phases, common LO and75Hz drift. No noise/multipath/ADC filter; independent of FFT template shifting.',cases=cases),indent=2)+'\n')
    print(json.dumps(cases,indent=2))
