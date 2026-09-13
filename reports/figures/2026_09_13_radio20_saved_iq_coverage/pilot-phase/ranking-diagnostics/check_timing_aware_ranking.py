"""Offline timing-tolerant ranking; unchanged C resolver and historical gates."""
import hashlib,json,subprocess,time
from pathlib import Path
import numpy as np
BASE=Path(__file__).parent
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out=BASE/'timing-aware-ranking-v1';out.mkdir(exist_ok=False)
ranking=json.loads((BASE/'expanded-proposal-ranking-v1.json').read_text())
inputs=json.loads((BASE/'combined-pilot-controls-v1/result.json').read_text())
benchmark=BASE/'expanded-worker-v1/bench'
assert digest(benchmark)==json.loads((BASE/'expanded-worker-v1/result.json').read_text())['binary_sha256']
refs=np.fromfile(BASE/'direct-references.ci16',dtype='<i2').reshape(4,3300,4).astype(float)
ref=refs[0,:,0]+1j*refs[0,:,1];energy=np.vdot(ref,ref).real
result=dict(new_rf_samples=0,receiver_time='frozen',acceptance_gates_changed=False,
    arm_cost_measured=False,live_tracking_qualified=False,fft=4096,
    candidate_budgets=[64,256],radii=[0,1,2,4,8],worker_binary_sha256=digest(benchmark),
    ranking_sha256=digest(BASE/'expanded-proposal-ranking-v1.json'),script_sha256=digest(Path(__file__)),cases=[])
for case,source in zip(ranking['cases'],inputs['cases']):
    label=f"{case['label']}-{case['number']}";path=BASE/'combined-pilot-controls-v1'/label/'iq.ci16'
    assert (case['label'],case['number'])==(source['label'],source['number']) and digest(path)==source['input_sha256']
    raw=np.fromfile(path,dtype='<i2').reshape(-1,2).astype(float);iq=raw[:,0]+1j*raw[:,1]
    before=time.monotonic();scores=[]
    for peak in case['scores']:
        powers=[]
        for shift in range(-8,9):
            start=peak['epoch']+22+shift;z=iq[start:start+3300];assert len(z)==3300
            powers.append(float(max(abs(np.fft.fft(z*ref.conj(),4096))**2)/max(float(energy*np.vdot(z,z).real),1)))
        scores.append(powers)
    scores=np.array(scores);elapsed=time.monotonic()-before;comparisons=[];runs={}
    baseline=BASE/'short-fft-scan-host-v1-results'/f'{label}-fft4096.jsonl'
    rows=[json.loads(line) for line in baseline.read_text().splitlines()]
    np.testing.assert_allclose(scores[:64,8],[r['rank_power'] for r in rows[:-1]],rtol=2e-12,atol=2e-14)
    for budget in (64,256):
        for radius in result['radii']:
            block=scores[:budget,8-radius:9+radius];index,column=np.unravel_index(np.argmax(block),block.shape)
            if int(index) not in runs:
                peak=case['scores'][index]
                completed=subprocess.run([str(benchmark),str(path),str(BASE/'direct-references.ci16'),str(peak['epoch']),str(peak['frequency']),str(peak['coarse_score'])],capture_output=True,check=True,timeout=12)
                assert not completed.stderr
                journal=out/f'{label}-candidate{index+1}.jsonl';journal.write_bytes(completed.stdout)
                worker=[json.loads(line) for line in completed.stdout.splitlines()]
                runs[int(index)]=dict(winner=int(index)+1,terminal=worker[-1],accepted=sum(r['accepted'] for r in worker if r['kind']==3),journal_sha256=digest(journal))
            comparisons.append(dict(budget=budget,radius=radius,ranking_shift=int(column)-radius,power=float(block[index,column]),**runs[int(index)]))
    result['cases'].append(dict(label=case['label'],number=case['number'],input_sha256=digest(path),ranking_seconds=elapsed,scores=scores.tolist(),comparisons=comparisons))
    print(label,[(r['budget'],r['radius'],r['winner'],r['accepted']) for r in comparisons],flush=True)
with (out/'result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
