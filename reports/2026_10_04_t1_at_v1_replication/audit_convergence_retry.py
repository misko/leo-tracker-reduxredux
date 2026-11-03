"""Recompute final scores and full constrained stationarity without optimizing."""
import hashlib
import json
from pathlib import Path
import numpy as np
from diagnose_convergence import objective_for
from resume_position_convergence import OUT
from constrained_fit import kkt_residual
from position_direct import coordinate_jacobian


def main():
    rows=[]
    for path in sorted((OUT/'final').glob('N*-*.json')):
        saved=json.loads(path.read_text());b=saved['best']
        obj,_=objective_for(saved['scan'],saved['arm'])
        scale=obj.scale.copy();scale[:2]=1.
        vector=np.array(b['vector']);z=vector/scale;z[:2]=b['point_km']
        value,gradient=obj.evaluate(vector)
        transformed=gradient*scale
        transformed[:2]=coordinate_jacobian(z[:2]).T@gradient[:2]
        bounds=[(None if lo is None else lo/s,None if hi is None else hi/s)
                for (lo,hi),s in zip(obj.bounds,scale)]
        bounds[:2]=[(-2.,2.)]*2
        matrix=np.zeros((len(obj.base.satellites),len(z)))
        matrix[:,6]=1.;matrix[:,7:obj.size]=obj.base.basis;matrix*=scale
        lower=np.full(len(matrix),obj.base.minimum_shift_s+1e-6)
        upper=np.full(len(matrix),obj.base.maximum_shift_s-1e-6)
        if np.linalg.norm(z[:2])>=2.-1e-5:
            normal=np.r_[-2*z[:2],np.zeros(len(z)-2)]
            matrix=np.vstack([matrix,normal]);lower=np.r_[lower,normal@z];upper=np.r_[upper,np.inf]
        norm=kkt_residual(transformed,z,bounds,matrix,lower,upper)
        check=dict(objective=float(value),kkt_residual=norm,success=norm<=1e-3)
        assert abs(check['objective']-b['objective'])<1e-7
        assert check['success']==saved['converged']
        assert abs(check['kkt_residual']-b['kkt_residual'])<1e-8
        original=json.loads((OUT/path.name).read_text())['original']
        rows.append(dict(scan=saved['scan'],arm=saved['arm'],converged=check['success'],
                         kkt_residual=check['kkt_residual'],score_error=check['objective']-b['objective'],
                         position_movement_m=saved['movement_m_vs_original'],
                         original_score_error=obj.evaluate(np.array(original['vector']))[0]-original['objective'],
                         final_source_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    receipt=dict(scope=__doc__,rows=rows,complete=len(rows)==18,
                 stationarity_tolerance=1e-3,search_radius_m=2000,
                 associations_changed=False,model_changed=False,
                 optimizer_note='Added roundoff-aware tiny-step acceptance and nuisance-only polishing; full free-position KKT independently rechecked.',
                 matched_maximum_budgets_s=[60,30,30,30,15,15],
                 unchanged_scans='Other nine scan pairs retain their original converged results.')
    (OUT/'final-audit.json').write_text(json.dumps(receipt,indent=2))
    print('Audited',len(rows),'arms; converged',sum(r['converged'] for r in rows),
          '; maximum position movement (m)',max(r['position_movement_m'] for r in rows),
          '; maximum score reconstruction error',max(abs(r['score_error']) for r in rows))


if __name__=='__main__':main()
