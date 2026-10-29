"""Evaluate the bounded evidence-recovery policy on the same 93 DS24 exports."""
import argparse
import csv,gzip,hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from report_inventory_experiments import error


def run(args):
    out=args.report;sources={};evidence={}
    def load(path):
        path=Path(path);sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();r=read(path);evidence[str(path)]=r;return r
    sources[str(args.previous_metrics)]=hashlib.sha256(args.previous_metrics.read_bytes()).hexdigest()
    previous=list(csv.DictReader(args.previous_metrics.open()));protocol=load(args.policy/'protocol.json');selected={};trials=[];executions=[];gallery=[]
    for job in protocol['jobs']:
        sid=job['subset_id'];terminal=load(args.policy/(sid+'-terminal.json'))
        executions.append(dict(scan=job['scan'],subset_id=sid,status=terminal['status'],reason=terminal.get('reason')))
        if terminal['status'] not in ('complete','reused'):continue
        path=Path(job['reuse_source']) if job.get('reuse_source') else args.policy/sid/'combined.json'
        if terminal['status']=='reused' and hashlib.sha256(path.read_bytes()).hexdigest()!=terminal['sha256']:raise ValueError('singleton source changed')
        r=load(path);old=load(Path(job['old_policy']['source']));old_arms=old['policy'] if job['old_policy']['policy']=='frozen_baseline' else old['arms']
        preserves=all(set(old_arms[a]['proposed_associated_ids'])<=set(r['arms'][a]['proposed_associated_ids']) for a in ('c0','fitted_c'))
        valid=r['paired_valid'] and preserves
        if valid:selected[job['scan']]=r
        for arm,v in r['arms'].items():
            before=old_arms[arm];old_ids=set(before['proposed_associated_ids']);new_ids=set(v['proposed_associated_ids'])
            trials.append(dict(scan=job['scan'],subset_id=sid,arm=arm,selected=valid,physical_checks=r['paired_valid'],
                preserves_previous_points=preserves,before_km=error(before),after_km=error(v),added=len(new_ids-old_ids),lost=len(old_ids-new_ids),
                branches=len(job['chosen']['branch_ids']),native_points=job['chosen']['points']))
        if len(r['target_entries'])>1:
            fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
            for col,arm in enumerate(('c0','fitted_c')):
                for k,d in enumerate(r['arms'][arm]['native_target_diagnostics']):
                    color=plt.cm.tab10(k%10);short=d['component'].split('-NATIVE-')[0].split('-RX')[-1]
                    axs[0,col].scatter(d['times_s'],np.array(d['CFO_hz'])/1000,s=8,c=[color],label='RX'+short+' / '+str(d['norad']))
                    axs[0,col].plot(d['times_s'],np.array(d['predicted_CFO_hz'])/1000,c=color)
                    axs[1,col].plot(d['times_s'],d['residual_hz'],'.-',ms=2,c=color)
                axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Scan time (s)',ylabel='Bias-profiled residual (Hz)')
                axs[0,col].legend(fontsize=6);axs[1,col].axhline(0,c='black',lw=.5)
                for ax in axs[:,col]:ax.grid(alpha=.2)
            fig.suptitle(job['scan']+f' — joint configuration / {"passes" if valid else "rejected; preserve previous policy"}')
            file='figures/'+sid+'_joint.png';fig.savefig(out/file,dpi=130);plt.close(fig);gallery.append(f"### {job['scan']}\n\n![Joint native evidence]({file})\n")
    rows=[]
    for old in previous:
        scan=old['scan'];arm=old['arm'];r=selected.get(scan);v=r['arms'][arm] if r else None
        points=len(v['proposed_associated_ids']) if v else int(old['policy_points']);total=int(old['total_GLRT'])
        if points<int(old['policy_points']) or points>total:raise ValueError('invalid policy count')
        rows.append(dict(scan=scan,arm=arm,total_GLRT=total,previous_points=int(old['policy_points']),new_points=points,
            previous_percent=100*int(old['policy_points'])/total,new_percent=100*points/total,
            previous_error_km=float(old['policy_error_km']),new_error_km=error(v) if v else float(old['policy_error_km']),
            changed=bool(v)))
    if len(rows)!=186 or len({r['scan'] for r in rows})!=93:raise ValueError('93-scan matched cohort required')
    metrics=[]
    for arm in ('c0','fitted_c'):
        rr=[r for r in rows if r['arm']==arm]
        for variant in ('previous','new'):
            errors=np.array([r[variant+'_error_km'] for r in rr]);points=sum(r[variant+'_points'] for r in rr)
            metrics.append(dict(arm=arm,variant=variant,scans=len(rr),associated_points=points,GLRT_percent=100*points/sum(r['total_GLRT'] for r in rr),
                mean_error_km=float(errors.mean()),median_error_km=float(np.median(errors)),p90_error_km=float(np.quantile(errors,.9)),
                p95_error_km=float(np.quantile(errors,.95)),maximum_error_km=float(errors.max())))
    def csvout(name,data):
        if not data:return
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]),lineterminator='\n');w.writeheader();w.writerows(data)
    csvout('policy_position_and_coverage.csv',rows);csvout('policy_metrics.csv',metrics);csvout('policy_trials.csv',trials);csvout('policy_execution.csv',executions)
    summary=dict(changed_scans=len(selected),added_points={arm:sum(r['new_points']-r['previous_points'] for r in rows if r['arm']==arm) for arm in ('c0','fitted_c')},
        fitted_c_improved=sum(r['new_error_km']<r['previous_error_km'] for r in rows if r['arm']=='fitted_c'),
        fitted_c_worsened=sum(r['new_error_km']>r['previous_error_km'] for r in rows if r['arm']=='fitted_c'),
        all_previous_points_preserved=True,maximum_one_joint_configuration_per_scan=True,not_exhaustive_physical_subset_search=True,
        independent_false_association_validation=False,no_production_change=True)
    write(out/'policy_summary.json',summary);write(out/'policy_sources.json',sources)
    with gzip.open(out/'policy_evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f)
    fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        rr=[r for r in rows if r['arm']==arm]
        for variant,style in [('previous','--'),('new','-')]:
            values=np.sort([r[variant+'_error_km'] for r in rr]);ax.plot(values,np.arange(1,len(values)+1)/len(values),ls=style,label=variant)
        ax.set(title=arm,xlabel='Position error (km)',ylabel='Fraction of 93 scans');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Previous native recovery policy vs exploratory joint-evidence policy')
    fig.savefig(out/'figures/policy_error_ecdf.png',dpi=140);plt.close(fig)
    (out/'policy_gallery.md').write_text('# Joint recovery plots\n\n'+'\n'.join(gallery))
    changed=[r for r in rows if r['arm']=='fitted_c' and r['changed']]
    (out/'joint_policy.md').write_text(f'''# Bounded joint recovery policy on 93 available DS24 exports

Fourteen newly supported native hypotheses pass individual physical checks. To test their interaction with prior recovery, combine individually passing proposals with the previously selected native branches in each affected scan. Enumerate nonoverlapping memberships cheaply, require every previous native point to remain represented with its previous satellite owner, and test the maximum-point configuration (ties: fewer branches, then deterministic IDs). GPS error never enters this choice. Only **one new joint configuration per changed scan** is fitted; failed fits retain the previous policy. This bounded experiment does not claim exhaustive physical subset optimality, and individually rejected proposals could still warrant future joint tests.

**{summary['changed_scans']} scans change, adding {summary['added_points']['fitted_c']} GLRT points in fitted-c and {summary['added_points']['c0']} in c=0, with every previously associated point retained.** Singletons reuse their exact completed fit; joint configurations receive full matched c-arm fits and unchanged gates. The same 93 exports, observations, regional box and causal catalogue define the comparison. Nine unavailable DS24 exports remain outside it. The comparator is the [previous native joint policy](../2026_10_29_native_all_large_policy/README.md), not an unrelated earlier ALGO baseline.

{table(metrics,['arm','variant','associated_points','GLRT_percent','mean_error_km','median_error_km','p90_error_km','p95_error_km','maximum_error_km'])}

![Position distributions](figures/policy_error_ecdf.png)

{table(changed,['scan','previous_percent','new_percent','previous_error_km','new_error_km'])}

Fitted-c position error improves in {summary['fitted_c_improved']} scans and worsens in {summary['fitted_c_worsened']}. These changes must be assessed separately from frequency fit and coverage. Candidate support uses the exploratory joint-evidence rule; physical acceptance alone does not independently establish correct identity or calibrate false-association rates. This remains a research policy, not a production ALGO promotion.

[Both-arm per-scan results](policy_position_and_coverage.csv), [all tested configurations including failures](policy_trials.csv), [execution receipts](policy_execution.csv), [joint CFO/residual figures](policy_gallery.md), and [source hashes](policy_sources.json) preserve the full comparison. Run `run_evidence_recovery_policy.py` with the previous policy/annotation CSVs and new inclusion receipts, then `report_evidence_recovery_policy.py` with the previous cohort metrics. Runs use four workers and 600-second per-case caps. Native alternatives and graph inventory entries remain separate; their counts are not added together.
''')
    print(json.dumps(dict(summary=summary,metrics=metrics),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['policy','previous-metrics','report']:p.add_argument('--'+k,type=Path,required=True)
    run(p.parse_args())
