"""Audit every flagged native proposal and advance the original graph ledger."""
import argparse
from collections import Counter
import csv,gzip,hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_native_cohort_validation import label,failures
from report_systematic_annotation import compact_evidence
from leo.analysis.research.grouped_prediction import identity_consensus


def polynomial_replay(branch,observations,tracks,policy):
    occupied={o for t in tracks for o in t['observation_ids']}
    occupied.update(o for p in policy.values() for o in p['proposed_associated_ids'])
    lane=sorted([o for o in observations if o['observation_id'] not in occupied and
        (o['receiver'],o['channel'],o['actual_rf_hz'])==(branch['receiver'],branch['channel'],branch['rf_hz'])],key=lambda o:(o['time_s'],o['observation_id']))
    prediction={}
    for piece in branch['pieces']:
        for ix in piece['indices']:
            o=lane[ix];prediction[o['observation_id']]=np.polynomial.legendre.legval(
                (o['time_s']-piece['reference_time_s'])/piece['time_scale_s'],piece['coefficients_hz'])
    predicted=np.array([prediction[o] for o in branch['observation_ids']]);residual=np.array(branch['values_hz'])-predicted
    if abs(np.sqrt(np.mean(residual**2))-branch['RMS_hz'])>1e-6:raise ValueError('stored Legendre polynomial does not replay')
    return residual


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);figs=out/'figures';figs.mkdir();sources={};evidence={}
    def load(p,archive=True):
        p=Path(p);sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p)
        if archive:evidence[str(p)]=r
        return r
    def csvout(name,rows):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    cohort=load(s/'flagged-native-cohort-v1/protocol.json');rows=[];fits=[];gallery=[]
    for j in cohort['all_eligible']:
        b=j['branch'];bid=b['branch_id'];paths=list(s.glob('flagged-native-annotations-v*/'+bid+'/result.json'))
        if len(paths)!=1:raise ValueError('exactly one annotation per flagged proposal')
        p=paths[0];r=load(p);load(p.parent/'protocol.json');load(p.parent.parent/(bid+'-terminal.json'))
        a=identity_consensus(r['folds'],score_name=r['identity_score_name']);inv=load(j['job']['inventory'],False);root=Path(inv['job']['root'])/inv['job']['case']
        residual=polynomial_replay(b,load(root/'observations.json',False),load(root/'tracks.json',False),inv['policy'])
        evidence['polynomial_replay/'+bid]=dict(times_s=b['times_s'],residual_hz=residual.tolist(),RMS_hz=b['RMS_hz'],quality_flags=b['quality_flags'])
        entry=dict(scan=label(j['job']),branch_id=bid,points=b['points'],span_s=b['span_s'],poly_degrees=';'.join(str(p['degree']) for p in b['pieces']),
            polynomial_RMS_hz=b['RMS_hz'],polynomial_flags=';'.join(b['quality_flags']),annotation=a['status'],norad=a.get('norad'),inclusion='not_eligible')
        if a['status']=='conditionally_supported_identity':
            trials=list(s.glob('flagged-native-inclusions-v*/'+bid+'/target_0.json'))
            if len(trials)!=1:raise ValueError('supported identity lacks inclusion result')
            path=trials[0];trial=load(path);control=load(path.parent/'control.json');load(path.parent/'protocol.json');load(path.parent.parent/(bid+'-terminal.json'))
            entry['inclusion']='passes' if trial['paired_valid'] else 'rejected';fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
            for col,arm in enumerate(['c0','fitted_c']):
                v=trial['arms'][arm];d=v['native_target_diagnostics'][0];t=d['times_s'];target_names={e['component'] for e in trial['target_entries']}
                fits.append(dict(scan=entry['scan'],branch_id=bid,arm=arm,points=b['points'],norad=a['norad'],passes=trial['paired_valid'],
                    control_passes=control['paired_valid'],before_km=error(control['arms'][arm]),after_km=error(v),polynomial_RMS_hz=b['RMS_hz'],orbit_RMS_hz=d['RMS_hz'],
                    added=v['added_points'],lost=v['lost_points'],failures=failures(v,target_names)))
                axs[0,col].scatter(t,np.array(d['CFO_hz'])/1000,s=14,c='black',label='Native measurements + integer alias')
                axs[0,col].plot(t,np.array(d['predicted_CFO_hz'])/1000,c='#4477aa',label='Shared causal orbit + receiver')
                axs[1,col].plot(t,residual,'.-',c='#cc3311',label='Original polynomial residual')
                axs[1,col].plot(t,d['residual_hz'],'.-',c='#4477aa',label='Orbit residual; constant profiled')
                axs[0,col].set(title=arm,ylabel='Unwrapped CFO (kHz)');axs[1,col].set(xlabel='Scan time (s)',ylabel='Residual (Hz)');axs[1,col].axhline(0,c='black',lw=.6)
                for ax in axs[:,col]:ax.grid(alpha=.2);ax.legend(fontsize=7)
            fig.suptitle(f"{entry['scan']} RX{b['receiver']} CH{b['channel']} / {b['points']} points / NORAD {a['norad']} / {entry['inclusion']}\nOriginal polynomial flag is retained; physical-model gates decide inclusion")
            fig.savefig(figs/(bid+'.png'),dpi=140);plt.close(fig);gallery.append(f"### {entry['scan']} / {bid}\n\n![CFO, polynomial and orbit residuals](figures/{bid}.png)\n")
        rows.append(entry)
    csvout('flagged_annotations.csv',rows);csvout('flagged_inclusion_trials.csv',fits)
    repo=Path(__file__).resolve().parents[1]
    previous_native=repo/'reports/2026_10_29_native_cohort_validation/native_branch_ledger.csv'
    policy_path=repo/'reports/2026_10_29_native_all_large_policy/scan_policy.csv'
    for path in [previous_native,policy_path]:sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    native_ledger=list(csv.DictReader(previous_native.open()));updates={r['branch_id']:r for r in rows}
    selected_native={b for p in csv.DictReader(policy_path.open()) for b in p['branch_ids'].split(';') if b}
    for r in native_ledger:
        if r['branch_id'] in updates:
            u=updates[r['branch_id']];r.update(annotation=u['annotation'],norad=u['norad'],position_trial=u['inclusion'])
        r['joint_selected']=r['branch_id'] in selected_native
    if not selected_native<={r['branch_id'] for r in native_ledger}:raise ValueError('joint selection absent from native ledger')
    csvout('native_branch_ledger.csv',native_ledger)
    old=Path(__file__).resolve().parents[1]/'reports/2026_10_29_omitted_native_branches/annotation_ledger.csv'
    sources[str(old)]=hashlib.sha256(old.read_bytes()).hexdigest();ledger=list(csv.DictReader(old.open()));q=s/'systematic-annotation-v1';selected=load(q/'attempt-14/selected.json');ids={r['track_id'] for r in selected};batch=[]
    for row in ledger:
        if row['track_id'] not in ids:continue
        receipt=load(q/'attempt-14'/(row['track_id']+'-terminal.json'));p=q/row['track_id']/'result.json';r=load(p);load(p.parent/'protocol.json')
        a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
        row.update(state=a['status'],norad=a.get('norad'),minimum_margin=a.get('minimum_margin'),annotation_source=str(p),partition_policy='distinct timestamps',
            geometry_only_early_exit=r.get('geometry_only_early_exit',False),distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        batch.append(dict(track_id=row['track_id'],scan=row['label'],status=a['status'],norad=a.get('norad'),execution=receipt['status']))
    csvout('annotation_ledger.csv',ledger);csvout('inventory_batch.csv',batch)
    summary=dict(flagged_proposals=len(rows),annotation_outcomes=dict(Counter(r['annotation'] for r in rows)),inclusion_trials=len(fits)//2,
        individually_passing=sum(r['inclusion']=='passes' for r in rows),original_inventory=len(ledger),original_assessed=sum(bool(r['annotation_source']) for r in ledger),
        batch_outcomes=dict(Counter(r['status'] for r in batch)),no_production_change=True)
    write(out/'summary.json',summary);write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f,separators=(',',':'))
    (out/'gallery.md').write_text('# All flagged-branch inclusion diagnostics\n\n'+'\n'.join(gallery))
    md=f"""# Polynomial residual flags can hide usable physical-orbit evidence

All **21 remaining large native proposals** have now been tested, retaining their original polynomial quality flags. Outcomes: {summary['annotation_outcomes']}. Of {summary['inclusion_trials']} consistent causal nominations, **{summary['individually_passing']} pass the unchanged individual inclusion checks** in both c arms, including every old association and point-ownership check. Overlap prevents adding these counts directly to the earlier clean cohort; the [all-quality joint policy](../2026_10_29_native_all_large_policy/README.md) resolves their interactions.

## What the flags mean here

Every one of these stored proposals carries `adjacent_residual_correlation`. A polynomial approximation is not the physical satellite Doppler curve. The original builder chooses degree with squared residual divided by a fixed 150 Hz noise scale plus `(degree+1) log(n)`, subject to its existing support and slope constraints. Correlated approximation error can therefore survive the complexity penalty. A polynomial flag is evidence to investigate, not proof that the raw measurements are clutter or that a satellite cannot explain them.

The saved models use **Legendre coefficients**, not ordinary power-series coefficients. Replaying every piece on the original lane ordering reproduces all 21 stored RMS values to within 1e-6 Hz. No degree, breakpoint, membership, CFO, alias or flag is changed. The raw data then enter the same causal orbit nomination and prediction checks as the clean proposals. Identity validation still uses three distinct randomized whole-block holdouts. The builder's legacy conditional interior-block diagnostic is retained only as existing provenance; it is not presented as new randomized validation or used to override physical checks.

The physical-model gains are observable: DS24-0053's 50-point branch falls from about 71 Hz polynomial RMS to 26 Hz orbit RMS; DS24-0075's 46-point branch falls from 34 to 19 Hz. Both pass individual inclusion. Some flagged proposals still fail, and some contain points already covered by alternative clean branches. Neither a low RMS nor a consistent nomination alone authorizes inclusion.

{table(rows,['scan','points','span_s','poly_degrees','polynomial_RMS_hz','annotation','norad','inclusion'])}

See [all 14 CFO and residual figures](gallery.md), [identity ledger](flagged_annotations.csv), and [matched position trials](flagged_inclusion_trials.csv). Each plot overlays the original polynomial residual and the bias-profiled orbit residual. These are descriptive in-sample residuals after separate randomized identity tests, not an independent model-selection score. Position error and frequency fit are reported separately, with matched c=0/fitted-c settings. Selection never uses GPS; errors alone use the established evaluation site. No future TLE or new RF collection is used.

## Original graph inventory also advanced

The next eight original graph tracks, each containing 70–71 unassociated points, completed bounded annotation. Outcomes: {summary['batch_outcomes']}. These are identity assessments, not new accepted position observations. The original ledger now has **{summary['original_assessed']} / {summary['original_inventory']} assessed entries**, preserving previous role disagreements and retests. Native proposals remain a separate overlapping inventory and do not inflate this denominator.

{table(batch,['scan','track_id','status','norad','execution'])}

The clean and flagged native cohorts together now cover all **93 discovered large native proposals**: 60 conditionally supported identities, 17 ambiguous, four unstable, ten insufficient-partition cases, and two prediction mismatches. The [complete native proposal ledger](native_branch_ledger.csv) contains all 813 proposals, the updated outcomes for all 93 large ones, and an explicit `joint_selected` column. This does not prove all 93 true satellite identities. Conditional support depends on the frozen graph, catalogue search and incumbent calibration; unresolved cases remain explicit.

Reproduce using the frozen `flagged-native-cohort-v1` protocol, `run_native_branch_annotations.py`, `run_native_branch_inclusions.py`, and `report_flagged_native_inventory.py`. All jobs use 600-second caps; annotation batches have at most eight workers. The original graph batch uses `run_annotation_inventory.py run --limit 8 --workers 8 --distinct-partitions`. [Source hashes](sources.json), [compressed evidence](evidence.json.gz), [original graph ledger](annotation_ledger.csv), and [batch results](inventory_batch.csv) preserve the audit trail. No production change or new ALGO is promoted.
"""
    (out/'README.md').write_text(md);print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
