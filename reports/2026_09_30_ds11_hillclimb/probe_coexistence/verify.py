"""Replay common-sample scores with QR solves, independently of least-squares runner."""
import json
from pathlib import Path

import numpy as np
import run

HERE=Path(__file__).resolve().parent


def main():
    plan=run.read(HERE/'plan.json');outcome=run.read(HERE/'outcome.json')
    for artifact in (plan,outcome):
        for path,h in artifact['sources'].items():assert run.digest(path)==h,path
    receipt=run.read(HERE/'receipt.json')
    assert receipt['exit_code']==0 and receipt['plan_sha256']==run.digest(HERE/'plan.json')
    summaries=[];maximum=0.
    cases=[(f"pair-{r['ordinal']:02d}",r) for r in plan['rows']]+[(f"control-{r['ordinal']:03d}",r) for r in plan['controls']]
    for name,row in cases:
        result=outcome['rows'][name];assert result['status']=='ok'
        path=result.get('excerpt_path',row.get('path'))
        assert run.digest(path)==result.get('excerpt_sha256',row.get('sha256'))
        iq=np.load(path,allow_pickle=False)
        families,train,held=run.matrices(row);n=len(train)
        assert not np.any(train&held)
        y=iq[:n,0].astype(float)+1j*iq[:n,1]
        for arm,matrix in families.items():
            q,r=np.linalg.qr(matrix[train],mode='reduced')
            coefficients=np.linalg.solve(r,q.conj().T@y[train])
            nmse=float(np.sum(abs(y[held]-matrix[held]@coefficients)**2)/np.sum(abs(y[held])**2))
            discrepancy=abs(nmse-result['scores'][arm]['held_nmse'])
            maximum=max(maximum,discrepancy)
            assert discrepancy<1e-12
            assert result['scores'][arm]['rank']==matrix.shape[1]
        scores=result['scores']
        if name.startswith('pair'):
            singles=min(scores[a]['held_nmse'] for a in ('a','b'))
            controls=min(scores[a]['held_nmse'] for a in ('a_rolled_b','b_rolled_a'))
            joint=scores['joint']['held_nmse']
            summaries.append(dict(case=name,joint_nmse=joint,best_single_nmse=singles,
                                  joint_gain_vs_best_single=singles-joint,
                                  joint_gain_vs_best_rolled_control=controls-joint,
                                  joint_beats_singles_and_controls=joint<min(singles,controls)))
        else:
            summaries.append(dict(case=name,single_beats_rolled=scores['single']['held_nmse']<scores['rolled']['held_nmse']))
    files=[HERE/'plan.json',HERE/'outcome.json',HERE/'receipt.json',Path(__file__)]
    result=dict(schema='ds11-common-probe-pilot-verification/v1',cases=summaries,
                maximum_qr_replay_discrepancy=maximum,position_fits=0,
                sources={str(p):run.digest(p) for p in files})
    run.write(HERE/'verification.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
