"""Independent per-frame QR replay of eight-frame frequency predictions."""
import json
from pathlib import Path

import numpy as np
import run

HERE=Path(__file__).resolve().parent


def main():
    p=run.previous;plan=p.read(HERE/'plan.json');outcome=p.read(HERE/'outcome.json')
    for artifact in (plan,outcome):
        for path,h in artifact['sources'].items():assert p.digest(path)==h,path
    old=p.read(run.PREVIOUS/'outcome.json');maximum=0.;qualified=0;frame_checks=0
    for row,result in zip(plan['rows'],outcome['rows'],strict=True):
        assert result['status']=='ok' and result['usable'] and result['frames']==8
        selection=p.read(result['selection_path'])
        assert p.digest(result['selection_path'])==result['selection_sha256']
        assert selection['held_used'] is False and selection['plan_sha256']==p.digest(HERE/'plan.json')
        best=min([r for r in selection['starts'] if r['qualified']],key=lambda r:r['training_nmse'])
        assert best==selection['selected'];qualified+=sum(r['qualified'] for r in selection['starts'])
        saved=old['rows'][f"pair-{row['ordinal']:02d}"]
        assert p.digest(saved['excerpt_path'])==saved['excerpt_sha256']
        blocks=run.blocks_for(row,np.load(saved['excerpt_path'],allow_pickle=False))
        deltas=dict(cached=[0.,0.],separate=[r['delta_khz'] for r in selection['separate']],joint=best['delta_khz'])
        for arm,delta in deltas.items():
            numerator=denominator=0.
            for i,b in enumerate(blocks):
                matrix=np.column_stack([a*np.exp(2j*np.pi*1000*d*b['times'])[:,None] for a,d in zip(b['parts'],delta,strict=True)])
                train,held=b['training'],b['held'];y=b['samples']
                assert not np.any(train&held)
                q,r=np.linalg.qr(matrix[train],mode='reduced')
                coefficients=np.linalg.solve(r,q.conj().T@y[train])
                error=float(np.sum(abs(y[held]-matrix[held]@coefficients)**2))
                energy=float(np.sum(abs(y[held])**2));numerator+=error;denominator+=energy
                maximum=max(maximum,abs(error/energy-result['scores'][arm]['frame_nmse'][i]));frame_checks+=1
            maximum=max(maximum,abs(numerator/denominator-result['scores'][arm]['nmse']))
    assert maximum<1e-12
    comparisons={}
    for left,right in (('joint','cached'),('joint','separate'),('separate','cached')):
        gains=[r['scores'][right]['nmse']-r['scores'][left]['nmse'] for r in outcome['rows']]
        comparisons[f'{left}_versus_{right}']=dict(wins=sum(g>0 for g in gains),mean_gain=float(np.mean(gains)),median_gain=float(np.median(gains)))
    files=[HERE/'plan.json',HERE/'outcome.json',Path(__file__)]
    output=dict(schema='ds11-eight-frame-frequency-verification/v1',qualified_starts=qualified,
                frame_scores_replayed=frame_checks,maximum_qr_replay_discrepancy=maximum,
                comparisons=comparisons,position_fits=0,sources={str(f):p.digest(f) for f in files})
    p.write(HERE/'verification.json',output)
    print(json.dumps(output,indent=2))


if __name__=='__main__':
    main()
