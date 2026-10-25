"""Generate GPS-free tables, conditional figures and numerical result audit."""
import csv
from pathlib import Path
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from matched_controls import digest, read, write
from geometry import CASES, MODELS, ARMS, HERE


def table(name, rows):
    with (HERE/name).open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def delta_terms(a, b):
    return {key:b[key]-a[key] for key in a}


def endpoint(arm, model, which):
    return arm['models'][model]['endpoints'][which]


def audit(results):
    checks = []
    maximum_decomposition = maximum_group_closure = 0.
    maximum_phase = maximum_Gamma = maximum_replay = 0.
    maximum_calibration_feedback = 0.
    all_points = 0
    for case, result in results.items():
        assert result['case'] == case and result['GPS_used'] is False and not result['position_fitting']
        assert result['inputs_preserved'] and result['maximum_workers'] == 1 and result['BLAS_threads'] == 1
        assert digest(result['baseline_path']) == result['baseline_sha256']
        assert digest(result['rf50_path']) == result['rf50_sha256']
        for source in result['source_seals']:
            assert digest(source['path']) == source['sha256']
        assert result['source_sha256'] == digest(HERE/'geometry.py')
        for arm in ARMS:
            ar = result['arms'][arm]
            contracts = []
            for model in MODELS:
                m = ar['models'][model]
                contracts.append(m['saved_endpoint_replay']['factor_contract'])
                maximum_replay = max(maximum_replay, abs(m['saved_endpoint_replay']['objective_replay_difference']))
                assert len(m['path']) == 11
                np.testing.assert_allclose([p['alpha'] for p in m['path']], np.linspace(0, 1, 11), atol=0)
                for p in m['path']:
                    all_points += 1
                    x = np.asarray(ar['baseline_endpoint'])+p['alpha']*np.asarray(ar['displacement_east_north_km'])
                    np.testing.assert_allclose(x, p['position_east_north_km'], atol=1e-12)
                    assert len(p['phase_refresh_changes_s']) == 5
                    assert p['phase_converged'] and p['Gamma_converged']
                    maximum_phase = max(maximum_phase, p['final_phase_change_s'])
                    maximum_Gamma = max(maximum_Gamma, p['final_log_precision_change'])
                    maximum_calibration_feedback = max(maximum_calibration_feedback, p['predictive_calibration_max_difference'])
                    maximum_decomposition = max(maximum_decomposition, abs(sum(p['terms'].values())-p['negative_twice_elbo']))
                for which, e in m['endpoints'].items():
                    d = e['derivatives']
                    for kind, rows in d['grouped_weighted_data_derivatives'].items():
                        maximum_group_closure = max(maximum_group_closure,
                            abs(sum(r['derivative_per_km'] for r in rows.values())-
                                d['term_directional_derivatives_per_km']['weighted_data']))
                    assert e['receiver_curves']['maximum_basis_reconstruction_error'] < 1e-12
                    if model == 'rf50':
                        for curve in e['receiver_curves']['curves']:
                            if curve['receiver'] == 2:
                                np.testing.assert_array_equal(curve['extra_hz'], np.zeros(len(curve['extra_hz'])))
                checks.append(dict(case=case, arm=arm, model=model, passed=True))
            assert contracts[0] == contracts[1]
            # Both c arms have identical counts, labels, and fixed segment budgets.
            other = result['arms'][ARMS[1] if arm == ARMS[0] else ARMS[0]]
            for model in MODELS:
                for p, q in zip(ar['models'][model]['path'], other['models'][model]['path'], strict=True):
                    for key in ('active_points', 'predictive_points', 'labels', 'norads'):
                        assert p[key] == q[key]
    assert all_points == 88 and maximum_calibration_feedback < 1e-10
    assert maximum_decomposition < 1e-6 and maximum_group_closure < 1e-6 and maximum_replay < 1e-5
    report = dict(passed=True, conditional_path_points=all_points, phase_refresh_solves=all_points*5,
                  maximum_decomposition_error=maximum_decomposition,
                  maximum_grouped_data_derivative_closure_error=maximum_group_closure,
                  maximum_final_phase_change_s=maximum_phase,
                  maximum_final_log_precision_change=maximum_Gamma,
                  maximum_saved_endpoint_replay_difference=maximum_replay,
                  maximum_predictive_calibration_feedback=maximum_calibration_feedback,
                  cases=checks, GPS_used=False, source_and_input_seals_verified=True,
                  result_seals=[dict(path=str(HERE/(case+'.json')), sha256=digest(HERE/(case+'.json'))) for case in CASES])
    write(HERE/'audit.json', report)
    return report


def make_tables(results):
    cross, paths, geom, phases, families, timebands, components, curves, term_changes = ([] for _ in range(9))
    for case, result in results.items():
        for arm, ar in result['arms'].items():
            for model, m in ar['models'].items():
                for p in m['path']:
                    paths.append(dict(case=case, arm=arm, model=model, alpha=p['alpha'],
                        east_km=p['position_east_north_km'][0], north_km=p['position_east_north_km'][1],
                        negative_twice_elbo=p['negative_twice_elbo'], RMS_hz=p['RMS_hz'],
                        final_phase_change_s=p['final_phase_change_s'],
                        final_log_precision_change=p['final_log_precision_change'], **p['terms']))
                for which, e in m['endpoints'].items():
                    p = e['summary'];g = e['geometry'];deriv=e['derivatives']
                    cross.append(dict(case=case, arm=arm, model=model, location=which,
                        negative_twice_elbo=p['negative_twice_elbo'], RMS_hz=p['RMS_hz'],
                        directional_derivative_per_km=deriv['directional_derivative_per_km'], **p['terms']))
                    geom.append(dict(case=case, arm=arm, model=model, location=which,
                        displacement_km=ar['displacement_km'],
                        weak_eigenvalue=g['eigenvalues'][0], strong_eigenvalue=g['eigenvalues'][1],
                        weak_axis_sigma_km=g['weak_axis_sigma_km'],
                        weak_axis_angle_to_displacement_deg=g['weak_axis_angle_to_displacement_deg'],
                        maximum_absolute_phase_correlation=g['maximum_absolute_phase_correlation'],
                        extraRX1_information_fraction_removed=g['appended_modes_displacement_information_fraction_removed'],
                        regularized_RX1_angle_proxy_deg=g['regularized_projected_RX1_angle_proxy_deg']))
                t0=m['endpoints']['baseline_endpoint']['summary']['terms']
                t1=m['endpoints']['rf50_endpoint']['summary']['terms']
                term_changes.extend(dict(case=case, arm=arm, model=model, term=k, change=v) for k,v in delta_terms(t0,t1).items())
            original=endpoint(ar,'baseline','baseline_endpoint')
            fixed_model=endpoint(ar,'rf50','baseline_endpoint')
            moved=endpoint(ar,'rf50','rf50_endpoint')
            for k,norad in enumerate(original['summary']['norads']):
                s0=original['summary'];sm=fixed_model['summary'];s1=moved['summary']
                phases.append(dict(case=case, arm=arm, norad=norad,
                    baseline_phase_s=s0['phases_s'][k], rf50_at_original_phase_s=sm['phases_s'][k],
                    rf50_at_moved_phase_s=s1['phases_s'][k],
                    model_change_at_original_s=sm['phases_s'][k]-s0['phases_s'][k],
                    movement_change_with_rf50_s=s1['phases_s'][k]-sm['phases_s'][k],
                    total_change_s=s1['phases_s'][k]-s0['phases_s'][k],
                    phase_prior_sigma_s=s0['phase_prior_sigma_s'][k],
                    displacement_phase_correlation=moved['geometry']['displacement_coordinate_phase_correlations'][k]))
            for kind, destination in [('family',families),('receiver_band_time',timebands),('component',components)]:
                d0=original['derivatives']['grouped_weighted_data_derivatives'][kind]
                dm=fixed_model['derivatives']['grouped_weighted_data_derivatives'][kind]
                data0=original[{'family':'family_data','receiver_band_time':'receiver_band_time_data','component':'component_data'}[kind]]
                data1=moved[{'family':'family_data','receiver_band_time':'receiver_band_time_data','component':'component_data'}[kind]]
                for key in d0:
                    destination.append(dict(case=case, arm=arm, group=key, points=d0[key]['points'],
                        baseline_data_derivative_per_km=d0[key]['derivative_per_km'],
                        rf50_data_derivative_at_original_per_km=dm[key]['derivative_per_km'],
                        derivative_change_per_km=dm[key]['derivative_per_km']-d0[key]['derivative_per_km'],
                        data_quadratic_change_original_to_moved=data1[key]['weighted_data']-data0[key]['weighted_data']))
            for c0, c1 in zip(original['receiver_curves']['curves'], moved['receiver_curves']['curves'], strict=True):
                delta=np.asarray(c1['total_hz'])-c0['total_hz']
                extra=np.asarray(c1['extra_hz'])
                curves.append(dict(case=case, arm=arm, receiver=c1['receiver'],band=c1['band'],
                    plot_rf_hz=c1['rf_hz'], total_change_mean_hz=float(delta.mean()),
                    total_change_RMS_hz=float(np.sqrt(np.mean(delta**2))),
                    total_change_centered_RMS_hz=float(np.std(delta)),
                    extra_RMS_hz=float(np.sqrt(np.mean(extra**2))), extra_maxabs_hz=float(np.max(abs(extra)))))
    for name,rows in [('cross_evaluation.csv',cross),('profile_path.csv',paths),('local_geometry.csv',geom),
                      ('family_phases.csv',phases),('family_influence.csv',families),('time_band_influence.csv',timebands),
                      ('component_influence.csv',components),('receiver_curve_statistics.csv',curves),
                      ('movement_loss_terms.csv',term_changes)]:
        table(name,rows)
    return dict(cross=cross,geom=geom,phases=phases,families=families,timebands=timebands,curves=curves)


def figures(results, tables):
    plt.rcParams.update({'font.size':9,'axes.grid':True,'grid.alpha':.2})
    colors={'baseline':'#555555','rf50':'#087f8c'}
    fig,axs=plt.subplots(2,2,figsize=(11,7),layout='constrained')
    for row,case in enumerate(CASES):
        for col,arm in enumerate(ARMS):
            ax=axs[row,col];ar=results[case]['arms'][arm]
            for model,m in ar['models'].items():
                loss=np.array([p['negative_twice_elbo'] for p in m['path']]);alpha=[p['alpha'] for p in m['path']]
                ax.plot(alpha,loss-loss[0],'-o',ms=3,color=colors[model],label=model)
            ax.axhline(0,color='black',lw=.6);ax.set_title(f'{case} · {arm} · displacement {ar["displacement_km"]:.3f} km')
            ax.set(xlabel='Frozen segment fraction (0 = original; 1 = RF50 endpoint)',
                   ylabel='Change in −2 ELBO\n(relative to original endpoint)')
            ax.legend()
    fig.suptitle('Full-data conditional path: five nuisance/phase refresh rounds per fixed position')
    fig.savefig(HERE/'profile_loss_path.png',dpi=160);plt.close(fig)

    fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for row,case in enumerate(CASES):
        for col,arm in enumerate(ARMS):
            ar=results[case]['arms'][arm];ax=axs[row,col]
            orig=endpoint(ar,'baseline','baseline_endpoint')['receiver_curves']['curves']
            moved=endpoint(ar,'rf50','rf50_endpoint')['receiver_curves']['curves']
            for c0,c1 in zip(orig,moved,strict=True):
                delta=np.array(c1['total_hz'])-c0['total_hz']
                label=f"RX{c1['receiver']} CH{'1–4' if c1['band']==0 else '5–8'} (mean {delta.mean():+.0f} Hz)"
                ax.plot(c1['time_s'],delta-delta.mean(),label=label,lw=1.2,
                        linestyle='-' if c1['receiver']==1 else '--')
            rx1=next(c for c in moved if c['receiver']==1)
            extra=np.asarray(rx1['extra_hz'])/(rx1['rf_hz']/11.5e9)
            ax.plot(rx1['time_s'],extra,color='black',lw=1.8,label='Appended RX1 component at 11.5 GHz')
            ax.set(title=f'{case} · {arm}',xlabel='Time since scan start (s)',ylabel='Hz (total curves mean-centered)')
            ax.legend(fontsize=7)
    fig.suptitle('Receiver frequency change: original model/original endpoint → RF50 model/RF50 endpoint')
    fig.savefig(HERE/'receiver_frequency_curves.png',dpi=160);plt.close(fig)

    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for row,case in enumerate(CASES):
        for col,arm in enumerate(ARMS):
            ax=axs[row,col];r=[r for r in tables['phases'] if r['case']==case and r['arm']==arm]
            r=sorted(r,key=lambda r:r['total_change_s'])
            x=np.arange(len(r));ax.bar(x,[p['model_change_at_original_s'] for p in r],label='Model change at original point',color='#edae49')
            ax.scatter(x,[p['total_change_s'] for p in r],label='Total change at moved point',color='#087f8c',s=16)
            ax.set_xticks(x,[str(p['norad']) for p in r],rotation=90,fontsize=6)
            ax.set(title=f'{case} · {arm}',ylabel='Satellite phase change (s)',xlabel='Frozen candidate NORAD')
            ax.legend(fontsize=7)
    fig.suptitle('Absolute timing-prior coordinates refit as receiver and position change')
    fig.savefig(HERE/'satellite_phase_changes.png',dpi=160);plt.close(fig)

    fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for row,case in enumerate(CASES):
        for col,arm in enumerate(ARMS):
            ax=axs[row,col];r=[r for r in tables['families'] if r['case']==case and r['arm']==arm]
            r=sorted(r,key=lambda r:abs(r['derivative_change_per_km']),reverse=True)[:10]
            r=sorted(r,key=lambda r:r['derivative_change_per_km'])
            ax.barh([p['group'] for p in r],[p['derivative_change_per_km'] for p in r],color=['#087f8c' if p['derivative_change_per_km']<0 else '#d96c46' for p in r])
            ax.axvline(0,color='black',lw=.6);ax.set(title=f'{case} · {arm}',xlabel='Change in weighted-data derivative per km',ylabel='Frozen candidate NORAD')
    fig.suptitle('Largest family changes in the data-term gradient at the original point\nNegative points along movement; shared priors, covariance and logvolume remain global')
    fig.savefig(HERE/'family_gradient_changes.png',dpi=160);plt.close(fig)

    owned_path=HERE/'family_owned_score_derivative_changes.csv'
    if owned_path.exists():
        with owned_path.open() as handle:
            owned=list(csv.DictReader(handle))
        fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
        for row,case in enumerate(CASES):
            for col,arm in enumerate(ARMS):
                ax=axs[row,col];r=[r for r in owned if r['case']==case and r['arm']==arm]
                r=sorted(r,key=lambda r:abs(float(r['total_owned_derivative_change_per_km'])),reverse=True)[:10]
                r=sorted(r,key=lambda r:float(r['total_owned_derivative_change_per_km']))
                values=[float(p['total_owned_derivative_change_per_km']) for p in r]
                ax.barh([p['norad'] for p in r],values,color=['#087f8c' if v<0 else '#d96c46' for v in values])
                ax.axvline(0,color='black',lw=.6)
                ax.set(title=f'{case} · {arm}',xlabel='Change in family-owned score derivative per km',ylabel='Frozen candidate NORAD')
        fig.suptitle('Data + family noise Gamma + phase/orbit/fragment priors: largest local gradient changes\nConditional joint decomposition; shared receiver, logvolume and predictive score remain global')
        fig.savefig(HERE/'family_owned_gradient_changes.png',dpi=160);plt.close(fig)

    fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for row,case in enumerate(CASES):
        for col,arm in enumerate(ARMS):
            r=[r for r in tables['timebands'] if r['case']==case and r['arm']==arm]
            matrix=np.full((4,10),np.nan)
            for p in r:
                rx,band,interval=p['group'].split(':');ir=(int(rx[-1])-1)*2+int(band=='CH5-8');it=int(interval[:3])//30
                if it<10: matrix[ir,it]=p['derivative_change_per_km']
            lim=max(.01,float(np.nanmax(abs(matrix))));ax=axs[row,col]
            im=ax.imshow(matrix,aspect='auto',cmap='RdBu_r',vmin=-lim,vmax=lim)
            ax.set_yticks(range(4),['RX1 CH1–4','RX1 CH5–8','RX2 CH1–4','RX2 CH5–8'])
            ax.set_xticks(range(10),[f'{t*30}–{(t+1)*30}' for t in range(10)],rotation=45,fontsize=7)
            ax.set(title=f'{case} · {arm}',xlabel='Time bin (s)');fig.colorbar(im,ax=ax,label='Data derivative change / km')
    fig.suptitle('When and where the conditional weighted-data gradient changes (blank = no active points)')
    fig.savefig(HERE/'time_receiver_band_gradient.png',dpi=160);plt.close(fig)

    labels=['data','receiver','phase','orbit','fragment','logvol','noise Γ','prior Γ','predictive']
    fig,axs=plt.subplots(2,2,figsize=(13,7),layout='constrained')
    for row,case in enumerate(CASES):
        for col,arm in enumerate(ARMS):
            ax=axs[row,col];ar=results[case]['arms'][arm]
            for im,model in enumerate(MODELS):
                t0=endpoint(ar,model,'baseline_endpoint')['summary']['terms'];t1=endpoint(ar,model,'rf50_endpoint')['summary']['terms'];d=delta_terms(t0,t1)
                receiver=sum(v for k,v in d.items() if k.startswith('prior_') and k not in ('prior_phase','prior_orbit','prior_fragment','prior_Gamma'))
                values=[d['weighted_data'],receiver,d['prior_phase'],d['prior_orbit'],d['prior_fragment'],d['logvolume'],d['noise_Gamma'],d['prior_Gamma'],d['predictive']]
                ax.bar(np.arange(len(labels))+(im-.5)*.35,values,width=.35,label=model,color=colors[model])
            ax.set_xticks(range(len(labels)),labels,rotation=45);ax.axhline(0,color='black',lw=.6)
            ax.set(title=f'{case} · {arm}',ylabel='Normalized loss change along complete segment');ax.legend(fontsize=7)
    fig.suptitle('Both models at both frozen endpoints: full objective decomposition, with nuisance refits')
    fig.savefig(HERE/'movement_loss_decomposition.png',dpi=160);plt.close(fig)


def main():
    results={case:read(HERE/(case+'.json')) for case in CASES}
    audited=audit(results)
    tables=make_tables(results)
    figures(results,tables)
    detail=read(HERE/'family_score_detail.json')
    assert detail['passed'] and detail['source_sha256']==digest(HERE/'family_score_detail.py')
    for item in detail['input_seals']:assert digest(item['path'])==item['sha256']
    write(HERE/'summary.json',dict(audit=audited, source_sha256=digest(Path(__file__)),
        output_sha256=[dict(path=str(p),sha256=digest(p)) for p in sorted(HERE.glob('*.csv'))],
        all_results_conditional_on_full_data_endpoints_and_frozen_RF_labels=True,
        full_normalized_objective_used=True, GPS_used=False,
        family_owned_score_decomposition_passed=True,
        maximum_family_owned_score_decomposition_error=max(abs(s['reconstruction_error']) for s in detail['summaries'])))
    print(audited)


if __name__=='__main__':
    main()
