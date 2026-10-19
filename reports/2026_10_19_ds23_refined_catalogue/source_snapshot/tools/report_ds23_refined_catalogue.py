"""Report broader causal identity search, RF/GPS disagreement and loss budget."""

import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ds23_precision_diagnostics import compare_screens
from ds23_refined_noise import learn_noise
from probe_ds23_raw_pilot_refinement import OUT as RAW
from probe_ds23_refined_family_catalogue import OUT
from report_algo01_ds23_sample import position_error
from run_algo01_ds23_sample import read,write,sha

CASE='DS23-0202'


def run():
    documents=[('CH2 refined',read(OUT/(CASE+'.json'))),('Both channels refined',read(OUT/(CASE+'_companion.json'))),
               ('Both refined, RF-scaled constants',read(OUT/(CASE+'_cross_rf.json')))]
    rows=[];diagnostics=[]
    for name,d in documents:
        valid=[r for r in d['trials'] if r.get('paired_valid')]
        minimum=min(r['arms']['c0']['negative_twice_elbo'] for r in valid)
        for r in d['trials']:
            if 'arms' not in r:continue
            norad=r['proposal']['norad'];target=[]
            for arm,v in r['arms'].items():
                for tr in v['tracks']:
                    if tr['norad']!=norad:continue
                    diag=compare_screens(tr['conditional_residual_hz'],tr['time_s'],tr['sigma_hz'])
                    target.append(diag['RF_scaled']['noise_screen_pass'])
                    diagnostics.append(dict(stage=name,norad=norad,arm=arm,track=tr['track'],**diag))
            errors={a:position_error(v['endpoint_latlon']) for a,v in r['arms'].items()}
            rows.append(dict(stage=name,norad=norad,legacy_paired_valid=r['paired_valid'],
                family_precision_screens_pass=all(target),loss=r['arms']['c0']['negative_twice_elbo'],
                loss_minus_best_valid=r['arms']['c0']['negative_twice_elbo']-minimum,
                c0_error_km=errors['c0'],fitted_c_error_km=errors['fitted_c']))
    loss=read(OUT/(CASE+'_loss.json'));chosen=next(r for r in loss['identities'] if r['norad']==loss['RF_selected_norad'])['arms']['c0']
    a,b=chosen['at_RF_endpoint'],chosen['at_evaluation_site']
    delta={k:b['terms'][k]-v for k,v in a['terms'].items()}
    companion=read(RAW/(CASE+'_companion.json'));_,radio=learn_noise(companion)
    summary=dict(rows=rows,precision_diagnostics=diagnostics,companion_radio_receipts=radio,
        catalogue_size=documents[1][1]['catalogue_size'],RF_chosen_norad=loss['RF_selected_norad'],
        evaluation_minus_RF_objective=b['negative_twice_elbo']-a['negative_twice_elbo'],loss_term_differences=delta,
        gradients=loss['gradients'],surface_samples=len(loss['grid']),
        previous_2p601km_result_conditional_on_fixed_identity=True,
        broader_RF_selection_does_not_preserve_previous_accuracy_gain=True,
        no_GPS_choice_of_identity_or_hyperparameters=True,target_met=False,
        scope='one inspected development scan; not full DS23 or untouched validation',source_sha256=sha(Path(__file__)))
    write(OUT/'summary.json',summary)
    with (OUT/'identity_comparison.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    colors={67335:'tab:blue',64442:'tab:orange',53531:'tab:green'}
    fig,axes=plt.subplots(1,3,figsize=(15,4.7),constrained_layout=True)
    for ax,(stage,_) in zip(axes,documents,strict=True):
        rr=[r for r in rows if r['stage']==stage]
        for r in rr:
            color=colors.get(r['norad'],'0.55');marker='o' if r['legacy_paired_valid'] else 'x'
            ax.scatter(r['c0_error_km'],r['loss_minus_best_valid'],color=color,marker=marker,s=55)
            ax.annotate(str(r['norad']),(r['c0_error_km'],r['loss_minus_best_valid']),xytext=(3,4),textcoords='offset points',fontsize=8)
        ax.axhline(0,color='k',lw=.6);ax.axvline(.5,color='crimson',ls='--',lw=.6)
        ax.set(title=stage,xlabel='Position error c=0 (km)',ylabel='RF loss above best gate-passing identity');ax.grid(alpha=.2);ax.margins(x=.12)
    fig.suptitle('Lower RF loss does not imply smaller position error · candidates never chosen using GPS')
    fig.savefig(OUT/'identity_RF_vs_accuracy.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(14,5),constrained_layout=True)
    d=documents[1][1]
    for r in d['trials']:
        n=r['proposal']['norad']
        if n not in colors:continue
        for ax,ch in zip(axes,[2,3],strict=True):
            t=next(t for t in r['arms']['c0']['tracks'] if t['norad']==n and f'-RX2-CH{ch}-' in t['track'])
            ax.plot(t['time_s'],t['conditional_residual_hz'],'.-',lw=.7,ms=3,color=colors[n],label=f'NORAD {n}')
            ax.set(title=f'RX2 CH{ch}',xlabel='Scan time (s)',ylabel='Conditional CFO residual (Hz)')
    for ax in axes:ax.axhline(0,color='k',lw=.5);ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Both curves independently remeasured · same causal priors and original observation IDs')
    fig.savefig(OUT/'identity_residuals.png',dpi=160);plt.close(fig)
    g=loss['grid'];xy=np.array([v['offset_east_north_km'] for v in g]);values=np.array([v['loss'] for v in g]);values-=a['negative_twice_elbo']
    fig,ax=plt.subplots(figsize=(8,7),constrained_layout=True)
    cf=ax.tricontourf(xy[:,0],xy[:,1],values,levels=18,cmap='viridis');fig.colorbar(cf,ax=ax,label='Normalized RF loss − RF endpoint loss')
    ax.scatter(xy[:,0],xy[:,1],s=12,c='white',edgecolors='k',linewidths=.3,label='Actual 2.5 km grid samples')
    ax.scatter(0,0,s=140,marker='*',color='red',label='Evaluation site')
    displacement=np.array(loss['RF_endpoint_xy_km'])-np.array(loss['evaluation_site_xy_km'])
    ax.scatter(*displacement,s=85,marker='X',color='orange',edgecolors='k',label='RF descent endpoint')
    gradient=-np.array(loss['gradients']['evaluation_site']['0.05']);direction=gradient/np.linalg.norm(gradient)*2
    ax.annotate('',xy=direction,xytext=[0,0],arrowprops=dict(arrowstyle='->',color='red',lw=2))
    ax.plot([],[],color='red',lw=2,label='−gradient at site; direction only (2 km arrow)')
    ax.set(xlabel='East of evaluation site (km)',ylabel='North of evaluation site (km)',aspect='equal',
        title='Fixed identities · five nuisance/phase refresh rounds per point\n10 km radius, clipped to original 25 × 25 km regional box')
    ax.legend(fontsize=8);fig.savefig(OUT/'fixed_identity_loss_surface.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,4.7),constrained_layout=True)
    ax.bar(range(len(delta)),list(delta.values()),color=['tab:blue' if k=='data' else 'tab:orange' for k in delta])
    ax.set_xticks(range(len(delta)),list(delta),rotation=30,ha='right');ax.axhline(0,color='k',lw=.5)
    ax.set(ylabel='Loss increase at evaluation site',title=f'Total +{sum(delta.values()):.2f}; conditional weighted residual term only +{delta["data"]:.2f}')
    ax.grid(axis='y',alpha=.2);fig.savefig(OUT/'loss_budget.png',dpi=160);plt.close(fig)
    table=['| Data / covariance | NORAD | RF loss above best valid | c=0 / fitted-c error km | Legacy gates | Refined family screens |',
           '|---|---:|---:|---:|---|---|']
    for r in rows:
        if r['norad'] not in colors:continue
        table.append(f'| {r["stage"]} | {r["norad"]} | {r["loss_minus_best_valid"]:.2f} | {r["c0_error_km"]:.4f} / {r["fitted_c_error_km"]:.4f} | {r["legacy_paired_valid"]} | {r["family_precision_screens_pass"]} |')
    body='''# DS23 scan 202: broader precise-family association and remaining position bias

Broader RF search overturns the earlier conditional accuracy gain. The prior
2.601km result retained NORAD64442. After screening all1,569 causal candidates,
NORAD67335 has lower penalized RF loss and passes both-arm gates, but gives
3.076km error after both channel curves are refined. NORAD53531 gives0.926km
yet loses RF evidence by98.26 and fails a precision-scaled family residual
screen. It cannot be selected using GPS. The0.5km DS23 goal remains unmet.

## Search uses one phase per family and the same physical model

The previously restored71-point family is now active. Screen the entire
unchanged causal bank at the regional center, the RF endpoint and four±2km
axial offsets. At each anchor integrate one shared family phase and separate
300Hz fragment constants, using pointwise RF noise and frozen family powers.
This prevents two curves borrowing independent phases in the proposal score.
The Gaussian proposal is an approximation to the final Student-phase model;
no orbital modes enter this cheap screen. Six shortlisted identities get full
five-round/48-step regional-center cold fits in both c arms with shared physical
orbit/eccentricity modes. Already-active family mergers are outside this
bounded test. This is full-catalogue screening, not exhaustive full refitting.

TLE epochs and collection cutoffs remain causal. No identity whitelist, GPS
prior or future TLE enters inference. Observation IDs, masks, physical priors,
noise laws, likelihood powers and budgets match across each identity comparison.
All failed trials are preserved; the best normalized c=0 RF objective among
both-arm gate-passing identities determines the RF winner.

## The companion supplies independently remeasured curved evidence

Export all34 original RX2 CH3 companion points through ShortWindowReader,
using declared manifests and hash-verified chunks/windows. The bounded exporter
reads915 windows, below its1,024 limit. This is targeted development evidence,
selected as the original family companion rather than by position error.
No new RF is collected or original recording changed. Raw NPZ payloads remain
local replay prerequisites and are not published.

Local carrier/epoch/code-rate refinement gives a degree4 polynomial RMS9.71Hz
and RF-only predictive noise10.81Hz; the archived graph residual was57.88Hz.
This comparison includes a possible degree change; the key new test is the
matched full position fit. CH2's predictive scale is11.33Hz. All108 selected
scan202 observations across the original three curves and this companion
remain available, with every original calibration point preserved. Refinement
and noise learning use no orbit, GPS or chosen satellite.

TABLE

![RF ranking and accuracy](identity_RF_vs_accuracy.png)
![Conditional residuals for three valid legacy candidates](identity_residuals.png)

The both-channel comparison strongly favors67335 over64442 (RF loss gap24.06).
At the unchanged64442 identity, refining the companion changes c=0 error from
2.601 to2.667km. Better CFO measurement and more observations do not guarantee
better localization under the fitted nuisance/prior model. The previous report's
2.601km result is valid only for its unchanged identity, not the broader search.

## A precision-aware residual diagnostic rejects the GPS-favored candidate

The legacy screen floors its scale at75Hz. Apply that same screen to75*r/sigma,
using each observation's RF-only sigma, to expose structure relative to actual
measurement precision. This is a conditional diagnostic, not a calibrated
posterior-predictive test. Both67335 and64442 pass on the two family curves in
both c arms.53531 fails CH2's step screen, even though legacy gates pass and
its geographic endpoint is closer. A focused test demonstrates a small linear
component hidden by the old75Hz floor and detected after scaling.

## Cross-RF shared constants improve evidence while worsening accuracy

Test90% shared same-family clock covariance, proportional to RF, across channels,
bands and receivers. Normalize RF to the family's maximum and retain an
independent diagonal remainder, preserving every fragment's300Hz marginal
uncertainty. Different families remain independent. This extends earlier
same-family/exact-RF covariance controls without simply tightening all offsets.
Use the top three gate-passing identities from the both-refined search and
retain the incumbent. All c pairs keep the same measurements and budgets.

RF evidence improves by about72 for67335, yet error grows to3.139km. The winner
does not change;53531 now fails legacy gates too. This is evidence that a better
frequency/prior objective need not improve localization. This covariance is an
engineering hypothesis, not a qualified new default.

## The fitted objective itself prefers the biased location

Hold RF-selected67335 and every other identity/mask fixed. At each diagnostic
position perform five phase/nuisance refresh rounds; do not run association,
graph discovery or position descent. The plot samples37 points on a2.5km grid
inside a10km radius of the supplied evaluation site and inside the original
25×25km regional box. Contours interpolate those samples. The red arrow shows
the negative gradient direction at the site, drawn with an arbitrary2km length;
it is not an optimization trajectory or a probability contour.

![Fixed-identity loss surface](fixed_identity_loss_surface.png)

The normalized objective at the evaluation site is25.63 higher than at the RF
endpoint. Finite-difference gradients at0.05/0.1km agree: approximately
(-7.56,+14.91)loss/km at the site versus(-0.084,-0.015) at the RF endpoint.
The major error is therefore not explained by simply failing to descend this
particular fixed-identity objective. This is a diagnostic surface; it does not
prove that the joint discrete/continuous search found a global minimum.

![Loss budget](loss_budget.png)

The conditional weighted residual term contributes only+1.99 of that gap.
Phase prior means/precisions, orbital prior penalties, receiver/fragment terms,
noise-scale Gamma cost and integration volume make up the rest. This algebraic
decomposition exactly reproduces the full normalized objective, but it is not
an independent causal attribution: all terms share jointly fitted nuisance
parameters. The leading family data-plus-mean-prior changes are distributed
across58735,62503 and65837; no one term accounts for the full discrepancy.

## What to do next

Retain the broader-search regression and do not promote the earlier conditional
accuracy gain as a general improvement. The fresh precise family can now help
revisit simultaneous replacements of other families; earlier joint searches
used the old measurements and a mask excluding this family. More generally,
extend bounded precise remeasurement beyond the early family and qualify signed
full-state orbital forecasts on strictly pre-RF TLE transitions, without GPS
selection. Prediction across independent receiver/family evidence is needed to
separate correlated hardware error from miscalibrated orbit priors.

These are one-scan development diagnostics. They do not establish full413 DS23
accuracy, untouched-scan generalization or the0.5km mean/median goal. All causal,
physical-support and matched-c requirements remain in force.

## Evidence and reproduction

[Summary](summary.json) · [Identity comparisons](identity_comparison.csv) ·
[Full evidence](evidence.tar.gz) · [Inventory](evidence_inventory.json) ·
[Validation](validation.json) · [Source snapshots](source_snapshot/).

Use the repository venv, PYTHONPATH=src:tools and BLAS/OMP threads1. Run
probe_ds23_refined_family_catalogue.py --case DS23-0202 with and without
--companion. The companion panel is exported with export_ds23_companion_panel.py
using the exact original CH3 track key; refine it through the frozen
probe_ds23_raw_pilot_refinement.run(case,'companion') function. Then run
probe_ds23_cross_rf_constants.py, diagnose_ds23_refined_loss.py (evaluation-only)
and this reporter. Five owned tests cover dense Gaussian parity, shared-phase
consistency, integer aliases/visibility, precision sensitivity and RF covariance.
'''.replace('TABLE','\n'.join(table))
    (OUT/'README.md').write_text(body)
    print('\n'.join(table),flush=True)


if __name__=='__main__':run()
