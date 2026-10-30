"""Reproduce the frozen-inventory bundle and conditional identity-mixture report."""
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


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir()
    hashes={};evidence={};verified={}
    def load(p):
        data=read(p);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        evidence[str(p)]=compact_replays(compact_evidence(data))
        for name,digest in (data.get('source_hashes',{}) if isinstance(data,dict) else {}).items():
            if name not in verified:verified[name]=hashlib.sha256(Path(name).read_bytes()).hexdigest()
            if verified[name]!=digest:raise ValueError('source changed: '+name)
        return data
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    discovery=load(s/'graph-bundle-components-v2/discovery.json')
    protocol=load(s/'graph-bundle-components-v2/protocol.json')
    equivalence=load(s/'graph-bundle-components-v2/deduplication_equivalence.json')
    old=load(s/'graph-bundle-components-v1/discovery.json')
    assert old['bundles']==discovery['bundles'] and equivalence['selected_jobs_identical']
    groups=[dict(bundle=b['bundle_id'],scan=b['job']['label'],points=b['points'],members=len(b['members']),
        member_ids=';'.join(m['track_id'] for m in b['members']),degree=b['nomination']['degree'],
        RMS_hz=b['nomination']['RMS_hz']) for b in discovery['bundles']]
    csvout('groups.csv',groups);votes=[];comparisons=[];components=[];member_rows=[];cases=[]
    for root in ('graph-bundle-component-annotation-v1','graph-bundle-soft-position-v1','graph-bundle-soft-phase-domain-v1'):
        for name in ('protocol.json','execution.json'):load(s/root/name)
        for p in sorted((s/root).glob('*-terminal.json')):
            terminal=load(p);assert terminal['status']=='complete'
    for b in protocol['jobs']:
        bid=b['bundle_id'];folder=s/'graph-bundle-soft-position-v1'/bid
        annotation=load(s/'graph-bundle-component-annotation-v1'/bid/'result.json')
        load(s/'graph-bundle-component-annotation-v1'/bid/'protocol.json')
        pr=load(folder/'protocol.json');control=load(folder/'control.json');soft=load(folder/'soft_mixture.json')
        result=load(folder/'result.json');members=load(folder/'member_audit.json')
        assert not result['qualified_soft_research_candidate'] and result['hard_target_association_count']==0
        votes.extend(dict(scan=b['job']['label'],**v) for v in annotation['annotation']['votes'])
        for arm,v in soft['arms'].items():
            assert not set(v['soft_observation_ids'])&set(v['proposed_associated_ids'])
            comparisons.append(dict(scan=b['job']['label'],points=b['points'],arm=arm,
                control_km=error(control['arms'][arm]),proposal_km=error(v),accepted=False,
                hard_target_points=0,phase_grid_pass=v['phase_resolution_audit']['local_agreement']))
            for kind,key in [('nominal','mixture'),('continuous_target','exact_target_components')]:
                for c in v[key]['components']:
                    d=c['diagnostics'][0]
                    components.append(dict(scan=b['job']['label'],arm=arm,kind=kind,norad=c['entry']['norad'],
                        weight=c['weight'],RMS_hz=d['profile_RMS_hz'],phase_boundary_mass=c['phase_boundary_mass'],
                        **d['noise']))
        for row in members['rows']:
            for c in row['components']:
                for m in c['checks']:
                    member_rows.append(dict(scan=b['job']['label'],arm=row['arm'],kind=row['kind'],norad=c['norad'],
                        member=m['member'],points=m['points'],RMS_hz=m['RMS_hz'],passed=m['passed'],**m['noise']))
        cases.append((b,pr,annotation,soft,members))
    csvout('position_trials.csv',comparisons);csvout('identity_votes.csv',votes)
    csvout('component_gates.csv',components);csvout('member_gates.csv',member_rows)
    phase_root=s/'graph-bundle-soft-phase-domain-v1/b5e8d9097d2968c75fc8'
    phase=load(phase_root/'result.json');load(phase_root/'protocol.json');phase_rows=[]
    for r in phase['rows']:
        c=max(r['components'],key=lambda c:c['weight'])
        phase_rows.append(dict(arm=r['arm'],limit_s=r['phase_limit_s'],spacing_s=r['phase_step_s'],
            score=r['score'],phase_mean_s=c['phase_mean_s'],boundary_mass=c['phase_boundary_mass'],
            RMS_hz=c['RMS_hz'],lag1=c['noise']['lag1_acf'],compatible_member_mass=r['compatible_member_mass']))
    for p in sorted(phase_root.glob('*-*.json')):load(p)
    csvout('phase_domain.csv',phase_rows)
    fig,axs=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    for row,(b,pr,ann,soft,members) in zip(axs,cases,strict=True):
        fit=b['nomination'];t=np.array(fit['times_s']);y=np.array(fit['aligned_values_hz']);mi=np.array(fit['member_indices'])
        for k in range(len(b['members'])):row[0].scatter(t[mi==k],y[mi==k]/1000,s=16,label=f'Fragment {k+1}')
        idx=np.argsort(t);row[0].plot(t[idx],(y-np.array(fit['residual_hz']))[idx]/1000,'k--',lw=1,label='Geometric polynomial')
        row[0].set(title=f"{b['job']['label']}: {b['points']} points",xlabel='Time (s)',ylabel='Alias-aligned CFO (kHz)')
        for arm,color in [('c0','#0072b2'),('fitted_c','#d55e00')]:
            c=max(soft['arms'][arm]['exact_target_components']['components'],key=lambda c:c['weight']);d=c['diagnostics'][0]
            row[1].plot(d['times_s'],np.array(d['raw_residual_hz'])-d['profile_bias_hz'],'.-',lw=.7,c=color,label=f"{arm}: {c['entry']['norad']}")
        row[1].axhline(0,c='k',lw=.6);row[1].set(title='Dominant hypothesis: structured residuals remain',xlabel='Time (s)',ylabel='Profile residual (Hz)')
        for ax in row:ax.grid(alpha=.2);ax.legend(fontsize=8)
    save(fig,'curves_and_residuals.png')
    fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        rows=[r for r in comparisons if r['arm']==arm];x=np.arange(len(rows))
        ax.bar(x-.18,[r['control_km'] for r in rows],.36,color='#888888',label='Matched control')
        ax.bar(x+.18,[r['proposal_km'] for r in rows],.36,color='#d55e00',label='Rejected soft trial')
        ax.set(xticks=x,xticklabels=[r['scan'] for r in rows],ylabel='Evaluation position error (km)',title=arm);ax.legend();ax.grid(axis='y',alpha=.2)
    save(fig,'position_trials.png')
    fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for arm,color in [('c0','#0072b2'),('fitted_c','#d55e00')]:
        for limit,style in [(15,'--'),(30,'-')]:
            detail=load(phase_root/f'{arm}-{limit}-0.025.json')['detail'];c=max(detail['components'],key=lambda c:c['weight'])
            axs[0].plot(c['phase_grid_s'],np.array(c['phase_weights'])/.025,style,c=color,label=f'{arm}, ±{limit}s')
        rows=[r for r in phase_rows if r['arm']==arm]
        axs[1].plot(np.arange(len(rows)),[r['lag1'] for r in rows],'o-',c=color,label=arm)
    axs[0].axvline(-15,c='k',lw=.6);axs[0].set(xlim=(-15.2,-14.5),xlabel='Phase (s)',ylabel='Conditional phase density (1/s)',title='V05: widening support barely shifts phase')
    axs[1].axhline(4/np.sqrt(81),c='k',ls='--',label='81-point gate')
    axs[1].set(xticks=range(4),xticklabels=['±15/.025','±20/.025','±30/.025','±30/.0125'],ylabel='Lag-one residual correlation',title='Same endpoint and receiver fit; still fails')
    for ax in axs:ax.legend(fontsize=8);ax.grid(alpha=.2)
    save(fig,'phase_domain.png')
    ledger=args.previous/'annotation_ledger.csv';hashes[str(ledger)]=hashlib.sha256(ledger.read_bytes()).hexdigest()
    rows=list(csv.DictReader(ledger.open()));assert len(rows)==1630 and len({r['track_id'] for r in rows})==1630
    shutil.copyfile(ledger,out/'annotation_ledger.csv')
    summary=dict(frozen_curves=discovery['frozen_inventory_size'],scans=len(discovery['scans']),
        eligible_unowned=sum(r['eligible_unowned_tracks'] for r in discovery['scans']),excluded=len(discovery['exclusions']),
        unique_edges=len(discovery['edges']),groups=len(groups),pairs=sum(r['members']==2 for r in groups),
        triples=sum(r['members']==3 for r in groups),tested_bundles=len(cases),accepted_bundles=0,new_hard_associated_points=0,
        ledger_unchanged=True,production_changed=False,verified_source_hashes=len(verified))
    write(out/'summary.json',summary);write(out/'sources.json',dict(report_sources=hashes,verified_upstream_sources=verified))
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    text=f'''# Full-inventory fragment grouping and uncertain satellite identity

The frozen inventory now has a systematic geometric grouping pass across **1,630 curves in 254 scans**. It nominates **35 groups: 33 pairs and two triples**. Both triples have been tested with hard identity checks and a new conditional satellite-label mixture. **Neither qualifies for inclusion; zero additional hard-associated points are credited.** This is research code, with no production or ALGO promotion.

## Inventory and grouping

Of 1,630 curves, 1,582 are currently large and wholly unowned. The other 48 are excluded as no longer current-large or partially owned. Groups use the same receiver, channel and RF; overlap or gap at most 12 seconds; disjoint observation IDs and timestamps; consistent integer alias lifts around every cycle; one order 1–4 BIC-selected polynomial with a 150 Hz noise floor; and both pooled and individual-member RMS below 250 Hz. At least three 12-second timestamp blocks are required. No satellite or GPS selects the grouping. Nomination is conditional on the frozen graph and full CFO data, not independent validation of track construction.

There are 39 unique pair edges connecting 72 curves into 35 groups; 1,510 eligible curves have no nominated edge. An initial discovery file counted repeated c-arm rows as separate edges (156). Deduplication reduced that to 39 while preserving **every bundle's measurements, integer lifts, and selected jobs exactly**. The original annotation inputs remain immutable; the equivalence receipt and hashes are included. The [individual annotation ledger](annotation_ledger.csv) is unchanged; [group hypotheses](groups.csv) are separate and do not authorize joins.

## Identity uncertainty survives pooling

The largest eligible groups with at least three members and at most 180 points, from distinct scans, were selected automatically. These are AUTO-3ec63849 (87 points) and V05 (81 points). Each receives three distinct random scanwide 12-second block partitions with two-second guards, matching c=0 and fitted-c candidates, priors and budgets. These are randomized blocks, not point-wise or chronological holdouts.

AUTO-3ec63849 favors 60351 in all six fold/arm comparisons, but the weakest margin over 61217 is only 2.65 against the required 10. V05 alternates between incumbent 59770 and new-family 63315. This demonstrates unresolved identity within the tested candidate set; neither is a verified satellite assignment.

![Curves and residuals](figures/curves_and_residuals.png)

## Conditional satellite-label mixture

The prototype freezes the union of candidates within 20 negative-twice-log-density units of a fold's winner, with held RMS at most 450 Hz, phase closure at most 0.01 s and nonnegative elevation, in both c arms of at least one fold. This is RF-only development selection using saved held scores, not a new independent validation set. Candidates are 60351/61217/67196 for AUTO-3ec63849 and 59770/63315 for V05.

It scores `-2 log(sum_j prior_j * exp(-score_j/2))`, with equal family priors and equal alias priors within each family. New-family components integrate causal phase, physical orbital uncertainty and receiver uncertainty. Known-family components condition the full coefficient covariance on incumbent predictive observations once, then evaluate the target conditional density. Targets do not update receiver calibration at a fixed position. A Gaussian joint-minus-incumbent-density test verifies this conditioning.

This mixture is conditional on the nominated bundle and candidate subset, **has no clutter component**, and cannot be interpreted as a full-catalogue identity probability. A concentrated conditional weight is not permission to label or count the points. Continuous-phase/exact-target checks, member checks with the same bundle bias, incumbent exact-family replay, ownership preservation and numerical integration checks remain mandatory. At least 99% of conditional component weight must satisfy physical checks.

## Matched position trials: both rejected

Both arms start at the center of the same 25×25 km box, with five phase-refresh rounds and matched Powell budgets (48 iterations / 240 evaluations per round). The regional center is 37.906, -122.545. The true site 37.849061591561885, -122.48574968092912 is used only here to report error. No future TLE is used. Candidate selection never sees these errors.

{table(comparisons,['scan','points','arm','control_km','proposal_km','accepted','hard_target_points','phase_grid_pass'])}

![Rejected position trials](figures/position_trials.png)

V05 improves by about 220 m in both experimental arms, while AUTO-3ec63849 worsens by about 140–200 m. **These are rejected trial outcomes, not delivered position improvements.** Both show structured residuals despite small RMS. Continuous-phase checks still fail; individual member checks also prevent pooled residual cancellation. The 0.1-second quadrature fails its score/gradient audit. AUTO's 0.05/0.025-second results agree much better; V05 needs a separate boundary diagnostic. See [all component gates](component_gates.csv), [member gates](member_gates.csv), and [identity votes](identity_votes.csv).

## V05 phase boundary: a real diagnostic issue, not the recovery

The original 0.1-second grid placed about 52–56% of its conditional phase mass in the outer 0.1 seconds of the ±15-second support. That is not a claim that this mass lies outside the support. At the saved positions and fixed receiver fits, the diagnostic evaluates ±15, ±20 and ±30 seconds on a 0.025-second grid, plus ±30 on a 0.0125-second grid. It uses only the existing causal orbit bank and refuses extrapolation. Prior mean, scale and degrees of freedom stay fixed; the normalized integration support changes, so scores across limits are not identical-prior comparisons.

{table(phase_rows,['arm','limit_s','spacing_s','phase_mean_s','boundary_mass','RMS_hz','lag1','compatible_member_mass'])}

![Phase range and residual correlation](figures/phase_domain.png)

Expanded support removes boundary mass but moves the phase mean only about 0.008–0.009 seconds. The ±30 scores agree within 0.000006 between the two fine grids at these endpoints. RMS stays about 109 Hz and lag-one residual correlation stays about 0.738, above `4/sqrt(81) = 0.444`. The same member failures persist. **The phase cutoff does not explain the residual structure at these endpoints.** This fixed-endpoint diagnostic does not establish convergence of a new position fit or its gradient.

## What we learned and next tests

Combining fragments can expose satellite ambiguity that single-fragment screening misses. Allowing a soft label does not solve an inadequate waveform model: high conditional identity confidence can coexist with correlated residuals. These tests do not yet distinguish satellite-model error, receiver error, peak-tracking bias, or an imperfect join. Nor do they prove the curves contain no position information.

Next, investigate whether residual discrepancies repeat at the same times on independently associated curves: shared across satellites in one receiver/band suggests receiver structure; shared by one satellite across receivers suggests orbit/transmitter structure. Any extra correction needs independent support and matched c-arm validation. In parallel with that scientific direction, the 33 pair hypotheses provide the next bounded inventory queue, deduplicated against previously tested groups. Do not indefinitely tune these two scans, relax noise gates to reach coverage, or count soft probability as hard association.

## Reproduction and evidence

Tools: `discover_graph_bundle_components.py`, `predictive_label_mixture.py`, `run_soft_bundle_position.py`, `audit_soft_bundle_members.py`, `audit_soft_phase_domain.py`, and this report generator. Terminal receipts, immutable protocols, compact replay evidence, and source hashes are in [evidence.json.gz](evidence.json.gz) and [sources.json](sources.json). [summary.json](summary.json) records counts. Existing default phase support remains ±15 seconds; expanded support is opt-in research only. The 1,630-row ledger remains unique and unchanged.

Validation: 45 targeted tests pass across label-mixture normalization, shared-family conditional covariance, member-bias vetoes, bounded phase support, grouping/alias consistency, bundle ownership, family routing, randomized partitions, phase-resolution checks and predictive likelihoods. Report generation verifies 522 upstream source hashes, terminal completion, unchanged bundle measurements across deduplication, unique ledger identities, and no target leakage into hard associations. These tests validate implementation invariants; they do not qualify the rejected physical fits.
'''
    (out/'README.md').write_text(text)
    print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
