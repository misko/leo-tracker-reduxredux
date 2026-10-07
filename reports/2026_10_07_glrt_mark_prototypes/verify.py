"""Read-only neutral-oracle and marked-gradient checks on saved cohort inputs."""
import json
from pathlib import Path
import numpy as np
import experiment as e
from position_direct import coordinate


def main():
    checks=[]
    for scan in e.SCANS:
        data,saved,source,pool,_=e.sweep.inputs(scan)
        for model in e.MODELS:
            neutral=e.Objective(data,saved,'fitted-c',model,'control')
            reference=e.sweep.objective(data,saved,'fitted-c',e.MODELS[model])
            vector=e.feasible_start(neutral,pool[0][1],20.,'fitted-c')
            vector[:2]=coordinate(pool[0][1]['point_km'])
            a,ag=neutral.evaluate(vector);b,bg=reference.evaluate(vector)
            np.testing.assert_allclose(a,b,atol=1e-7,rtol=0)
            np.testing.assert_allclose(ag,bg,atol=1e-6,rtol=1e-8)
            np.testing.assert_allclose(neutral.curvature(vector),reference.curvature(vector),atol=1e-6,rtol=1e-9)
            check=dict(scan=scan,model=model,neutral_nll_error=float(a-b),
                       neutral_gradient_max_error=float(np.max(abs(ag-bg))))
            if scan in ('N01','N16'):
                errors={}
                for mode in e.MODES[1:]:
                    obj=e.Objective(data,saved,'fitted-c',model,mode)
                    value,gradient=obj.evaluate(vector)
                    direction=np.random.default_rng(7007).normal(size=len(vector))
                    direction[:2]*=1e-7;direction[2:6]*=1e-3
                    direction[6:obj.size]*=1e-5;direction[obj.size:]*=.01
                    numeric=(obj.evaluate(vector+direction)[0]-obj.evaluate(vector-direction)[0])/2
                    analytic=float(gradient@direction)
                    np.testing.assert_allclose(numeric,analytic,atol=2e-7,rtol=1e-5)
                    errors[mode]=float(numeric-analytic)
                check['marked_directional_gradient_errors']=errors
            checks.append(check)
    (Path(__file__).parent/'verification.json').write_text(json.dumps(checks,indent=2))
    print(f'{len(checks)} neutral objective/gradient/curvature checks and 16 marked directional checks passed')


if __name__=='__main__':main()
