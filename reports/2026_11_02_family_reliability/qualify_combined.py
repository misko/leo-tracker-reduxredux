"""Apply every preregistered combined-model gate before computing diagnostics.

The raw runner records mixture residual gates but not phase-boundary eligibility.
This explicit final pass enforces that protocol requirement; it never refits.
Raw files are preserved and are not final acceptance artifacts.
"""
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp

ROOT=Path(__file__).resolve().parent
ARMS=('c0','fitted_c')


def qualifies(row):
    masses=[f['phase_boundary_mass'] for f in row.get('mixture_details',[])]
    return bool(all(row.get(k) is True for k in
        ('phase_closed','optimizer_success','all_gates_pass','native_ids_preserved'))
        and np.isfinite(row['objective']) and np.isfinite(row['x']).all()
        and not row.get('lost_ids') and not row.get('unexpected_reassignments')
        and all(np.isfinite(v) and v<.01 for v in masses))


def ensemble(rows):
    models={}
    for r in rows:models.setdefault((r['hypothesis'],r['SD_scale']),{})[r['arm']]=r
    eligible={k:v for k,v in models.items() if all(a in v and qualifies(v[a]) for a in ARMS)}
    result=dict(pairs_tested=len(models),paired_qualified=len(eligible),
        scope='Generalized-ELBO diagnostic weights; not calibrated identity probabilities or an approved selection policy')
    for arm in ARMS:
        if not eligible:result[arm]=dict(status='unresolved',x=None,models=[]);continue
        keys=list(eligible)
        logw=np.array([-.5*eligible[k][arm]['objective']+np.log({1.:.6,2.:.3,4.:.1}[k[1]]) for k in keys])
        w=np.exp(logw-logsumexp(logw));xy=np.array([eligible[k][arm]['x'] for k in keys]);mean=w@xy
        result[arm]=dict(status='diagnostic_ensemble',x=mean.tolist(),
            models=[dict(hypothesis=k[0],SD_scale=k[1],weight=float(ww)) for k,ww in zip(keys,w)],
            between_model_covariance_km2=((xy-mean).T@((xy-mean)*w[:,None])).tolist(),
            uncertainty_scope='Only between-model dispersion, excluding within-model and unmodeled uncertainty')
    return result


def main():
    import importlib.util
    spec=importlib.util.spec_from_file_location('combined_driver',ROOT/'combined.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);diag=m.diag_module()
    for case in ('DS26-0070','DS26-0309'):
        folder=ROOT/'combined'/case
        rows=[json.loads(p.read_text()) for pattern in ('*-c0.json','*-fitted_c.json')
              for p in sorted(folder.glob(pattern))]
        result=ensemble(rows);result['case']=case
        result['phase_boundary_reclassifications']=sum(r['qualified']!=qualifies(r) for r in rows)
        # RF weights sealed before truth is evaluated.
        (folder/'qualified_ensemble_rf.json').write_text(json.dumps(result,indent=2)+'\n')
        for arm in ARMS:
            x=result[arm]['x'];result[arm]['error_m']=diag.error(np.asarray(x)) if x is not None else None
        (folder/'qualified_ensemble.json').write_text(json.dumps(result,indent=2)+'\n')
        print(case,'paired qualified',result['paired_qualified'],'phase boundary reclassifications',result['phase_boundary_reclassifications'])


if __name__=='__main__':main()
