"""Publish timing eligibility, a rejected shared-family curve, and a joint recovery."""
import argparse,csv,gzip,hashlib,json,shutil
from collections import defaultdict
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from annotation_partition_plan import require_distinct_annotation
from leo.analysis.research.grouped_prediction import replay_split
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_predictive_role_reassessment import complete_replay_slacks
from report_predictive_covariance_transfer import compact_replays
from report_systematic_annotation import compact_evidence


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();hashes={};evidence={}
    def load(p):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();v=read(p);evidence[str(p)]=compact_replays(compact_evidence(v));return v
    def copy(p,name):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();shutil.copyfile(p,out/name)
    def csvout(name,rows):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    geometry=s/'shifted-partition-inventory-geometry-v1';g=load(geometry/'summary.json');load(geometry/'protocol.json')
    authorities=load(geometry/'sources.json')
    for p,digest in authorities.items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest:raise ValueError('geometry input changed')
    copy(geometry/'rows.csv','geometry_inventory.csv');copy(geometry/'sources.json','geometry_sources.json');copy(geometry/'protocol.json','geometry_protocol.json')
    # Preserve all frozen schedules compactly, rather than publishing 34 MB of indentation.
    plans=load(geometry/'plans.json')
    with gzip.open(out/'geometry_plans.json.gz','wt') as f:json.dump(plans,f,separators=(',',':'))
    evidence.pop(str(geometry/'plans.json'))
    ar=s/'incidental-58528-shifted-validation-v1/annotation';a=load(ar/'result.json');pr=load(ar/'protocol.json');require_distinct_annotation(a,pr)
    annotation_terminal=load(ar.parent/'execution.json')
    if annotation_terminal['status']!='complete':raise ValueError('annotation incomplete')
    focus=np.asarray(pr['partition_plan']['target_times_s']);partitions=[]
    fig,axes=plt.subplots(3,1,figsize=(12,6),layout='constrained')
    for ax,f in zip(axes,a['folds'],strict=True):
        tr,he=replay_split(focus,f['split']);purged=~tr&~he
        for mask,color,label in [(tr,'#0072b2','Training'),(he,'#d55e00','Held'),(purged,'#999999','Guard')]:ax.scatter(focus[mask],np.zeros(mask.sum()),c=color,label=label)
        partitions.append(dict(seed=f['seed'],origin_s=f['split']['block_origin_s'],training=int(tr.sum()),held=int(he.sum()),held_indices=' '.join(map(str,np.flatnonzero(he)))))
        ax.set(yticks=[],title=f"Seed {f['seed']}: origin {f['split']['block_origin_s']:.3f} s; {tr.sum()} training / {he.sum()} held",xlabel='Scan time (s)');ax.legend(loc='upper right',ncol=3,fontsize=8);ax.grid(axis='x',alpha=.2)
    save(fig,'shifted_partitions.png');csvout('partitions.csv',partitions)
    joint_root=s/'joint-63388-cohort-review-v1';load(joint_root/'protocol.json');joint_execution=load(joint_root/'execution.json')
    if joint_execution[0]['status']!='RF_verified_joint_candidate':raise ValueError('joint trial not qualified')
    cases=[('28-point 58528',s/'incidental-58528-shifted-inclusion-v1/trial','target_0.json',False),
           ('52-point 63388 pair',joint_root/'dfe857973b749b61-63388/trial','new_family.json',True)]
    rows=[];failures=[];diagnostics={}
    for name,trial,file,joint in cases:
        c=load(trial/'control.json');v=load(trial/file);audit=load(trial/'exact_owner_replay.json');p=load(trial/'protocol.json')
        for path,digest in audit['source_hashes'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('replay source changed')
        qualified=bool(c['paired_valid'] and v['paired_valid'] and audit['all_verified'])
        if joint:
            common=load(trial/'common_residual_audit.json');qualified=qualified and common['reviewed_joint_candidate']
        else:
            for stage in load(trial.parent/'execution.json'):
                if stage['status']!='complete':raise ValueError('inclusion incomplete')
        targets={o for t in p['targets'] for o in t['observation_ids']}
        for arm,z in v['arms'].items():
            b=c['arms'][arm];before=set(b['proposed_associated_ids']);after=set(z['proposed_associated_ids'])
            if after-before!=targets or before-after:raise ValueError('unexpected membership scope')
            rows.append(dict(case=name,arm=arm,qualified=qualified,target_points=len(targets),before_km=error(b),after_km=error(z),
                control_objective=b['negative_twice_elbo'],addition_objective=z['negative_twice_elbo']))
            if joint:
                ds=[dict(component=d['component'],times_s=d['times_s'],CFO_hz=d['CFO_hz'],residual_hz=np.asarray(d['raw_residual_hz'])-d['profile_bias_hz']) for d in z['family']['diagnostics']]
            else:ds=z['target_diagnostics']
            diagnostics[name,arm]=ds
        for r in audit['rows']:
            for gate,slack in complete_replay_slacks(r).items():
                if slack<0:failures.append(dict(case=name,role=r['role'],arm=r['arm'],gate=gate,slack=slack))
    csvout('position_trials.csv',rows);csvout('failed_gates.csv',failures)
    fig,axes=plt.subplots(3,2,figsize=(13,10),layout='constrained');index=0
    for name,_,_,_ in cases:
        for k,d in enumerate(diagnostics[name,'fitted_c']):
            ax,bx=axes[index];index+=1;t=np.asarray(d['times_s']);y=np.asarray(d['CFO_hz']);r=np.asarray(d['residual_hz'])
            ax.plot(t,y/1000,'.',label='GLRT');ax.plot(t,(y-r)/1000,'-',label='Orbit + fitted nuisance terms');ax.set(title=name+' / '+d['component'],ylabel='CFO (kHz)');ax.legend(fontsize=7)
            for arm in ('c0','fitted_c'):
                e=diagnostics[name,arm][k];bx.plot(e['times_s'],e['residual_hz'],'.-',lw=.7,label=arm)
            bx.axhline(0,c='k',lw=.6);bx.set_ylabel('Residual (Hz)');bx.legend(fontsize=8)
            for axy in (ax,bx):axy.set_xlabel('Scan time (s)');axy.grid(alpha=.2)
    save(fig,'curves_and_residuals.png')
    batch=load(args.previous/'summary.json');ledger_path=args.previous/'annotation_ledger.csv';hashes[str(ledger_path)]=hashlib.sha256(ledger_path.read_bytes()).hexdigest();ledger=list(csv.DictReader(ledger_path.open()))
    copy(args.previous/'comparisons.csv','batch_comparisons.csv');copy(args.previous/'failed_replay_gates.csv','batch_failed_gates.csv')
    final={r['scan']:r['variant'] for r in csv.DictReader((out/'batch_comparisons.csv').open()) if r['final_variant']=='True'}
    gate_cases=defaultdict(set)
    for r in csv.DictReader((out/'batch_failed_gates.csv').open()):
        if r['variant']==final[r['scan']]:gate_cases[r['evidence_role'],r['gate'].rsplit('/',1)[-1]].add(r['scan'])
    gate_rows=[dict(evidence_role=role,gate=gate,cases=len(scans),scans='; '.join(sorted(scans))) for (role,gate),scans in sorted(gate_cases.items())]
    csvout('batch_gate_counts.csv',gate_rows)
    for r in ledger:
        if r['track_id']=='24c69d7ca55902f72724':r.update(predictive_recheck_source=str(ar/'result.json'),predictive_recheck_state=a['annotation']['status'],predictive_recheck_minimum_margin=a['annotation']['minimum_margin'],annotation_likelihood_role='predictive_only; shifted_origin_v1',predictive_inclusion_source=str(cases[0][1]),predictive_research_inclusion='inclusion_rejected')
        if r['track_id'] in ('eff44a665438eedc49a2','b00922ab759cb2f6045e'):r.update(same_family_joint_source=str(cases[1][1]),same_family_joint_status='RF_verified_joint_candidate',same_family_joint_norad=63388)
    csvout('annotation_ledger.csv',ledger)
    remaining=[r for r in load(args.previous/'remaining_role_candidates.json') if r['track_id']!='24c69d7ca55902f72724']
    write(out/'remaining_role_candidates.json',remaining)
    write(out/'summary.json',dict(geometry=g,batch=batch,remaining_role_candidates=len(remaining),incidental_identity=a['annotation'],incidental_inclusion_qualified=False,joint_points=52,production_changed=False,goal_complete=False))
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    (out/'README.md').write_text(f'''# Testing short curves without weakening the physical model

This iteration separates three questions: whether a curve has enough validation support, whether its identity is plausible, and whether it is jointly consistent with the positioning model. The 28-point RX2 CH4 curve passes the first two after a timestamp-only partition change, but fails the third. Two prior recoveries for satellite 63388 pass a joint 52-point test.

## A validation-alignment bottleneck

The 28-point AUTO-f08da5cb curve spans 78.230–105.913 seconds. Under the fixed zero-origin 12-second grid, its first block holds only three points, below the four-point minimum. Repeating random seeds produces only two usable physical holdout sets. The original insufficient-evidence result was correct under that protocol.

The new **opt-in research protocol** seeds the block origin uniformly within 12 seconds. Block width remains 12 seconds; training guards remain two seconds; each fold still needs at least eight training and four held target observations. All receivers and channels use the same scanwide split. The first three usable distinct physical holdout sets are chosen using timestamps alone from a frozen 67-seed pool. No frequencies, satellite identity, or GPS error select a partition. Existing zero-origin receipts and default behavior are unchanged.

{table(partitions,['seed','origin_s','training','held'])}

![Physical training, held, and guarded points](figures/shifted_partitions.png)

These sets overlap; in particular, the final two share twelve held points. They are **distinct tests, not three independent replications** or a calibrated association probability. This is a changed validation design, not a retroactive pass under the old design.

A timestamp-only audit of all **{g['curves']}** inventoried native curves finds 1,180 already eligible under the fixed design and **450 newly eligible** under the shifted design. Of those 450, **447 are wholly unowned**, including **419 marked insufficient partitions in the audit's input ledger**. Three are partly owned and require separate unused-fragment reconstruction. This is validation eligibility, not 450 recovered satellite associations. The audit reconstructs calibration timestamps from frozen graph rows; an exact comparison on the 28-point case matches all 2,381 context timestamps. Every frozen plan and source hash accompanies this report.

## 58528: a plausible identity still fails inclusion

The same causal candidate search favors **58528 in all three partitions and both c arms**, with minimum conditional score margin **{a['annotation']['minimum_margin']:.2f}** over the tested runner-up 66206. This search is conditional on the frozen graph and incumbent labels; it is not a proof of identity. Target points do not calibrate the receiver during annotation.

The full inclusion trial fails the target residual slope check in both arms: absolute slope z is approximately **3.76 (c=0)** and **3.26 (fitted-c)** against a limit of 3. Fitted-c RMS is only **68.5 Hz**, yet the residual declines over time. Small RMS alone hides a systematic mismatch. Exact replay reports no other negative gate slack. The target remains withheld. A next discriminating test is whether independently held observations of the existing 58528 family support the same shape correction, before adding receiver or orbital freedom.

## 63388: earlier individual recoveries also work together

The 27- and 25-point RX1 CH7 curves in AUTO-ceb24498 share one satellite phase/orbit distribution, separate existing track-bias priors, and receiver uncertainty integrated once. Both had independently supported predictive annotations. Matched Powell controls and additions, exact orbit/ownership replay, and a same-receiver common-residual audit all pass. The 52 points were already counted as individual research recoveries; this result establishes joint compatibility and does **not** add another 52 unique recovered points.

{table(rows,['case','arm','qualified','target_points','before_km','after_km'])}

![GLRT curves, fitted orbital predictions, and residuals](figures/curves_and_residuals.png)

The plotted orbital curves include the model's fitted nuisance terms; residuals include the existing per-track constant bias. Numerical objectives are recorded separately in [position_trials.csv](position_trials.csv). Controls and additions contain different target observations, so raw objective changes are not evidence of better position accuracy. The 28-point trial is standalone and is not combined with the earlier 75-point 63906 recovery from the same scan.

## Inventory progress and next work

[Batch five](../2026_10_30_predictive_role_reassessment_batch5/README.md) completes another **{batch['annotations']}** older-role annotations and **{batch['position_cases']}** position trials. **{batch['qualified_curves']} curves / {batch['qualified_points']} points** qualify in separate trials. Its complete accepted and rejected results, matched c arms, capture provenance, and figures are retained. The batch leaves {batch['remaining_role_candidates']} older-role cases; the separate 58528 assessment removes one more, leaving **{len(remaining)}**. The updated ledger here additionally records the rejected 58528 trial and jointly qualified 63388 pair while preserving prior native-IQ and family-consistency withholdings.

The newly RF-qualified 68-point AUTO-9efe3f9e / 100165 target worsens error from **352 to 453 m (c=0)** and **222 to 268 m (fitted-c)** in matched trials. It remains a research association candidate, not an accuracy improvement. This is another direct counterexample to assuming that increasing associated-point count necessarily improves localization.

The following counts use the final trial for each scan, counting a scan once per gate and evidence role across both c arms. A scan can fail several gates; these are not disjoint rejection categories. Optimizer and phase-resolution failures are separately recorded in the original trial evidence.

{table(gate_rows,['evidence_role','gate','cases'])}

Structured target residuals dominate these final trials: nine scans fail the step statistic, eight fail lag correlation, six fail slope and five fail quadratic structure. This diagnoses the checks that reject them; it does not yet distinguish orbital error, receiver error, measurement contamination, or incorrect identities. No target RMS gate fails in this batch. Incumbent failures in some cases also expose tension between newly added evidence and existing associations.

Next work is bounded shifted-origin validation of wholly unowned curves that previously lacked partition support, followed by the same physical inclusion checks. For supported identities with structured residuals, family-to-target and target-to-family prediction should precede additional nuisance flexibility. Individual successes must then be tested together and on a fresh cohort before promotion. Causal TLEs and the regional 25 × 25 km initialization are retained; evaluation GPS is used only for reporting errors. No production version changes here, and the complete annotation-and-inclusion goal remains unfinished.
''')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('study','previous','output'):p.add_argument('--'+n,type=Path,required=True)
    run(p.parse_args())
