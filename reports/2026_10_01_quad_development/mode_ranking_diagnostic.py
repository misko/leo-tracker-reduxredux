"""Offline ranking headroom from existing accepted modes; no new fits or policy promotion."""
from pathlib import Path
import numpy as np
from run_shared_visibility_pilot import HERE,sealed,digest,verify_sources,save


def objective_choice(row):
    a,b=row['recovered'],row['variant']
    if not a['accepted']:return 'variant' if b['accepted'] else None
    if not b['accepted']:return 'recovered'
    delta=row['objective_changes']['recovered']
    if delta is None or not np.isfinite(delta):raise ValueError('missing objective comparison')
    return 'variant' if delta < -1e-6 else 'recovered'


def stats(errors):
    values=[e for e in errors if e is not None]
    return dict(planned=len(errors),accepted=len(values),median_m=float(np.median(values)),
                p90_m=float(np.percentile(values,90)),within1000m=sum(e<=1000 for e in values),
                within3000m=sum(e<=3000 for e in values))


def main():
    output={};inputs={}
    for label,name in [('pairs','full-pairs-complete-v1.json'),('quads','recursive-quads-complete-v1.json')]:
        path=HERE/name;data=sealed(path);verify_sources(data['input_sha256']);inputs[str(path)]=digest(path)
        # Select using acceptance and objective before accessing reference errors.
        choices=[objective_choice(r) for r in data['rows']]
        baseline=[];selected=[];oracle=[];rows=[]
        for row,choice in zip(data['rows'],choices,strict=True):
            a,b=row['recovered'],row['variant']
            ea=a['error_m'] if a['accepted'] else None;eb=b['error_m'] if b['accepted'] else None
            options=[e for e in [ea,eb] if e is not None]
            selected_error=row[choice]['error_m'] if choice else None
            baseline.append(ea);selected.append(selected_error);oracle.append(min(options) if options else None)
            rows.append(dict(unit=row['unit'],objective_choice=choice,baseline_error_m=ea,variant_error_m=eb,
                selected_error_m=selected_error,oracle_error_m=oracle[-1],objective_delta=row['objective_changes'].get('recovered')))
        output[label]=dict(baseline=stats(baseline),objective_choice=stats(selected),geographic_oracle=stats(oracle),rows=rows,
            oracle_better_than_objective_by_over100m=sum(r['selected_error_m']-r['oracle_error_m']>100 for r in rows if r['selected_error_m'] is not None))
    save(HERE/'mode-ranking-diagnostic-v1.json',dict(results=output,input_sha256=inputs,
        source_sha256={str(Path(__file__).resolve()):digest(__file__)},
        qualification='Offline exposed-data diagnostic using already computed accepted modes. Both arms would cost extra; no inference-budget feasibility claimed. Geographic oracle deliberately uses reference error only to estimate available-mode headroom, never a usable selector. No new fits.'))
    print({k:{a:b for a,b in v.items() if a!='rows'} for k,v in output.items()})


if __name__=='__main__':main()
