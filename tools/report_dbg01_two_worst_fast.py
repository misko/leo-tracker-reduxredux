"""Report the frozen two-worst-fast DBG01 runs, without selecting repairs by GPS."""

import argparse
import copy
import csv
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np

from run_dbg01_case import DEFAULT, configure
import debug_algo02_ds23_0268 as engine
from dbg01_unassociated import ownership
from dbg01_unassociated import candidate_gates
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.retained_track_likelihood import profile, whitening, PERIOD
from report_algo02_ds23 import position_error
from investigate_ds23_0268_remaining_tracks import family_frequency
from run_algo01_ds23_sample import ROOT, read, write, sha

REPORT=ROOT/'reports/2026_10_21_dbg01_two_worst_fast'
CASES=('DS23-0268','DS23-0405')


def csv_write(path,rows):
    with path.open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def family_coverage(job):
    case,root,index=job;out=configure(case,root)
    result=read(out/f'family_{index:02d}.json');scan,node,keep,base,old=engine.context()
    target=result['target'];keep=keep.copy()
    for row,sl in zip(base.rows,base.slices,strict=True):
        if row['candidate_norad']==target:keep[sl]=False
    entries=[e for e in copy.deepcopy(engine.entries_for(old)) if e['norad']!=target]
    tracks={t['key']:t for t in scan.tracks}
    total=len(read(engine.SOURCE/case/'observations.json'));rows=[]
    for arm,saved in result['arms'].items():
        p=engine.build(node,keep,arm,np.array(saved['phase_reference']),entries)
        x=np.array(saved['endpoint_east_north_km'])
        if abs(p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo'])>1e-4:
            raise ValueError('ablation endpoint failed independent replay')
        extended=engine.extend_associations(p,x,saved['gates'])
        compatible=[dict(r,observation_ids=r.get('observation_ids',tracks[r['component']]['observation_ids']))
            for r in extended['tracks'] if r['norad']!=target]
        ids=ownership(compatible)
        rows.append(dict(case=case,arm=arm,excluded_norad=target,position_error_km=position_error(saved['endpoint_latlon']),
            endpoint_east_km=x[0],endpoint_north_km=x[1],frequency_RMS_hz=saved['RMS_hz'],
            associated_original_points=len(ids),all_original_GLRT=total,associated_original_percent=100*len(ids)/total,
            removed_curved_points=result['deleted_curved_points'],removed_predictive_points=result['deleted_predictive_points'],
            remaining_position_curved_points=saved['active_points'],
            remaining_position_predictive_points=saved.get('predictive_points',0),
            paired_gates_valid=result['paired_gates_valid'],
            final_phase_change_s=saved['final_phase_change_s'],
            excluded_family_not_allowed_to_reenter=True))
    return rows


def coverage(root):
    jobs=[(case,root,i) for case in CASES for i in range(len(read(Path(root)/case/'interventions.json')['family']))]
    with ProcessPoolExecutor(max_workers=12) as pool:
        rows=[r for pair in pool.map(family_coverage,jobs) for r in pair]
    REPORT.mkdir(parents=True,exist_ok=True)
    csv_write(REPORT/'family_ablations.csv',rows)
    write(REPORT/'family_coverage_replay.json',dict(rows=rows,
        original_endpoints_and_gates_independently_replayed=True,
        no_GPS_selected_family_exclusion=True))


def comparison():
    all_rows=read(ROOT/'reports/2026_10_20_ds23_combined_recovery_full/evaluation.json')['all_rows']
    rows=[]
    for case in CASES:
        for r in all_rows:
            if r['case']==case:
                rows.append(dict(case=case,method=r['method'],arm=r['arm'],
                    position_error_km=r['position_error_km_report_only'],associated_percent=r['associated_original_percent'],
                    points=r['associated_original_points'],tracks=r['associated_tracks'],RMS_hz=r['frequency_RMS_hz'],
                    scope='dataset-wide policy',status=r.get('recovery_pipeline_status') or 'complete'))
        for label,folder,key in [('skew_phase','2026_10_20_ds23_skew_phase_full/position','skew_policy_arms'),
                ('multi_family_position','2026_10_20_ds23_multifamily_proposals_v2','policy_arms')]:
            d=read(ROOT/'reports'/folder/(case+'.json'))
            baseline=next(r for r in rows if r['case']==case and r['method']=='original_ALGO02' and r['arm']=='c0')
            for arm,r in d[key].items():
                rows.append(dict(case=case,method=label,arm=arm,position_error_km=position_error(r['endpoint_latlon']),
                    associated_percent=None,points=None,tracks=None,RMS_hz=r['RMS_hz'],
                    scope='position prototype; coverage not remeasured',
                    status=('accepted' if d.get('accepted',d.get('qualified')) else 'incumbent fallback')))
    source=ROOT/'reports/2026_10_20_ds23_0268_identity_resolution/identity_comparison.csv'
    for r in csv.DictReader(source.open()):
        if r['hypothesis'] not in ['split','split_CH2']:continue
        rows.append(dict(case='DS23-0268',method='targeted_'+r['hypothesis'],arm=r['arm'],
            position_error_km=float(r['position_error_km']),associated_percent=float(r['associated_percent']),
            points=int(r['associated_points']),tracks=int(r['tracks']),RMS_hz=None,
            scope='single-scan development; not generalized',status='original paired gates pass'))
    csv_write(REPORT/'method_comparison.csv',rows)
    methods=['original_ALGO02','signed_prior','skew_phase','multi_family_position','combined_recovery','targeted_split','targeted_split_CH2']
    names=['ALGO02','Signed phase prior','Skew phase prior','Multi-family position proposal','Combined recovery','Targeted RX identity split','Targeted split + CH2 recovery']
    fig,axes=plt.subplots(1,2,figsize=(13,5.8),layout='constrained',sharex=True,sharey=True)
    for ax,case in zip(axes,CASES,strict=True):
        for j,m in enumerate(methods):
            records=[r for r in rows if r['case']==case and r['method']==m]
            if not records:
                ax.text(.1,j,'not run',color='.5',va='center');continue
            for arm,offset,color,marker in [('c0',-.13,'tab:blue','o'),('fitted_c',.13,'tab:orange','s')]:
                r=next(r for r in records if r['arm']==arm)
                ax.scatter(r['position_error_km'],j+offset,edgecolors=color,marker=marker,s=44,
                    facecolors='none' if m.startswith('targeted') else color)
                ax.text(r['position_error_km']+.07,j+offset,f"{r['position_error_km']:.3f}",fontsize=8,va='center')
        ax.set(title=case,xlabel='Position error (km)',xlim=(0,6.9))
        ax.axvline(.5,color='seagreen',ls='--',lw=1);ax.grid(axis='x',alpha=.2)
    axes[0].set_yticks(range(len(methods)),names,fontsize=9);axes[0].invert_yaxis()
    axes[0].plot([],[],color='tab:blue',marker='o',ls='',label='c = 0')
    axes[0].plot([],[],color='tab:orange',marker='s',ls='',label='fitted c');axes[0].legend(loc='lower right')
    fig.suptitle('Worst two fast ALGO02 scans · existing newer approaches\nHollow points: targeted 0268 development; not a dataset-wide policy')
    fig.savefig(REPORT/'method_comparison.png',dpi=170);plt.close(fig)
    return rows


def candidate_plots(case,root):
    out=Path(root)/case
    inventory=read(out/'unassociated_inventory.json')['arms']
    raw={o['observation_id']:o for o in read(engine.SOURCE/case/'observations.json')}
    report_rows=[]
    curves={c['component']:c for c in inventory['fitted_c']}
    documents={k:read(out/f'unassociated_{k}_fitted_c.json') for k in ['causal','following']}
    by_kind={k:{r['component']:r for r in d['rows']} for k,d in documents.items()}
    ranked=sorted([c for c in curves.values() if c['kind']=='unassociated_graph_subset'],
        key=lambda c:float(np.ptp(c['times'])),reverse=True)
    with PdfPages(REPORT/f'{case}_unassociated_orbits.pdf') as pdf:
        for rank,c in enumerate(ranked):
            fig,axes=plt.subplots(2,1,figsize=(12,6),layout='constrained',sharex=True)
            times=np.array(c['times']);native=np.array([raw[o]['measured_cfo_hz'] for o in c['observation_ids']])
            axes[0].scatter(times,native/1000,c='crimson',s=15,label='Unassociated original GLRT')
            for kind,color in [('causal','tab:blue'),('following','tab:orange')]:
                row=by_kind[kind].get(c['component'])
                candidate=(row.get('best_passing') or (row['candidates'][0] if row['candidates'] else None)) if row else None
                if candidate is None:continue
                residual=np.array(candidate['residual_hz'])
                prediction=native-residual
                segments=np.split(np.arange(len(times)),np.flatnonzero(abs(np.diff(prediction))>PERIOD/2)+1)
                for segment_index,segment in enumerate(segments):
                    axes[0].plot(times[segment],prediction[segment]/1000,color=color,lw=1.5,
                        label=f"{kind}: {candidate['norad']}, phase {candidate['phase_s']:+.2f}s" if segment_index==0 else None)
                axes[1].plot(times,residual,'.-',color=color,ms=3,
                    label=f"{kind}: RMS {candidate['rms_hz']:.1f} Hz; {'passes' if candidate['passing'] else 'fails'}")
                report_rows.append(dict(case=case,component=c['component'],kind=kind,points=len(times),
                    start_s=float(times[0]),end_s=float(times[-1]),norad=candidate['norad'],
                    phase_s=candidate['phase_s'],rms_hz=candidate['rms_hz'],bias_hz=candidate['bias_hz'],
                    passing=candidate['passing'],passing_alternatives=len(row['passing_norads']),
                    minimum_elevation_deg=candidate['minimum_elevation_deg'],
                    slope_z=candidate['noise']['slope_z'],mean_z=candidate['noise']['mean_z'],
                    quadratic_bic_gain=candidate['noise']['quadratic_bic_gain'],
                    step_z=candidate['noise']['maximum_step_z'],lag1_acf=candidate['noise']['lag1_acf'],
                    real_following_element=candidate['real_following_element']))
            axes[1].axhline(0,color='black',lw=.8)
            for ax in axes:
                ax.grid(alpha=.2)
                if ax.get_legend_handles_labels()[0]:ax.legend(fontsize=8)
            if not axes[1].get_legend_handles_labels()[0]:
                axes[1].text(.05,.5,'Insufficient distinct-time support for a satellite screen',transform=axes[1].transAxes)
            axes[0].set(ylabel='Native CFO (kHz)');axes[1].set(xlabel='Device time (s)',ylabel='Residual (Hz)')
            fig.suptitle(c['component']+'\nFrozen fitted-c RF endpoint/hardware; independent phase/alias/constant; lines broken at native alias wraps')
            pdf.savefig(fig)
            if rank<3:fig.savefig(REPORT/f'{case}_unassociated_{rank+1:02d}.png',dpi=155)
            plt.close(fig)
    return report_rows


def replay_candidates(root):
    checks=[]
    for case in CASES:
        out=configure(case,root);scan=engine.context()[0]
        inventory=read(out/'unassociated_inventory.json')['arms']
        endpoint=read(engine.SOURCE/case/'algo02_result.json')['policy_arms']
        for kind in ['causal','following']:
            bank=scan.sky if kind=='causal' else dict(np.load(out/'following_bank.npz'))
            for arm in engine.ARMS:
                curves={c['component']:c for c in inventory[arm]}
                document=read(out/f'unassociated_{kind}_{arm}.json')
                for row in document['rows']:
                    c=curves[row['component']];times=np.array(c['times'])
                    for candidate in row['candidates']+([row['best_passing']] if row['best_passing'] else []):
                        j=int(np.flatnonzero(scan.norads==candidate['norad'])[0])
                        sub=dict(time_s=bank['time_s'],position_km=bank['position_km'][[j]],velocity_km_s=bank['velocity_km_s'][[j]])
                        f,e=phase_frequency_grid(sub,times,*endpoint[arm]['endpoint_latlon'],
                            phase_seconds=candidate['phase_s'],rf_hz=c['rf_hz'])
                        terms=profile(c['values'],f,*whitening(times),bias_sigma=300)
                        passed,noise=candidate_gates(terms,e,times)
                        delta=float(np.max(abs(terms['residual'][0]-candidate['residual_hz'])))
                        if delta>1e-5 or abs(terms['cost'][0]-candidate['cost'])>1e-5 or bool(passed[0])!=candidate['passing']:
                            raise ValueError('independent orbit/CFO/gate replay failed')
                        checks.append(dict(case=case,arm=arm,kind=kind,component=c['component'],norad=candidate['norad'],maximum_residual_difference_hz=delta))
    write(REPORT/'candidate_replay.json',dict(checks=checks,all_saved_candidate_residuals_and_gates_replayed=True,
        direct_range_rate_geometry_used_instead_of_phase_tangent_function=True,
        reference_position_not_used=True))


def shared_family_check(case,root):
    out=configure(case,root);scan,node,keep,base,old=engine.context();arm='fitted_c'
    saved=old['policy_arms'][arm];x=np.asarray(saved['endpoint_east_north_km'])
    p=engine.build(node,keep,arm,np.asarray(saved['phase_reference']),engine.entries_for(old));state=p.state(x)
    document=read(out/'unassociated_causal_fitted_c.json')
    inventory={c['component']:c for c in read(out/'unassociated_inventory.json')['arms'][arm]}
    rows=[]
    for rank,row in enumerate(sorted([r for r in document['rows'] if r['kind']=='unassociated_graph_subset'],
            key=lambda r:r['end_s']-r['start_s'],reverse=True)[:6]):
        best=row['best_passing'] or row['candidates'][0];c=inventory[row['component']]
        j=int(np.flatnonzero(scan.norads==best['norad'])[0]);times=np.array(c['times'])
        ix=np.searchsorted(scan.times,times);q=c['rf_hz']/11.5e9
        f,_=family_frequency(p,x,j)
        terms=profile(c['values'],q*f[ix],*whitening(times),bias_sigma=300)
        sub=dict(time_s=scan.sky['time_s'],position_km=scan.sky['position_km'][[j]],velocity_km_s=scan.sky['velocity_km_s'][[j]])
        nominal,_=phase_frequency_grid(sub,times,*saved['endpoint_latlon'],phase_seconds=state['phases'][j],rf_hz=c['rf_hz'])
        plain=profile(c['values'],nominal,*whitening(times),bias_sigma=300)
        active_family_points=sum(int(keep[sl].sum()) for row0,sl in zip(p.rows,p.slices,strict=True) if row0['candidate_index']==j)
        rows.append(dict(component=c['component'],norad=best['norad'],globally_supported=j in p.supported,
            active_curved_family_points=active_family_points,
            current_phase_is_prior_only=active_family_points==0,
            shared_phase_s=float(state['phases'][j]),independent_phase_s=best['phase_s'],
            shared_phase_and_orbit_RMS_hz=float(terms['rms'][0]),
            shared_phase_nominal_orbit_RMS_hz=float(plain['rms'][0]),independent_phase_nominal_orbit_RMS_hz=best['rms_hz']))
        if rank==0:
            fig,ax=plt.subplots(figsize=(11,4),layout='constrained')
            phase_label='Current forecast phase' if active_family_points==0 else 'Shared learned phase'
            for residual,label,color in [(terms['residual'][0],phase_label+' and fitted orbit modes','black'),
                    (plain['residual'][0],phase_label+', nominal orbit','tab:green'),
                    (best['residual_hz'],'Independent phase, nominal orbit','tab:blue')]:
                ax.plot(times,residual,'.-',ms=3,color=color,label=label)
            ax.axhline(0,color='.5',lw=.8);ax.grid(alpha=.2);ax.legend(fontsize=8)
            ax.set(title=c['component']+f" · candidate {best['norad']}\nFrozen RF position and receiver calibration; same unresolved points",
                xlabel='Device time (s)',ylabel='Residual after constant (Hz)')
            fig.savefig(REPORT/f'{case}_shared_family_residual.png',dpi=165);plt.close(fig)
    write(out/'shared_family_check.json',dict(rows=rows,reference_position_not_used=True,
        independent_phase_not_an_accepted_shared_family_association=True))
    return rows


def table(rows,columns):
    lines=['| '+' | '.join(title for key,title in columns)+' |','| '+' | '.join('---' for _ in columns)+' |']
    for r in rows:
        lines.append('| '+' | '.join(f'{r[k]:.3f}' if isinstance(r[k],float) else str(r[k]) for k,title in columns)+' |')
    return '\n'.join(lines)


def figures(root):
    REPORT.mkdir(parents=True,exist_ok=True)
    replay_candidates(root)
    comparisons=comparison();families=read(REPORT/'family_coverage_replay.json')['rows']
    fig,axes=plt.subplots(2,2,figsize=(13,11),layout='constrained')
    for col,case in enumerate(CASES):
        group=[r for r in families if r['case']==case and r['arm']=='fitted_c']
        for row,key in enumerate(['position_error_km','associated_original_percent']):
            ax=axes[row,col];yy=np.arange(len(group))
            for arm,offset,color in [('c0',-.13,'tab:blue'),('fitted_c',.13,'tab:orange')]:
                records=[next(r for r in families if r['case']==case and r['arm']==arm and
                    r['excluded_norad']==g['excluded_norad']) for g in group]
                ax.scatter([r[key] for r in records],yy+offset,color=color,s=18,label=arm)
                bad=[i for i,r in enumerate(records) if not r['paired_gates_valid']]
                ax.scatter([records[i][key] for i in bad],(yy+offset)[bad],marker='x',color='crimson',s=50)
            ax.set_yticks(yy,[str(r['excluded_norad']) for r in group],fontsize=8);ax.invert_yaxis()
            ax.set(title=case,xlabel='Position error (km)' if row==0 else 'Remaining original GLRT associated (%)')
            ax.grid(axis='x',alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Every satellite-family ablation · red × fails paired residual gates\nRemaining coverage excludes the removed family; these are influence diagnostics')
    fig.savefig(REPORT/'family_ablation_comparison.png',dpi=165);plt.close(fig)
    candidate_rows=[];text=['# DBG01: the two worst fast ALGO02 scans\n',
        'DS23-0268 and DS23-0405 rank first and second among available fast ALGO02 endpoints, using fitted-c error. '
        'This is retrospective diagnosis. The original estimator and its benchmark are unchanged.\n',
        '![Position comparison](method_comparison.png)\n',
        '![All satellite-family ablations and remaining association](family_ablation_comparison.png)\n',
        table([r for r in comparisons if r['arm']=='fitted_c'],[
            ('case','Scan'),('method','Method'),('position_error_km','Error km'),('associated_percent','Original GLRT %'),('status','Status')]),
        '\n0268 combined recovery exhausted its 900 s search budget; its retained endpoint passes but the search is incomplete. '
        '0405 combined recovery completed. Targeted 0268 repairs are single-scan development, not an automatically generalized method. '
        'The lowest-error 0268 split uses fewer points than the split plus CH2. Geographic error does not select identities. '
        'The multi-family position proposal is a family-subset-generated position proposal scored against original curved evidence; '
        'it is not an independently established new satellite-label assignment. Skew and multi-family coverage was not remeasured here.\n']
    text.append('The most recent opposite-receiver curve, reception-identity and RF/clock prototypes have not yielded '
        'a qualified position comparison on these two scans. Results from other development/confirmation cohorts are not '
        'substituted into this per-scan comparison.\n')
    for case in CASES:
        out=Path(root)/case;validation=read(out/'validation.json');audit=read(out/'audit.json')
        protocol=read(out/'unassociated_protocol.json');candidate_rows.extend(candidate_plots(case,root))
        shared=shared_family_check(case,root)
        text+=['\n## '+case+'\n',table(validation['coverage'],[
            ('arm','c arm'),('GLRT_points','All original GLRT'),('associated_points','Associated'),
            ('associated_percent','Associated %'),('associated_tracks','Tracks'),('unassociated_points','Unassociated'),
            ('graph_owned_unassociated','In graph'),('outside_graph','Outside graph')]),
            '\nAll native lanes, exact partial masks and original point identities are retained. Gray is context; red is unassociated.\n']
        for name,caption in [('associated_GLRT_fitted_c.png','Associated GLRT and polynomial tracks'),
                ('unassociated_GLRT_fitted_c.png','Unassociated GLRT and polynomial tracks'),
                ('track_residuals.png','Retained track residuals'),('loss_gradient_10km.png','Conditional loss and gradient'),
                ('convergence_10km.png','Regional starts and solver paths'),
                ('influence_and_controls.png','All family and individual-track ablations; generic controls'),
                ('loss_decomposition.png','Reference versus endpoint loss decomposition')]:
            text.append(f'\n![{caption}]({out/name})\n')
        text.append('The upper loss views sample 317 locations at 1 km spacing in a 10 km regional disk; '
            'lower views sample 289 points at 0.25 km spacing over ±2 km around evaluation truth. '
            'Pixels refit nuisance means, robust precision and five phase refreshes with fixed observations/labels/aliases. '
            'They do not rerun acquisition or association. The 81 restart paths can switch curved nominations/aliases among '
            'a finite cold-discovered pool after accepted c0 steps; predictive labels remain fixed. Fitted c follows the same branch schedule.\n')
        text.append('Restart summary: `'+str(validation['restarts'])+'`.\n')
        if validation['restarts']['fitted_c']['paired_valid_starts']==0:
            text.append('**All 81 reassociating restart endpoints fail the unchanged paired residual gates.** '
                'They are diagnostic solver endpoints, not accepted positions. The saved ALGO02 incumbent remains the benchmark. '
                'For this scan the selected branches relabel RX1 CH3 T002 from 66150 to 63380; '
                'that curve then fails slope, curvature, step and autocorrelation screens despite RMS below 450 Hz. '
                'The agreement of endpoints therefore does not certify the replacement identity.\n')
        gaps={a:audit['arms'][a]['diagnostic_point']['negative_twice_elbo']-
            audit['arms'][a]['endpoint']['negative_twice_elbo'] for a in engine.ARMS}
        text.append(f"The fixed reference site has a worse normalized loss by {gaps['c0']:.3f} / {gaps['fitted_c']:.3f} "
            'in c0 / fitted-c after refreshing phases and nuisances. This is evidence of a conditional model preference; '
            'it does not prove the transmitter identities or isolate a hardware defect.\n')
        fr=[r for r in families if r['case']==case and r['arm']=='fitted_c']
        valid=[r for r in fr if r['paired_gates_valid'] and r['final_phase_change_s']<=.01]
        best=min(valid,key=lambda r:r['position_error_km']) if valid else None
        if best:
            text.append(f"Among gate-passing, phase-converged deletion diagnostics, the smallest fitted-c error is "
                f"{best['position_error_km']:.3f} km after removing {best['excluded_norad']}. "
                'No satellite is removed automatically based on this reference-error ranking.\n')
        text+=['\n### Satellite-family ablation\n',table(fr,[('excluded_norad','Removed family'),
            ('position_error_km','Error km'),('frequency_RMS_hz','RMS Hz'),('associated_original_percent','Remaining GLRT %'),
            ('removed_curved_points','Curved removed'),('removed_predictive_points','Predictive removed'),('paired_gates_valid','Both gates pass')]),
            '\nEach deletion removes that family from curved calibration and predictive evidence; the original nuisance design stays fixed. '
            'Remaining association is reconstructed at the ablated endpoint and the deleted family cannot reenter. '
            'Raw objectives with different masks are not ranked. A lower geographic error is an influence diagnostic, not a deletion rule.\n',
            '\n### Unassociated evidence and following-TLE diagnostics\n',
            f"The exact inventory has {protocol['counts']['fitted_c']['graph_unassociated']} graph-owned and "
            f"{protocol['counts']['fitted_c']['outside_graph']} outside-graph unresolved points. "
            f"Both catalogue screens test {protocol['catalogue_candidates']} candidate identities over ±15 s in 0.25 s steps. "
            f"Following elements are unavailable for {len(protocol['post_missing'])} candidates; those causal fallbacks are labeled.\n",
            'The RF-estimated position, receiver/band drift, offsets and smooth coefficients are frozen. '
            'Only phase, integer pilot alias and a constant with 300 Hz prior are fitted per evidence group, using a matched 150 Hz diagnostic white-noise scale. '
            'RMS ≤450 Hz, |constant|≤3000 Hz, horizon and unchanged mean/slope/quadratic/step/ACF noise limits are all required. '
            'These per-curve candidates do not establish a shared-family association or enter the causal position result.\n']
        for kind in ['causal','following']:
            d=read(out/f'unassociated_{kind}_fitted_c.json')
            graph=[r for r in d['rows'] if r['kind']=='unassociated_graph_subset']
            orphan=[r for r in d['rows'] if r['kind']!='unassociated_graph_subset']
            text.append(f"- {kind}: {sum(r['best_passing'] is not None for r in graph)}/{len(graph)} graph subsets and "
                f"{sum(r['best_passing'] is not None for r in orphan)}/{len(orphan)} fixed orphan time blocks have at least one passing independent candidate. "
                f"{d['insufficient_support_points']} points lack four distinct times within their group and are not individually assigned.\n")
        text.append('\nFollowing TLEs do not by themselves resolve the missing-evidence problem under the frozen RF endpoint/calibration. '
            'The following comparison separates the current shared phase plus fitted orbit correction from the nominal orbit at '
            'that same phase, and from an independently fitted nominal-orbit phase. These are conditional diagnostics, not three new estimators.\n')
        text.append(table(shared,[('component','Curve'),('norad','Candidate'),('active_curved_family_points','Retained curved family points'),('shared_phase_s','Current phase s'),
            ('independent_phase_s','Independent phase s'),('shared_phase_and_orbit_RMS_hz','Shared phase + orbit RMS Hz'),
            ('shared_phase_nominal_orbit_RMS_hz','Shared phase nominal RMS Hz'),
            ('independent_phase_nominal_orbit_RMS_hz','Independent phase nominal RMS Hz')]))
        text.append(f'\n![Shared-family residual discrepancy]({case}_shared_family_residual.png)\n')
        if case=='DS23-0268':
            text.append('**Diagnosis:** the longest unresolved graph subset is RX1 CH3 T000, 82 observations over '
                '58.54 s. Its leading candidate is 64923. Causal RMS is 159.28 Hz and following-TLE RMS is 144.40 Hz, '
                'but both fail slope, quadratic, step and autocorrelation tests. For the causal fit, slope z=4.86, '
                'quadratic BIC gain=41.70 and step z=7.35. Low RMS is therefore insufficient. '
                'This is one persisted polynomial piece; a multi-piece join is not demonstrated as the cause. '
                'The earlier targeted improvements concern other curves and disputed 53923/67953 ownership, '
                'and are not reproduced by a generic signed phase-prior update. '
                'A useful next test is family-excluded, jointly calibrated reentry with gate-aware fitting and competing identities retained; '
                'neither a free per-track slope nor GPS-ranked family deletion is justified by this diagnostic.\n')
        else:
            text.append('**Diagnosis:** the longest unresolved curve is RX1 CH7 T000, 82 observations over 74.19 s; '
                'the next-longest RX1 CH1 T002 also independently nominates 66465. The longest curve passes the causal independent '
                'screen at +0.25 s phase and 181.03 Hz RMS, while its current -0.373 s phase gives 562.08 Hz RMS. '
                '**Follow-up interpretation correction:** 66465 has zero retained curved points and no retained predictive entries. '
                'The -0.373 s value is the causal forecast prior, not a phase learned from an established associated family. '
                'Removing fitted orbit modes at that same shared phase leaves RMS unchanged, so this contrast is a phase/family-consistency '
                'issue under the frozen receiver calibration, rather than an effect of those orbit modes. '
                'The following element reaches 200.12 Hz RMS but fails structured-noise gates. '
                'The longest curve has one persisted polynomial piece, so a multi-piece join is not demonstrated. '
                'The parsimonious next prototype is coherent reentry of both RX1 curves with one common 66465 phase, '
                'testing 59582 as a competing family hypothesis and rechecking every existing associated curve. '
                'Independent per-track phases must not be adopted as if they established a common satellite. '
                'The new regional restart branches that choose 63380 for a different CH3 curve fail the original gates and must retain the incumbent.\n')
        longest=sorted([r for r in candidate_rows if r['case']==case and r['kind']=='causal'],key=lambda r:r['end_s']-r['start_s'],reverse=True)[:8]
        paired=[r for row in longest for r in candidate_rows if r['case']==case and r['component']==row['component']]
        text.append(table(paired,[('component','Graph subset'),('kind','TLE'),('points','Points'),('norad','Candidate'),
            ('rms_hz','RMS Hz'),('passing','All screens pass'),('passing_alternatives','Passing identities'),('slope_z','Slope z')]))
        for i in range(1,min(3,len(longest))+1):text.append(f'\n![Unassociated orbit comparison {i}]({case}_unassociated_{i:02d}.png)\n')
        text.append(f'\n[Complete unassociated graph-curve gallery]({case}_unassociated_orbits.pdf). '
            'Outside-graph blocks are fixed 20 s partitions, not found tracks. Many passing candidates on a short or linear block indicate ambiguity, '
            'not explained points. The screen keeps every unresolved observation; no point is trimmed to make a candidate pass.\n')
    csv_write(REPORT/'unassociated_candidates.csv',candidate_rows)
    text+=['\n## Reproduction and validation\n',
        'Use `PYTHONPATH=/tmp/algo03-feasible-deps:src:tools`, single BLAS/OMP threads and the repository venv. '
        'Run `tools/run_dbg01_case.py --case CASE --stage STAGE` for prepare, audit, discover, bank, analyze, figures; '
        'then `tools/run_dbg01_unassociated.py --stage prepare`, `--stage screen`; '
        'then `tools/report_dbg01_two_worst_fast.py --stage coverage` and `--stage figures`. '
        '0268 reuses hash-checked earlier numerical diagnostics and regenerates figures. All large artifacts are on local bulk storage.\n',
        '[Full method comparison including matched c arms](method_comparison.csv) · '
        '[All satellite-family ablations](family_ablations.csv) · [All unassociated candidate diagnostics](unassociated_candidates.csv).\n']
    (REPORT/'README.md').write_text('\n'.join(text))
    write(REPORT/'validation.json',dict(cases=CASES,no_new_RF=True,no_original_results_modified=True,
        original_case_validations={c:sha(Path(root)/c/'validation.json') for c in CASES},
        family_coverage_replayed=True,following_TLEs_diagnostic_only=True,
        standard_sha256=sha(ROOT/'reports/DBG01/README.md'),
        sources={f:sha(ROOT/'tools'/f) for f in ['report_dbg01_two_worst_fast.py','run_dbg01_case.py','run_dbg01_unassociated.py','dbg01_unassociated.py']}))
    print(REPORT/'README.md')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=DEFAULT)
    parser.add_argument('--stage',choices=['coverage','figures'],required=True)
    args=parser.parse_args()
    if args.stage=='coverage':coverage(args.root)
    else:figures(args.root)


if __name__=='__main__':main()
