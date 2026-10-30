"""Publish receiver-witness diagnostics, held challenges and the next pair batch."""
import argparse,csv,gzip,hashlib,json,shutil
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def run(args):
    s=args.study;out=args.output;out.mkdir(exist_ok=False,parents=True);(out/'figures').mkdir()
    hashes={};verified={};evidence={}
    def load(p):
        d=read(p);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();evidence[str(p)]=compact_replays(compact_evidence(d))
        if isinstance(d,dict):
            for name,digest in d.get('source_hashes',{}).items():
                if name not in verified:verified[name]=hashlib.sha256(Path(name).read_bytes()).hexdigest()
                if verified[name]!=digest:raise ValueError('changed source '+name)
        return d
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    executions=[]
    roots=['soft-bundle-independent-witness-v1','soft-bundle-independent-witness-v2','soft-bundle-witness-held-v1',
           'graph-bundle-largest-pairs-annotation-v1','graph-bundle-largest-pairs-split-v1','graph-bundle-largest-pairs-inclusion-v1','shared-bundle-independent-witness-v1']
    for root in roots:
        for name in ('protocol.json','execution.json'):load(s/root/name)
        for p in sorted((s/root).glob('*-terminal.json')):
            d=load(p);executions.append(dict(root=root,receipt=p.name,status=d['status'],seconds=d.get('seconds'),reason=d.get('reason')))
            if d['status']!='complete':
                log=p.with_name(p.name.replace('-terminal.json','.log'));hashes[str(log)]=hashlib.sha256(log.read_bytes()).hexdigest();evidence[str(log)]=dict(log_text=log.read_text())
    csvout('executions.csv',executions)
    witness_cases=[('AUTO-3ec63849',s/'soft-bundle-independent-witness-v2/f12cd9df7dd9956f605c'),
                   ('V05',s/'soft-bundle-independent-witness-v1/b5e8d9097d2968c75fc8'),
                   ('AUTO-e565210d',s/'shared-bundle-independent-witness-v1/4a1934c3238d29ff5e11')]
    transfers=[];dominant=[];plots=[]
    for scan,folder in witness_cases:
        result=load(folder/'result.json');load(folder/'protocol.json')
        for row in result['results']:
            winner=max(row['targets'],key=lambda r:r['weight']);plots.append((scan,row['arm'],winner))
            for target in row['targets']:
                for r in target['transfers']:
                    simple=dict(scan=scan,arm=row['arm'],norad=target['target']['norad'],conditional_weight=target['weight'],
                        **{k:r[k] for k in ('relation','width_s','scaling','points','supported_points','baseline_RMS_hz','corrected_RMS_hz','correlation_on_supported')},
                        noise_pass=r['noise_after']['noise_screen_pass'],lag1_after=r['noise_after']['lag1_acf'])
                    transfers.append(simple)
                    if target is winner and r['relation']=='same_receiver' and r['scaling']=='hz' and r['width_s'] in (3,6):dominant.append(simple)
    csvout('witness_transfers.csv',transfers)
    held=[];heldroot=s/'soft-bundle-witness-held-v1'
    for seed in load(heldroot/'protocol.json')['seeds']:
        folder=heldroot/str(seed);load(folder/'protocol.json');r=load(folder/'result.json')
        for arm in r['results']:
            for q in arm['proposals']:
                base=next(p for p in arm['proposals'] if (p['norad'],p['alias'],p['width_s'])==(q['norad'],q['alias'],0))
                held.append(dict(seed=seed,arm=arm['arm'],norad=q['norad'],alias=q['alias'],width_s=q['width_s'],held_points=arm['held_points'],
                    supported_points=q['held_supported_points'],RMS_hz=q['score']['rms_hz'],baseline_RMS_hz=base['score']['rms_hz'],
                    score_change=q['score']['negative_twice_log_density']-base['score']['negative_twice_log_density'],
                    boundary_mass=q['phase_boundary_mass'],phase_gap_s=arm['training']['final_phase_change_s']))
    csvout('held_predictions.csv',held)
    batch=s/'graph-bundle-largest-pairs-annotation-v1';jobs=load(batch/'protocol.json')['jobs'];annotations=[];member_votes=[]
    for b in jobs:
        folder=batch/b['bundle_id'];r=load(folder/'result.json');load(folder/'protocol.json');a=r['annotation']
        annotations.append(dict(scan=b['job']['label'],bundle=b['bundle_id'],points=b['points'],status=a['status'],norad=a['norad'],minimum_margin=a['minimum_margin'],member_pass=r['bundle_member_checks']['passed']))
        member_votes.extend(dict(scan=b['job']['label'],**v) for v in r['bundle_member_checks']['votes'])
    csvout('pair_annotations.csv',annotations);csvout('member_identity_votes.csv',member_votes)
    splitroot=s/'graph-bundle-largest-pairs-split-v1/4a1934c3238d29ff5e11';split=load(splitroot/'result.json');load(splitroot/'protocol.json');csvout('split_identity.csv',split['rows'])
    trial=s/'graph-bundle-largest-pairs-inclusion-v1/trial';pr=load(trial/'protocol.json');control=load(trial/'control.json');addition=load(trial/'target_0.json');audit=load(trial/'exact_owner_replay.json')
    assert split['all_support_shared'] and not addition['paired_valid'] and not audit['all_verified']
    inv=load(s/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');den=inv['summary'][0]['total_GLRT'];position=[]
    for arm,v in addition['arms'].items():
        c=control['arms'][arm];diag=v['target_diagnostics'][0];noise={k:a[0].item() for k,a in batch_noise_screen(np.array(diag['residual_hz'])[None],diag['times_s']).items()}
        position.append(dict(arm=arm,control_km=error(c),proposal_km=error(v),baseline_points=len(c['proposed_associated_ids']),
            proposed_points=len(v['proposed_associated_ids']),total_GLRT=den,baseline_percent=100*len(c['proposed_associated_ids'])/den,
            proposed_percent=100*len(v['proposed_associated_ids'])/den,credited_new_points=0,target_RMS_hz=diag['RMS_hz'],lag1=noise['lag1_acf'],accepted=False))
    csvout('position_trial.csv',position)
    failed=[]
    for row in audit['rows']:
        worst={}
        for replay in row['exact_family_replays']:
            for gate,value in replay['all_gate_slacks'].items():worst[gate]=min(worst.get(gate,float('inf')),value)
        failed.extend(dict(role=row['role'],arm=row['arm'],gate=k,minimum_slack=v) for k,v in worst.items() if v<0)
    csvout('failed_gates.csv',failed)
    # Separate group status from immutable per-curve labels.
    discovery=load(s/'graph-bundle-components-v2/discovery.json');group_rows=[]
    for b in discovery['bundles']:
        row=dict(bundle=b['bundle_id'],scan=b['job']['label'],points=b['points'],members=len(b['members']),status='not_group_annotated',norad=None)
        for root in ('predictive-graph-bundle-annotation-v1','graph-bundle-component-annotation-v1','graph-bundle-largest-pairs-annotation-v1'):
            p=s/root/b['bundle_id']/'result.json'
            if p.exists():
                a=load(p)['annotation'];row.update(status=a['status'],norad=a['norad'],source=str(p))
        group_rows.append(row)
    csvout('group_status.csv',group_rows)
    prior=args.previous/'annotation_ledger.csv';hashes[str(prior)]=hashlib.sha256(prior.read_bytes()).hexdigest();shutil.copyfile(prior,out/'annotation_ledger.csv')
    ledger=list(csv.DictReader(prior.open()));assert len(ledger)==1630 and len({r['track_id'] for r in ledger})==1630
    fig,axs=plt.subplots(3,2,figsize=(14,11),layout='constrained')
    for row,(scan,folder) in zip(axs,witness_cases,strict=True):
        _,_,target=next(v for v in plots if v[0]==scan and v[1]=='fitted_c');t=np.asarray(target['target']['times_s']);r=np.asarray(target['target']['residual_hz'])
        transfer=next(q for q in target['transfers'] if q['relation']=='same_receiver' and q['width_s']==3 and q['scaling']=='hz')
        row[0].plot(t,r,'.-',lw=.6,c='#555555',label='Target residual');row[0].plot(t,transfer['prediction_hz'],c='#e69f00',label='Other-family receiver prediction')
        row[1].plot(t,transfer['residual_after_hz'],'.-',lw=.6,c='#0072b2',label='After diagnostic correction')
        row[0].set(title=f"{scan}: candidate {target['target']['norad']}");row[1].set(title=f"3 s kernel; noise screen passes: {transfer['noise_after']['noise_screen_pass']}")
        for ax in row:ax.axhline(0,c='k',lw=.5);ax.set(xlabel='Time (s)',ylabel='Residual (Hz)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Matched no-target control positions; fitted-c. Full-fit diagnostics, not accepted corrections.')
    save(fig,'receiver_witnesses.png')
    fig,axs=plt.subplots(1,2,figsize=(13,4),layout='constrained')
    for width,off,color in [(3,-.18,'#0072b2'),(6,.18,'#d55e00')]:
        rows=[r for r in held if r['norad']==60351 and r['width_s']==width];x=np.arange(len(rows))
        axs[0].bar(x+off,[r['score_change'] for r in rows],.36,color=color,label=f'{width} s')
        axs[1].bar(x+off,[r['supported_points']/r['held_points']*100 for r in rows],.36,color=color,label=f'{width} s')
    labels=[f"{r['seed']}\n{r['arm']}" for r in held if r['norad']==60351 and r['width_s']==3]
    for ax in axs:ax.set_xticks(range(len(labels)),labels,fontsize=7);ax.grid(axis='y',alpha=.2);ax.legend()
    axs[0].axhline(0,c='k',lw=.6);axs[0].set(ylabel='Corrected minus baseline predictive score',title='Positive is worse: 60351 held-block challenge')
    axs[1].set(ylabel='Held points with two-family support (%)',title='3 s correction cannot bridge withheld blocks')
    save(fig,'held_prediction.png')
    fig,axs=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    for ax,b,a in zip(axs.flat,jobs,annotations,strict=True):
        fit=b['nomination'];t=np.array(fit['times_s']);y=np.array(fit['aligned_values_hz']);groups=np.array(fit['member_indices']);order=np.argsort(t)
        for k in range(2):ax.scatter(t[groups==k],y[groups==k]/1000,s=13,label=f'Fragment {k+1}')
        ax.plot(t[order],(y-np.array(fit['residual_hz']))[order]/1000,'k--',lw=.8)
        ax.set(title=f"{a['scan']} / {a['points']} points\n{a['status']}",xlabel='Time (s)',ylabel='Alias-aligned CFO (kHz)');ax.legend(fontsize=8);ax.grid(alpha=.2)
    save(fig,'pair_curves.png')
    fig,axs=plt.subplots(1,2,figsize=(13,4),layout='constrained')
    for arm,color in [('c0','#0072b2'),('fitted_c','#d55e00')]:
        d=addition['arms'][arm]['target_diagnostics'][0];axs[0].plot(d['times_s'],d['residual_hz'],'.-',lw=.6,c=color,label=arm)
    axs[0].axhline(0,c='k',lw=.6);axs[0].set(title='63381: strong identity, correlated residuals',xlabel='Time (s)',ylabel='Profile residual (Hz)');axs[0].legend()
    x=np.arange(2);axs[1].bar(x-.18,[r['control_km'] for r in position],.36,color='#888888',label='Matched control');axs[1].bar(x+.18,[r['proposal_km'] for r in position],.36,color='#d55e00',label='Rejected addition')
    axs[1].set(xticks=x,xticklabels=[r['arm'] for r in position],ylabel='Evaluation position error (km)',title='No recovery credit for this trial');axs[1].legend()
    for ax in axs:ax.grid(alpha=.2)
    save(fig,'63381_position_and_residuals.png')
    summary=dict(new_groups_tested=len(annotations),new_supported_identity_groups=sum(r['status']=='conditionally_supported_identity' for r in annotations),
        new_position_qualified_groups=0,new_credited_points=0,group_annotated=sum(r['status']!='not_group_annotated' for r in group_rows),
        group_remaining=sum(r['status']=='not_group_annotated' for r in group_rows),production_changed=False,individual_ledger_unchanged=True,
        witness_correction_validated_for_inclusion=False,source_hashes_verified=len(verified))
    write(out/'summary.json',summary);write(out/'sources.json',dict(report_sources=hashes,verified_upstream_sources=verified))
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    text=f'''# Independent residual witnesses and the next large-fragment batch

This iteration adds a **96-point, strongly supported 63381 group** to the annotation evidence, but its position-inclusion trial remains rejected for correlated residuals. It also finds a same-receiver correction that passes a descriptive noise screen on the previously ambiguous AUTO-3ec63849 curve. That correction has **not** passed predictive validation. No additional hard-associated points or production changes are credited.

## Receiver witnesses: a partial explanation

The two previous triples and the new supported pair are evaluated at saved matched-control positions: target observations never enter the control position or receiver calibration. Incumbent residuals use exact causal orbit replay at those positions. Every witness retains physical observation IDs; a witness sharing any target observation is rejected. Receiver groups exclude the target's proposed satellite family, with at least two other families required locally. Predictions average within each family, then equally across available families, so duplicated channels do not gain extra family votes. Kernel widths 3, 6 and 12 seconds and Hz/fractional scaling are fixed before evaluation; insufficient support yields zero correction. No amplitude is fitted to the target.

The original primary check is same receiver, 6 seconds, Hz scaling. The 3-second sensitivity produces the promising AUTO-3ec63849 result; it must not be silently promoted to a preselected primary. Same-band, other-receiver, same-satellite and same-satellite/other-receiver checks are retained in [all transfer results](witness_transfers.csv). These are full-incumbent-fit diagnostics, not independent holdout evidence. For the ambiguous triples, target phase/orbit fitting still uses the target; 63381 instead uses its incumbent shared posterior.

{table(dominant,['scan','arm','norad','width_s','supported_points','baseline_RMS_hz','corrected_RMS_hz','noise_pass'])}

![Receiver witness transfer](figures/receiver_witnesses.png)

AUTO-3ec63849's 3-second same-receiver correction passes the noise screen in both c arms; the 6-second primary does not. Other-receiver evidence is much weaker. V05's preferred 63315 hypothesis improves only slightly with same-receiver witnesses and still fails. Its alternative 59770 has stronger same-satellite similarity on the same receiver, but weaker transfer from the other receiver and still fails. The conditional identity weights are not full-catalogue satellite probabilities.

One first execution refused to extend AUTO-3ec63849 to ±30-second phase support because that would leave the existing causal orbit bank. The failed receipt is preserved. A new output directory reruns it at its original ±15-second support; V05 retains the separately tested ±30-second diagnostic. No extrapolated or post-observation orbit bank is introduced.

## Randomized scanwide-block challenge: what it tests

The promising AUTO-3ec63849 case reuses its three saved randomized 12-second partitions with 2-second guards. Every held/guard observation is removed from receiver fitting and witness construction across the scan. Target training points condition phase/orbit/bias uncertainty, while held target points only evaluate prediction. Both c arms share candidates, priors, fixed 150 Hz noise, unit family powers and budgets. The same 0.025-second phase grid is used for uncorrected, 3-second and 6-second variants. Candidates and partitions were selected during previous RF development; this is a conditional challenge, not fresh unbiased model selection. Correction-estimation uncertainty is not integrated, so favorable scores alone could not authorize inclusion.

![Held prediction and support](figures/held_prediction.png)

The 3-second predictor has **zero directly supported held points in every fold/arm**. Its kernel truncation and two-family requirement cannot bridge these removed blocks. Small score/RMS changes arise through changed target-training conditioning, not a directly predicted correction inside the held blocks. The 6-second predictor supports 11/34, 16/19 and 11/20 held points but worsens the 60351 predictive score in all six fold/arm checks (about +0.58 to +1.18 negative-twice-log-density units). Thus a correction is not validated. This test challenges temporal interpolation across missing blocks; it does not disprove a contemporaneous common receiver fluctuation when independent measurements are available at the same time. No independent-point holdout or gate relaxation is substituted.

## Four largest untested pair groups

To keep progressing through the inventory, the four largest two-fragment groups not previously group-annotated were selected, one per scan, without GPS or satellite labels. This tests 96, 94, 90 and 87 points. All remain conditional on frozen graph geometry and bounded causal candidate search.

{table(annotations,['scan','points','status','norad','minimum_margin','member_pass'])}

![New pair groups](figures/pair_curves.png)

AUTO-e565210d supports **63381** across all folds and both c arms, with minimum pooled margin 116.92. Each fragment also survives a separate-label competitor challenge: all 12 member/arm/partition checks favor 63381, with minimum margin **87.43** against 10 required. Competitor nomination deliberately uses each member's held frequencies to search for counterexamples, while predictive fitting uses training only; this is adversarial screening, not unbiased validation. The other groups remain ambiguous or inconsistent across partitions. A smooth polynomial alone cannot establish a common satellite identity.

## Strong 63381 identity does not yet authorize position inclusion

The shared-family inclusion trial starts both matched variants at the regional center of the 25×25 km box, preserves existing priors and receiver calibration equations, and compares c=0 with fitted-c. The true site is used only to report error. Incumbent ownership is preserved. Exact orbit replacement is audited one family at a time. The trial retains all 96 target observations as a proposal, but fails the target's lag-one residual gate in both arms; these are **zero credited new associations**.

{table(position,['arm','control_km','proposal_km','target_RMS_hz','lag1','baseline_percent','proposed_percent','credited_new_points','accepted'])}

![63381 residuals and rejected position trial](figures/63381_position_and_residuals.png)

RMS is about 71 Hz, but residual correlation is about 0.646 against `4/sqrt(96) = 0.408`. Mean, slope, quadratic and step screens pass in the nominal target diagnostic. Exact replay still rejects the target; all negative replay slacks are retained in [failed_gates.csv](failed_gates.csv). The error reductions are only about 11–12 metres and are not accepted gains. The proposed coverage column is hypothetical, not delivered coverage.

At the no-target control position, other-satellite same-receiver correction reduces this curve to about 64 Hz RMS; same-satellite correction reduces it to about 62 Hz. Neither passes the noise screen. Same-satellite evidence from the other receiver has limited support and much smaller effect. This points toward some same-receiver structure, but does not uniquely distinguish receiver hardware, estimator bias, shared fitting effects, or remaining satellite/model errors.

## Recovery state and next work

There are now **{summary['group_annotated']} annotated group hypotheses out of 35**, leaving **{summary['group_remaining']} untested groups** in this frozen grouping pass. [group_status.csv](group_status.csv) records the group state separately from the unchanged 1,630-curve [individual ledger](annotation_ledger.csv). Supported identity and position qualification remain separate states.

The next bounded work should continue down that untested queue and investigate fast residual structure using independent observations. A principled shared receiver covariance or CFO-estimator correction would need a witness-supported timescale/amplitude, uncertainty propagation, and held-block/whole-scan validation. The present short-kernel subtraction is not ready to deploy. For 63381, revisit correlated estimation error and native GLRT peak geometry before broadening orbital freedom: identity is already strongly supported and flexible phase fitting alone would not explain the oscillatory residual evidence. Do not infer better position from extra association count or lower in-sample RMS.

## Reproduction and checks

New tools are `diagnose_soft_bundle_witnesses.py` and `validate_soft_bundle_witnesses.py`. Existing bundle annotation, split-identity challenge, shared-family inclusion and exact-owner replay tools produced the pair results. Twenty-six targeted tests pass, covering physical-ID exclusion, no target amplitude fitting, minimum family support, held/guard exclusion, conditional covariance, mixtures, bundle reconstruction, ownership and family routing. All raw outputs use exclusive directories and terminal receipts. [sources.json](sources.json), [evidence.json.gz](evidence.json.gz), [executions.csv](executions.csv) and the CSV tables preserve provenance, including the refused phase expansion. To reproduce witness diagnostics with the final CLI, explicitly set `--phase-limit` to the saved case protocol: 30 for V05 and 15 for AUTO-3ec63849; the first prototype hardcoded 30 before the bounded-range refusal prompted this option. Use `--shared` for the 63381 case. No production or ALGO version is changed.
'''
    (out/'README.md').write_text(text);print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
