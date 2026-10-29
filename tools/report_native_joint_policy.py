"""Evaluate the exhaustive native-subset policy across the frozen DS24 exports."""
import argparse
from collections import Counter,defaultdict
import csv,gzip,hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_native_cohort_validation import failures,label
from report_systematic_annotation import compact_evidence
from run_native_joint_subsets import select_valid_subset


def run(args):
    s=args.study;root=args.joint;sources={};evidence={}
    def load(p,archive=True):
        p=Path(p);sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p)
        if archive:evidence[str(p)]=r
        return r
    protocol=load(root/'protocol.json');groups=defaultdict(list);trials={};controls={};subset_rows=[];replays=[]
    for subset in protocol['all_subsets']:
        sid=subset['subset_id'];ids=subset['branch_ids'];jid=subset['job_id']
        if len(ids)==1:
            matches=[p for prefix in ['omitted-branch-inclusions','flagged-native-inclusions'] for p in s.glob(prefix+'-v*/'+ids[0]+'/target_0.json')]
            if len(matches)!=1:raise ValueError('one frozen singleton receipt required')
            path=matches[0]
        else:
            receipt=load(root/(sid+'-terminal.json'))
            if receipt['status'] not in ('complete','reused'):raise ValueError('joint enumeration not terminal complete')
            path=Path(subset['reuse_source']) if subset.get('reuse_source') else root/sid/'combined.json'
            if subset.get('reuse_source') and hashlib.sha256(path.read_bytes()).hexdigest()!=subset['reuse_sha256']:raise ValueError('reused joint evidence changed')
        r=load(path);c=load(path.parent/'control.json');pr=load(path.parent/'protocol.json')
        if jid not in controls:controls[jid]=c
        for arm,v in c['arms'].items():
            previous=controls[jid]['arms'][arm]
            diff=abs(v['negative_twice_elbo']-previous['negative_twice_elbo'])
            distance=float(np.linalg.norm(np.asarray(v['endpoint_east_north_km'])-previous['endpoint_east_north_km']))
            if diff>1e-5 or distance>1e-5:raise ValueError('matched control differs between subsets')
            replays.append(dict(subset_id=sid,arm=arm,objective_difference=diff,endpoint_difference_km=distance))
        row=dict(subset,paired_valid=r['paired_valid'],source=str(path));groups[jid].append(row);trials[sid]=r
        target_names={e['component'] for e in r['target_entries']}
        for arm,v in r['arms'].items():subset_rows.append(dict(scan=label(r['job']),subset_id=sid,branch_ids=';'.join(ids),points=subset['points'],
            arm=arm,passes=r['paired_valid'],control_passes=c['paired_valid'],added=v['added_points'],lost=v['lost_points'],
            control_error_km=error(c['arms'][arm]),error_km=error(v),failures=failures(v,target_names)))
    selected={jid:select_valid_subset(rows) for jid,rows in groups.items()}
    out=args.output;out.mkdir(parents=True,exist_ok=False);figs=out/'figures';figs.mkdir()
    def csvout(name,rows):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    csvout('all_subsets.csv',subset_rows);csvout('control_replay.csv',replays)
    ds=load(s/'omitted-branch-discovery-v1/protocol.json');rows=[];choices=[];joint_gallery=[]
    for job in ds['jobs']:
        inv=load(job['inventory'],archive=False);jid=job['job_id'];choice=selected.get(jid);candidate=trials[choice['subset_id']] if choice else None
        total=inv['summary'][0]['total_GLRT']
        choices.append(dict(scan=label(job),job_id=jid,branch_ids=';'.join(choice['branch_ids']) if choice else '',
            native_points=choice['points'] if choice else 0,source=choice['source'] if choice else job['inventory'],
            policy='validated_native_subset' if choice else 'frozen_baseline',
            tested_subsets=len(groups.get(jid,[])),control_passes=controls[jid]['paired_valid'] if jid in controls else 'not_refit'))
        for arm,baseline in inv['policy'].items():
            v=candidate['arms'][arm] if candidate else baseline;old=set(baseline['proposed_associated_ids']);new=set(v['proposed_associated_ids'])
            if old-new:raise ValueError('selected policy loses an old associated point')
            if candidate and not candidate['paired_valid']:raise ValueError('policy chooses a failing subset')
            rows.append(dict(scan=label(job),job_id=jid,arm=arm,total_GLRT=total,baseline_points=len(old),policy_points=len(new),
                added=len(new-old),baseline_percent=100*len(old)/total,policy_percent=100*len(new)/total,
                baseline_error_km=error(baseline),policy_error_km=error(v),selected_branches=len(choice['branch_ids']) if choice else 0,
                control_vs_frozen_error_difference_m=1000*(error(controls[jid]['arms'][arm])-error(baseline)) if jid in controls else 0.))
        if choice and len(choice['branch_ids'])>1:
            fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
            for col,arm in enumerate(['c0','fitted_c']):
                for k,d in enumerate(candidate['arms'][arm]['native_target_diagnostics']):
                    color=plt.cm.tab10(k);t=d['times_s'];short=d['component'].split('-NATIVE')[0].split('-RX')[-1]
                    axs[0,col].scatter(t,np.array(d['CFO_hz'])/1000,s=14,c=[color],label='RX'+short+' / '+str(d['norad']))
                    axs[0,col].plot(t,np.array(d['predicted_CFO_hz'])/1000,c=color)
                    axs[1,col].plot(t,d['residual_hz'],'.-',c=color)
                axs[0,col].set(title=arm,ylabel='Unwrapped CFO (kHz)');axs[1,col].set(xlabel='Scan time (s)',ylabel='Residual (Hz)')
                axs[0,col].legend(fontsize=7);axs[1,col].axhline(0,c='black',lw=.6)
                for ax in axs[:,col]:ax.grid(alpha=.2)
            fig.suptitle(label(job)+': all selected native branches included jointly; all old/new checks pass')
            fig.savefig(figs/(jid+'.png'),dpi=140);plt.close(fig);joint_gallery.append(f"### {label(job)}\n\n![Joint CFO and residuals](figures/{jid}.png)\n")
    csvout('scan_policy.csv',choices);csvout('position_and_coverage.csv',rows)
    metrics=[]
    for arm in ['c0','fitted_c']:
        rr=[r for r in rows if r['arm']==arm]
        for variant in ['baseline','policy']:
            errors=np.array([r[variant+'_error_km'] for r in rr]);counts=[r[variant+'_points'] for r in rr]
            metrics.append(dict(arm=arm,variant=variant,scans=len(rr),associated_points=sum(counts),
                GLRT_percent=100*sum(counts)/sum(r['total_GLRT'] for r in rr),mean_error_km=float(errors.mean()),
                median_error_km=float(np.median(errors)),p90_error_km=float(np.quantile(errors,.9)),p95_error_km=float(np.quantile(errors,.95)),maximum_error_km=float(errors.max())))
    csvout('cohort_metrics.csv',metrics)
    changed=[r for r in rows if r['arm']=='fitted_c' and r['selected_branches']]
    summary=dict(scans=len(ds['jobs']),supported_identity_scans=len(groups),tested_subsets=len(protocol['all_subsets']),
        new_joint_trials=sum(not j.get('reuse_source') for j in protocol['jobs']),joint_trials=len(protocol['jobs']),
        reused_joint_trials=sum(bool(j.get('reuse_source')) for j in protocol['jobs']),passing_joint_trials=sum(trials[j['subset_id']]['paired_valid'] for j in protocol['jobs']),
        selected_scans=len(changed),selected_branches=sum(r['selected_branches'] for r in changed),
        added_points={a:sum(r['added'] for r in rows if r['arm']==a) for a in ['c0','fitted_c']},
        fitted_c_improved=sum(r['policy_error_km']<r['baseline_error_km'] for r in changed),
        fitted_c_worsened=sum(r['policy_error_km']>r['baseline_error_km'] for r in changed),
        maximum_control_replay_difference=max(r['objective_difference'] for r in replays),no_production_change=True)
    annotation_path=Path(protocol['annotations_source']);sources[str(annotation_path)]=hashlib.sha256(annotation_path.read_bytes()).hexdigest()
    annotations=list(csv.DictReader(annotation_path.open()));states={r['branch_id']:r['inclusion_status'] for r in annotations}
    csvout('all_large_annotations.csv',annotations)
    summary['rescued_individually_rejected_branches']=sum(states[bid]=='rejected' for choice in selected.values() if choice for bid in choice['branch_ids'])
    write(out/'summary.json',summary)
    fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for ax,arm in zip(axs,['c0','fitted_c'],strict=True):
        rr=[r for r in rows if r['arm']==arm]
        for variant,color,style in [('baseline','#555555','-'),('policy','#cc3311','--')]:
            values=np.sort([r[variant+'_error_km'] for r in rr]);ax.step(values,np.arange(1,len(values)+1)/len(values),where='post',c=color,ls=style,label=variant)
        ax.set(title=arm,xlabel='Evaluation position error (km)',ylabel='Fraction of 93 scans');ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Exhaustive native-subset recovery: position distributions largely overlap');fig.savefig(figs/'position_ecdf.png',dpi=145);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for arm,color,marker in [('c0','#4477aa','o'),('fitted_c','#ee6677','s')]:
        rr=sorted([r for r in rows if r['arm']==arm and r['selected_branches']],key=lambda r:r['scan'])
        xx=np.arange(len(rr));axs[0].scatter(xx,[r['policy_percent']-r['baseline_percent'] for r in rr],c=color,marker=marker,label=arm)
        axs[1].scatter(xx,[1000*(r['policy_error_km']-r['baseline_error_km']) for r in rr],c=color,marker=marker,label=arm)
        for ax in axs:ax.set_xticks(xx,[r['scan'].split('-')[-1] for r in rr],rotation=90,fontsize=7)
    axs[0].set(ylabel='GLRT association gain (percentage points)',xlabel='DS24 scan');axs[1].set(ylabel='Position error change (m); negative is better',xlabel='DS24 scan');axs[1].axhline(0,c='black',lw=.6)
    for ax in axs:ax.legend();ax.grid(alpha=.2)
    fig.suptitle('One selected recovery set per scan; overlapping alternatives never double counted');fig.savefig(figs/'scan_changes.png',dpi=145);plt.close(fig)
    write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f,separators=(',',':'))
    selected_table=[dict(scan=r['scan'],branches=r['selected_branches'],added=r['added'],before_percent=r['baseline_percent'],after_percent=r['policy_percent'],
        before_km=r['baseline_error_km'],after_km=r['policy_error_km']) for r in sorted(changed,key=lambda r:r['scan'])]
    supported=protocol.get('supported_identities',46);candidate_count=protocol.get('candidate_annotations',72)
    joint_names=', '.join(c['scan'] for c in choices if c['branch_ids'] and len(c['branch_ids'].split(';'))>1)
    md=f"""# Joint native-track recovery policy — DS24 frozen cohort

The preceding [individual-trial report](../2026_10_29_native_cohort_validation/README.md) found 31 passing clean native proposals, but some overlap and some scans have multiple candidates. This report resolves point ownership and tests interactions. Its frozen input contains {candidate_count} annotated proposals, including every polynomial-quality state when the expanded 93-proposal inventory is used.

## Exhaustive RF-only selection

All {supported} conditionally supported identities are eligible, including individually rejected trials. Across {len(groups)} scans they form **{len(protocol['all_subsets'])} nonoverlapping subsets**: {supported} previously tested singletons and **{summary['joint_trials']} joint configurations** ({summary['new_joint_trials']} newly run, {summary['reused_joint_trials']} reused unchanged with verified hashes). Exact enumeration is bounded to twelve proposals per scan. Every new trial includes a matched control; their maximum replay objective discrepancy is {summary['maximum_control_replay_difference']:.3g}. No original GLRT point is duplicated within a subset. Each native discovery source must match the SHA-256 stored at annotation time; changed input files are rejected.

Choose the fully passing subset with the most distinct native GLRT points, then fewer branches, then a deterministic branch-ID tie break. GPS error does not enter selection. If no subset passes, preserve the frozen baseline. Every target and original-track gate, old-point preservation, phase convergence and regional bound remains enforced in both c arms. There is no gate relaxation or satellite-model modification in this experiment.

**{summary['passing_joint_trials']} / {summary['joint_trials']} joint configurations pass.** The final policy selects **{summary['selected_branches']} branches across {summary['selected_scans']} scans**, adding **{summary['added_points']['fitted_c']} GLRT points** in fitted-c ({summary['added_points']['c0']} in c=0). Overlapping alternatives never contribute duplicate points. The selected policy rescues {summary['rescued_individually_rejected_branches']} individually rejected branches through joint fitting. Selected multi-branch combinations occur in {joint_names}.

## Cohort accuracy and coverage

The evaluation covers all **93 available frozen DS24 exports**. Unaffected scans retain their frozen parent outputs. Changed scans use the newly validated joint result or an already validated singleton. All selected results retain old associations. The matched-control versus frozen-parent endpoint differences are recorded per scan; the largest error difference, about 1.3 m, belongs to unselected DS24-0083. Its current c=0 control has an existing RX1 CH8 T002 residual failure, so this remains an unresolved baseline issue rather than an accepted native recovery. Nine missing DS24 exports are outside this cohort.

{table(metrics,['arm','variant','associated_points','GLRT_percent','mean_error_km','median_error_km','p90_error_km','p95_error_km','maximum_error_km'])}

![Position distributions](figures/position_ecdf.png)

Among the {len(changed)} changed scans, fitted-c position error improves in {summary['fitted_c_improved']} and worsens in {summary['fitted_c_worsened']}. The distributions remain very similar. This verifies additional compatible coverage; it does not establish a substantial position-accuracy improvement or justify a new production ALGO. More observations from already represented satellite families can add little independent geometric information, while model discrepancies can still shift the optimum. That interpretation is consistent with these results; it is not a proved decomposition of the position error.

![Per-scan changes](figures/scan_changes.png)

The following table is the selected fitted-c policy, not a collection of incompatible single-branch experiments. Both arms are in the CSV.

{table(selected_table,['scan','branches','added','before_percent','after_percent','before_km','after_km'])}

## Scope, evidence and reproduction

All discovery observations, causal candidate sets, priors, original calibration masks, and optimizer budgets match their single-branch experiments. New branches remain predictive-only; none directly estimates receiver offsets/drifts. Each joint run uses five phase-refresh rounds and 48 iterations per round from the 25×25 km regional center. The ground-truth coordinate 37.849061591561885, -122.48574968092912 is used only for evaluation. No future TLE, new RF acquisition, or production change is involved.

See [all tested subsets](all_subsets.csv), [one policy per scan](scan_policy.csv), [per-scan paired errors and coverage](position_and_coverage.csv), [cohort statistics](cohort_metrics.csv), [matched-control replay](control_replay.csv), [source hashes](sources.json), and [compressed evidence](evidence.json.gz). `run_native_joint_subsets.py` enumerates every nonoverlapping subset and runs bounded trials (eight workers, 600-second cap per subset). `include_predictive_annotations.py --native-from-validation --joint-only` supports mixed Graph/Hough sources using their annotation hashes. `report_native_joint_policy.py` reproduces this report. Tests verify exact nonoverlap enumeration, selection independent of supplied evaluation errors, and source-provenance rejection.

The wider goal remains open: ambiguous, unstable and geometry-limited identities remain unresolved, and the original 1,630-track ledger is not fully assessed. Polynomial flags are retained as provenance rather than treated as proof of a wrong satellite. This is a completed subset audit of the supplied candidate cohort, not a claim that all large tracks are now correctly identified or usable.

## Joint orbit and residual figures

"""+'\n'.join(joint_gallery)
    (out/'README.md').write_text(md);print(json.dumps(summary,indent=2));print(table(metrics,['arm','variant','GLRT_percent','mean_error_km','median_error_km','p90_error_km']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['study','joint','output']:p.add_argument('--'+key,type=Path,required=True)
    run(p.parse_args())
