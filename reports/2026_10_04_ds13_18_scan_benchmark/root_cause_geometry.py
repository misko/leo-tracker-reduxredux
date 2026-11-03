"""Read-only reconstruction of score changes and local nuisance degeneracy."""
import argparse
import json
from pathlib import Path
import numpy as np
from root_cause import LABELS, ARMS, load_case, make_objective
from position_direct import coordinate_jacobian


def profile_information(matrix, nuisance):
    a=matrix[:2,:2]; b=matrix[np.ix_([0,1],nuisance)]
    c=matrix[np.ix_(nuisance,nuisance)]
    p=a-b@np.linalg.pinv(c,rcond=1e-12)@b.T
    return (p+p.T)/2


def run(root,output):
    result=[]
    for label in LABELS:
        data,meta,owners,saved,source,sha=load_case(root,label)
        refined=json.loads((Path(root)/label/'seed-timing-v6/refinement/refined.json').read_text())
        selection=json.loads((Path(root)/label/'seed-timing-v6/selection-p10-g600-t1.json').read_text())
        modes={r['catalog_number']:r for r in selection['arms']['fitted-c']['alternatives']['final']['selected']}
        fold_records=[json.loads(p.read_text()) for p in sorted((Path(root)/label/'seed-timing-v6/calibration-v2').glob('fold-*.json'))]
        top=np.isin(data.original_rows,refined['top_rows'])
        for arm in ARMS:
            fold_params=np.array([r['arms'][arm]['parameters'][2:6] for r in fold_records])
            fold_common=[float(np.mean(np.array(r['arms'][arm]['parameters'])[6+np.array(r['satellite_indices'],int)])) for r in fold_records]
            fold_c=[r['arms'][arm]['coefficient'] for r in fold_records]
            obj=make_objective(data,float(np.mean(np.unique(data.rf))),arm)
            snapshots={}
            for name,record in [('roof',saved['arms'][arm]['roof']),('best',saved['arms'][arm]['best_found'])]:
                vector=np.asarray(record['vector']);obj.base.deadline=float('inf')
                val,grad=obj.evaluate(vector)
                if abs(val-record['objective'])>1e-6:raise ValueError('objective mismatch')
                like=obj.likelihood.last_result
                row_nll=np.empty(len(data.times))
                for rows,value in zip(obj.likelihood.prepared.group_row_indices,like['log_likelihood']):
                    if len(rows)!=1:raise ValueError('not singleton')
                    row_nll[rows]=-value
                prior=obj.base.penalty(vector[:obj.size])[0]
                snapshots[name]=dict(row_nll=row_nll,prior_nll=prior,
                    coefficient=record['coefficient'],parameters=record['parameters'],
                    common_timing_s=float(vector[6]),
                    association_probability=like['row_association_probability'].copy(),
                    position_gradient=coordinate_jacobian(record['point_km']).T@grad[:2],
                    clutter_fraction=float(np.mean(like['clutter_probability'])),
                    effective_support=float(like['row_association_probability'].sum()))
                if name=='roof':
                    scale=np.asarray(obj.scale).copy()
                    transform=np.diag(scale);transform[:2,:2]=coordinate_jacobian([0,0])
                    h=transform.T@obj.curvature(vector)@transform
                    nuisance=list(range(2,len(vector)-(arm=='zero-c')))
                    prof=profile_information(h,nuisance)
                    eig=np.linalg.eigvalsh(prof)
                    snapshots[name]['fisher']=dict(profile_eigenvalues_per_km2=eig.tolist(),
                        fixed_nuisance_eigenvalues_per_km2=np.linalg.eigvalsh(h[:2,:2]).tolist(),
                        remaining_trace_fraction=float(np.trace(prof)/np.trace(h[:2,:2])),
                        condition_number=float(eig[1]/eig[0]) if eig[0]>0 else None,
                        caveat='Local Fisher/Schur diagnostic, not exact observed Hessian or calibrated error bars; ignores active constraint faces and visibility jumps.')
            roof,best=snapshots['roof'],snapshots['best']
            delta=best['row_nll']-roof['row_nll']
            contributions=[]
            for n in np.unique(owners):
                mask=owners==n
                j=int(np.flatnonzero(data.numbers==n)[0])
                delta_s=roof['parameters'][6+j]-roof['common_timing_s']
                contributions.append(dict(satellite=int(n),windows=int(mask.sum()),
                    non_top_windows=int(np.sum(mask&~top)),
                    association_mode_offset_s=modes[int(n)]['offset_s'],
                    association_native_rms_hz=modes[int(n)]['rms_hz'],
                    roof_total_timing_s=roof['parameters'][6+j],roof_relative_timing_s=delta_s,
                    roof_timing_prior_nll=.5*delta_s**2,
                    roof_mean_own_association_probability=float(np.mean(roof['association_probability'][mask,j])),
                    roof_owned_windows_probability_over_half=int(np.sum(roof['association_probability'][mask,j]>.5)),
                    data_nll_best_minus_roof=float(delta[mask].sum())))
            prior_delta=best['prior_nll']-roof['prior_nll']
            exact=saved['arms'][arm]['best_found']['objective']-saved['arms'][arm]['roof']['objective']
            if abs(delta.sum()+prior_delta-exact)>1e-6:raise ValueError('NLL decomposition fails')
            result.append(dict(label=label,arm=arm,source=source,source_sha256=sha,
                non_top_windows=int((~top).sum()),windows=len(top),
                roof_converged=saved['arms'][arm]['roof']['success'],
                best_converged=saved['arms'][arm]['best_found']['success'],
                best_status=saved['arms'][arm]['best_found']['status'],
                radius_m=saved['arms'][arm]['radius_m'],boundary=saved['arms'][arm]['boundary'],
                calibration_warning=bool(meta.get('calibration_warnings')),
                fold_common_timing_range_s=float(np.ptp(fold_common)),
                fold_rx0_offset_range_hz=float(np.ptp(fold_params[:,0])),
                fold_rx1_offset_range_hz=float(np.ptp(fold_params[:,2])),
                fold_rx0_drift_range_hz_s=float(np.ptp(fold_params[:,1])),
                fold_rx1_drift_range_hz_s=float(np.ptp(fold_params[:,3])),
                fold_rf_coefficient_range=float(np.ptp(fold_c)),
                total_nll_best_minus_roof=exact,prior_nll_best_minus_roof=prior_delta,
                fisher=roof['fisher'],
                delta_rx0_drift_hz_s=best['parameters'][3]-roof['parameters'][3],
                delta_rx1_drift_hz_s=best['parameters'][5]-roof['parameters'][5],
                delta_c_hz_per_ghz=best['coefficient']-roof['coefficient'],
                timing_change_rms_s=float(np.sqrt(np.mean((np.asarray(best['parameters'][6:])-roof['parameters'][6:])**2))),
                roof_clutter_fraction=roof['clutter_fraction'],best_clutter_fraction=best['clutter_fraction'],
                roof_gradient_per_km=roof['position_gradient'].tolist(),
                best_gradient_per_km=best['position_gradient'].tolist(),
                contributions=contributions))
            print(label,arm,'remaining position information',round(100*roof['fisher']['remaining_trace_fraction'],3),flush=True)
    Path(output).write_text(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root');p.add_argument('output')
    a=p.parse_args();run(a.root,a.output)
