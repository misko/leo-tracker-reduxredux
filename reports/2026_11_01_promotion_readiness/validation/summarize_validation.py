"""Render and audit saved replacement diagnostics without rerunning fits."""
import csv
from pathlib import Path
import subprocess
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from validate_replacements import OUT, REPO, SEALED, CASES, read, write, sha
from predictive_uniqueness import from_additional_checks, from_saved_screen


def csv_write(name, rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w') as handle:
        writer=csv.DictWriter(handle,fields)
        writer.writeheader()
        writer.writerows(rows)


def run():
    figdir=OUT/'figures'
    figdir.mkdir(exist_ok=True)
    manifest=read(SEALED/'manifest.json')
    raw_checks={p:sha(SEALED/p)==digest for p,digest in manifest['raw_json_sha256'].items()
                if any(p.startswith(c+'/') for c in CASES)}
    source_checks={p:sha(p)==digest for p,digest in manifest['source_sha256'].items()}
    assert all(raw_checks.values()) and all(source_checks.values()), 'Sealed input mismatch'
    summary=[]; candidates=[]; predictive=[]; tle=[]; transfers=[]; sensitivity=[]; native=[]; guards={}
    fig,axes=plt.subplots(2,2,figsize=(12,8),constrained_layout=True)
    fig2,axes2=plt.subplots(2,2,figsize=(12,8),constrained_layout=True)
    case_text=[]
    for ax,ax2,(case,(old,new)) in zip(axes.flat,axes2.flat,CASES.items()):
        extra=read(OUT/case/'additional_checks.json')
        screen=read(SEALED/case/str(old)/'screen.json')
        result=read(SEALED/case/'result.json')
        diag=read(SEALED/case/'diagnostics/combined.json')
        record=next(r for r in result['records']['combined'] if r['name']==f'{old}_to_{new}')
        guards[case]={'receiver_shared_5s':from_additional_checks(extra),
                      'receiver_shared_15s':from_additional_checks(extra,phase_sd_s=15.),
                      'legacy_screen':from_saved_screen(screen,new)}
        guard=guards[case]['receiver_shared_5s']
        x=np.arange(len(screen['nominees']))
        for arm,shift in [('c0',-.15),('fitted_c',.15)]:
            means=[]
            for n in screen['nominees']:
                fitrows=[r for r in extra['rows'] if r['model']=='receiver_offset' and r['phase_sd_s']==5. and r['arm']==arm]
                byfold={(r['fold'],r['norad']):r for r in fitrows}
                margins=[byfold[(r['fold'],old)]['predictive_score']-r['predictive_score'] for r in fitrows if r['norad']==n]
                means.append(float(np.mean(margins)))
                predictive.append(dict(case=case,arm=arm,norad=n,model='receiver_offset',phase_sd_s=5.,
                                       unique_folds=len(margins),mean_gain_vs_incumbent=float(np.mean(margins)),
                                       minimum_gain_vs_incumbent=min(margins),wins_vs_incumbent=sum(g>0 for g in margins)))
            ax.bar(x+shift,means,width=.3,label=arm)
        ax.axhline(0,color='k',lw=.8)
        ax.set_xticks(x,[str(n)+('*' if n==new else '') for n in screen['nominees']])
        ax.set_title(f'{case}: {guard["status"]}; minimum competitor margin {guard["minimum_margin"]:.2f}')
        ax.set_ylabel('Mean normalized held-score gain vs incumbent')
        ax.set_xlabel('NORAD (* accepted replacement)')
        ax.legend()
        fitpath=Path(record['fits_path'])
        fitrows=read(fitpath)
        start_displacement={a:float(np.linalg.norm(np.asarray(next(r for r in fitrows if r['arm']==a and r['start']=='published')['x'])-
                                                  np.asarray(next(r for r in fitrows if r['arm']==a and r['start']=='family_omitted')['x']))) for a in ('c0','fitted_c')}
        for arm in ('c0','fitted_c'):
            fit=record['pair'][arm]
            parameter=next(r for r in fit['parameters'] if r['norad']==new)
            for setting in diag['sensitivity']:
                if setting['arm']==arm:
                    sensitivity.append(dict(case=case,**setting))
            summary.append(dict(case=case,incumbent=old,replacement=new,arm=arm,native_target_points=screen['points'],
                 tracks=len(screen['tracks']),receivers=len(set(t['receiver'] for t in fit['tracks'] if t['norad']==new)),
                 causal_finalists=len(screen['nominees']),accepted_joint=True,rf_gain_after_penalty=record['gains'][arm],
                 all_original_gates_pass=fit['all_gates_pass'],phase_closed=fit['phase_closed'],
                 phase_s=parameter['phase_s'],phase_sigma_s=parameter['phase_sigma_s'],
                 largest_orbital_standardized_mode=max(map(abs,parameter['orbital_standardized']),default=None),
                 start_endpoint_difference_km=start_displacement[arm],
                 receiver_shared_guard=guard['status'],minimum_competitor_predictive_margin=guard['minimum_margin'],
                 original_unique_folds=len(set(tuple(p['held_blocks']) for p in screen['partitions'])),
                 additional_unique_folds=len(extra['parts']),
                 before_error_m=result['baseline'][arm]['error_m'],after_error_m=fit['error_m'],
                 ownership_audit_pass=not(extra['ownership'][arm]['lost_curved_ids'] or extra['ownership'][arm]['unexpected_owners']),
                 retrospective_status='not_evaluated_by_scope'))
        for n,provenance in extra['provenance'].items():
            tle.append(dict(case=case,norad=n,regime='causal',element_epoch_utc_ns=provenance['element_epoch_utc_ns'],
                            collected_utc_ns=provenance['collected_utc_ns'],
                            element_sha256=sha_lines(provenance['lines'])))
        for n in screen['nominees']:
            proposal=next((r for r in result['records']['combined'] if r['hypothesis']['norad']==n),None)
            paths=[]
            if n==old:
                paths=[SEALED/case/str(old)/'control_history.json']
                if not paths[0].exists():paths=[SEALED/case/str(old)/'control_original.json']
            elif proposal is not None:
                paths=[Path(proposal['fits_path'])]
            rows=[r for path in paths if path.exists() for r in read(path)]
            if not rows:
                candidates.append(dict(case=case,norad=n,status='not_joint_fitted',reason='not an eligible predictive proposal',objective=None))
            for r in rows:
                candidates.append(dict(case=case,norad=n,arm=r['arm'],start=r['start'],status=r['status'],qualified=r['qualified'],
                     objective=r.get('objective'),phase_closed=r.get('phase_closed'),optimizer_success=r.get('optimizer_success'),
                     minimum_failed_gate_slack=min(r.get('failed_gates',{}).values(),default=None),
                     failed_gates=str(r.get('failed_gates',{})),path=str(paths[0])))
        for t in diag['native']:
            for label in ('before','after'):
                native.append(dict(case=case,arm=t['arm'],component=t['component'],context=label,**t[label]))
        for t in diag['transfer']:
            transfers.append(dict(case=case,kind='receiver',**{k:v for k,v in t.items() if k not in ('residual_hz','predictive_sigma_hz')}))
        track=read(SEALED/case/'whole_track_transfer.json')
        for t in track['rows']:
            if t['method']=='combined':
                transfers.append(dict(case=case,kind='whole_track',**{k:v for k,v in t.items() if k not in ('residual_hz','predictive_sigma_hz')}))
        for setting,marker in [('margin_001','o'),('margin_005','s'),('receiver50','^')]:
            rows=[r for r in diag['sensitivity'] if r['method']==setting]
            for r in rows:
                ax2.scatter(r['minimum_slack'],r['displacement_km'],marker=marker,s=70,
                            color='#1f77b4' if r['arm']=='c0' else '#ff7f0e',
                            facecolors='none' if not r['qualified'] else None)
        ax2.axvline(0,color='k',lw=.8)
        ax2.set_title(case)
        ax2.set_xlabel('Minimum unchanged normalized gate slack')
        ax2.set_ylabel('Displacement from accepted endpoint (km)')
        ax2.text(.02,.97,'○ +.01 gate; □ +.05 gate; △ receiver50\nblue c0; orange fitted c; hollow fails',
                 transform=ax2.transAxes,va='top',fontsize=8)
        # Preserve native target CFO, fitted radio-adjusted prediction and
        # residuals; every scatter is one original observation.
        target=[t for t in record['pair']['fitted_c']['tracks'] if t['norad']==new]
        nf,nax=plt.subplots(len(target),2,figsize=(12,max(3,1.8*len(target))),squeeze=False,constrained_layout=True)
        for aa,t in zip(nax,target):
            times=np.asarray(t['times_s']);values=np.asarray(t['values_hz']);res=np.asarray(t['residual_hz'])
            aa[0].scatter(times,values/1000,s=8,label='native on selected alias branch')
            aa[0].plot(times,(values-res)/1000,color='tab:orange',label='joint radio-adjusted prediction')
            aa[1].scatter(times,res,s=8)
            aa[1].axhline(0,color='k',lw=.5)
            aa[1].axhspan(-150,150,color='gray',alpha=.1,label='±150 Hz diagnostic scale')
            aa[0].set_ylabel(f'RX{t["receiver"]} CH{t["channel"]}\nCFO (kHz)')
            aa[1].set_ylabel('Residual (Hz)')
            for aaa in aa:aaa.set_xlabel('Scan time (s)')
        nax[0,0].legend(fontsize=7)
        nf.suptitle(f'{case}: causal {old} → {new}; fitted c; saved accepted native evidence')
        nf.savefig(figdir/(case+'-native.png'),dpi=140)
        plt.close(nf)
    fig.suptitle('Receiver-shared offsets: accepted replacement must beat all finalists on every unique fold')
    fig.savefig(figdir/'predictive_competitors.png',dpi=160)
    fig2.suptitle('Saved full-scan nuisance/gate sensitivity; no acceptance decisions changed')
    fig2.savefig(figdir/'gate_sensitivity.png',dpi=160)
    plt.close('all')
    write(OUT/'uniqueness_guards.json',guards)
    csv_write('association_summary.csv',summary)
    csv_write('candidate_fits.csv',candidates)
    csv_write('predictive_comparison.csv',predictive)
    csv_write('tle_inventory.csv',tle)
    csv_write('reused_transfer.csv',transfers)
    csv_write('reused_sensitivity.csv',sensitivity)
    csv_write('reused_native_residual_stats.csv',native)
    write(OUT/'run_manifest.json',dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
          generated_utc_ns=time.time_ns(),sealed_source_checks=source_checks,sealed_selected_raw_checks=raw_checks,
          added_code_sha256={p.name:sha(p) for p in OUT.glob('*.py')},
          original_manifest_sha256=sha(SEALED/'manifest.json'),cases=list(CASES),
          additional_compute_seconds={c:read(OUT/c/'additional_checks.json')['seconds'] for c in CASES},
          seed=20261111,noise_hz=150.,constant_sigma_hz=300.,shared_rate_sigma_hz_s=.5,
          phase_grid_s=[-30,30,.4],phase_sd_s=[5,15],region_policy='cavity RF point plus ±5 km corners clipped to configured ±12.5 km box; frozen radio; not joint refit',
          models=['per-track constants + shared rate (legacy diagnostic)','receiver-shared constants + shared rate','frozen radio + shared rate'],
          causality='only sealed scan-causal complete 72h catalogue finalists; no later TLE or GPS in additional fits',
          guard='at least5 unique synchronized held-block assignments; both c arms; min over all finalist/fold score margins strictly >0; no calibrated probability',
          missing='fresh cold regional discovery, exact fitting every causal catalogue member, independent orbit attribution, and untouched-scan validation not run',
          command='PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=src:tools /srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python validate_replacements.py CASE; summarize_validation.py'))
    print({c:{k:v['status'] for k,v in g.items()} for c,g in guards.items()})


def sha_lines(lines):
    import hashlib
    return hashlib.sha256('\n'.join(lines).encode()).hexdigest()


if __name__=='__main__':run()
