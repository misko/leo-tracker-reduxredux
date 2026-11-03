"""Real-capture gradient audit only; no fit matrix or reference starts."""
import json,importlib.util
from pathlib import Path
from dataclasses import replace
import numpy as np
from objective import BackgroundObjective,paired

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parents[1]
SPEC=importlib.util.spec_from_file_location('background_actual_loader',REPORTS/'2026_10_07_sigma1_root_cause/oracle.py')
loader=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(loader)

def main():
    from leo.contracts.regional_position import PositionScore
    out=[]
    for case in ('1939','2139'):
        doc,old,obs,prior,bank,cp,prefix=loader.load(case)
        prior_doc=json.loads((REPORTS/'2026_10_07_sigma1_cones'/case/'polished.json').read_text())
        seed=min((r for r in prior_doc['candidates'] if r['option']=='control' and r['arm']=='fitted-c' and r['feasible']),key=lambda r:r['selection_score'])
        basin=seed['basin'];assoc=cp.get(prefix+':'+basin+':association')['result'];cal=cp.get(prefix+':'+basin+':calibration')['result'];subset=bank.select(assoc['selected_indices'])
        admitted=json.loads((HERE.parent/'identity/paired_topone.json').read_text())['cases'][case]['100ns']['rows']
        pairs=np.array([[r['row0'],r['row1']] for r in admitted])
        for r,(i,j) in zip(admitted,pairs,strict=True):
            assert abs(r['epoch_difference_ns'])<=100
            assert obs.receiver[i]==0 and obs.receiver[j]==1
            assert obs.measured_hz[i]==r['cfo0_hz'] and obs.measured_hz[j]==r['cfo1_hz']
            assert obs.rf_hz[i]==obs.rf_hz[j]==r['rf_hz']
        score=replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.)
        kwargs=dict(receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']),pairs=pairs,rho=.9)
        original=paired.PairedObjective(obs,subset,prior,score,**kwargs)
        zero=BackgroundObjective(obs,subset,prior,score,eta=0,**kwargs)
        objective=BackgroundObjective(obs,subset,prior,score,eta=.9,**kwargs)
        v=np.asarray(seed['vector']);vo,go,_=original.evaluate(v);vz,gz,_=zero.evaluate(v)
        assert vo==vz;np.testing.assert_array_equal(go,gz)
        value,g,terms=objective.evaluate(v);background=objective.last_background.copy();checks=[]
        for index,step in ((0,.001),(1,.001),(2,.001),(3,.0001),(4,.001),(5,.0001),(6,.001),(7,1e-5),(12,1e-5)):
            d=np.eye(objective.size)[index]*step
            fd=(objective.evaluate(v+d)[0]-objective.evaluate(v-d)[0])/(2*step)
            error=abs(fd-g[index]);assert error<.01+.0001*abs(fd)
            checks.append(dict(index=index,step=step,analytic=g[index],finite=fd,absolute_error=error))
        out.append(dict(case=case,basin=basin,pair_count=len(pairs),eta0_exact_parity=True,objective=value,clock_background_gradient_common_rf_c=float(objective.design[:,4]@background['clock_gradient']),background_probability_mean=float(background['common_background_probability'].mean()),checks=checks))
        assert abs(out[-1]['clock_background_gradient_common_rf_c'])<1e-12
    (HERE/'actual_gradient_receipts.json').write_text(json.dumps(out,default=loader.CONTROLS.encode,indent=2))
    print('Actual-data gradient audits passed',[(r['case'],r['pair_count']) for r in out])

if __name__=='__main__':main()
