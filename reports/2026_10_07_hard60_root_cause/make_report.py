"""Summarize the completed diagnostic probes, without changing cohort results."""
import csv
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import diagnose as d

STAGES = {
 ('N29','sigma2_60'): 'Final calibrated likelihood / association preference; adequate grid coverage.',
 ('N05','gaussian60'): 'Final candidate ranking across regional calibrations; adequate grid coverage.',
 ('N49','gaussian60'): 'Grid coverage plus final convergence rejection of a better-scoring nearby feasible state.',
 ('N39','smooth60'): 'Calibration convergence rejection discards both reference-covering regions.',
 ('N64','smooth60'): 'Coarse local minima and grid pruning; restoring a covering region is sufficient in this diagnostic.',
 ('N49','hard30'): 'Coarse/grid pruning plus calibration failures; restoring a covering region is sufficient in this diagnostic.',
 ('N64','gaussian30'): 'Coarse/grid pruning plus downstream calibration/association/ranking; one restored coarse region is insufficient.',
 ('N25','smooth30'): 'Coarse/grid pruning plus downstream ranking; a restored 1.02 km fitted-c candidate still loses by score.',
}


def save(fig,name):
    for suffix in ('png','svg'):fig.savefig(d.HERE/f'{name}.{suffix}',dpi=170)
    plt.close(fig)


def plots(paths,coarse):
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,path,arm in zip(axes,paths[:2],d.ARMS):
        rows=[r for r in path['outputs'] if r['arm']==arm and r['step']!='release']
        ax.plot([r['error_km'] for r in rows],[r['score_delta'] for r in rows],'-o',color='#1876a3',ms=4)
        failed=[r for r in rows if not r['converged']]
        ax.scatter([r['error_km'] for r in failed],[r['score_delta'] for r in failed],marker='x',color='#bd1622',s=65,label='Stationarity check failed')
        first,last=rows[0],rows[-1]
        ax.scatter([0],[last['score_delta']],marker='*',color='#bd1622',s=150,label='Reference location')
        ax.axhline(0,color='#888',ls=':',lw=1)
        ax.set(title=f'N29: {arm}',xlabel='Position error along the path (km)',ylabel='Score increase from saved winner (lower is better)')
        ax.text(.98,.94,f"At reference:\nData NLL +{last['data_nll']-first['data_nll']:.1f}\nTiming prior {last['timing_penalty']-first['timing_penalty']:+.2f}",
                transform=ax.transAxes,ha='right',va='top',bbox=dict(facecolor='white',edgecolor='#ddd'))
        ax.grid(alpha=.2);ax.legend(loc='lower left',fontsize=8)
    fig.suptitle('Hard 60’s worst scan: the current likelihood favors a displaced position\n'
                 'Local continuation profiles with nuisance refits every ≤0.5 km; not global-minimum certificates',fontsize=12)
    save(fig,'n29_likelihood_profile')
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    names={'sigma2_60':'Hard 60','smooth60':'Smooth 60','gaussian30':'Gaussian 30','hard30':'Hard 30','gaussian60':'Gaussian 60'}
    colors={'sigma2_60':'#1876a3','smooth60':'#238b57','gaussian30':'#9d4320'}
    for r in coarse:
        if r['label']=='N64':
            axes[0].plot([max(abs(b) for b in v['slopes_hz_s']) for v in r['trace']],
                         color=colors[r['phase']],label=names[r['phase']],lw=1.2)
    axes[0].axhline(30,color='#777',ls=':',lw=1)
    axes[0].set(title='Same N64 grid point and bootstrap seed',xlabel='Objective evaluation',ylabel='Larger absolute temporary slope (Hz/s)')
    axes[0].legend(fontsize=8);axes[0].grid(alpha=.15)
    rows=[r for r in coarse if r['phase']!='sigma2_60']
    vals=[r['target_fit_excess_over_hard60_state'] for r in rows]
    axes[1].barh(range(len(rows)),vals,color='#d86c29')
    axes[1].set_yticks(range(len(rows)),[r['label']+' / '+names[r['phase']] for r in rows]);axes[1].invert_yaxis()
    for i,v in enumerate(vals):axes[1].text(v+25,i,f'{v:.1f}',va='center',fontsize=9)
    axes[1].set_xlim(0,max(vals)*1.2)
    axes[1].set(title='A better feasible coarse fit already exists',xlabel='Excess score over Hard 60 state under the same target model')
    axes[1].grid(axis='x',alpha=.15)
    fig.suptitle('Temporary clock excursions change which local minimum the coarse fit reaches\n'
                 'The comparison on the right keeps position, observations, satellite bank and target objective fixed',fontsize=12)
    save(fig,'coarse_local_minima')


def main():
    saved=d.read(d.HERE/'saved_audit.json');probes=d.read(d.HERE/'probes.json')
    paths=d.read(d.HERE/'profile_paths.json')['outputs']
    coarse=d.read(d.HERE/'coarse_replay.json')['outputs']
    baselines=d.read(d.HERE/'baseline_scale.json')['outputs']
    assert probes['completed']==probes['requested']==17
    assert len(paths)==3 and len(coarse)==6 and len(baselines)==6
    assert not any('traceback' in r for r in probes['outputs'])
    assert d.run.data.digest(d.HERE/'diagnose.py')==d.read(d.HERE/'protocol.json')['source_code']
    for r in coarse:
        np.testing.assert_allclose(r['replay']['objective'],r['original_score'],atol=1e-6,rtol=0)
    rows=[]
    for case in saved['cases']:
        label,phase=case['label'],case['phase']
        for arm in d.ARMS:
            original=case['selections'][arm]
            r=dict(label=label,phase=phase,arm=arm,original_error_km=original['error_km'],
                original_score=original['selection_score'],failure_stage=STAGES[label,phase],
                reference_in_retained_region=any(g['covers_reference'] for g in case['regions']),
                reference_in_successful_region=any(g['covers_reference'] and g['status']=='complete' for g in case['regions']),
                nearest_grid_point_km=case['nearest_grid_point_km'],grid_points_within25km=case['points_within25'],
                covering_point_rank=case['best_reference_covering_point']['rank'])
            for mode in ['grid_rescue','calibration_retry']:
                candidates=[p['winners'][arm] for p in probes['outputs'] if p['kind']=='pipeline'
                    and p['label']==label and p['phase']==phase and p['mode']==mode and p['winners'][arm]]
                best=min(candidates,key=lambda v:v['selection_score'],default=None)
                r[mode+'_error_km']=best['error_km'] if best else None
                r[mode+'_score_change']=best['selection_score']-original['selection_score'] if best else None
                r[mode+'_would_replace_original']=best['selection_score']<original['selection_score'] if best else None
            rows.append(r)
    with (d.HERE/'failure_stages.csv').open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    plots(paths,coarse)
    lines=['Worst-case stage diagnosis for Hard 60 and five alternatives','',
        'This is a diagnostic study of eight scan/configuration cases covering both c arms, not a new N64 benchmark.',
        'Original inputs, searches, calibration records and selected results remain unchanged.',
        'Truth is used only for evaluation, fixed-position likelihood profiles, and choosing an existing reference-covering grid point for a causal rescue test.',
        'A geographically improved rescue is not a real pipeline improvement unless its model score beats the old winner. The CSV records both.',
        'Final-stage c=0/fitted-c use matched observations, banks, baselines and budgets. Calibration remains fitted-c. No new RF collection.', '',
        'Why Hard 60 is robust on this cohort:',
        'Hard 60 has no interior slope penalty. It imposes a box bound on each stage-specific affine slope; it is not a physical cap on the full receiver drift.',
        'All six primary configurations have timing sigma 2 s and the same corrected 40/20/10/5 km hierarchy and 400-point budget.',
        'Hard 60 hits a coarse bound in 141/25,600 attempts (0.55%); Hard 30 in 1,635/25,600 (6.39%). Smooth 60 adds a nonzero coarse penalty in 6,535/25,600 attempts (25.53%); Gaussian acts in virtually every successful coarse fit.',
        'Hard 60 retained a region covering the reference in 64/64 scans. Hard30, Gaussian60, Smooth60 and Smooth30 cover 63/64; Gaussian30 covers 62/64.',
        'These are empirical observations on the same development cohort, not proof that +/-60 is a universally optimal physical prior.',
        'The historical before/after comparison also changed timing sigma and grid policy, so its benefit cannot be attributed to the slope cap alone.', '',
        'Same-point coarse replay:',
        'At N64 (-80,-80), all methods have the identical geometric bootstrap; initial slopes are 13.064 and -6.203 Hz/s.',
        'Hard60 and Smooth60 temporarily reach 60 Hz/s. Smooth60 incurs its penalty at eight evaluations and finishes with small slopes at a worse local minimum.',
        'The saved Hard60 state is feasible under the alternative objectives and beats Smooth60 by 67.05 score units and Gaussian30 by 822.57 at that SAME point.',
        'At N49 (-80,-80), Hard60 also provides feasible lower scores than Hard30 (1,797.95 units) and Gaussian60 (1,947.87 units) under each target model.',
        'All six instrumented coarse replays reproduced their saved scores to 1e-6. This directly demonstrates optimizer-path/local-minimum effects, not merely an intended prior preference.', '']
    for c in saved['cases']:
        label,phase=c['label'],c['phase'];lines.append(f'{label} / {phase}: {STAGES[label,phase]}')
        lines.append('  Errors zero-c / fitted-c: '+ ' / '.join(f"{c['selections'][a]['error_km']:.3f} km" for a in d.ARMS))
        lines.append(f"  Nearest evaluated point {c['nearest_grid_point_km']:.3f} km; {c['points_within25']} grid points within 25 km; best covering point rank {c['best_reference_covering_point']['rank']}.")
        for row in [r for r in rows if r['label']==label and r['phase']==phase]:
            for mode in ['grid_rescue','calibration_retry']:
                if row[mode+'_error_km'] is not None:
                    lines.append(f"  {row['arm']} {mode}: {row[mode+'_error_km']:.3f} km, score change {row[mode+'_score_change']:+.3f}; would replace old winner: {row[mode+'_would_replace_original']}.")
    lines.extend(['',
        'N29: the final calibrated data likelihood, not the timing penalty, explains the observed displacement on the explored branch.',
        'The fitted-c reference endpoint raises data NLL by 543.201 and lowers the timing penalty by 1.849, for total +541.352. The zero-c counterpart is +668.696 data and -1.121 timing, total +667.575.',
        'Small-step nuisance profiling reaches the reference and then returns near 5.4--5.6 km when position is released. This is evidence of model/association/calibration preference, not a global-minimum certificate.',
        'The 11.4596875 GHz RF group contributes +341.633 fitted-c NLL units against the reference; the 10.959687498 GHz group contributes -56.570 in favor of it. Both receivers contribute to the total disagreement.',
        'Halving or removing the frozen piecewise receiver correction did not eliminate the approximately 5 km bias. This rules out that simple explanation; independent RF calibration or association evidence is still needed to identify the physical cause.',
        'N05 zero-c: the accepted 3.772 km candidate loses to 14.672 km by only 16.54 score units. Grid coverage is adequate; across-region ranking is the relevant failure.',
        'N49 Gaussian60: a feasible 4.760 km boundary candidate scores about 2,835 units better than the selected 48.039 km state, but fails the unchanged 0.001 stationarity threshold. Extra continuation and inspection of SLSQP terminal states do not certify it.',
        'SLSQP reports success for the rejected N39/N49 calibration states; independent stationarity residuals range from approximately 0.00104 to 1.014. These were not deadline failures. Terminal-state inspection does not resolve them by simply returning the last state.',
        'The reset-timing calibration recovery preserves the existing convergence threshold; it can choose a higher-scoring calibration local minimum that subsequently yields a much better full association/position fit.', '',
        'Three proposed Hard60 variants (not evaluated on all 64 in this report):',
        '1. Coarse multi-start: retain Hard60, sigma 2 s, the grid and point budget. At each coarse location compare the current bootstrap with one deterministic reset of nuisance timing/slopes. Choose by model score. This tests whether better coarse local minima improve discovery/association quality. Report its extra fit cost.',
        '2. Calibration recovery: when a coarse candidate fails prefit/postfit stationarity, try one continuation, then one zero-timing restart, while keeping the same caps and acceptance checks. N39 provides a direct diagnostic example; apply uniformly, without truth-based retries.',
        '3. Small RF residual correction: retain the Hard60 search; during final fitting add strongly regularized receiver-by-RF residual frequency offsets (initial prior SD 50 Hz, outer bound 150 Hz). Remove directions duplicated by receiver offsets and the existing linear RF coefficient c. This targets the observed RF disagreement; it is a hypothesis, not a demonstrated fix.',
        'For variant 3, test first on the bad cases with blocked validation over time/RF, then all N01--N64. Extra RF freedom can absorb geometric information; require geographic median, p90 and worst-case improvement, not only lower training NLL.',
        'For all variants retain both final c arms with matched observations/banks/priors/budgets within each variant, and compare runtime, coverage and calibration failures as well as position and frequency fit.', '',
        'Validation: 17 stage-probe jobs, 3 paired local-continuation profiles, 6 matched clock-baseline scale groups, 6 exact coarse replays, 4 finite-difference calibration inspections and 5 SLSQP terminal-state inspections.',
        'Nonconverged diagnostic fits are retained and marked, including some profile points. They are never silently accepted as repaired localization results.',
        'Reproduction: use the deployed numerical interpreter /opt/leo-tracker/current-api/.venv/bin/python with PYTHONPATH=/opt/leo-regional-position/5600cd81e5f2-r2/worker/src and single-threaded BLAS.',
        'Run diagnose.py, profile_paths.py, inspect_scores.py, terminal_audit.py, baseline_scale.py, coarse_replay.py, make_report.py in this folder. Existing raw engine caches may be reused on repeats; the first run is preserved here.'
    ])
    (d.HERE/'findings.txt').write_text('\n'.join(lines)+'\n')
    old_manifest=d.read(d.SOFT/'artifact_manifest.json')
    for name,expected in old_manifest['files'].items():assert d.run.data.digest(d.SOFT/name)==expected,name
    files=[p for p in d.HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts
           and p.name!='artifact_manifest.json' and p.suffix in ('.py','.json','.csv','.txt','.png','.svg','.log')]
    d.engine.write(d.HERE/'artifact_manifest.json',dict(original_study_manifest=d.run.data.digest(d.SOFT/'artifact_manifest.json'),
        files={str(p.relative_to(d.HERE)):d.run.data.digest(p) for p in sorted(files)}))
    print('PASS: all diagnostic outputs present; six exact coarse replays; original study unchanged;',len(files),'artifacts hashed.')


if __name__=='__main__':main()
