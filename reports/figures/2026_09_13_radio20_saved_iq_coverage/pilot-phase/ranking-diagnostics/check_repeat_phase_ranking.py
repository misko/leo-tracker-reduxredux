"""Choose a measured first-repeat hypothesis; frozen-time diagnostic only."""
import hashlib,json,subprocess
from pathlib import Path
import numpy as np
BASE=Path(__file__).parent;out=BASE/'repeat-phase-ranking-v1';out.mkdir(exist_ok=False)
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((BASE/'expanded-proposal-ranking-v1.json').read_text())
prior=json.loads((BASE/'combined-pilot-controls-v1/result.json').read_text())
refs=np.fromfile(BASE/'direct-references.ci16',dtype='<i2').reshape(4,3300,4).astype(float)
ref=refs[0,:,0]+1j*refs[0,:,1];energy=np.vdot(ref,ref).real
binary=BASE/'expanded-worker-v1/bench'
assert digest(binary)==json.loads((BASE/'expanded-worker-v1/result.json').read_text())['binary_sha256']
result=dict(scope='repeat_phase_ranking_frozen_worker_replay',new_rf_samples=0,acceptance_gates_changed=False,
    live_tracking_qualified=False,production_origin_contract_implemented=False,arm_cost_measured=False,
    script_sha256=digest(Path(__file__)),worker_sha256=digest(binary),cases=[])
for case,original in zip(manifest['cases'],prior['cases']):
    label=f"{case['label']}-{case['number']}";directory=out/label;directory.mkdir()
    source=BASE/f"paced-original-seed-input-v1/{case['label']}.ci16"
    expected={'positive':'af991e03e69271c253d2fe6b5aeff110c9da5d5bd6ddda8c6850584f9e97b1c4','control':'5b945b575fbff519de733ded2418b2f82110458ff52237e2a3126d8d7a53d5b9'}[case['label']]
    assert digest(source)==expected
    raw=np.fromfile(source,dtype='<i2').reshape(-1,2);offset=case['number']*447851
    assert hashlib.sha256(raw[offset:offset+447851].tobytes()).hexdigest()==original['input_sha256']
    iq=raw[offset:offset+20000].astype(float);z=iq[:,0]+1j*iq[:,1];powers=[];bins=[]
    for peak in case['scores'][:64]:
        row=[];freq=[]
        for shift in (0,3333,6667):
            x=z[peak['epoch']+22+shift:peak['epoch']+3322+shift]
            spectrum=abs(np.fft.fft(x*ref.conj(),4096))**2/max(float(energy*np.vdot(x,x).real),1)
            index=int(np.argmax(spectrum));power=float(spectrum[index]);row.append(power);freq.append(index)
            direct=abs(np.vdot(ref,x*np.exp(-2j*np.pi*index*np.arange(3300)/4096)))**2/max(float(energy*np.vdot(x,x).real),1)
            np.testing.assert_allclose(power,direct,rtol=2e-10,atol=2e-14)
        powers.append(row);bins.append(freq)
    scores=np.array(powers);index,repeat=np.unravel_index(np.argmax(scores),scores.shape)
    peak=case['scores'][index];shift=(0,3333,6667)[repeat]
    selected=raw[offset+shift:offset+shift+447851];assert len(selected)==447851
    selected.tofile(directory/'iq.ci16')
    run=subprocess.run([str(binary),str(directory/'iq.ci16'),str(BASE/'direct-references.ci16'),str(peak['epoch']),str(peak['frequency']),str(peak['coarse_score'])],capture_output=True,check=True,timeout=12)
    assert not run.stderr
    (directory/'worker.jsonl').write_bytes(run.stdout)
    rows=[json.loads(line) for line in run.stdout.splitlines()];past=[r for r in rows if r['kind']==3]
    result['cases'].append(dict(label=case['label'],number=case['number'],source_sha256=expected,source_offset=offset,
        repeat=int(repeat),repeat_shift=shift,winner=int(index)+1,proposal=peak,power=float(scores[index,repeat]),
        powers=powers,bins=bins,terminal=rows[-1],accepted=sum(r['accepted'] for r in past),
        selected_iq_sha256=digest(directory/'iq.ci16'),journal_sha256=digest(directory/'worker.jsonl')))
    print(label,'repeat',repeat,'winner',index+1,'accepted',sum(r['accepted'] for r in past),flush=True)
with (out/'result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
