"""Local nuisance/position information for every completed joint pilot fit."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_joint_relative_audit import position_information
from probe_ds23_joint_relative_position import OUT,context,make
from run_algo01_ds23_sample import read,write


def one(job):
    source,saved=job;d=context(saved['case']);rows=[]
    for arm,record in saved['arms'].items():
        p=make(d,arm,np.asarray(record['joint_phase_reference']),saved['include_relative'],saved['bias_sigma_hz'])
        x=np.asarray(record['endpoint_east_north_km']);c=p.calculate(x);coef=c['coefficient'];rf=p.relative_problem
        u=[c['features'][p.keep]];g=p.noise_groups[p.keep]
        weights=[d['powers'][g]*c['noise_precision'][g]/p.point_noise[p.keep]**2]
        if p.relative_include:
            geometry=rf.geometry(x);ru=np.zeros((len(rf.values),len(coef)));ru[:,p.relative_mapping]=geometry['features'];u.append(ru)
            weights.append(c['relative_noise_precision'][rf.noise_groups]/rf.noise**2)
        def prediction(position):
            geometry=p.calculate(position);values=[(p.q*geometry['intercept']+geometry['features']@coef)[p.keep]]
            if p.relative_include:
                rg=rf.geometry(position);values.append(rg['intercept']+rg['features']@coef[p.relative_mapping])
            return np.concatenate(values)
        derivative=np.column_stack([(prediction(x+delta)-prediction(x-delta))/.05 for delta in np.eye(2)*.025])
        result=position_information(derivative,np.vstack(u),np.concatenate(weights),c['coefficient_prior_precision'])
        rows.append(dict(source=source,case=saved['case'],variant=saved['variant'],arm=arm,accepted=saved['accepted'],
            endpoint_latlon=record['endpoint_latlon'],**result))
    return rows


def main():
    sources=[('development',OUT),('confirmation20',OUT/'confirmation20')];jobs=[]
    for name,path in sources:
        assert read(path/'independent_numerical_audit.json')['all_passed']
        for record in read(path/'execution.json')['rows']:
            if record['status']=='complete' and record['variant'] in ['quarantined_GLRT','joint_bias424']:jobs.append((name,record))
    with ProcessPoolExecutor(max_workers=8) as pool:rows=[r for pair in pool.map(one,jobs) for r in pair]
    write(OUT/'local_information_without_GPS.json',dict(rows=rows,
        only_actual_calibration_factors_used_predictive_linear_information_not_added=True,
        derivatives_at_fixed_coefficients_then_nuisances_eliminated=True,
        conditional_on_Gamma_identities_and_model_not_calibrated_position_confidence=True,reference_position_used=False))
    from report_algo02_ds23 import position_error
    evaluation=[dict(r,position_error_km_report_only=position_error(r['endpoint_latlon'])) for r in rows]
    write(OUT/'local_information_evaluation.json',dict(rows=evaluation,report_only_GPS=True,
        not_a_coverage_test_or_identification_of_wrong_satellite=True))
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
    for variant,color in [('quarantined_GLRT','#777777'),('joint_bias424','#168b91')]:
        selected=[r for r in evaluation if r['variant']==variant and r['arm']=='fitted_c']
        x=np.array([r['local_position_axis_SD_km'][-1] for r in selected]);y=np.array([r['position_error_km_report_only'] for r in selected])
        axes[0].scatter(x,y,c=color,s=30,label=variant)
        axes[1].scatter([r['fraction_trace_information_retained'] for r in selected],y,c=color,s=30,label=variant)
        for xx,yy,r in zip(x,y,selected,strict=True):
            if r['case'] in ['DS23-0202','DS23-0293']:axes[0].annotate(r['case'].split('-')[1],(xx,yy),fontsize=8)
    axes[0].set(xlabel='Largest conditional local position SD (km)',ylabel='Raw endpoint error (km)')
    axes[1].set(xlabel='Fraction of position information retained after nuisance fitting',ylabel='Raw endpoint error (km)')
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Position information lost to phase, orbit and radio uncertainty\nAll completed default/control fits; includes rejected endpoints; local SD is not calibrated confidence')
    fig.savefig(OUT/'local_information.png',dpi=160);plt.close(fig)
    print('Information diagnostics complete',len(rows),flush=True)


if __name__=='__main__':main()
