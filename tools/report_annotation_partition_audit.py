"""Publish timestamp-partition coverage, retests and matched inclusion outcomes."""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.grouped_prediction import identity_consensus,replay_split
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);figs=out/'figures';figs.mkdir()
    sources={};evidence={}
    def load(path):
        path=Path(path);sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        r=read(path);evidence[str(path)]=r;return r
    def csvfile(name,rows):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    prior_path=Path(__file__).resolve().parents[1]/'reports/2026_10_29_curved_family_roles/annotation_ledger.csv'
    sources[str(prior_path)]=hashlib.sha256(prior_path.read_bytes()).hexdigest()
    prior={r['track_id']:r for r in csv.DictReader(prior_path.open())}
    audit=s/'annotation-partition-audit-v1';load(audit/'protocol.json');audits={};arows=[]
    for p in sorted(audit.glob('*/result.json')):
        for r in load(p)['rows']:
            audits[r['track_id']]=r;old=prior[r['track_id']]
            arows.append(dict(track_id=r['track_id'],scan=r['label'],component=r['component'],points=r['points'],
                previous_status=old['state'],original_distinct_holdouts=r['original_distinct_usable'],
                schedule_ready=r['schedule']['ready'],selected_distinct_holdouts=len(r['schedule']['selected']),
                reason=r['schedule']['reason'],timestamp_attempts=len(r['schedule']['attempts'])))
    csvfile('partition_audit.csv',arows)
    categories=list(dict.fromkeys(r['previous_status'] for r in arows));fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,key in zip(axs,['original_distinct_holdouts','selected_distinct_holdouts'],strict=True):
        bottom=np.zeros(len(categories))
        for count in range(4):
            v=[sum(r['previous_status']==cat and r[key]==count for r in arows) for cat in categories]
            ax.bar(range(len(categories)),v,bottom=bottom,label=str(count));bottom+=v
        ax.set_xticks(range(len(categories)),[c.replace('_identity','').replace('_','\n') for c in categories]);ax.set_ylabel('Inventoried DS24 tracks');ax.legend(title='Distinct usable holdouts')
    axs[0].set_title('Original three fixed seeds');axs[1].set_title('Frozen timestamp-only search, up to 67 seeds')
    fig.savefig(figs/'partition_coverage.png',dpi=145);plt.close(fig)
    root=s/'distinct-partition-reruns-v1';protocol=load(root/'protocol.json');retests=[];votes=[]
    for job in protocol['jobs']:
        q=job['row'];tid=q['track_id'];receipt=root/(tid+'-terminal.json');terminal=load(receipt) if receipt.exists() else {'status':'pending'}
        p=root/tid/'result.json';annotation={};r={}
        if p.exists():
            r=load(p);load(p.parent/'protocol.json');annotation=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
        row=dict(track_id=tid,scan=q['label'],component=q['component'].split('-RF')[0],points=q['points'],category=job['category'],
            previous_status=job['prior']['state'],previous_norad=job['prior']['norad'],execution=terminal['status'],
            new_status=annotation.get('status','not_completed'),new_norad=annotation.get('norad'),minimum_margin=annotation.get('minimum_margin'))
        retests.append(row)
        for vote in annotation.get('votes',[]):votes.append(dict(track_id=tid,component=row['component'],**vote))
    csvfile('retests.csv',retests)
    if votes:csvfile('votes.csv',votes)
    fig,ax=plt.subplots(figsize=(12,7),layout='constrained')
    for idx,row in enumerate(retests):
        for arm,offset,color in [('c0',-.13,'#4477aa'),('fitted_c',.13,'#ee6677')]:
            vv=[v for v in votes if v['track_id']==row['track_id'] and v['arm']==arm]
            ax.scatter([v['margin'] for v in vv],[idx+offset]*len(vv),c=color,s=24,label=arm if idx==0 else None)
    ax.set_yticks(range(len(retests)),[r['component'].replace('DS25-','DS25 alias: ')+' / '+r['new_status'].replace('_identity','') for r in retests],fontsize=8)
    ax.axvline(10,c='black',ls='--',label='Existing margin requirement');ax.set_xscale('symlog',linthresh=10);ax.invert_yaxis();ax.set_xlabel('Winner–runner-up margin (−2 log predictive density)');ax.legend();ax.grid(axis='x',alpha=.2)
    fig.savefig(figs/'retest_margins.png',dpi=145);plt.close(fig)
    # Show actual target points; different seed numbers alone do not show diversity.
    example=next(j for j in protocol['jobs'] if j['category']=='newly_eligible');a=audits[example['row']['track_id']];t=np.asarray(a['times_s']);fig,ax=plt.subplots(figsize=(11,4),layout='constrained')
    attempts={r['seed']:r for r in a['schedule']['attempts']}
    sets=[('old '+str(r['seed']),attempts[r['seed']]) for r in a['original']]+[('new '+str(r['seed']),r) for r in a['schedule']['selected']]
    for i,(label,receipt) in enumerate(sets):
        train,held=replay_split(t,receipt)
        for mask,c,name in [(train,'#bbbbbb','Training'),(held,'#cc3311','Held'),(~train&~held,'#eeaa33','Guard')]:
            ax.scatter(t[mask],np.full(mask.sum(),i),s=17,c=c,label=name if i==0 else None)
    ax.set_yticks(range(len(sets)),[x[0] for x in sets]);ax.invert_yaxis();ax.set(xlabel='Scan time (s)',title=example['row']['component'].split('-RF')[0]);ax.legend(ncol=3)
    fig.savefig(figs/'partition_example.png',dpi=145);plt.close(fig)
    inclusions=[];gallery=[];gate_rows=[];inc=s/'distinct-partition-inclusions-v1'
    if (inc/'protocol.json').exists():
        ip=load(inc/'protocol.json')
        for job in ip['jobs']:
            tid=job['row']['track_id'];folder=inc/tid
            terminal=inc/(tid+'-terminal.json')
            if terminal.exists():load(terminal)
            if not (folder/'combined.json').exists():continue
            load(folder/'protocol.json');control=load(folder/'control.json');trial=load(folder/'combined.json')
            gate_path=s/'distinct-partition-gates-v1'/tid/'result.json'
            if gate_path.exists():
                explanation=load(gate_path)
                for arm,v in explanation['variants']['combined'].items():
                    for t in v['tracks']:
                        if t['component']==job['row']['component']:
                            gate_rows.append(dict(scan=job['row']['label'],arm=arm,failures='; '.join(t['failure_reasons']),
                                RMS_hz=t['conditional']['rms_hz'],lag1_acf=t['conditional']['diagnostics']['lag1_acf'],
                                passing_RX_CH_owners=t['pre_gate_passing_owners'],multiple_owners_required=t['multiple_owners_required']))
            for arm,v in trial['arms'].items():
                cv=control['arms'][arm];inclusions.append(dict(track_id=tid,scan=job['row']['label'],arm=arm,control_error_km=error(cv),trial_error_km=error(v),
                    control_RMS_hz=cv['RMS_hz'],trial_RMS_hz=v['RMS_hz'],added=v['added_points'],lost=v['lost_points'],
                    control_pass=control['paired_valid'],trial_pass=trial['paired_valid'],target_pass=all(t['gate']['compatible'] for t in v['targets'])))
            fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
            for col,arm in enumerate(['c0','fitted_c']):
                target=trial['arms'][arm]['targets'][0];tt=target['times_s']
                axs[0,col].scatter(tt,np.asarray(target['CFO_hz'])/1000,s=13,label='GLRT');axs[0,col].plot(tt,np.asarray(target['predicted_CFO_hz'])/1000,c='#cc3311',label='Orbit + receiver fit')
                axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[0,col].legend(fontsize=8)
                axs[1,col].plot(tt,target['residual_hz'],'.-',ms=4);axs[1,col].axhline(0,c='black',lw=.8);axs[1,col].set(xlabel='Scan time (s)',ylabel='Conditional residual (Hz)')
                for ax in axs[:,col]:ax.grid(alpha=.2)
            fig.suptitle(job['row']['component'].split('-RF')[0]+f" | paired proposal passes: {trial['paired_valid']}")
            fig.savefig(figs/(tid+'.png'),dpi=140);plt.close(fig);gallery.append(f"![GLRT and residuals](figures/{tid}.png)")
    if inclusions:
        csvfile('inclusions.csv',inclusions);ids=list(dict.fromkeys(r['track_id'] for r in inclusions));fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
        for ax,arm in zip(axs,['c0','fitted_c'],strict=True):
            rr=[next(r for r in inclusions if r['track_id']==tid and r['arm']==arm) for tid in ids]
            for k,r in enumerate(rr):
                ax.plot([k,k],[r['control_error_km'],r['trial_error_km']],c='#bbbbbb');ax.scatter(k,r['control_error_km'],c='black',marker='_',s=130,label='Matched control' if k==0 else None)
                ax.scatter(k,r['trial_error_km'],c='#4477aa' if r['trial_pass'] else '#cc3311',marker='o' if r['trial_pass'] else 'x',s=50)
            ax.set_xticks(range(len(rr)),[r['scan'] for r in rr],rotation=45,ha='right');ax.set(title=arm,ylabel='Evaluation position error (km)');ax.grid(axis='y',alpha=.2);ax.legend()
        fig.suptitle('Insertion experiments: circles pass paired checks; crosses are rejected proposals')
        fig.savefig(figs/'inclusion_errors.png',dpi=145);plt.close(fig)
    if gate_rows:csvfile('gate_failures.csv',gate_rows)
    family_rows=[];family_gallery=[];family_diagnosis=[];family=s/'distinct-partition-family-67906-v1'
    if (family/'inclusion/combined.json').exists():
        load(family/'protocol.json');load(family/'terminal.json');load(family/'inclusion/protocol.json')
        for path in sorted((family/'inclusion').glob('*.json')):
            trial=load(path)
            if 'arms' not in trial:continue
            for arm,v in trial['arms'].items():
                family_rows.append(dict(variant=path.stem,arm=arm,error_km=error(v),added=v['added_points'],lost=v['lost_points'],paired_pass=trial['paired_valid'],
                    targets_pass=all(t['gate']['compatible'] for t in v['targets'])))
        trial=load(family/'inclusion/combined.json');fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
        for col,arm in enumerate(['c0','fitted_c']):
            for k,t in enumerate(trial['arms'][arm]['targets']):
                color=plt.cm.tab10(k);label=t['component'].split('-RX')[-1].split('-RF')[0]
                axs[0,col].scatter(t['times_s'],np.asarray(t['CFO_hz'])/1000,s=13,c=[color],label='RX'+label)
                axs[0,col].plot(t['times_s'],np.asarray(t['predicted_CFO_hz'])/1000,c=color)
                axs[1,col].plot(t['times_s'],t['residual_hz'],'.-',ms=4,c=color)
            axs[0,col].set(title=arm,ylabel='GLRT CFO (kHz)');axs[0,col].legend(fontsize=8);axs[1,col].axhline(0,c='black',lw=.8);axs[1,col].set(xlabel='Scan time (s)',ylabel='Residual (Hz)')
        fig.suptitle(f"DS24-0070 / family 67906, two individually annotated curves; paired pass = {trial['paired_valid']}")
        fig.savefig(figs/'family_67906.png',dpi=145);plt.close(fig);csvfile('family_67906.csv',family_rows)
        family_gallery.append('![Shared family GLRT and residuals](figures/family_67906.png)')
        gp=family/'gates/result.json'
        if gp.exists():
            gg=load(gp);rr=gg['variants']['combined']['fitted_c']['tracks'];fig,axs=plt.subplots(3,1,figsize=(12,9),sharex=True,layout='constrained')
            for t in rr:
                col=0 if t['norad']==67906 else 1 if t['receiver']==1 else 2
                tt=np.asarray(t['times_s']);mask=(tt>=30)&(tt<=120)
                if mask.sum()<2:continue
                label=f"{t['norad']} RX{t['receiver']} CH{t['channel']}"
                axs[col].plot(tt[mask],np.asarray(t['residual_hz'])[mask],'.-',ms=4,label=label)
            for ax,title in zip(axs,['Target family 67906','Other families on RX1','Other families on RX2'],strict=True):
                ax.axhline(0,c='black',lw=.8);ax.axvspan(46,76,color='#999999',alpha=.1);ax.set(title=title,ylabel='Conditional residual (Hz)');ax.legend(fontsize=7,ncol=3);ax.grid(alpha=.2)
            axs[-1].set_xlabel('Scan time (s)');fig.suptitle('DS24-0070: shared target discrepancy and available calibration witnesses\nShaded interval has no retained other-family RX1 observations; same fitted-c solution')
            fig.savefig(figs/'family_residual_context.png',dpi=145);plt.close(fig);family_gallery.append('![Residual context](figures/family_residual_context.png)')
            for arm,v in gg['variants']['combined'].items():
                targets=[t for t in v['tracks'] if t['norad']==67906]
                a,b=targets;ta,tb=np.asarray(a['times_s']),np.asarray(b['times_s']);ya,yb=np.asarray(a['residual_hz']),np.asarray(b['residual_hz'])
                distances=abs(ta[:,None]-tb);pairs=sorted((float(distances[i,j]),i,j) for i,j in zip(*np.where(distances<=.5),strict=True));used_a=set();used_b=set();chosen=[]
                for _,i,j in pairs:
                    if i in used_a or j in used_b:continue
                    used_a.add(i);used_b.add(j);chosen.append((i,j))
                ia,ib=np.asarray(chosen).T
                witnesses=sum(sum(46<=x<=76 for x in t['times_s']) for t in v['tracks'] if t['receiver']==1 and t['norad']!=67906)
                family_diagnosis.append(dict(arm=arm,unique_pairs_within_0_5s=len(chosen),residual_correlation=float(np.corrcoef(ya[ia],yb[ib])[0,1]),
                    pair_difference_RMS_hz=float(np.sqrt(np.mean((ya[ia]-yb[ib])**2))),other_family_RX1_points_46_to_76s=witnesses,
                    failures={t['component']:'; '.join(t['failure_reasons']) for t in targets}))
            write(out/'family_residual_diagnosis.json',family_diagnosis)
    ledger=[];queue=s/'systematic-annotation-v1'
    for t in load(queue/'protocol.json')['rows']:
        row=dict(prior[t['track_id']])
        if not row.get('annotation_source'):
            p=(Path(t['known_validation']) if t['known_validation'] else queue/t['track_id'])/'result.json'
            if p.exists():
                r=load(p);a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'));row.update(state=a['status'],norad=a['norad'],annotation_source=str(p),minimum_margin=a.get('minimum_margin'))
            else:
                receipts=sorted(queue.glob('attempt-*/'+t['track_id']+'-terminal.json'))
                if receipts:row['state']='execution_'+load(receipts[-1])['status']
        a=audits.get(t['track_id']);r=next((r for r in retests if r['track_id']==t['track_id']),{})
        row.update(distinct_schedule_ready=a['schedule']['ready'] if a else '',original_distinct_holdouts=a['original_distinct_usable'] if a else '',
            distinct_retest_status=r.get('new_status',''),distinct_retest_norad=r.get('new_norad',''))
        ledger.append(row)
    csvfile('annotation_ledger.csv',ledger)
    summary=dict(audited=len(arows),schedule_ready=sum(r['schedule_ready'] for r in arows),
        previously_insufficient_newly_ready=sum(r['previous_status']=='insufficient_partitions' and r['schedule_ready'] for r in arows),
        previously_supported_repeated_target_holdouts=sum(r['previous_status']=='conditionally_supported_identity' and r['original_distinct_holdouts']<3 for r in arows),
        retest_outcomes={g:dict(Counter(r['new_status'] for r in retests if r['category']==g)) for g in ['newly_eligible','retest_supported']},
        inventory_assessed=sum(bool(r['annotation_source']) for r in ledger),inventory_total=len(ledger),no_production_change=True)
    write(out/'summary.json',summary);write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f,separators=(',',':'))
    display=[dict(scan=r['scan'],track=r['component'].split('-RX')[-1],points=r['points'],old=r['previous_status'].replace('_identity',''),new=r['new_status'].replace('_identity',''),satellite=r['new_norad']) for r in retests]
    text=f'''# Large-track annotation: distinct randomized validation blocks

All {len(arows)} inventoried DS24 tracks received a timestamp-only audit. {summary['schedule_ready']} can support the declared three distinct usable target holdouts within the frozen seed pool. Nineteen previously insufficient tracks become testable; this does not itself establish their identity. Of 122 previously conditionally supported identities, 91 used fewer than three distinct target holdouts. Eight of the 82 retestable cases were selected by descending point count for this iteration; nine cannot satisfy the stricter schedule within the tested pool. Their original labels remain recorded, with reduced validation diversity explicitly flagged.

![Partition counts](figures/partition_coverage.png)

## Protocol

Keep 12-second scan-wide blocks, 2-second guards, at least eight target training points and four target held points. Start with seeds 20261029, 94721 and 4081, then 64 integers generated by NumPy default_rng(20261029). Select the first three usable **distinct sets of held target blocks**. Selection uses timestamps and sample counts only, before observing candidate fits or evaluation errors. Whole blocks share assignments across receivers and channels. The original 25% selection rule uses ceiling rounding separately for target and other blocks, so the held point fraction need not equal 25%.

The frozen selection is replayed and checked against current timestamps before fitting. No match, noise or residual gate was relaxed. Candidate search still uses the causal catalogue, training-only nominations and matched c=0/fitted-c arms. The graph and incumbent identities remain frozen full-recording inputs. Distinct partitions still overlap in training data and are **not three independent datasets**. Failure to find a schedule in 67 seeds is not proof that no partition exists.

![Example partitions](figures/partition_example.png)

The example shows target timestamps with the complete scan-wide assignments, including guards from background blocks. Gray is training, red held, yellow excluded by guards.

## Frozen size-ranked retest

Eight largest newly eligible tracks and eight largest previously supported tracks with repeated holdouts were selected without GPS error. This is a targeted diagnostic cohort, not a random estimate of dataset-wide performance. Partial executions remain explicit; no candidate is accepted by this report.

{table(display,list(display[0]))}

![Per-partition margins](figures/retest_margins.png)

Each dot is one c arm and partition. A large score margin is not a calibrated identity probability. Consistent identities additionally require held target RMS ≤450 Hz, phase refresh convergence ≤0.01 s and nonnegative elevation. Existing score definitions and uncertainty approximations are unchanged; see the previous [annotation protocol](../2026_10_29_systematic_track_annotation/README.md).

## Position insertion

Newly supported curved targets are tested individually with their stable partition-derived alias. Each proposal has a matched control, the same priors, original noise/weights, existing predictive observations, five phase refreshes and 48 position iterations per round. Both c arms start at the existing regional center in the 25 × 25 km box. Satellite identities are fixed for these insertion tests. GPS is used only to compute the reported error. No old points may be lost under the existing paired research rule. Passing these checks alone does not establish position improvement.

'''
    if inclusions:
        rows=[dict(scan=r['scan'],arm=r['arm'],error_km=f"{r['control_error_km']:.3f} → {r['trial_error_km']:.3f}",added=r['added'],lost=r['lost'],control_pass=r['control_pass'],proposal_pass=r['trial_pass'],target_pass=r['target_pass']) for r in inclusions]
        text+=table(rows,list(rows[0]))+'\n\n![Position errors](figures/inclusion_errors.png)\n\n'+'\n\n'.join(gallery)
    else:text+='No completed insertion results were available in this snapshot.\n'
    if gate_rows:
        text+='\n\n## Exact rejection reasons\n\nThe saved objectives and every gate were replayed. No gate threshold changed. All six individual proposals fail the paired checks. Five fail residual-noise checks; DS24-0070 passes the physical and residual checks but has only one passing receiver/channel owner for its learned orbital correction.\n\n'+table(gate_rows,list(gate_rows[0]))
        text+='\n\nLow RMS alone is insufficient: DS24-0079 has approximately 30 Hz RMS but residual lag-one correlation about 0.635. DS24-0042 improves the evaluation error substantially while retaining correlated residuals. These may motivate a correctly validated discrepancy covariance or a better shared receiver/orbit model; they do not justify deleting points or relaxing a threshold based on GPS benefit.\n'
    if family_rows:
        text+='\n\n## Companion-family test\n\nDS24-0070 has a separately retested CH1 curve selecting the same satellite 67906. Because CH2 failed only owner support, we tested CH1 alone, CH2 alone and both with a shared family correction. This choice used the gate diagnosis and same-satellite evidence, not position error. The matched control and both c arms are retained.\n\n'+table(family_rows,list(family_rows[0]))+'\n\n'+'\n\n'.join(family_gallery)
    if family_diagnosis:
        text+='\n\nThe joint proposal also fails: CH1 has correlated residuals and CH2 develops a step-screen failure. Both lose usable owner support. The target curves share a residual pattern across channels, but both are on RX1. The retained model has zero other-family RX1 observations from 46 to 76 seconds, including the visible transition near 65 seconds. RX2 observations cannot by themselves determine a receiver-specific RX1 correction. This is a concrete calibration-coverage gap, not proof of a receiver step or an orbit error. The plotted correlations are descriptive after fitting, not an independent statistical test.\n\n'+table([{k:v for k,v in r.items() if k!='failures'} for r in family_diagnosis],[k for k in family_diagnosis[0] if k!='failures'])
        text+='\n\nThe next discriminating experiment is to recover a different satellite on RX1 during that interval from the original GLRT evidence and test whether it predicts the same discrepancy. If there is no such witness, a shared receiver-discrepancy model must preserve this uncertainty; estimating a free step from these two same-family curves alone would not identify its physical cause.\n'
    text+='\n\n## A label that does not survive distinct holdouts\n\nDS24-0015 RX2 CH5 T000 previously supported 62288. Two distinct target holdouts still favor it in both c arms, with margins around 47–51. The third instead favors 69130 with margins around 70–76 and fails prediction adequacy. The correct new annotation is **unstable**, not a forced replacement with 69130. Seven of eight previously supported labels survive the stricter retest; one does not. This illustrates why repeat seed counts cannot substitute for checking which target samples were actually withheld.\n'
    text+=f'''\n\n## Scope and next decisions

The full ledger contains {len(ledger)} unique large graph tracks, of which {summary['inventory_assessed']} have explicit annotation outcomes. DS24's 289 outcomes include insufficient support, ambiguity and mismatch; they are not 289 recovered tracks. Missing exports and coherent GLRT curves never selected into the graph remain outside this denominator. All original annotations and the predictive-role disagreements from the previous report remain preserved. New distinct-holdout conclusions occupy separate ledger columns.

This iteration changes research validation tooling only. It does not increase production GLRT coverage, revise an ALGO release or establish the 500 m goal. The next decisions should distinguish identity uncertainty, residual-model failure, lost incumbent evidence and weak position information. More fitted points must not be equated with better location accuracy.

Machine-readable evidence: [audit](partition_audit.csv), [retests](retests.csv), [ledger](annotation_ledger.csv), [summary](summary.json), [source SHA-256](sources.json), [compressed numerical evidence](evidence.json.gz). Reproduce with `tools/audit_annotation_partitions.py`, the annotators' `--partition-audit` argument and `tools/report_annotation_partition_audit.py`. Raw source paths and execution receipts are archived in the evidence; repeated observation-ID arrays and optimizer histories use hashes under the established compact-evidence convention.
'''
    (out/'README.md').write_text(text)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
