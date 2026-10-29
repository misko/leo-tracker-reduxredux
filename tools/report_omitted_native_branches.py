"""Publish the frozen native-branch discovery, validation and inclusion audit."""
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
from debug_fast_graph_unassociated import read, write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from leo.analysis.research.grouped_prediction import identity_consensus
from leo.analysis.research.retained_track_likelihood import profile, whitening
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);figs=out/'figures';figs.mkdir()
    sources={};evidence={}
    def load(p):
        p=Path(p);sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p);evidence[str(p)]=r;return r
    def csvout(name,rows):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    discovery=s/'omitted-branch-discovery-v1';protocol=load(discovery/'protocol.json');branches={};scans=[];unique=set();clean=set()
    for job in protocol['jobs']:
        root=discovery/job['job_id'];pr=load(root/'protocol.json');sm=load(root/'summary.json');load(discovery/(job['job_id']+'-terminal.json'))
        label=job['label'];label='DS24-0103' if label=='AUTO-bfc006db' else label
        for method in ['graph','hough']:
            r=load(root/(method+'.json'));scans.append(dict(scan=label,job_id=job['job_id'],method=method,input_points=sm['input_points'],**sm['methods'][method]))
            for b in r['branches']:
                bid=b['branch_id'];unique.update((job['job_id'],o) for o in b['observation_ids'])
                if b['large'] and b['quality_status']=='no_structure_detected':clean.update((job['job_id'],o) for o in b['observation_ids'])
                if bid not in branches:branches[bid]=dict(scan=label,job=job,branch=b,methods=[])
                branches[bid]['methods'].append(method)
    csvout('discovery_by_scan.csv',scans)
    ledger=[]
    for bid,v in branches.items():
        b=v['branch'];ledger.append(dict(branch_id=bid,scan=v['scan'],job_id=v['job']['job_id'],methods=';'.join(v['methods']),
            **{k:b[k] for k in ['receiver','channel','rf_hz','points','span_s','start_s','end_s','RMS_hz','quality_status','large']},
            annotation='not_tested',norad='',position_trial='not_tested'))
    annroot=s/'omitted-branch-annotations-v1';load(annroot/'protocol.json');annotations=[]
    for p in sorted(annroot.glob('*/result.json')):
        r=load(p);load(p.parent/'protocol.json');load(annroot/(p.parent.name+'-terminal.json'))
        a=identity_consensus(r['folds'],score_name=r['identity_score_name']);bid=r['track_id'];v=branches[bid];b=v['branch']
        annotations.append(dict(scan=v['scan'],branch_id=bid,points=b['points'],span_s=b['span_s'],status=a['status'],norad=a['norad']))
        row=next(q for q in ledger if q['branch_id']==bid);row.update(annotation=a['status'],norad=a['norad'])
    csvout('annotations.csv',annotations)
    controls=s/'omitted-branch-controls-v1';cp=load(controls/'protocol.json');nullrows=[]
    for j in cp['jobs']:
        jid=j['job_id'];load(controls/(jid+'-terminal.json'));load(controls/jid/'protocol.json')
        for cohort,root in [('real',discovery),('scrambled',controls)]:
            for method in ['graph','hough']:
                r=load(root/jid/(method+'.json'));bb=r['branches']
                nullrows.append(dict(job_id=jid,cohort=cohort,method=method,branches=len(bb),large=sum(b['large'] for b in bb),
                    clean_large=sum(b['large'] and b['quality_status']=='no_structure_detected' for b in bb)))
    csvout('scrambled_controls.csv',nullrows)
    fits=[];checks=[];inc=s/'omitted-branch-inclusions-v1';load(inc/'protocol.json');gallery=[]
    for path in sorted(inc.glob('*/target_0.json')):
        r=load(path);c=load(path.parent/'control.json');pr=load(path.parent/'protocol.json');load(inc/(path.parent.name+'-terminal.json'))
        bid=path.parent.name;v=branches[bid];b=v['branch'];inv=load(v['job']['inventory']);total=inv['summary'][0]['total_GLRT']
        next(q for q in ledger if q['branch_id']==bid)['position_trial']='passes_checks' if r['paired_valid'] else 'rejected'
        fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
        for col,arm in enumerate(['c0','fitted_c']):
            row=r['arms'][arm];control=c['arms'][arm];d=row['native_target_diagnostics'][0];t=np.array(d['times_s'])
            raw=np.array(d['CFO_hz'])-d['predicted_CFO_hz'];terms=profile(raw,np.zeros(len(t)),*whitening(t),bias_sigma=300.)
            noise={k:np.asarray(value)[0].item() for k,value in batch_noise_screen(terms['innovations'],t).items()}
            if not np.isclose(terms['rms'][0],d['RMS_hz'],atol=1e-6):raise ValueError('residual replay mismatch')
            checks.append(dict(scan=v['scan'],arm=arm,branch_id=bid,RMS_hz=d['RMS_hz'],bias_hz=d['bias_hz'],alias=int(terms['alias'][0]),**noise))
            fits.append(dict(scan=v['scan'],branch_id=bid,arm=arm,passes=r['paired_valid'],points=b['points'],norad=pr['targets'][0]['norad'],
                control_error_km=error(control),trial_error_km=error(row),added=row['added_points'],lost=row['lost_points'],
                control_percent=100*len(control['proposed_associated_ids'])/total,proposed_percent=100*len(row['proposed_associated_ids'])/total,
                target_RMS_hz=d['RMS_hz'],calibration_change=row['linear_calibration_max_difference'],
                control_objective=control['negative_twice_elbo'],trial_objective=row['negative_twice_elbo']))
            axs[0,col].scatter(t,np.array(d['CFO_hz'])/1000,s=14,label='Native GLRT + integer alias')
            axs[0,col].plot(t,np.array(d['predicted_CFO_hz'])/1000,color='#cc3311',label='Causal orbit + shared model')
            axs[1,col].plot(t,d['residual_hz'],'.-',label='Profiled residual')
            axs[1,col].axhline(0,color='black',lw=.7)
            axs[0,col].set(title=arm,ylabel='Unwrapped CFO (kHz)');axs[1,col].set(xlabel='Scan time (s)',ylabel='Residual (Hz)')
            for ax in axs[:,col]:ax.grid(alpha=.2);ax.legend(fontsize=8)
        fig.suptitle(f"{v['scan']} RX{b['receiver']} CH{b['channel']} / NORAD {pr['targets'][0]['norad']} / {b['points']} native points\n"+
            ('Passes existing checks; research only' if r['paired_valid'] else 'REJECTED: residual structure remains'))
        fig.savefig(figs/(bid+'.png'),dpi=140);plt.close(fig);gallery.append(f"### {v['scan']}\n\n![Orbit and residual](figures/{bid}.png)\n")
    csvout('position_trials.csv',fits);csvout('residual_checks.csv',checks);csvout('native_branch_ledger.csv',ledger)
    csvout('large_native_branches.csv',[r for r in ledger if r['large']])
    with gzip.open(out/'native_memberships.json.gz','wt') as f:json.dump({k:v['branch']['observation_ids'] for k,v in branches.items()},f)
    # Preserve all previously published role/retest annotations, then merge terminal batch 13.
    old=Path(__file__).resolve().parents[1]/'reports/2026_10_29_receiver_gap_recovery/annotation_ledger.csv'
    sources[str(old)]=hashlib.sha256(old.read_bytes()).hexdigest();original=list(csv.DictReader(old.open()));q=s/'systematic-annotation-v1'
    selected=load(q/'attempt-13/selected.json');selected_ids={r['track_id'] for r in selected};batch=[]
    for row in original:
        if row['track_id'] not in selected_ids:continue
        receipt=load(q/'attempt-13'/(row['track_id']+'-terminal.json'));p=q/row['track_id']/'result.json'
        if p.exists():
            r=load(p);load(p.parent/'protocol.json');a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
            row.update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),annotation_source=str(p),
                partition_policy='distinct timestamps',geometry_only_early_exit=r.get('geometry_only_early_exit',False),distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        batch.append(dict(track_id=row['track_id'],scan=row['label'],execution=receipt['status'],status=row['state']))
    csvout('annotation_ledger.csv',original);csvout('inventory_batch.csv',batch)
    summary=dict(scans=len(protocol['jobs']),input_points=sum(r['input_points'] for r in scans if r['method']=='graph'),
        proposed_unique_points=len(unique),distinct_native_proposals=len(branches),large_proposals=sum(r['large'] for r in ledger),
        clean_large_proposals=sum(r['large'] and r['quality_status']=='no_structure_detected' for r in ledger),clean_large_unique_points=len(clean),
        tested_annotations=len(annotations),supported_annotations=sum(r['status']=='conditionally_supported_identity' for r in annotations),
        inclusion_passes=sum(r['passes'] for r in fits if r['arm']=='c0'),qualified_added_points=sum(r['added'] for r in fits if r['arm']=='c0' and r['passes']),
        original_inventory=len(original),original_assessed=sum(bool(r['annotation_source']) for r in original),batch_execution=dict(Counter(r['execution'] for r in batch)))
    write(out/'summary.json',summary)
    fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for method,color in [('graph','#4477aa'),('hough','#ee6677')]:
        rr=[r for r in scans if r['method']==method];vals=np.sort([r['points'] for r in rr])
        axs[0].plot(vals,np.arange(1,len(vals)+1)/len(vals),label=method,color=color)
        counts=[sum(r['large'] for r in nullrows if r['method']==method and r['cohort']==c) for c in ['real','scrambled']]
        offset=-.18 if method=='graph' else .18;axs[1].bar(np.arange(2)+offset,counts,.35,label=method,color=color)
    axs[0].set(xlabel='Proposed native points per scan (all sizes)',ylabel='Fraction of 93 scans');axs[1].set(xticks=[0,1],xticklabels=['Real','Block scrambled'],ylabel='Large proposals in matched 9 scans')
    for ax in axs:ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Discovery proposals are not accepted satellite associations');fig.savefig(figs/'discovery.png',dpi=145);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for ax,arm in zip(axs,['c0','fitted_c'],strict=True):
        rr=[r for r in fits if r['arm']==arm]
        for i,r in enumerate(rr):
            ax.plot([i,i],[r['control_error_km'],r['trial_error_km']],c='#777777');ax.scatter(i,r['control_error_km'],marker='_',s=140,c='black')
            ax.scatter(i,r['trial_error_km'],marker='o' if r['passes'] else 'x',c='#228833' if r['passes'] else '#cc3311',s=55)
        ax.set(xticks=range(len(rr)),xticklabels=[r['scan'] for r in rr],title=arm,ylabel='Evaluation error (km)');ax.tick_params(axis='x',rotation=45);ax.grid(alpha=.2)
    fig.suptitle('Black bars: matched controls. Green: passes checks. Red: rejected trials.');fig.savefig(figs/'position_errors.png',dpi=145);plt.close(fig)
    write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f,separators=(',',':'))
    headline=[dict(scan=r['scan'],arm=r['arm'],passes=r['passes'],added=r['added'],before_km=r['control_error_km'],after_km=r['trial_error_km'],before_percent=r['control_percent'],proposed_percent=r['proposed_percent']) for r in fits]
    text=f"""# Systematic recovery of native GLRT branches — 2026-10-29

Across all **{summary['scans']} available frozen DS24 exports**, the two existing track builders found **{summary['large_proposals']} distinct large proposals** outside the original graph. **{summary['clean_large_proposals']}** pass the polynomial residual screen, covering **{summary['clean_large_unique_points']} unique native points**. These are proposals with overlapping alternatives, not 93 newly established physical tracks.

Of eight frozen large-branch tests, six have a consistent causal satellite nomination across three distinct randomized holdouts and both c arms. Four pass the subsequent matched position-inclusion checks, adding **{summary['qualified_added_points']} points across four scans** without losing old associations. Three improve position slightly; one worsens slightly. Two other consistent nominations fail the residual structure screen. This iteration does not establish a general position-accuracy improvement and does not promote a new ALGO or change production.

## What changed

The old inventory covers 1,630 large unassociated **existing graph tracks** across the deduplicated study, including 289 in DS24. That misses native GLRT sequences never constructed into graph tracks. This supplemental pass starts with {summary['input_points']:,} native winners outside the graph and unassociated in both c arms. It separates receiver, channel and actual RF frequency, applies unchanged Graph and Hough track builders, preserves original CFO measurements plus integer alias lifts, and records every remaining point. No orbital prediction, GPS coordinate or receiver model participates in discovery.

The exact TrackConfig is archived in the evidence and matches the published DSX01 selected Graph configuration (20 fields; maximum degree four, minimum eight points, maximum slope 8,000 Hz/s). Large means at least 20 points spanning 20 seconds. Exact original-point memberships deduplicate proposals; nonidentical overlaps remain explicit alternatives. {summary['distinct_native_proposals']} proposals of all sizes cover {summary['proposed_unique_points']:,} unique native points. These are not accepted associations. Nine missing DS24 exports remain outside this 93-scan frozen corpus; this is not a claim of complete raw-data coverage.

![Discovery and controls](figures/discovery.png)

The negative control preserves within-block shapes and independently shifts circular CFO in each 12-second RX/channel/RF block. DS24-0070 plus eight uniformly sampled other scans use the same configuration. Neither method finds a large branch in these nine scrambled scans. Real matched scans produce five Graph and four Hough large proposals (overlap possible). This is a structural sanity check, not a calibrated false-discovery rate.

The DS24-0070 reference also provides an audit against the prior manually inspected gap witnesses: automatic Hough recovers 11/12 CH3-gap points; both methods recover the ten-point CH4-low branch. The five-point CH4-high branch stays below the unchanged minimum support. Thus 21 of the previous 27 provisional witness points are rediscovered without manual time/CFO windows. The earlier CH3 graph segment is deliberately excluded because it already belongs to the original graph.

## Causal identity tests

Select the largest clean large proposal per scan, then the eight largest across scans; Graph wins exact membership duplicates. No position error or satellite identity is used for selection. Annotation uses the causal catalogue and three distinct timestamp-selected randomized 12-second block holdouts, with two-second guards, the existing calibration mask, and matched c=0/fitted-c settings. All six supported cases use an already active satellite-family posterior. Support is conditional on the frozen graph, its incumbent identities, and the searched competitors; it is not independent proof of the emitter.

{table(annotations,['scan','points','span_s','status','norad'])}

## Matched inclusion results

All six supported cases were tested, with the original priors/noise, five phase-refresh rounds and 48 optimizer iterations per round, starting at the regional center in the 25×25 km box. The branch is predictive-only: it cannot directly estimate receiver offsets/drifts or orbital coefficients. At any fixed position the calibration coefficient change is zero; position movement can indirectly change the original curved-data posterior. Old graph geometry and candidate sets remain fixed. Native point ownership is explicit; legacy post-fit searching cannot silently accept the new proposal.

GPS is used only to compute these errors at 37.849061591561885, -122.48574968092912. Columns labelled proposed include points from rejected trials; those points must not be counted as accepted. Objective values are archived separately and are not evidence of localization improvement: adding data changes the objective's number of observations.

{table(headline,['scan','arm','passes','added','before_km','after_km','before_percent','proposed_percent'])}

![Matched position errors](figures/position_errors.png)

The DS24-0090 and DS24-0093 branches have RMS well below the 450 Hz limit but structured whitened innovations. Their identities can remain plausible while the shared prediction fails. The exact mean, slope, quadratic, step and autocorrelation screens are in [residual checks](residual_checks.csv). No gate was relaxed. Diagnostic residual plots below profile one constant bias; the orbit overlay includes the shared receiver model and excludes that branch-specific diagnostic bias.

DS24-0093 fails the slope screen (z=5.17/5.42 against 3), quadratic screen (BIC gain=11.33/21.00 against 10), step screen (z=5.14/5.37 against 4), and lag-one correlation screen (0.67/0.71 against 0.57), for c=0/fitted-c respectively. DS24-0090 has a broad residual bend: quadratic gain=25.45/30.24, step z=5.99/6.72, and correlation=0.77/0.75 against 0.45. Its slope passes. A step-test failure does not by itself establish a physical receiver step: a smooth bend can trigger that statistic. Neither case establishes whether the discrepancy originates in the orbit, receiver, or a wrong join; independent transfer across other receivers/families is still required.

## Inventory, reproducibility and next work

The original graph-track ledger now has **{summary['original_assessed']} / {summary['original_inventory']}** assessed entries. Batch 13 ended with {summary['batch_execution']}. Previous role disagreements and distinct-partition retests are preserved. Native proposals have a separate denominator; adding their overlapping alternatives to 1,630 would falsely imply independent tracks.

Start with [all native proposals](native_branch_ledger.csv), [large proposals](large_native_branches.csv), [exact memberships](native_memberships.json.gz), [per-scan counts](discovery_by_scan.csv), [original graph ledger](annotation_ledger.csv), [annotations](annotations.csv), [position trials](position_trials.csv), and [controls](scrambled_controls.csv). [Source hashes](sources.json) and [compressed numerical evidence](evidence.json.gz) preserve protocols, seeds, commands and terminal receipts.

Reproduce discovery with `tools/discover_omitted_graph_branches.py batch --study STUDY --output NEW_DIRECTORY`. Annotation uses `tools/annotate_predictive_only.py --native-branches METHOD_JSON --track BRANCH_ID --distinct-partitions --uncalibrated-phase-mixture --phase-step .025` plus inventory/output arguments. Inclusion uses `tools/include_predictive_annotations.py --native-branches METHOD_JSON --validation ANNOTATION_DIRECTORY` plus inventory/output arguments. Exact executed commands are in terminal receipts. Generate this report with `tools/report_omitted_native_branches.py --study STUDY --output NEW_REPORT`.

Discovery: eight workers, 120-second cap per scan. Controls: four workers, same cap. Annotation: eight workers, 600-second cap per case. Inclusion: six workers, same cap. All 93 discovery, nine control, eight annotation and six inclusion jobs completed. Fifteen focused tests passed for native measurement/alias fidelity, lane separation, point ownership, unchanged calibration membership, randomized partitions and predictive roles. No RF acquisition or QNAP mutation occurred.

Next: extend the frozen identity tests beyond these eight proposals; diagnose structured residuals using independent same-receiver and same-family evidence; retain ambiguous identities; evaluate any general model correction on a separate cohort. Recovery eligibility and position-accuracy improvement remain separate requirements.

## Orbit and residual figures

"""+'\n'.join(gallery)
    (out/'README.md').write_text(text)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
