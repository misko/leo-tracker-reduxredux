"""Locate exhaustive pilot-delay winners in the original coarse proposal order."""
import hashlib,json
from pathlib import Path
import numpy as np
from tests.starlink_glrt.test_cpu_coarse import sorted_peak_oracle
BASE=Path(__file__).parent
manifest=json.loads((BASE/'confirmed-rx-full-delay-v1/result.json').read_text())
results=[]
for case in manifest['cases']:
    root=BASE/case['source'];op=json.loads((root/'operator.json').read_text())
    path=root/'grids.u32';assert hashlib.sha256(path.read_bytes()).hexdigest()==op['artifacts'][path.name]['sha256']
    grid=np.fromfile(path,dtype='<u4').reshape(-1,11,3333)[case['attempt']-1]
    rows=[json.loads(x) for x in (root/'worker.jsonl').read_text().splitlines()]
    scan=next(r for r in rows if r['kind']=='scan' and r['attempt']==case['attempt'])
    peaks=sorted_peak_oracle(grid,10000)
    assert [list(p) for p in peaks[:64]]==scan['peaks']
    epoch=case['group_maxima'][0]['epoch']
    distance=lambda e:min(abs(e-epoch),3333-abs(e-epoch))
    nearby=[dict(rank=n+1,epoch=e,frequency=f,score=score,delta=e-epoch) for n,(e,f,score) in enumerate(peaks) if distance(e)<=8]
    exact=grid[:,epoch]
    result=dict(source=case['source'],attempt=case['attempt'],exhaustive_epoch=epoch,
        exhaustive_power=case['group_maxima'][0]['power'],coarse_proposal_count=len(peaks),
        first_resolvable_candidate=nearby[0] if nearby else None,nearby_candidates=nearby,
        highest_coarse_score_at_exact_epoch=int(exact.max()),
        grid_cells_strictly_above_exact_max=int(np.count_nonzero(grid>exact.max())),
        grids_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    results.append(result);print(result,flush=True)
output=dict(scope='exhaustive_delay_to_original_coarse_proposal_association',cases=results,
    new_rf_samples=0,acceptance_gates_changed=False,worker_handoffs_measured=False,
    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
with (BASE/'confirmed-rx-coarse-recall-v1.json').open('x') as f:json.dump(output,f,indent=2);f.write('\n')
