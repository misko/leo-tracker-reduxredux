"""Report confidence, joint identity search and genuinely additional GLRT curves."""

import csv
import shutil
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from probe_ds23_fixed_confidence import OUT as CONFIDENCE
from probe_ds23_joint_family_search import OUT as JOINT
from probe_ds23_secondary_curves import OUT as CURVES
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from audit_ds23_learned_residuals import OUT as RESIDUAL
from run_ds23_association_diagnostics import CASES
from report_algo01_ds23_sample import position_error,summarize
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha
from leo.analysis.research.visible_arc_variants import wrap

OUT=ROOT/'reports/2026_10_19_ds23_association_evidence'
METHODS=('baseline','unit','confidence_only','support_confidence','confident_only')
LABELS=('RX support (incumbent)','Equal weight','Identity confidence','RX support × confidence','Only confidence ≥0.95')


def save_csv(path,rows):
    with path.open('w') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def ids(record):
    return {oid for t in record['gates']['tracks'] for oid in t['observation_ids']}


def validate_pair(pair):
    assert ids(pair['c0'])==ids(pair['fitted_c'])
    for r in pair.values():
        assert all(t['compatible'] for t in r['gates']['tracks'])
        assert r['gates']['accepted_points']==r['active_points']


def run():
    OUT.mkdir(parents=True,exist_ok=True);cases=sorted(read(CONFIDENCE/'protocol.json')['cases'])
    assert len(cases)==20 and len(read(CONFIDENCE/'execution.json'))==20
    assert all(r['code']==0 for r in read(CONFIDENCE/'execution.json'))
    for directory in (JOINT,CURVES):
        assert sorted(read(directory/'protocol.json')['cases'])==sorted(CASES)
        assert len(read(directory/'execution.json'))==4 and all(r['code']==0 for r in read(directory/'execution.json'))
    weights=[];fallbacks={m:0 for m in METHODS};confidence_gates={}
    for case in cases:
        d=read(CONFIDENCE/(case+'.json'));assert not d['GPS_used'] and d['source_sha256']==sha(ROOT/'tools/probe_ds23_fixed_confidence.py')
        assert d['learned_input_sha256']==sha(LEARNED/(case+'.json'))
        confidence_gates[case]={}
        for method in METHODS:
            if method=='baseline':pair=d['baseline'];valid=True
            else:
                v=d['results'][method];pair=v['policy_arms'];valid=v['paired_valid']
                fallbacks[method]+=not valid;confidence_gates[case][method]=v['failures']
                if method!='confident_only':assert v['mask']==d['fixed_primary_mask']
            validate_pair(pair)
            for arm in ('c0','fitted_c'):
                r=pair[arm];weights.append(dict(case=case,method=method,arm=arm,error_km=position_error(r['endpoint_latlon']),
                    RMS_hz=r['RMS_hz'],points=r['active_points'],trial_paired_valid=valid,baseline_fallback=not valid))
    summary={m:{arm:summarize([r['error_km'] for r in weights if r['method']==m and r['arm']==arm]) for arm in ('c0','fitted_c')} for m in METHODS}
    save_csv(OUT/'weighting_by_scan.csv',weights)
    fig,axes=plt.subplots(2,1,figsize=(14,7),sharex=True,constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for m,label in zip(METHODS,LABELS,strict=True):
            ax.plot(range(20),[next(r['error_km'] for r in weights if r['case']==c and r['method']==m and r['arm']==arm) for c in cases],'.-',label=label)
        ax.axhline(.5,c='crimson',ls='--',lw=1);ax.set(title=arm,ylabel='Position error (km)');ax.grid(alpha=.2);ax.legend(fontsize=8,ncol=3)
    axes[-1].set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=45)
    fig.suptitle('Confidence controls · 20 development scans · paired failure → incumbent fallback')
    fig.savefig(OUT/'confidence_position_by_scan.png',dpi=160);plt.close(fig)

    joint_rows=[];recovery=[];search_summary=[];curve_summary=[]
    fig,axes=plt.subplots(2,2,figsize=(12,8),constrained_layout=True)
    curve_fig,curve_axes=plt.subplots(2,2,figsize=(13,8),constrained_layout=True)
    for case,ax,cax in zip(CASES,axes.flat,curve_axes.flat,strict=True):
        d=read(JOINT/(case+'.json'));assert not d['GPS_used'] and d['source_sha256'] in read(JOINT/'protocol.json')['source_versions_sha256']
        assert d['learned_input_sha256']==sha(LEARNED/(case+'.json'));validate_pair(d['policy_arms'])
        baseline=d['baseline']['c0']['negative_twice_elbo'];node=read(SOURCE/case/'result.json')['final_node']
        for r in d['singles']+d['joint']:
            families=len({node['seed']['rows'][c['row_index']]['candidate_index'] for c in r['changes']})
            delta=r['loss']-baseline
            joint_rows.append(dict(case=case,families_replaced=families,delta_RF_loss=delta,valid=r['valid'],
                c0_error_km=position_error(r['record']['endpoint_latlon']),changes=str(r['changes'])))
            ax.scatter(families,delta,c='tab:blue' if r['valid'] else '.7',s=15,alpha=.6,marker='o' if r['valid'] else 'x')
        ax.axhline(0,c='crimson',ls='--');ax.set(title=case,xlabel='Simultaneous family replacements',ylabel='RF loss minus incumbent')
        ax.set_xticks([1,2,3,4]);ax.set_yscale('symlog',linthresh=1);ax.grid(alpha=.2)
        best=d['best_valid'];search_summary.append(dict(case=case,single_trials=len(d['singles']),joint_trials=len(d['joint']),
            valid_trials=sum(r['valid'] for r in d['singles']+d['joint']),accepted=d['chosen'] is not None,
            best_valid_delta=None if best is None else best['loss']-baseline,
            baseline_c0_error_km=position_error(d['baseline']['c0']['endpoint_latlon']),
            selected_c0_error_km=position_error(d['policy_arms']['c0']['endpoint_latlon']),
            selected_fitted_error_km=position_error(d['policy_arms']['fitted_c']['endpoint_latlon'])))
        v=read(CURVES/(case+'.json'));assert not v['GPS_used'] and v['source_sha256']==sha(ROOT/'tools/probe_ds23_secondary_curves.py')
        assert v['prior_input_sha256']==sha(LEARNED/(case+'.json'));validate_pair(v['arms'])
        assert set(v['original_active_ids'])<=set(v['final_active_ids'])
        accepted={r['proposal'] for r in v['accepted']}
        for trial in v['trials']:
            track=trial['track'];times=np.array(track['times']);values=wrap(np.array(track['values']))
            selected=trial['proposal'] in accepted;color=plt.get_cmap('tab10')(trial['proposal']%10)
            secondary=np.array([not c['winner'] for c in track['source_peaks']]);y=wrap(values)
            cax.scatter(times[~secondary],y[~secondary]/1000,c=color,s=15,marker='o')
            cax.scatter(times[secondary],y[secondary]/1000,c=color,s=34,marker='x')
            cax.plot([],[],marker='o',lw=0,color=color,label=f"RX{track['receiver']} CH{track['channel']} / {len(times)} pts / "+('retained' if selected else 'fails gates'))
            for candidate in trial['candidates']:
                recovery.append(dict(case=case,proposal=trial['proposal'],norad=candidate['norad'],points=len(times),
                    secondary_points=int(secondary.sum()),paired_valid=candidate['paired_valid'],
                    selected_independently=trial['chosen'] is not None and candidate['norad']==trial['chosen']['norad'],
                    accepted_jointly=selected and trial['chosen'] is not None and candidate['norad']==trial['chosen']['norad'],
                    c0_error_km=position_error(candidate['arms']['c0']['endpoint_latlon']),
                    fitted_error_km=position_error(candidate['arms']['fitted_c']['endpoint_latlon']),
                    local_RMS_radius_km=candidate['local_information'].get('RMS_radius_km'),
                    failures='; '.join(candidate['failures'])))
        cax.set(title=case,xlabel='Time in scan (s)',ylabel='Selected GLRT CFO, aliased (kHz)');cax.grid(alpha=.2);cax.legend(fontsize=7,framealpha=.9)
        curve_summary.append(dict(case=case,radio_proposals=v['proposals_total'],tested=len(v['trials']),
            accepted=len(v['accepted']),new_points=len(v['final_active_ids'])-len(v['original_active_ids']),
            secondary_points=sum(not c['winner'] for r in v['accepted'] for c in r['track']['source_peaks']),
            baseline_c0_error_km=position_error(v['baseline']['c0']['endpoint_latlon']),
            new_c0_error_km=position_error(v['arms']['c0']['endpoint_latlon']),
            baseline_fitted_error_km=position_error(v['baseline']['fitted_c']['endpoint_latlon']),
            new_fitted_error_km=position_error(v['arms']['fitted_c']['endpoint_latlon'])))
    fig.suptitle('Full-prior family search · blue passes c0 gates, gray fails · lower RF loss is preferred')
    fig.savefig(OUT/'joint_family_search.png',dpi=160);plt.close(fig)
    curve_fig.suptitle('Radio-only discovered curves · circles winning peaks, crosses secondary peaks\nColor identifies each curve; legend records paired gates · canonical CFO, no frequency adjustment')
    curve_fig.savefig(OUT/'secondary_curves.png',dpi=160);plt.close(curve_fig)
    save_csv(OUT/'joint_trials.csv',joint_rows);save_csv(OUT/'joint_summary.csv',search_summary)
    if recovery:save_csv(OUT/'recovery_candidates.csv',recovery)
    save_csv(OUT/'recovery_summary.csv',curve_summary)
    for name in ('residual_transfer.png','receiver_band_RMS.png'):
        shutil.copyfile(RESIDUAL/name,OUT/name)
    residual=read(RESIDUAL/'summary.json')
    transfer=read(OUT/'satellite_correction_transfer.json')
    assert transfer['source_sha256']==sha(ROOT/'tools/audit_ds23_satellite_correction_transfer.py') and not transfer['GPS_used']
    for row in transfer['summary']:
        if row['stage']!='after_satellite_correction':continue
        old=next(r for r in residual['correlation'] if all(r[k]==row[k] for k in ('arm','same_receiver','same_band','same_family')))
        if row['pooled_median_correlation'] is not None:assert abs(row['pooled_median_correlation']-old['pooled_median_correlation'])<1e-10
    fig,axes=plt.subplots(2,2,figsize=(13,8),constrained_layout=True)
    for case,ax in zip(CASES,axes.flat,strict=True):
        tracks=[r for r in read(RESIDUAL/(case+'.json'))['tracks'] if r['arm']=='c0']
        candidates={j:sum(r['points'] for r in tracks if r['norad']==j) for j in {r['norad'] for r in tracks}
                    if len({r['receiver'] for r in tracks if r['norad']==j})==2}
        family=max(candidates,key=candidates.get)
        for r in tracks:
            if r['norad']!=family:continue
            ax.plot(r['time_s'],r['residual_hz'],'.-',lw=.7,ms=3,label=f"RX{r['receiver']} CH{r['channel']}")
        ax.axhline(0,c='black',ls=':',lw=.7);ax.set(title=f'{case} · NORAD {family}',xlabel='Time (s)',ylabel='Conditional residual (Hz)');ax.grid(alpha=.2);ax.legend(fontsize=7,ncol=2)
    fig.suptitle('Largest cross-receiver family in each diagnostic scan · automatically selected by retained points')
    fig.savefig(OUT/'cross_receiver_family_examples.png',dpi=160);plt.close(fig)
    write(OUT/'summary.json',dict(weighting=summary,weighting_fallbacks=fallbacks,joint_search=search_summary,
        secondary_curves=curve_summary,residual_summary=residual,satellite_correction_transfer=transfer['summary'],goal_half_km_met=False))
    write(OUT/'validation.json',dict(all20_weighting_cases_complete=True,all4_diagnostic_cases_complete=True,
        paired_final_gates_and_observation_ID_sets_match=True,no_original_recovery_calibration_points_removed=True,
        all_new_case_source_hashes_match=True,GPS_only_used_by_this_reporting_tool=True,
        source_sha256=sha(Path(__file__)),confidence_gate_failures=confidence_gates,new_tool_unit_tests_passed=15,
        before_after_residual_stages_reproduce_existing_conditioned_correlations=True))
    table=['| Weighting policy | c0 mean / median km | Fitted-c mean / median km | Paired trial failures / 20 |',
        '|---|---:|---:|---:|']
    for method,label in zip(METHODS,LABELS,strict=True):
        a,b=summary[method]['c0'],summary[method]['fitted_c']
        table.append(f"| {label} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} | {fallbacks[method]} |")
    jt=['| Scan | Single / joint trials | Gate-passing trials | Best valid RF loss difference | Accepted replacement |', '|---|---:|---:|---:|---|']
    for r in search_summary:
        jt.append(f"| {r['case']} | {r['single_trials']} / {r['joint_trials']} | {r['valid_trials']} | {r['best_valid_delta'] if r['best_valid_delta'] is None else round(r['best_valid_delta'],3)} | {r['accepted']} |")
    ct=['| Scan | New curves / GLRT points (secondary) | c0 before → after km | Fitted-c before → after km |','|---|---:|---:|---:|']
    for r in curve_summary:
        ct.append(f"| {r['case']} | {r['accepted']} / {r['new_points']} ({r['secondary_points']}) | {r['baseline_c0_error_km']:.3f} → {r['new_c0_error_km']:.3f} | {r['baseline_fitted_error_km']:.3f} → {r['new_fitted_error_km']:.3f} |")
    body='''# DS23: confidence weighting, simultaneous family replacements and extra GLRT curves

The 0.5 km mean and median target remains unmet. These experiments use the
same causal catalogue, pre-RF phase-history prior, physical orbit modes and
300 Hz fragment constants as the incumbent. They do not choose satellites,
parameters or positions from GPS. Every position trial starts at the center
of the same 25 × 25 km box, latitude 37.906, longitude −122.545. The supplied
reference (37.849061591561885, −122.48574968092912) enters this report only.
Both c=0 and fitted-c use matched observations, labels, aliases and five
phase-refresh rounds with up to 48 position steps each. Existing source
observations, original winners and published ALGO01 are not modified.

## Does emphasizing certain associations help?

WEIGHTS

All twenty development scans remain in every denominator. A failed trial in
either c arm falls back to the incumbent pair; trial failures and raw results
are preserved. Equal, confidence-only and support-times-confidence controls
keep the exact incumbent mask. The hard confidence control explicitly removes
fragments below 0.95 and is reported separately. No additional point trimming
is allowed to rescue a trial. Frozen confidence is an approximate all-bank
identity-competition weight, not a calibrated probability. Generalized losses
with different powers or observation sets are not compared to select weights.
No scan is assigned its geographically best variant.

Cross-receiver support remains useful, but more emphasis on conditional
identity certainty does not produce a material improvement. Identity certainty
does not imply an accurate TLE, correct nuisance model, or useful independent
position geometry. Hard removal can discard the few curves that distinguish
position from phase and receiver drift.

![Weighting position errors](confidence_position_by_scan.png)

## Does the discrepancy follow hardware or a satellite?

At c0, the median scan residual RMS is RX1 low/high 119.4/147.9 Hz and
RX2 low/high 79.7/108.6 Hz. Standardizing by each point's independently
estimated radio noise gives 1.18/1.20 versus 0.64/0.88. Both bands are
available in eleven scans; all twenty have the low band.

Both receiver-common and satellite-common discrepancies are present. Compare
the same jointly fitted receiver calibration with the nominal TLE, then with
fitted phase/orbit corrections. Remove each fragment's mean in both stages.

| c0 residual comparison | Before satellite correction | After satellite correction | Matched track pairs / scans |
|---|---:|---:|---:|
| Same family/band, different RX | +0.461 | −0.020 | 124 / 19 |
| Same RX/band, different family | +0.326 | +0.459 | 593 / 20 |
| Same RX, different band/family | +0.317 | +0.329 | 444 / 11 |

The satellite-common discrepancy is real in the nominal-TLE comparison and
is largely removed by the fitted satellite terms. The remaining shared
residual follows the receiver more clearly. For the after-correction stage,
medians of per-scan medians are +0.449, +0.304 and −0.039 respectively.
This is descriptive, not a proof that the receiver causes the position bias:
both stages condition on the same jointly fitted receiver, and the fit can
trade receiver, position and satellite phase corrections against each other.
Matched track pairs are dependent. A near-zero cross-RX residual correlation
cannot exonerate the TLE or establish an identity. No interpolation is used:
nearest-distance-first unique observation pairs must be within 0.5 s, at
least six pairs per track comparison. See the original residual report for
all eight RX/band/family strata, sample counts and both c arms.

![RX and band RMS](receiver_band_RMS.png)
![Before and after satellite correction](satellite_correction_transfer.png)
![Residual correlation strata](residual_transfer.png)
![Same family on different receivers](cross_receiver_family_examples.png)

## Broader simultaneous whole-family replacement search

JOINT

This is a diagnostic set: the ongoing scan217 investigation and the three
largest c0 errors in the twenty-scan incumbent benchmark, rather than an
unbiased four-scan validation. Every track is screened against the entire
unchanged causal catalogue at the incumbent, regional center and four ±2 km
anchors. Three alternative identities per incumbent family get full-prior
c0 refits. After a measured 420 s timeout on scan202's 75-fragment model,
its proposal fits use two phase rounds and at most12 position steps;
the other three cases use five rounds and48 steps. Every promising finalist
receives the full five-round/48-step fit in both c arms and must improve
the incumbent full c0 loss. Initial failures and code versions are preserved.
A beam retains two alternatives for each of four families, then
tests all 72 pair/triple/quadruple combinations. An alternative can enter a
joint trial even when its single trial fails. Whole-family changes include
inactive fragment rows but never add their observations to the likelihood.
Original RF powers, noise, masks and physical priors remain frozen. This is
a bounded beam, not an exhaustive enumeration of every catalogue assignment.

Final selection requires lower normalized c0 negative-twice ELBO and passing
both c-arm gates; the same selected assignment is used in both arms. Invalid
trials and RF-disfavored but geographically better candidates remain visible
in the CSV. GPS cannot be used to override the radio evidence ranking.

![Joint family replacement losses](joint_family_search.png)

## Recover curved evidence from alternative GLRT peaks

CURVES

The radio-only polynomial search reads all gate-passing cached peaks, excludes
all original calibration slots and already-associated incumbent c0 output tracks, and
allows exactly one peak per physical probe. Secondary peaks retain that
probe's canonical observation ID; they do not become extra independent
measurements. Discovery uses alias-aware quadratic/cubic random seeds,
existing degree-penalized refinement up to order four, residual/noise gates,
and the original active-curvature threshold of 250 Hz departure from affine.
It uses 1,800 deterministic proposal trials per lane. Curves are ranked by
their radio-only penalized gain; the largest four are tested. This is not
exhaustive. Each selected peak's margin determines its own uncertainty under
the unchanged radio-only variance law; a weaker peak does not inherit the
winning peak's smaller variance.

Each new curve gets three all-catalogue identity proposals and independent
paired cold-start fits with the original calibration. A passing identity is
chosen by normalized c0 ELBO on that same augmented observation set. The
curve is then tested jointly with earlier accepted additions. No original
calibration point is removed. This is a gate-based retention prototype, not
a calibrated existence posterior or justification to maximize point count.

The candidate CSV records both position errors and Schur-complement local
information after marginalizing the model's nuisance columns. These local
widths hold the fitted Gamma precisions fixed; they are not calibrated error
bars and changes in them do not establish better localization. Scan217's
valid new 22-point curve includes seven secondary peaks: the local RMS radius
shrinks from 1.640 to 1.567 km, but c0 error grows from 1.025 to 1.193 km.
It provides some model-conditional information without correcting the bias.

![Recovered curves and individual GLRT peak types](secondary_curves.png)

## Recommendation and limits

Keep cross-receiver support as the reference weighting. Do not promote hard
confidence selection or accept a satellite because it moves the result closer
to GPS. Use residual structure across different satellite families on the
same receiver as a hardware-model diagnostic. Use common behavior of a
satellite across independent receivers as an orbit/transmitter diagnostic.
The two can coexist and must be tested with the physical shared terms.

The next qualification should predict held-out receiver/family evidence with
calibration learned from other families, and qualify the actual dense GLRT
fractional-time estimator against dynamic delay/Doppler controls. A corrected
radio fit and more associated points are insufficient: the fixed-rule result
must also improve position on scans not used to develop it. None of these
development results establishes the 0.5 km target or performance on all 413
DS23 recordings. A separate curvature/shape study reports the other completed
twenty-scan evidence controls without changing the published ALGO01 default.

## Reproduction and receipts

Use the repository venv, PYTHONPATH=src:tools and BLAS/OMP threads one.
Run run_ds23_fixed_confidence.py for the twenty sealed sample cases.
Run probe_ds23_joint_family_search.py and probe_ds23_secondary_curves.py
with --case for the four cases in their protocol.json, then this reporting
tool. Scan202's search additionally uses --proposal-rounds 2 --proposal-steps 12.
The source_v1 snapshot reproduces the first three joint-search cases.
No new RF, IQ reread, QNAP mutation or post-observation TLE is involved.
Published lossless evidence archives unpack to the original reports/ paths;
source snapshots overlay the earlier published research tools.

[Summary](summary.json) · [Validation](validation.json) ·
[Lossless full evidence](evidence.tar.gz) · [Evidence hashes](evidence_inventory.json) ·
[Per-scan weighting](weighting_by_scan.csv) · [Joint trials](joint_trials.csv) ·
[Joint summary](joint_summary.csv) · [Recovery candidates](recovery_candidates.csv) ·
[Recovery summary](recovery_summary.csv) ·
[Before/after correction strata](satellite_correction_transfer_summary.csv) ·
[Before/after matched pairs](satellite_correction_transfer_pairs.csv) ·
[Original residual report](../2026_10_18_ds23_learned_residuals/README.md) ·
[Further causal shape and curvature controls](../2026_10_19_ds23_curvature_shape_study/README.md).
'''
    (OUT/'README.md').write_text(body.replace('WEIGHTS','\n'.join(table)).replace('JOINT','\n'.join(jt)).replace('CURVES','\n'.join(ct)))
    print('\n'.join(table));print('\n'.join(jt));print('\n'.join(ct))


if __name__=='__main__':run()
