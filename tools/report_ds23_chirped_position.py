"""Independently replay the real RF pilot, then evaluate geographic errors."""

import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_predictive_subsets import realize_predictive_subsets,assert_realized_predictive_membership
from ds23_windowed_differential_factor import make_differential_problem,attach_differential_predictive,windowed_geometry,lift_measured_contrast
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_frequency_events import summary
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha
from select_ds23_differential_information import OUT as PARENT

OUT=PARENT/'instantaneous_chirp_position_recovery'


def main():
    execution=read(OUT/'execution.json');assert execution['all_terminal']
    rows=[];audits=[];information=[]
    for case in read(OUT/'protocol.json')['cases']:
        scan,node,_,powers,means,model,_,signed,_=context_signed(case)
        plan=read(OUT/(case+'_plan.json'));augmented,entries,_=realize_predictive_subsets(scan,plan['entries'])
        ids=assert_realized_predictive_membership(augmented,entries,plan['disjoint']['excluded_probe_graph_ids'])
        for method in ['matched_control','conditional_RF','plus_radio_RF']:
            path=OUT/(case+'_'+method+'.json');saved=read(path)
            if saved['status']!='complete':
                audits.append(dict(case=case,method=method,status=saved['status'],error=saved.get('error')));continue
            pair={};maximum=0.
            for arm,r in saved['arms'].items():
                p=make_differential_problem(augmented,node,np.array(plan['keep'],bool),arm,
                    np.asarray(r['phase_reference']),powers,means,model,saved['measurements'])
                attach_differential_predictive(p,entries,powers);x=np.asarray(r['endpoint_east_north_km']);c=p.calculate(x)
                difference=abs(c['negative_twice_elbo']-r['negative_twice_elbo']);maximum=max(maximum,difference)
                assert difference<1e-6
                if saved['measurements']:
                    assert np.allclose(c['coefficient_covariance']@c['calibration_posterior_precision'],np.eye(len(c['coefficient'])),atol=1e-8)
                assert len(c.get('linear_raw_prediction_residual_hz',[]))==len(ids)
                checked=summary(p,x,entries);assert checked['linear_calibration_max_difference']==0
                checked['final_phase_change_s']=r['final_phase_change_s'];pair[arm]=checked
            gates=valid(pair)
            audit=dict(case=case,method=method,status='complete',original_paired_gates_pass=bool(gates),
                declared_paired_valid=saved['paired_valid'],maximum_normalized_loss_difference=maximum,
                physical_predictive_rows=len(ids),RF_GLRT_actual_samples_disjoint=True,
                source_sha256=sha(path));audits.append(audit)
            # Evaluation truth enters only after physical likelihood replay.
            from report_algo02_ds23 import position_error
            for arm,r in saved['arms'].items():
                accepted=r if saved['paired_valid'] else signed['policy_arms'][arm]
                rows.append(dict(case=case,method=method,arm=arm,paired_valid=saved['paired_valid'],
                    original_error_km=position_error(signed['policy_arms'][arm]['endpoint_latlon']),
                    raw_error_km=position_error(r['endpoint_latlon']),fallback_error_km=position_error(accepted['endpoint_latlon']),
                    RMS_hz=r['RMS_hz'],RF_contrasts=len(saved['measurements']),
                    maximum_RF_standardized_residual=max(abs(np.asarray(r.get('differential_residual_hz',[]))/r.get('differential_sigma_hz',1)),default=0)))
        # Quantify what the one contrast adds at the same fixed control position.
        control=read(OUT/(case+'_matched_control.json'));rf=read(OUT/(case+'_conditional_RF.json'))
        if control['status']=='complete' and rf['status']=='complete':
            for arm,r in control['arms'].items():
                x=np.asarray(r['endpoint_east_north_km']);reference=np.asarray(r['phase_reference']);keep=np.array(plan['keep'],bool)
                p0=make_differential_problem(augmented,node,keep,arm,reference,powers,means,model,[])
                p1=make_differential_problem(augmented,node,keep,arm,reference,powers,means,model,rf['measurements'])
                c0,c1=p0.calculate(x),p1.calculate(x);features=c0['features'][keep];groups=p0.noise_groups[keep]
                weights=np.asarray(powers)[groups]*c0['noise_precision'][groups]/p0.point_noise[keep]**2
                gram=np.diag(c0['coefficient_prior_precision'])+features.T@(weights[:,None]*features)
                nb,ns=p0.hardware.shape[1],p0.smooth.shape[1];phase=nb+ns;orbit=phase+len(p0.labels);fragment=orbit+3*len(p0.supported)
                for measurement in rf['measurements']:
                    g=windowed_geometry(p0,measurement,x);h=g['features'];slots=measurement['curve_rows']
                    z=lift_measured_contrast(measurement['difference_hz'],measurement['native_CFO_hz'],measurement['lifted_CFO_hz'],[p0.alias[k] for k in slots])
                    innovation=float(z-g['intercept_hz']-h@c0['coefficient']);variance=float(h@np.linalg.solve(gram,h))
                    change=h*(c1['coefficient']-c0['coefficient'])
                    information.append(dict(case=case,arm=arm,probe=measurement['probe'],
                        same_fixed_position=True,pre_measurement_innovation_hz=innovation,
                        pre_measurement_predictive_SD_hz=float(np.sqrt(variance+measurement['sigma_hz']**2)),
                        pre_measurement_standardized_innovation=float(innovation/np.sqrt(variance+measurement['sigma_hz']**2)),
                        radio_prediction_change_hz=float(change[:phase].sum()),phase_prediction_change_hz=float(change[phase:orbit].sum()),
                        orbit_prediction_change_hz=float(change[orbit:fragment].sum()),fragment_prediction_change_hz=float(change[fragment:].sum()),
                        total_prediction_change_hz=float(change.sum())))
    write(OUT/'independent_audit_and_evaluation.json',dict(audits=audits,rows=rows,information=information,
        all_terminal=True,report_only_GPS=True,single_scan_engineering_not_generalization=True,
        full_DS23_benchmark_unchanged=True))
    if rows:
        with (OUT/'position_comparison.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        fig,axes=plt.subplots(1,2,figsize=(9,4.4))
        methods=['matched_control','conditional_RF','plus_radio_RF'];colors=['#777777','#168b91','#df801b']
        for ax,arm in zip(axes,['c0','fitted_c'],strict=True):
            selected=[r for r in rows if r['arm']==arm]
            for i,method in enumerate(methods):
                r=next(r for r in selected if r['method']==method)
                ax.scatter(i,r['raw_error_km'],color=colors[i],marker='o' if r['paired_valid'] else 'x',s=70)
            ax.axhline(selected[0]['original_error_km'],color='black',linestyle=':',label='Original full-GLRT incumbent')
            ax.set_xticks(range(3),['Matched\ncontrol','Conditional\nRF SD','Plus radio\nSD']);ax.set(title=arm,ylabel='Position error (km)');ax.grid(axis='y',alpha=.2)
        axes[1].legend(fontsize=8);fig.suptitle('DS23-0317 · one qualified midpoint carrier contrast\nSame quarantined GLRT data, causal candidates/priors, cold regional start')
        fig.tight_layout();fig.savefig(PARENT/'chirped_position_pilot.png',dpi=160);plt.close(fig)
    print(rows,flush=True)


if __name__=='__main__':main()
