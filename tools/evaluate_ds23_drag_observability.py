"""Independent direct-frequency and QR checks of the Bstar sensitivity audit."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.linalg import qr
from sgp4.api import Satrec

from analyze_dsx01_fixed_site import ecef_states
from ds23_frequency_events import make_event_problem
from fit_s01_69333_tle_parameter import perturb
from probe_ds23_drag_observability import OUT, ARMS, hashes
from probe_ds23_fft_grid_position import setup
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.sky.propagation import ElementSetCatalogue


def verify(case):
    record=read(OUT/(case+'.json'))
    if record['source_sha256']!=hashes():
        raise ValueError('frozen sensitivity source changed')
    scan,node,mask,base,old,signed,binding,model,powers,means,entries=setup(case)
    rows=[]
    for arm in ARMS:
        saved=signed['policy_arms'][arm]
        p=make_event_problem(scan,node,mask,arm,np.asarray(saved['phase_reference']),powers,means,model,[])
        x=np.asarray(saved['endpoint_east_north_km']);c=p.calculate(x)
        start=p.hardware.shape[1]+p.smooth.shape[1]
        for family in record['arms'][arm]['families']:
            j=int(np.flatnonzero(scan.norads==family['norad'])[0]);local=p.labels.index(j)
            use=mask & (p.flat_labels==local);times=p.flat_times[use];n=len(times)
            latest=Satrec.twoline2rv(*scan.elements[str(family['norad'])]['lines'])
            catalogue=ElementSetCatalogue(('plus','minus'),(family['norad'],)*2,
                tuple(perturb(latest,'bstar',h) for h in (1e-5,-1e-5)))
            position,velocity,good=ecef_states(catalogue,scan.receipt['origin_utc_ns'],scan.sky['time_s'])
            if not good.all():
                raise ValueError('direct-frequency propagation failed')
            bank=dict(time_s=scan.sky['time_s'],position_km=position,velocity_km_s=velocity)
            frequency=paired_phase_frequency(bank,np.tile(times,2),np.repeat([0,1],n),
                np.full(2,p.reference[local]),*latlon(x))[0].reshape(2,n)
            direct=(frequency[0]-frequency[1])/(2e-5)*family['Bstar_sigma']*p.q[use]
            k=p.supported.index(j)
            columns=[start+local]+list(range(start+len(p.labels)+3*k,start+len(p.labels)+3*k+3))
            columns+=list(range(c['features'].shape[1]-len(p.members),c['features'].shape[1]))
            a=c['features'][use][:,columns];s=p.point_noise[use]
            projection=family['nominal_noise_projection']
            reconstructed=a@np.asarray(projection['representation_coefficient'])+np.asarray(projection['independent_hz'])
            delta=float(np.max(abs(direct-reconstructed)))
            direct_tolerance=max(.001,.01*float(np.max(abs(reconstructed))))
            u=a/s[:,None];norm=np.linalg.norm(u,axis=0);u=u[:,norm>0]/norm[norm>0]
            q,r,pivots=qr(u,mode='economic',pivoting=True)
            rank=projection['existing_rank']
            q=q[:,:rank]
            z=reconstructed/s
            residual=z-q@(q.T@z)
            difference=float(np.linalg.norm(residual-np.asarray(projection['independent_hz'])/s))
            tolerance=1e-6*max(1.,float(np.linalg.norm(z)))
            direct_white=direct/s;direct_residual=direct_white-q@(q.T@direct_white)
            row=dict(case=case,arm=arm,norad=family['norad'],points=n,
                direct_frequency_max_difference_hz=delta,direct_frequency_tolerance_hz=direct_tolerance,
                direct_frequency_check=delta<=direct_tolerance,
                QR_residual_difference_noise_norm=difference,QR_check=difference<=tolerance,
                direct_frequency_independent_noise_norm=float(np.linalg.norm(direct_residual)),
                original_independent_noise_norm=projection['independent_noise_norm'],
                raw_noise_norm=projection['raw_noise_norm'],
                raw_RMS_hz=projection['raw_RMS_hz'],independent_RMS_hz=projection['independent_RMS_hz'],
                original_finite_difference_qualified=family['finite_difference_qualified'])
            row['verified']=bool(row['direct_frequency_check'] and row['QR_check'] and
                row['original_finite_difference_qualified'])
            rows.append(row)
    return dict(case=case,rows=rows,all_verified=all(r['verified'] for r in rows),
        sensitivity_result_sha256=sha(OUT/(case+'.json')))


def main():
    protocol=read(OUT/'protocol.json');cases=protocol['development_cases']+protocol['confirmation_cases']
    receipts=[]
    with ProcessPoolExecutor(max_workers=24) as pool:
        futures={pool.submit(verify,c):c for c in cases}
        for future in as_completed(futures):
            try:
                receipts.append(future.result())
            except Exception as exc:
                receipts.append(dict(case=futures[future],error=repr(exc)))
    errors=[r for r in receipts if 'error' in r or not r.get('all_verified',False)]
    write(OUT/'independent_verification.json',dict(all_terminal=True,receipts=receipts,errors=errors,
        evaluator_source_sha256=sha(Path(__file__)),no_GPS_or_new_position_fit=True))
    if errors:
        print('Verification failed',[(r['case'],r.get('error')) for r in errors],flush=True)
        return
    rows=[r for receipt in receipts for r in receipt['rows']]
    cohorts={}
    for cohort in ('development','confirmation'):
        selected=[r for r in rows if r['case'] in protocol[cohort+'_cases']]
        families=sorted({(r['case'],r['norad']) for r in selected})
        qualified=sum(all(next(r for r in selected if (r['case'],r['norad'],r['arm'])==(case,norad,arm))[
            'original_independent_noise_norm']>=1 for arm in ARMS) for case,norad in families)
        cohorts[cohort]=dict(scans=len(protocol[cohort+'_cases']),supported_families=len(families),
            families_with_independent_noise_norm_at_least_one_both_c_arms=qualified,
            qualification_fraction=qualified/len(families),
            maximum_independent_noise_norm=max(r['original_independent_noise_norm'] for r in selected),
            maximum_independent_RMS_hz=max(r['independent_RMS_hz'] for r in selected),
            maximum_direct_frequency_independent_noise_norm=max(r['direct_frequency_independent_noise_norm'] for r in selected))
    advance=all(r['qualification_fraction']>=.1 for r in cohorts.values())
    write(OUT/'evaluation.json',dict(cohorts=cohorts,advance_to_position_fits=advance,
        independent_verification_sha256=sha(OUT/'independent_verification.json'),
        no_localization_improvement_claimed=True,existing_covariance_not_validated_by_projection=True))
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for cohort,color in (('development','#3075a6'),('confirmation','#b8678a')):
        selected=[r for r in rows if r['case'] in protocol[cohort+'_cases'] and r['arm']=='fitted_c']
        axes[0].scatter([r['raw_noise_norm'] for r in selected],
            [max(1e-12,r['original_independent_noise_norm']) for r in selected],s=15,alpha=.65,color=color,label=cohort)
        values=sorted(r['original_independent_noise_norm'] for r in selected)
        axes[1].plot(values,np.arange(1,len(values)+1)/len(values),color=color,label=f'{cohort}: {len(values)} families')
    axes[0].set(xscale='log',yscale='log',xlabel='Total causal Bstar displacement (noise norm)',
        ylabel='Independent displacement after existing modes (noise norm)')
    axes[0].axhline(1,color='black',ls='--',lw=.8)
    axes[1].set(xscale='log',xlabel='Independent Bstar direction (noise norm)',ylabel='Fraction of families')
    axes[1].axvline(1,color='black',ls='--',lw=.8)
    for ax in axes:
        ax.grid(alpha=.15);ax.legend(fontsize=8)
    fig.suptitle('DS23 · 40 scans · causal drag sensitivity at published RF positions\n'
        'Existing phase + three physical modes + fragment constants projected out · fitted-c shown')
    fig.tight_layout(rect=(0,0,1,.88));fig.savefig(OUT/'drag_independent_information.png',dpi=175);plt.close(fig)
    print(cohorts,'advance',advance,flush=True)


if __name__=='__main__':
    main()
