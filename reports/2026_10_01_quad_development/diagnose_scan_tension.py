"""Reference-free per-scan contributions at an already audited joint solution."""
import argparse
import json
from pathlib import Path
import numpy as np
from run_window import prepare_window
from regression_batch import digest

HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('block');args=parser.parse_args()
    directory=HERE/'independent-v2'/args.block
    audit_path=directory/'evaluation.json'
    assert digest(audit_path)==audit_path.with_suffix('.sha256').read_text().strip()
    audited=json.loads(audit_path.read_text());by_id={r['unit']:r for r in audited['rows']}
    quad_id=args.block+'-Q';assert by_id[quad_id]['accepted']
    receipt_path=directory/(quad_id+'.json');assert digest(receipt_path)==by_id[quad_id]['receipt_sha256']
    receipt=json.loads(receipt_path.read_text());state=np.asarray(receipt['best']['mean'])
    binding,scans,columns,_,_=prepare_window(quad_id)
    rows=[]
    for k,((scan,_,ports),indices) in enumerate(zip(scans,columns)):
        local=state[indices];precision=np.r_[0.,0.,1.,np.full(len(local)-3,4.)]
        assignments=[int(np.argmax(p.score_all(local))) for p in ports]
        value=float(.5*(precision*local)@local-sum(p.score_selected(local,i) for p,i in zip(ports,assignments)))
        active={0,1,*np.flatnonzero(local).tolist()};predictions=[]
        for p,i in zip(ports,assignments):
            if i<p.candidate_count:
                pred=p.predict_selected(local,i);predictions.append((p,pred))
                active.update(np.flatnonzero(np.any(pred.jacobian!=0,axis=0)).tolist())
        active=np.array(sorted(active));metric=np.diag(precision[active]);gradient=(precision*local)[active]
        for p,pred in predictions:
            r=p.observation-pred.mean;v=np.linalg.solve(pred.covariance,r);w=(4+len(r))/(4+float(r@v))
            j=pred.jacobian[:,active];gradient-=w*j.T@v;metric+=w*j.T@np.linalg.solve(pred.covariance,j)
        effective=metric[:2,:2]-metric[:2,2:]@np.linalg.solve(metric[2:,2:],metric[2:,:2])
        assert np.min(np.linalg.eigvalsh(effective))>0
        single_id=args.block+f'-S{k+1}';single_path=directory/(single_id+'.json')
        assert by_id[single_id]['accepted'] and digest(single_path)==by_id[single_id]['receipt_sha256']
        single=json.loads(single_path.read_text())['best']
        rows.append(dict(scan=scan.unit_id,tracks=len(ports),signal_tracks=len(predictions),
            conditional_objective=value,single_objective=single['objectives'][-1],
            objective_increase=value-single['objectives'][-1],
            spatial_gradient_per_km=gradient[:2].tolist(),profiled_irls_information=effective.tolist(),
            fitted_clock_s=float(local[2]),single_clock_s=single['mean'][2],
            changed_assignments=sum(a!=b for a,b in zip(assignments,single['associations'])),
            single_minus_joint_position_m=(1000*(np.asarray(single['mean'][:2])-state[:2])).tolist()))
    assert abs(sum(r['conditional_objective'] for r in rows)-receipt['best']['objectives'][-1])<1e-6
    result=dict(rows=rows,gradient_sum_per_km=np.sum([r['spatial_gradient_per_km'] for r in rows],axis=0).tolist(),
        evaluation_sha256=digest(audit_path),receipt_sha256=digest(receipt_path),source_sha256=digest(__file__),
        qualification='Reference-free decomposition at accepted quad state. IRLS Schur information is local curvature, not calibrated covariance. Objective increases compare different hard-association optima; they are not likelihood-ratio tests or grounds for discarding a scan.')
    path=directory/'scan-tension.json'
    with path.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
