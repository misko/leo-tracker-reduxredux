"""Finer frequency ranking at exhaustive winners; no worker acceptance claim."""
import hashlib,json
from pathlib import Path
import numpy as np
BASE=Path(__file__).parent;root=BASE/'confirmed-rx-full-delay-v1'
manifest=json.loads((root/'result.json').read_text())
refs=np.fromfile(BASE/'direct-references.ci16',dtype='<i2').reshape(4,3300,4).astype(float)
ref=refs[0,:,0]+1j*refs[0,:,1];energy=np.vdot(ref,ref).real
results=[]
for case in manifest['cases']:
    path=BASE/case['source']/'scan.iq.ci16'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==case['source_sha256']
    raw=np.fromfile(path,dtype='<i2').reshape(-1,14000,2)[case['attempt']-1].astype(float)
    iq=raw[:,0]+1j*raw[:,1];groups=[]
    for prior in case['group_maxima']:
        choices=[]
        for shift in range(-2,3):
            first=22+prior['epoch']+shift;z=iq[first:first+3300];assert len(z)==3300
            spectrum=abs(np.fft.fft(z*ref.conj(),16384))**2
            k=int(spectrum.argmax());denom=max(float(energy*np.vdot(z,z).real),1)
            power=float(spectrum[k]/denom)
            direct=abs(np.vdot(ref,z*np.exp(-2j*np.pi*k*np.arange(3300)/16384)))**2/denom
            np.testing.assert_allclose(power,direct,rtol=2e-10,atol=2e-14)
            choices.append(dict(epoch=prior['epoch']+shift,bin=k,power=power,cfo_hz=(k if k<8192 else k-16384)*2500000/16384))
        groups.append(max(choices,key=lambda c:c['power']))
    results.append(dict(source=case['source'],attempt=case['attempt'],refined=groups))
result=dict(scope='offline_single_pilot_finer_frequency_and_local_delay_ranking',
    fft_bins=16384,local_delay_radius=2,direct_dft_checks=105,worker_acceptance_measured=False,
    new_rf_samples=0,live_tracking_qualified=False,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cases=results)
with (root/'refined.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
for case in results:print(case['source'],case['attempt'],case['refined'])
