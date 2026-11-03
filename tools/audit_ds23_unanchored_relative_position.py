"""Independent grid geometry, physical-mode derivatives and position evaluation."""

from concurrent.futures import ProcessPoolExecutor
import copy
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_unanchored_relative_position import OUT,context,make
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import read,write,sha
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def grid(p,x,phase,bank=None):
    f,e=phase_frequency_grid(p.sky if bank is None else bank,p.times,*latlon(x),phase_seconds=phase)
    n=np.arange(len(p.times))
    return p.q*(f[p.second,n]-f[p.first,n]),np.minimum(e[p.first,n],e[p.second,n])


def physical_columns(p,x,phase):
    columns=[];step=.001
    for local in p.supported:
        for mode in range(3):
            values=[]
            for sign in [-1,1]:
                bank=dict(time_s=p.sky['time_s'],position_km=p.sky['position_km'].copy(),velocity_km_s=p.sky['velocity_km_s'].copy())
                for key in ['position_km','velocity_km_s']:bank[key][local]+=sign*step*p.mode_bank[key][3*local+mode]
                values.append(grid(p,x,phase,bank)[0])
            columns.append((values[1]-values[0])/(2*step))
    return np.column_stack(columns) if columns else np.zeros((len(p.values),0))


def one(saved,output_dir=None):
    case,variant=saved['case'],saved['variant'];physical=variant.startswith('physical')
    data=context(case,physical);p=make(data,np.asarray(saved['phase_reference']),saved['bias_sigma_hz'])
    scan=data[0];cutoff=scan.receipt['cutoff_utc_ns']
    assert scan.receipt['reference_position_used'] is False
    for label in p.labels:
        provenance=scan.elements[str(int(scan.norads[label]))]['provenance']
        assert max(provenance['element_epoch_utc_ns'],provenance['collected_utc_ns'])<=cutoff
    x=np.asarray(saved['endpoint_east_north_km']);c=p.calculate(x)
    loss=abs(c['negative_twice_elbo']-saved['negative_twice_elbo']);assert loss<1e-6
    f,e=grid(p,x,p.reference);plus,_=grid(p,x,p.reference+.01);minus,_=grid(p,x,p.reference-.01)
    # Check the full reference prediction separately, since individual phase
    # derivatives carry different labels even in a differenced observation.
    g=p.geometry(x);phase=p.phases(x);exact,e=grid(p,x,phase)
    orbital=physical_columns(p,x,phase);begin=len(p.labels);stop=begin+3*len(p.supported)
    prediction=exact+orbital@c['coefficient'][begin:stop]
    prediction+=saved['bias_sigma_hz']*c['coefficient'][stop+p.noise_groups]
    residual=p.values-prediction;maximum=float(np.max(abs(residual-p.exact_residual(x)[0])))
    assert maximum<1e-4
    linear_columns=physical_columns(p,x,p.reference)
    derivative_difference=float(np.max(abs(linear_columns-g['features'][:,begin:stop]),initial=0))
    assert derivative_difference<1e-4
    gates=[]
    for k,sl in enumerate(p.slices):
        noise=batch_noise_screen(residual[sl][None],p.times[sl]);rms=float(np.sqrt(np.mean(residual[sl]**2)))
        bias=float(saved['bias_sigma_hz']*c['coefficient'][stop+k])
        passed=bool(rms<=450 and abs(bias)<=3000 and e[sl].min()>=0 and noise['noise_screen_pass'][0])
        gates.append(passed);assert passed==saved['gates'][k]['compatible']
    accepted=all(gates) and np.max(abs(phase))<=15 and saved['final_phase_change_s']<=.01
    assert accepted==saved['accepted']
    # Local information diagnostic; phase and noise Gamma precisions conditioned.
    d=[]
    for delta in np.eye(2)*.025:
        values=[]
        for point in [x-delta,x+delta]:
            geometry=p.geometry(point);values.append(geometry['intercept']+geometry['features']@c['coefficient'])
        d.append((values[1]-values[0])/.05)
    design=np.column_stack((np.column_stack(d),g['features']))
    w=c['noise_precision'][p.noise_groups]/p.noise**2
    precision=design.T@(design*w[:,None]);precision[2:,2:]+=np.diag(c['coefficient_prior_precision'])
    covariance=np.linalg.inv(precision);eig=np.linalg.eigvalsh(covariance[:2,:2])
    return dict(case=case,variant=variant,maximum_normalized_loss_difference=loss,
        maximum_independent_exact_residual_difference_hz=maximum,maximum_physical_mode_derivative_difference_hz=derivative_difference,
        accepted=accepted,local_position_covariance_km2=covariance[:2,:2],local_position_axis_SD_km=np.sqrt(eig),
        local_information_conditional_not_accuracy_or_global_confidence=True,
        actual_RF_model_has_no_radio_or_c_coordinates=True,causal_element_epoch_and_collection_checked=True,
        source_sha256=sha((OUT if output_dir is None else Path(output_dir))/(case+'_'+variant+'.json')))


def main():
    execution=read(OUT/'execution.json');assert execution['all_terminal']
    assert all(r['status']=='complete' for r in execution['rows'])
    with ProcessPoolExecutor(max_workers=6) as pool:audits=list(pool.map(one,execution['rows']))
    from report_algo02_ds23 import position_error
    rows=[]
    for r in execution['rows']:
        rows.append(dict(case=r['case'],variant=r['variant'],accepted=r['accepted'],
            raw_error_km=position_error(r['endpoint_latlon']),
            policy_fitted_c_error_km=position_error(r['endpoint_latlon'] if r['accepted'] else r['original_signed_incumbent']['fitted_c']['endpoint_latlon']),
            original_c0_error_km=position_error(r['original_signed_incumbent']['c0']['endpoint_latlon']),
            original_fitted_c_error_km=position_error(r['original_signed_incumbent']['fitted_c']['endpoint_latlon']),
            frequency_RMS_hz=r['RMS_hz'],relative_observations=r['relative_observations']))
    write(OUT/'independent_audit_and_evaluation.json',dict(audits=audits,rows=rows,all_terminal=True,
        report_only_GPS=True,development_scans_not_generalization=True,no_method_promoted=True))
    fig,axes=plt.subplots(1,2,figsize=(12,4.8));cases=read(OUT/'protocol.json')['cases'];variants=[r[0] for r in read(OUT/'protocol.json')['variants']]
    colors=['#777777','#168b91','#c18c35','#8765b4']
    for j,variant in enumerate(variants):
        selected=[next(r for r in rows if r['case']==case and r['variant']==variant) for case in cases]
        for i,r in enumerate(selected):
            axes[0].scatter(i+(j-1.5)*.13,r['raw_error_km'],color=colors[j],marker='o' if r['accepted'] else 'x',s=50,label=variant if i==0 else None)
            axes[1].scatter(i+(j-1.5)*.13,r['frequency_RMS_hz'],color=colors[j],marker='o' if r['accepted'] else 'x',s=50)
    for i,case in enumerate(cases):
        old=next(r for r in rows if r['case']==case)
        axes[0].scatter(i,old['original_fitted_c_error_km'],color='black',marker='*',s=100,label='Original fitted-c incumbent' if i==0 else None)
    for ax in axes:ax.set_xticks(range(len(cases)),[c.split('-')[1] for c in cases]);ax.set_xlabel('DS23 development scan');ax.grid(alpha=.2)
    axes[0].set_ylabel('Position error (km)');axes[1].set_ylabel('Relative-frequency RMS (Hz)');axes[0].legend(fontsize=7)
    fig.suptitle('Full unanchored relative-CFO curves · different observation model\nCircles pass all relative gates; cross fails; c cancels analytically')
    fig.tight_layout();fig.savefig(OUT/'development_comparison.png',dpi=160);plt.close(fig)
    print(rows,flush=True)


if __name__=='__main__':main()
