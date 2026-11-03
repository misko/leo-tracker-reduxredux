"""Replay RF profile scores and expose the scope of finite-window controls."""

from concurrent.futures import ProcessPoolExecutor
import copy
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from audit_ds23_targeted_differential_rf import reconstruct
from ds23_smooth_component_workspace import SmoothComponentWorkspace
from ds23_chirped_component_workspace import ChirpedComponentWorkspace
from run_algo01_ds23_sample import read,write,sha
from select_ds23_differential_information import OUT


def replay(record):
    case,probe=record['case'],record['probe'];base=reconstruct(record);count=0;maximum=0.
    summaries={}
    for name in ['profile_response','profile_response_fine','profile_response_smooth','profile_response_smooth_rate5000']:
        saved=read(OUT/name/f'{case}_probe{probe:06d}.json');assert saved['status']=='complete'
        p=base if 'smooth' not in name else SmoothComponentWorkspace.from_workspace(base)
        fits=[saved['tight_full']]+[f for r in saved['injected_fits'] for f in r['fits']]
        # Perturbed observations require rebuilding the recorded injection.
        from ds23_differential_rf_epoch import inject_component_rates
        for f in fits[:1]:
            value=p.statistics(f['parameters']);maximum=max(maximum,abs(value['score']-f['score']));count+=1
        for row in saved['injected_fits']:
            for sign,f in zip([-1,1],row['fits'],strict=True):
                rates=np.zeros(2);rates[row['component']]=sign*row['magnitude_hz_s']
                view=copy.copy(p);view.y=inject_component_rates(p,saved['tight_full']['parameters'],rates)
                value=view.statistics(f['parameters']);maximum=max(maximum,abs(value['score']-f['score']));count+=1
        summaries[name]=dict(maximum_response_error_hz=saved['maximum_observed_response_discrepancy_hz'],
            hessian_asymmetry=saved['observed_response']['hessian_asymmetry'],
            minimum_hessian_eigenvalue=saved['observed_response']['minimum_eigenvalue'])
    p=SmoothComponentWorkspace.from_workspace(base)
    smooth=read(OUT/'smooth_validation'/f'{case}_probe{probe:06d}.json')
    tasks=[(smooth['full'],None,None)]+[(r['fit'],i,None) for i,r in enumerate(smooth['folds'])]
    tasks += [(r['fit'],None,r['frames']) for r in smooth['bootstrap_replicates']]
    original=list(p.segments)
    for f,parity,draws in tasks:
        p.segments=original if draws is None else [original[k] for k in draws]
        value=p.statistics(f['parameters'],parity);maximum=max(maximum,abs(value['score']-f['score']));count+=1
    p.segments=original
    chirp=read(OUT/'chirped_validation'/f'{case}_probe{probe:06d}.json')
    if chirp['status']=='complete':
        c=ChirpedComponentWorkspace.from_workspace(base);original=list(c.segments)
        tasks=[(chirp['full'],None,None)]+[(r['fit'],i,None) for i,r in enumerate(chirp['folds'])]
        tasks += [(r['fit'],None,r['frames']) for r in chirp['bootstrap_replicates']]
        for f,parity,draws in tasks:
            c.segments=original if draws is None else [original[k] for k in draws]
            value=c.statistics(f['parameters'],parity);maximum=max(maximum,abs(value['score']-f['score']));count+=1
            noise=value['squared_error']/max(1,value['samples']-17*len(c.segments)-8)
            covariance=np.diag(c.scale)@np.linalg.solve(value['normal'],np.eye(8))@np.diag(c.scale)*noise/2
            assert np.allclose(covariance,f['covariance'],rtol=1e-10,atol=1e-5)
    assert maximum<1e-12
    result=dict(case=case,probe=probe,replayed_scores=count,maximum_score_difference=maximum,
        RF_checks_pass=smooth['RF_and_epoch_qualified'],response_controls=summaries,
        chirp_status=chirp['status'],chirp_quality_checks_pass=chirp.get('chirp_quality_checks_pass',False),
        source_RF_sha256=sha(OUT/'RF_pilot.json'))
    print(case,probe,count,maximum,flush=True);return result


def main():
    chirps=read(OUT/'chirped_validation/evaluation.json');assert chirps['all_terminal']
    source=read(OUT/'RF_pilot.json');selected=sorted([r for r in source['rows'] if r.get('RF_qualified')],key=lambda r:(r['case'],r['probe']))
    with ProcessPoolExecutor(max_workers=3) as pool:rows=list(pool.map(replay,selected))
    execution=read(OUT/'windowed_position/execution.json');protocol=read(OUT/'windowed_position/protocol.json')
    assert execution['all_terminal'] and len(execution['rows'])==0 and len(protocol['cases'])==0
    write(OUT/'profile_response_independent_audit.json',dict(rows=rows,all_terminal=True,
        total_replayed_scores=sum(r['replayed_scores'] for r in rows),no_position_factors_applied=True,
        wide_rate_response_controls_prevented_unqualified_position_use=True,
        no_full_DS23_accuracy_change=True))
    fig,axes=plt.subplots(1,3,figsize=(13,4.6),sharey=True)
    for ax,r in zip(axes,rows,strict=True):
        old=next(a for a in read(OUT/'RF_independent_audit.json')['rows'] if (a['case'],a['probe'])==(r['case'],r['probe']))
        values=([max(abs(t['difference_hz']) for t in old['injected_frequency_rate_checks'])]+
            [r['response_controls'][name]['maximum_response_error_hz'] for name in
             ['profile_response_fine','profile_response_smooth','profile_response_smooth_rate5000']])
        colors=['#c54e55','#c18c35','#168b91','#c54e55']
        ax.bar(range(4),values,color=colors)
        ax.axhline(.3,color='black',linestyle='--',linewidth=1)
        for k,value in enumerate(values):ax.text(k,value*1.10,f'{value:.3f}',ha='center',fontsize=8)
        ax.set_xticks(range(4),['Original GN\n1kHz/s','Tight linear\n1kHz/s','Smooth observed\n1kHz/s','Smooth observed\n5kHz/s'],rotation=25,ha='right',fontsize=8)
        ax.set_title(r['case']+'/'+str(r['probe']));ax.set_yscale('log');ax.grid(axis='y',alpha=.2)
    axes[0].set_ylabel('Maximum rate-response prediction error (Hz)')
    fig.suptitle('A local RF response check does not establish validity over the full Doppler-rate range\nDashed line: unchanged0.3Hz engineering check; no position improvement claimed',fontsize=11)
    fig.tight_layout();fig.savefig(OUT/'carrier_rate_response_controls.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
