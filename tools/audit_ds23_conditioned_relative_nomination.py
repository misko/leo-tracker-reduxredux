"""Independent covariance densities and exact-orbit replay of conditional ranks."""

from concurrent.futures import ProcessPoolExecutor
import numpy as np

from audit_ds23_joint_relative_position import relative_features
from audit_ds23_unanchored_relative_position import grid,physical_columns
from ds23_conditioned_relative_nomination import refine_prediction
from probe_ds23_conditioned_relative_nomination import OUT,baseline,candidate_prior
from probe_ds23_joint_relative_position import make
from ds23_causal_phase_location import adjust_means
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from run_algo01_ds23_sample import read,write,sha


def one(saved):
    d,base=baseline(saved['case']);scan=d['scan'];labels=list(range(len(scan.norads)))
    widths,receipts=phase_widths(scan,labels);means=forecast_phase_mean(receipts,d['model']['shrinkage'])
    if d['signed']['accepted']:means=adjust_means(means,receipts,d['model'],d['signed']['selection'])
    means=np.asarray(means);widths*=d['model']['multiplier'];checks=[]
    assert scan.receipt['reference_position_used'] is False
    for arm,records in saved['arms'].items():
        original=base['arms'][arm];p=make(d,arm,np.asarray(original['joint_phase_reference']),False,float(np.sqrt(2)*300))
        x=np.asarray(original['endpoint_east_north_km']);c=p.calculate(x);cov=np.linalg.inv(c['joint_calibration_precision'])
        groups={g['group']:g for g in d['groups']}
        for group in records['groups']:
            g=groups[group['group']];sigma=g['noise_sigma_hz']*np.sqrt(2)
            for row in group['candidates']:
                for role in ['first','second']:
                    label=row[role+'_index'];provenance=scan.elements[str(int(scan.norads[label]))]['provenance']
                    assert max(provenance['element_epoch_utc_ns'],provenance['collected_utc_ns'])<=scan.receipt['cutoff_utc_ns']
                rf,mu,matrix,slots=candidate_prior(d,p,cov,c['coefficient'],g,row,means,widths);references=[]
                def geometry(phase):references.append(phase.copy());return rf.geometry(x,phase)
                fitted=refine_prediction(rf.values,geometry,mu,matrix,rf.phase_sigma,sigma)
                assert abs(fitted['score']-row['score'])<1e-6
                reference=references[-2] if fitted['phase_valid'] else references[-1]
                rf.reference=reference;intercept,features=relative_features(rf,x)
                y=rf.values-intercept-features@mu;dense=np.eye(len(y))*sigma**2+features@matrix@features.T
                score=float(y@np.linalg.solve(dense,y)+np.linalg.slogdet(dense)[1]+len(y)*np.log(2*np.pi))
                difference=abs(score-row['score']);assert difference<2e-3
                residual_difference=0.
                if fitted['phase_valid']:
                    phase=fitted['phase_s'];coefficient=fitted['coefficient'];nominal,e=grid(rf,x,phase)
                    begin=len(rf.labels);stop=begin+3*len(rf.supported)
                    residual=rf.values-nominal-physical_columns(rf,x,phase)@coefficient[begin:stop]-rf.bias_sigma*coefficient[-1]
                    residual_difference=float(np.max(abs(residual-np.asarray(row['prediction']['residual_hz']))));assert residual_difference<2e-4
                checks.append(dict(group=g['group'],arm=arm,first_norad=row['first_norad'],second_norad=row['second_norad'],
                    dense_predictive_score_difference=difference,independent_exact_residual_difference_hz=residual_difference))
    return dict(case=saved['case'],checks=checks,causal_element_epoch_and_collection_checked=True,
        reference_position_used=False,source_sha256=sha(OUT/(saved['case']+'.json')))


def main():
    execution=read(OUT/'execution.json');assert execution['all_terminal']
    complete=[r for r in execution['rows'] if r['status']=='complete']
    with ProcessPoolExecutor(max_workers=8) as pool:audits=list(pool.map(one,complete))
    write(OUT/'independent_numerical_audit.json',dict(audits=audits,all_passed=True,
        GLRT_posterior_calibration_not_updated_in_nomination=True,independent_dense_predictive_density_and_grid_orbit=True,
        causal_element_epoch_and_collection_checked=True,reference_position_used=False))
    print('Conditional nomination audits passed',len(audits),flush=True)


if __name__=='__main__':main()
