"""Report a negative calibration-role control on a frozen same-site cohort."""

from pathlib import Path
import shutil
import tarfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import probe_ds23_distributed_calibration_roles as study
from ds23_calibration_roles import predictive_roles
from report_algo02_ds23 import position_error
from report_ds23_dbg01_iteration_001 import csv_write
from run_algo01_ds23_sample import ROOT,read,write,sha

RAW=study.OUT;OUT=ROOT/'reports/2026_10_23_ds23_distributed_calibration_roles_assessment'


def save(fig,name):
    fig.savefig(OUT/'figures'/name,dpi=145);plt.close(fig)


def examples(case):
    study.runner.configure();d=study.runner.engine.current_setup(case)
    inv=read(study.inventory.OUT/(case+'.json'));weak=[r for r in inv['rows'] if not r['would_retain_calibration']]
    if not weak:return
    fig,axes=plt.subplots(len(weak),2,figsize=(14,3.8*len(weak)),squeeze=False,layout='constrained')
    for axs,row in zip(axes,weak,strict=True):
        track=d['scan'].tracks[row['track_index']];sl=d['base'].slices[row['row']];use=d['keep'][sl]
        t=np.asarray(track['times'])[use];y=np.asarray(track['values'])[use];z=(t-t.mean())/np.ptp(t)
        axs[0].scatter(t,y/1000,s=20,c='black',label='Exact original active GLRT')
        for degree in [1,2,3,4]:
            if degree>1 and len(t)-1<4*(degree+1):continue
            u=np.polynomial.legendre.legvander(z,degree);pred=u@np.linalg.lstsq(u,y,rcond=None)[0]
            axs[0].plot(t,pred/1000,label=f'Degree{degree}');axs[1].plot(t,y-pred,'.-',label=f'Degree{degree}')
        axs[0].set(title=f"RX{row['receiver']} CH{row['channel']} / {row['norad']} / {len(t)} points; power{row['original_power']}",ylabel='Graph CFO (kHz)')
        e=row['evidence'];axs[1].set(title=e.get('reason') or f"Every deletion: min nonlinear RMS{e['minimum_nonlinear_RMS_hz']:.1f}Hz, BIC gain{e['minimum_penalized_BIC_gain']:.1f}",ylabel='Polynomial residual (Hz)');axs[1].axhline(0,c='gray')
        for ax in axs:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle(case+' · sources selected using RF alone, before any role-change position fits\nDeletions diagnose distributed support only; every original active point remains in the likelihood')
    save(fig,case+'_weak_original_sources.png')


def main():
    assert read(RAW/'execution.json')['all_passed'];p=read(RAW/'protocol.json')
    for folder in ['figures','tables','evidence','source/tools','source/tests']:(OUT/folder).mkdir(parents=True,exist_ok=True)
    rows=[];sources=[];failures=[];checks=[];summary=[]
    for case in p['cases']:
        data=read(RAW/(case+'.json'));inv=read(study.inventory.OUT/(case+'.json'))
        for r in inv['rows']:
            e=r['evidence'];sources.append(dict(case=case,component=r['component'],norad=r['norad'],points=r['active_points'],original_power=r['original_power'],qualified=e['qualified'],reason=e.get('reason',''),minimum_nonlinear_RMS_hz=e.get('minimum_nonlinear_RMS_hz',''),minimum_penalized_BIC_gain=e.get('minimum_penalized_BIC_gain',''),degrees=str(e.get('degrees_selected',[]))))
        checks.extend(data['independent_endpoint_checks'])
        for arm in ['c0','fitted_c']:
            base=data['baseline_arms'][arm];raw=data['arms'][arm];policy=data['policy_arms'][arm]
            rows.append(dict(case=case,cohort='engineering' if case in p['engineering'] else 'random20',arm=arm,demoted_points=inv['would_demote_points'],qualified=data['qualified'],
                original_error_km=position_error(base['endpoint_latlon']),raw_error_km=position_error(raw['endpoint_latlon']),policy_error_km=position_error(policy['endpoint_latlon']),
                original_associated=data['baseline_coverage'][arm]['associated'],raw_associated=data['coverage'][arm]['associated'],policy_associated=data['policy_coverage'][arm]['associated'],total_GLRT=data['baseline_coverage'][arm]['total_GLRT'],
                original_RMS_hz=base['RMS_hz'],raw_remaining_calibration_RMS_hz=raw['RMS_hz'],raw_negative_twice_elbo=raw['negative_twice_elbo'],
                ID_union_unchanged=data['all_likelihood_IDs_unchanged'],original_accepted_IDs_preserved=data['all_original_accepted_IDs_preserved'][arm]))
            for role,gates in [('calibration',raw['gates']['tracks']),('predictive',raw['linear_gates'])]:
                for g in gates:
                    if not g['compatible']:failures.append(dict(case=case,arm=arm,role=role,component=g['component'],norad=g['norad'],points=g['points']))
    for arm in ['c0','fitted_c']:
        for cohort in ['engineering','random20','all22']:
            rr=[r for r in rows if r['arm']==arm and (cohort=='all22' or r['cohort']==cohort)]
            for model,key,coverage in [('Incumbent','original_error_km','original_associated'),('Unqualified raw control','raw_error_km','raw_associated'),('Qualified policy with fallback','policy_error_km','policy_associated')]:
                x=np.array([r[key] for r in rr]);summary.append(dict(arm=arm,cohort=cohort,model=model,scans=len(rr),mean_error_km=float(x.mean()),median_error_km=float(np.median(x)),maximum_error_km=float(x.max()),associated=sum(r[coverage] for r in rr),total_GLRT=sum(r['total_GLRT'] for r in rr),improved=sum(r[key]<r['original_error_km']-1e-6 for r in rr),worsened=sum(r[key]>r['original_error_km']+1e-6 for r in rr)))
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    for j,arm in enumerate(['c0','fitted_c']):
        for k,model in enumerate(['Incumbent','Qualified policy with fallback']):
            s=next(s for s in summary if s['arm']==arm and s['cohort']=='random20' and s['model']==model)
            axes[j].bar(np.arange(2)+(k-.5)*.34,[s['mean_error_km'],s['median_error_km']],width=.33,label=model,color=f'C{k}')
        axes[j].set(xticks=[0,1],xticklabels=['Mean','Median'],ylabel='Position error (km)',title=arm);axes[j].axhline(.5,c='green',ls='--');axes[j].legend(fontsize=8);axes[j].grid(axis='y',alpha=.2)
    fig.suptitle('Frozen random20 same-site confirmation · degree2–4 distributed curvature rule\nOriginal likelihood IDs retained; gate failures fall back. Fitted-c mean worsens; no promotion')
    save(fig,'random20_summary.png')
    fig,axes=plt.subplots(2,1,figsize=(16,9),layout='constrained')
    for ax,arm in zip(axes,['c0','fitted_c'],strict=True):
        rr=[r for r in rows if r['arm']==arm and r['cohort']=='random20'];delta=np.array([r['policy_error_km']-r['original_error_km'] for r in rr])*1000
        ax.bar(range(len(rr)),delta,color=['crimson' if v>0 else 'C0' for v in delta]);ax.axhline(0,c='gray');ax.set(xticks=range(len(rr)),xticklabels=[r['case'][5:] for r in rr],ylabel='Change in error (m)',title=arm+' · positive means worse');ax.grid(axis='y',alpha=.2)
    fig.suptitle('RF eligibility and residual checks do not guarantee better position\nSame predeclared rule on all20 scans, no geographic selection of role changes')
    save(fig,'per_scan_error_changes.png')
    fig,axes=plt.subplots(1,2,figsize=(16,5),layout='constrained');old=read(study.inventory.PARENT/'execution.json')['rows'];new=read(study.inventory.OUT/'execution.json')['rows']
    x=np.arange(len(new));axes[0].bar(x-.2,[r['would_demote_points'] for r in old],width=.4,label='Quadratic-only diagnostic');axes[0].bar(x+.2,[r['would_demote_points'] for r in new],width=.4,label='Degree2–4 + degree-search penalty');axes[0].set(xticks=x,xticklabels=[r['case'][5:] for r in new],ylabel='Original calibration points flagged',title='Same RF-frozen22-case inventory');axes[0].tick_params(axis='x',rotation=60);axes[0].legend(fontsize=8)
    valid=[r for r in sources if r['minimum_nonlinear_RMS_hz']!=''];axes[1].scatter([r['minimum_nonlinear_RMS_hz'] for r in valid],[r['minimum_penalized_BIC_gain'] for r in valid],s=12,c=['C0' if r['qualified'] else 'crimson' for r in valid]);axes[1].axvline(250,c='gray',ls='--');axes[1].axhline(10,c='gray',ls='--');axes[1].set(xscale='symlog',yscale='symlog',xlabel='Minimum fitted nonlinear RMS over deletions (Hz)',ylabel='Minimum BIC gain after degree-search penalty',title='Short sources without eligible fits are excluded from scatter')
    for ax in axes:ax.grid(alpha=.2)
    save(fig,'RF_curvature_inventory.png')
    for case in ['DS23-0409','DS23-0310']:examples(case)
    for name,data in [('positions',rows),('summary',summary),('source_eligibility',sources),('failed_gates',failures),('endpoint_audits',checks)]:csv_write(OUT/'tables'/(name+'.csv'),data)
    write(OUT/'evidence/evaluation.json',dict(summary=summary,rows=rows,all44endpoint_checks_passed=len(checks)==44,new_ALGO_release=False,full_DS23_rollout_rejected=True))
    for name in ['protocol.json','execution.json']:shutil.copyfile(RAW/name,OUT/'evidence'/name)
    manifest=[]
    for name,source in [('roles',RAW),('degree4_inventory',study.inventory.OUT),('quadratic_inventory',study.inventory.PARENT)]:
        files=sorted(source.glob('*.json'));target=OUT/'evidence'/(name+'.tar.gz')
        with tarfile.open(target,'w:gz') as archive:
            for f in files:archive.add(f,arcname=f.name,recursive=False)
        if target.stat().st_size>=45*1024**2:raise ValueError('split report evidence archive')
        manifest.append(dict(file=str(target.relative_to(OUT)),sha256=sha(target),bytes=target.stat().st_size,files=len(files)))
    write(OUT/'evidence/archive_manifest.json',manifest)
    for name in ['inventory_ds23_calibration_curvature.py','inventory_ds23_distributed_calibration_curvature.py','ds23_distributed_polynomial_curvature.py','ds23_calibration_roles.py','probe_ds23_distributed_calibration_roles.py',Path(__file__).name]:shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    for name in ['test_ds23_calibration_curvature_inventory.py','test_ds23_distributed_polynomial_curvature.py','test_ds23_calibration_roles.py']:shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    write(OUT/'evidence/source_hashes.json',{str(f.relative_to(OUT)):sha(f) for f in (OUT/'source').rglob('*.py')})
    print('Role-control report complete',len(checks),'endpoint checks',flush=True)


if __name__=='__main__':main()
