"""Local sensitivity to nuisance-integration volume; no refitted position claim."""

from pathlib import Path
import numpy as np
from probe_ds23_height import context,OUT
from probe_ds23_history_calibrated_phase import make_problem
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def run():
    records=[];cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    for case in cases:
        scan,node,keep,powers,means,model,noise,baseline=context(case,'archived')
        r=baseline['c0'];x=np.array(r['endpoint_east_north_km'])
        p=make_problem(scan,node,keep,'c0',np.array(r['phase_reference']),powers,means,model['multiplier'],model['nu'])
        columns=[];gradient={k:[] for k in ('negative_twice_elbo','quadratic','logvolume','gamma_cost')}
        for k in (0,1):
            d=np.zeros(2);d[k]=.01;a,b=p.calculate(x+d),p.calculate(x-d)
            columns.append((p.residual(x+d)-p.residual(x-d))/.02)
            for name in gradient:gradient[name].append((a[name]-b[name])/.02)
        jacobian=np.column_stack(columns);normal=2*jacobian.T@jacobian
        eigen=np.linalg.eigvalsh(normal)
        delta=np.linalg.solve(normal,np.array(gradient['logvolume']))
        records.append(dict(case=case,RF_position_east_north_km=x,gradient_per_km=gradient,
            local_GN_eigenvalues_per_km2=eigen,estimated_shift_if_logvolume_removed_km=delta,
            estimated_shift_norm_km=float(np.linalg.norm(delta))))
    write(OUT/'volume_gradient.json',dict(records=records,no_GPS_used=True,
        c0_only_local_sensitivity_not_a_controlled_position_ablation=True,
        Gauss_Newton_linearization_not_a_refitted_endpoint=True,
        noise_and_phase_precisions_vary_inside_original_calculate=True,
        source_sha256=sha(Path(__file__))))
    print('Local volume-removal displacement estimate median/max km',
          np.median([r['estimated_shift_norm_km'] for r in records]),max(r['estimated_shift_norm_km'] for r in records),flush=True)


if __name__=='__main__':run()
