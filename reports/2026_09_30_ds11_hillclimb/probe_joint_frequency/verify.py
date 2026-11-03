"""Independent QR replay and source/selection checks for sealed frequency fits."""
import json
from pathlib import Path

import numpy as np
import run

HERE=Path(__file__).resolve().parent


def main():
    p=run.previous;plan=p.read(HERE/'plan.json');outcome=p.read(HERE/'outcome.json')
    for artifact in (plan,outcome):
        for path,h in artifact['sources'].items():assert p.digest(path)==h,path
    old=p.read(run.PREVIOUS/'outcome.json')
    maximum=0.;starts=0
    for row,result in zip(plan['rows'],outcome['rows'],strict=True):
        assert result['status']=='ok' and result['usable']
        selection=p.read(result['selection_path'])
        assert p.digest(result['selection_path'])==result['selection_sha256']
        assert selection['held_used'] is False and selection['plan_sha256']==p.digest(HERE/'plan.json')
        selected=min([s for s in selection['starts'] if s['qualified']],key=lambda s:s['training_nmse'])
        assert selected==selection['selected']
        starts+=sum(s['qualified'] for s in selection['starts'])
        previous=old['rows'][f"pair-{row['ordinal']:02d}"]
        assert p.digest(previous['excerpt_path'])==previous['excerpt_sha256']
        iq=np.load(previous['excerpt_path'],allow_pickle=False)
        families,training,held=p.matrices(row);n=len(training)
        times=np.arange(n)/5e6;times-=np.mean(times[training])
        y=iq[:n,0].astype(float)+1j*iq[:n,1]
        frequencies=dict(cached=[0.,0.],separate=[s['delta_khz'] for s in selection['separate']],joint=selected['delta_khz'])
        for arm,delta in frequencies.items():
            matrix=np.column_stack([families[a]*np.exp(2j*np.pi*1000*d*times)[:,None]
                                    for a,d in zip(('a','b'),delta,strict=True)])
            q,r=np.linalg.qr(matrix[training],mode='reduced')
            coefficients=np.linalg.solve(r,q.conj().T@y[training])
            score=float(np.sum(abs(y[held]-matrix[held]@coefficients)**2)/np.sum(abs(y[held])**2))
            maximum=max(maximum,abs(score-result['scores'][arm]))
    assert maximum<1e-12
    comparisons={}
    for comparator in ('cached','separate'):
        gains=[r['scores'][comparator]-r['scores']['joint'] for r in outcome['rows']]
        comparisons[comparator]=dict(wins=sum(g>0 for g in gains),mean_gain=float(np.mean(gains)),median_gain=float(np.median(gains)))
    paths=[HERE/'plan.json',HERE/'outcome.json',Path(__file__)]
    verification=dict(schema='ds11-common-probe-joint-frequency-verification/v1',
                      maximum_qr_replay_discrepancy=maximum,qualified_starts=starts,
                      comparisons=comparisons,position_fits=0,
                      sources={str(path):p.digest(path) for path in paths})
    p.write(HERE/'verification.json',verification)
    print(json.dumps(verification,indent=2))


if __name__=='__main__':
    main()
