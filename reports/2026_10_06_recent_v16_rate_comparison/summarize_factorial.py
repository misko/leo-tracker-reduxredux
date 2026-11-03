"""Truthful partial factorial results: missing cases are blank, never zero error."""
import csv
import fcntl
import html
import json
from datetime import datetime,timezone
import numpy as np
import factorial as study


def paired_changes(rows):
    """Within-scan comparisons only; never subtract unmatched cohort medians."""
    fields=('scan','refinement','model','cone','arm')
    lookup={tuple(r[k] for k in fields):r for r in rows if r['status']=='complete'}
    output=[]
    for axis,before,after in [('refinement','original','refined'),('model','T1AT','V16'),
                              ('cone','off','on'),('arm','zero-c','fitted-c')]:
        for key,base in lookup.items():
            if base[axis]!=before: continue
            other=list(key);other[fields.index(axis)]=after
            candidate=lookup.get(tuple(other))
            if candidate is None: continue
            output.append(dict(scan=base['scan'],contrast=f'{axis}: {after} minus {before}',
                held_fixed='; '.join(f'{f}={base[f]}' for f in fields if f not in ('scan',axis)),
                baseline_error_m=base['distance_m'],changed_error_m=candidate['distance_m'],
                change_m=candidate['distance_m']-base['distance_m'],
                both_converged=base['converged'] and candidate['converged'],
                either_boundary=base['boundary'] or candidate['boundary']))
    return output


def collect():
    rows=[]
    attempts={}
    for path in sorted((study.REPORT/'batches').glob('*/*-progress.json')):
        try:
            for attempt in json.loads(path.read_text()):
                attempts[(attempt['scan'],attempt['case'])]=attempt['status']
        except json.JSONDecodeError:
            continue  # Progress snapshots can be observed while being written.
    for scan in json.loads(study.stage.COHORT.read_text())['scans']:
        label=scan['label']
        for refinement,model,cone in study.cases():
            for arm in study.stage.ARMS:
                path=study.OUT/'positions'/label/refinement/model/cone/f'{arm}.json'
                row=dict(scan=label,rate_msps=scan['sample_rate_hz']/1e6,refinement=refinement,
                    model=model,cone=cone,arm=arm,status='pending',distance_m=None,converged=None,
                    boundary=None,assigned_windows=None,passing_windows=None,coverage=None,
                    posterior_rms_hz=None,strong_soft_windows=None,mean_signal_posterior=None,
                    selected_satellites=None,input_sha256=None,source=str(path))
                attempt=attempts.get((label,f'{refinement}-{model}-{cone}'))
                if attempt and attempt!='complete': row['status']=attempt
                if path.exists():
                    r=json.loads(path.read_text())
                    assert r['experiment']==dict(protocol_sha256=study.stage.sha(study.REPORT/'protocol.json'),
                                                 refinement=refinement,model=model,cone=cone)
                    assert r['maximum_budgets_s']==study.stage.POSITION_BUDGET and r['radius_km']==4.
                    assoc=json.loads(study.Path(r['input_metadata']['association_source']).read_text())
                    final=assoc['final']
                    row.update(status='complete',distance_m=r['distance_m'],converged=r['converged'],
                        boundary=r['boundary'],assigned_windows=r['windows'],passing_windows=final['denominator'],
                        coverage=final['coverage'],posterior_rms_hz=r['posterior_weighted_residual_rms_hz'],
                        strong_soft_windows=r['strong_soft_windows'],mean_signal_posterior=r['mean_signal_posterior'],
                        selected_satellites=len(r['numbers']),input_sha256=r['input_sha256'])
                rows.append(row)
    # Matched measurements/bank/baseline in every final-score contrast.
    for label in {r['scan'] for r in rows}:
        for refinement in study.REFINEMENTS:
            subset=[r for r in rows if r['scan']==label and r['refinement']==refinement and r['status']=='complete']
            # NPZ container hashes may differ despite identical arrays; check arrays exactly.
            if subset:
                first=study.Path(subset[0]['source']).parent/'input.npz'
                with np.load(first,allow_pickle=False) as z: reference={k:z[k] for k in z.files}
                for r in subset[1:]:
                    with np.load(study.Path(r['source']).parent/'input.npz',allow_pickle=False) as z:
                        assert set(z.files)==set(reference)
                        for k in z.files: np.testing.assert_array_equal(z[k],reference[k])
    return rows


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    study.REPORT.mkdir(parents=True,exist_ok=True)
    with (study.REPORT/'summary.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        rows=collect();complete=[r for r in rows if r['status']=='complete']
        timestamp=datetime.now(timezone.utc).isoformat()
        (study.REPORT/'results.json').write_text(json.dumps(dict(updated_utc=timestamp,complete=len(complete),planned=len(rows),rows=rows),indent=2))
        with (study.REPORT/'results.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        pairs=paired_changes(rows)
        with (study.REPORT/'paired-changes.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['scan','contrast','held_fixed','baseline_error_m',
                'changed_error_m','change_m','both_converged','either_boundary'])
            writer.writeheader();writer.writerows(pairs)
        labels=sorted({r['scan'] for r in rows});cases=study.cases()
        fig,axes=plt.subplots(1,2,figsize=(17,10),sharey=True,layout='constrained')
        cmap=plt.get_cmap('viridis_r').copy();cmap.set_bad('#eeeeee')
        for ax,arm in zip(axes,study.stage.ARMS):
            grid=np.full((len(labels),len(cases)),np.nan)
            for r in complete:
                if r['arm']!=arm: continue
                i=labels.index(r['scan']);j=cases.index((r['refinement'],r['model'],r['cone']))
                grid[i,j]=r['distance_m']
                suffix=(' △' if r['boundary'] else '')+(' ×' if not r['converged'] else '')
                ax.text(j,i,f"{r['distance_m']:.0f}{suffix}",ha='center',va='center',fontsize=8,
                        color='white' if r['distance_m']>2300 else 'black')
            im=ax.imshow(grid,vmin=0,vmax=4000,cmap=cmap,aspect='auto')
            ax.set_xticks(range(len(cases)),[f"{m}\n{'refined' if r=='refined' else 'original'}\ncone {c}" for r,m,c in cases],fontsize=9)
            ax.set_yticks(range(len(labels)),labels);ax.set_title('Fitted c' if arm=='fitted-c' else 'c = 0')
        fig.colorbar(im,ax=axes,label='Best-found position error (m)',shrink=.7)
        fig.suptitle(f'Recent 16 scans · refinement × cone prior × position score\n{len(complete)}/{len(rows)} fits available; gray cells pending',fontsize=17)
        fig.supxlabel('Independent 4 km searches · △ boundary · × unconverged\nOriginal/refined branches recalibrated separately; score/cone/RF contrasts use identical branch inputs.',fontsize=11)
        fig.savefig(study.REPORT/'position-error-matrix.png',dpi=150);plt.close(fig)
        available=sorted({r['scan'] for r in complete})
        if available:
            fig,axes=plt.subplots(len(available),2,figsize=(13,3.8*len(available)),squeeze=False,
                                  sharex=True,layout='constrained')
            for axes_row,label in zip(axes,available):
                for ax,arm in zip(axes_row,study.stage.ARMS):
                    subset=[r for r in complete if r['scan']==label and r['arm']==arm]
                    for r in subset:
                        i=cases.index((r['refinement'],r['model'],r['cone']))
                        color='#0072B2' if r['model']=='T1AT' else '#D55E00'
                        marker='^' if r['boundary'] else 'o'
                        ax.scatter(r['distance_m'],i,c=color,marker=marker,s=50)
                        if not r['converged']: ax.scatter(r['distance_m'],i,c='black',marker='x',s=35)
                        ax.annotate(f"{r['distance_m']:.0f}",(r['distance_m'],i),xytext=(6,0),
                                    textcoords='offset points',va='center',fontsize=9)
                    ax.set_yticks(range(8),[f'{m} · {r} · cone {c}' for r,m,c in cases],fontsize=9)
                    ax.set_ylim(7.6,-.6);ax.set_xlim(-100,4600);ax.grid(axis='x',alpha=.2)
                    ax.axvline(4000,color='gray',linestyle=':')
                    ax.set_title(f"{label} · {'fitted c' if arm=='fitted-c' else 'c = 0'} · {len(subset)}/8 cases")
                    ax.set_xlabel('Best-found position error (m)')
            fig.suptitle('Eight-way comparison · available scans only\nBlank rows pending; triangles boundary; × unconverged',fontsize=15)
            fig.savefig(study.REPORT/'available-scan-comparison.png',dpi=145);plt.close(fig)
        columns=('scan','refinement','model','cone','arm','distance_m','converged','boundary','coverage','posterior_rms_hz')
        def val(r,k):
            v=r[k]
            if isinstance(v,float): return f'{100*v:.1f}%' if k=='coverage' else f'{v:.1f}'
            return html.escape(str(v))
        table=''.join('<tr>'+''.join(f'<td>{val(r,k)}</td>' for k in columns)+'</tr>' for r in complete)
        text=f'''<!doctype html><meta charset="utf-8"><title>Recent scans: eight-way model comparison</title>
<style>body{{font:16px system-ui;max-width:1500px;margin:2em auto;padding:0 1em}}td,th{{padding:.4em;border-bottom:1px solid #ddd}}img{{width:100%}}</style>
<h1>Refinement × cones × T1-AT / V16</h1><p>Snapshot {timestamp}. {len(complete)} of {len(rows)} final RF-arm fits available.</p>
<p><a href="report.html">Standalone report with methods and paired findings</a> · <a href="report.md">Markdown report</a></p>
<p>Eight combinations per scan, each with fitted c and c = 0. 8 scans at 2.5 MS/s and 8 at 10 MS/s. Each scan is localized independently.</p>
<p>T1-AT here means its original Gaussian position score (C0) on full-data calibration and greedy+replacement associations, not a replay of historical five-fold calibration. V16 changes the final likelihood/timing-prior settings.</p>
<p>Refinement off uses saved original frequencies and original GLRT-score winners; on uses orbit-blind refined frequencies and refined-score winners. Calibration and association rerun per branch. Thus this measures the total effect, including changed winners.</p>
<p>Cones are frozen from the earlier 20-scan dataset, not trained on this cohort. A soft positive-receiver detection-prior tilt enters final scoring only; no hard wrong-sky exclusions or missing-receiver veto. Hard horizon gating is unchanged. Cone strength 0.5; floor 0.1; unsupported sky neutral.</p>
<p>All final score/cone/RF arms within a measurement branch use identical associated windows, satellite bank and fixed receiver baseline. Fresh matched search budgets, 4 km radius, no holdout folds. Conditional known-roof upstream calibration; these are exploratory best-found positions, not blind tests or certified global minima. Better RMS need not mean better position.</p>
<p>Pending cells are not failures or zero errors. Completed but unconverged and boundary cases are explicitly marked. Do not compare raw likelihood values across models. Aggregate comparisons should use only matched completed scans, not different available subsets.</p>
<img src="position-error-matrix.png">{('<img src="available-scan-comparison.png">' if available else '')}<p><a href="results.csv">Full CSV including pending cases</a> · <a href="paired-changes.csv">Matched per-scan error changes (negative = better)</a> · <a href="protocol.json">Frozen protocol</a></p>
<table><tr>{''.join('<th>'+k+'</th>' for k in columns)}</tr>{table}</table>'''
        (study.REPORT/'index.html').write_text(text)
        from paired_plots import plot
        plot(rows,study.REPORT/'paired-position-effects.png')
        from build_report import write_report
        write_report(rows,pairs,timestamp)
        print(json.dumps(dict(complete=len(complete),planned=len(rows),report=str(study.REPORT/'index.html'))),flush=True)


if __name__=='__main__': main()
