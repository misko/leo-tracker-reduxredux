"""Interior-only alignment search on retained pilots; no production acceptance claim.

Missing IQ outside a retained cut is never invented. Every hypothesis uses
the same 3236 observed samples and an in-bounds slice of a pinned reference.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.signal import zoom_fft

BASE=Path(__file__).parent
ROOT=BASE/'live-observer3-60-v1'
RATE=2500000
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    op=json.loads((ROOT/'operator.json').read_text())
    for name in ('worker.jsonl','worker.iq.ci16'):
        assert digest(ROOT/name)==op['artifacts'][name]['sha256']
    refpath=BASE/'direct-references.ci16'
    assert digest(refpath)=='78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2'
    raw=np.fromfile(refpath,dtype='<i2').reshape(4,3300,4).astype(float)
    refs=raw[:,:,0]+1j*raw[:,:,1]
    raw=np.fromfile(ROOT/'worker.iq.ci16',dtype='<i2').reshape(-1,2).astype(float)
    iq=raw[:,0]+1j*raw[:,1]
    rows=[json.loads(line) for line in (ROOT/'worker.jsonl').read_text().splitlines()]
    output=dict(scope='fixed_interior_alignment_search',sample_rate=RATE,common_samples=3236,
                timing_search_quarters=[-64,64],frequency_half_width_hz=1000,frequency_grid_hz=5,
                new_rf_samples=0,acceptance_gates_changed=False,production_acceptance_evaluated=False,
                false_alarm_calibrated=False,source_sha256=digest(Path(__file__)),
                input_sha256={n:digest(ROOT/n) for n in ('worker.jsonl','worker.iq.ci16')},cases=[])
    for attempt in range(1,7):
        local=[r for r in rows if r.get('attempt')==attempt]
        center=next(r for r in local if r['kind']==2)['cfo_hz']
        grid=np.linspace(center-1000,center+1000,401);measurements=[]
        for row in [r for r in local if r['kind']==3]:
            at=row['iq_offset'];z=iq[at+32:at+3268];assert len(z)==3236
            energy=np.vdot(z,z).real;best=None;fixed=None
            for quarter in range(-64,65):
                whole,phase=divmod(row['reference_phase']+quarter,4)
                ref=refs[phase,32-whole:3268-whole];assert len(ref)==len(z)
                bins=zoom_fft(z*ref.conj(),[grid[0],grid[-1]],len(grid),fs=RATE,endpoint=True)
                k=int(np.argmax(abs(bins)))
                power=float(abs(bins[k])**2/(energy*np.vdot(ref,ref).real))
                candidate=dict(offset_quarters=quarter,cfo_hz=float(grid[k]),power=power,
                               frequency_boundary=k in (0,400),timing_boundary=abs(quarter)==64)
                if quarter==0:fixed=candidate
                if best is None or power>best['power']:best=candidate
            # Independently evaluate the selected complex dot without zoom FFT.
            whole,phase=divmod(row['reference_phase']+best['offset_quarters'],4)
            ref=refs[phase,32-whole:3268-whole]
            dot=np.vdot(ref,z*np.exp(-2j*np.pi*best['cfo_hz']*np.arange(len(z))/RATE))
            direct=float(abs(dot)**2/(energy*np.vdot(ref,ref).real))
            np.testing.assert_allclose(best['power'],direct,rtol=1e-8,atol=1e-12)
            measurements.append(dict(frame=row['frame'],original_first=row['first'],
                original_phase=row['reference_phase'],original_c_coherence=row['coherence'],
                fixed_timing_frequency_search=fixed,local_search=best))
        output['cases'].append(dict(attempt=attempt,measurements=measurements))
        print(attempt,[(r['frame'],round(r['local_search']['power'],4),r['local_search']['offset_quarters']) for r in measurements],flush=True)
    with (BASE/'live-observer3-alignment-v1.json').open('x') as stream:
        json.dump(output,stream,indent=2);stream.write('\n')


if __name__=='__main__':main()
