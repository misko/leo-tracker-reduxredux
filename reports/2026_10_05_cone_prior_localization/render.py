"""Audit and visualize the completed frozen-cone N01--N16 experiment."""
import csv
import hashlib
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE/'polished'
SCANS = [f'N{i:02}' for i in range(1, 17)]
ARMS = ('fitted-c', 'zero-c')
VARIANTS = ('control', 'selection', 'position', 'combined')
LABELS = dict(control='Matched control', selection='Cone in selection',
              position='Cone in position model', combined='Cone in both')
COLORS = dict(control='#555555', selection='#d55e00', position='#0072b2', combined='#009e73')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_read(path):
    return json.loads(Path(path).read_text())


def audit():
    protocol = json_read(HERE/'protocol.json')
    for path, sha in protocol['dependencies'].items():
        assert digest(path) == sha, path
    receipts = {}; records = {}; rows = []
    for scan in SCANS:
        receipt = json_read(HERE/'inputs'/scan/'receipt.json')
        receipts[scan] = receipt
        assert receipt['dependencies'] == protocol['dependencies']
        assert receipt['zero_strength_parity']
        for path, sha in receipt['sources'].items():
            assert digest(path) == sha, path
        for kind in ('base', 'sky'):
            assert digest(HERE/'inputs'/scan/f'{kind}.npz') == receipt['inputs'][kind]['input_sha256']
        for arm in ARMS:
            for variant in VARIANTS:
                path = RESULTS/f'{scan}-{arm}-{variant}.json'
                r = json_read(path); records[scan, arm, variant] = r
                kind = 'sky' if variant in ('selection', 'combined') else 'base'
                meta = receipt['inputs'][kind]
                assert r['dependencies'] == protocol['dependencies']
                assert r['input_sha256'] == meta['input_sha256']
                assert r['fit_original_rows'] == r['evaluation_original_rows'] == meta['original_rows']
                assert r['heldout_original_rows'] == []
                assert len(set(r['fit_original_rows'])) == r['windows'] == meta['windows']
                assert r['numbers'] == meta['numbers']
                assert r['radius_km'] == 4.
                assert r['maximum_budgets_s'] == protocol['budgets']
                assert r['additional_polish_allowance_s'] == 20.
                assert digest(r['polish_source']) == r['polish_source_sha256']
                assert digest(HERE/'polish.py') == r['polish_implementation_sha256']
                assert r['distance_m'] <= 4000.01
                np.testing.assert_allclose(r['distance_m'], 1000*np.linalg.norm(r['best']['point_km']), atol=1e-5)
                assert bool(r['converged']) == (r['kkt'] <= 1e-3)
                assert max(abs(x) for x in r['best']['parameters'][6:]) <= 20.00001
                if arm == 'zero-c':
                    assert r['best']['coefficient'] == 0.
                for source, sha in r['cross_sources'].items():
                    assert digest(source) == sha
                row = dict(scan=scan, arm=arm, variant=variant, windows=r['windows'],
                           satellites=len(r['numbers']), coverage_pct=100*meta['coverage'],
                           distance_m=r['distance_m'], converged=r['converged'],
                           boundary=r['boundary'], kkt=r['kkt'],
                           owner_rms_hz=r['owner_rms_hz'],
                           posterior_weighted_rms_hz=r['posterior_weighted_residual_rms_hz'],
                           data_nll=r['data_nll'], no_cone_data_nll=r['common_no_cone_data_nll'],
                           timing_prior_nll=r['timing_prior_nll'], objective=r['objective'],
                           rf_coefficient_hz_per_ghz=r['best']['coefficient'])
                rows.append(row)
        for variant in VARIANTS:
            a, b = [records[scan, arm, variant] for arm in ARMS]
            assert a['fit_original_rows'] == b['fit_original_rows']
            assert a['numbers'] == b['numbers'] and a['input_sha256'] == b['input_sha256']
    assert len(records) == 128
    for row in rows:
        base = records[row['scan'], row['arm'], 'control']
        row['delta_distance_m'] = row['distance_m']-base['distance_m']
        row['pair_converged'] = row['converged'] and base['converged']
        row['delta_owner_rms_hz'] = row['owner_rms_hz']-base['owner_rms_hz']
    return protocol, receipts, records, rows


def statistics(rows):
    result = []
    for arm in ARMS:
        for variant in VARIANTS:
            r = [x for x in rows if x['arm'] == arm and x['variant'] == variant]
            distance = np.array([x['distance_m'] for x in r])
            delta = np.array([x['delta_distance_m'] for x in r])
            paired = [x['delta_distance_m'] for x in r if x['pair_converged']]
            result.append(dict(arm=arm, variant=variant, median_error_m=float(np.median(distance)),
                mean_error_m=float(np.mean(distance)), p90_error_m=float(np.quantile(distance,.9)),
                below_1km=int(np.sum(distance<1000)), below_500m=int(np.sum(distance<500)),
                improved_gt_10m=int(np.sum(delta < -10)), worsened_gt_10m=int(np.sum(delta > 10)),
                median_delta_m=float(np.median(delta)), mean_delta_m=float(np.mean(delta)),
                converged=sum(x['converged'] for x in r), boundary=sum(x['boundary'] for x in r),
                converged_pairs=len(paired),
                converged_pair_median_delta_m=float(np.median(paired)) if paired else None,
                median_owner_rms_hz=float(np.median([x['owner_rms_hz'] for x in r]))))
    return result


def figures(records, receipts):
    plt.rcParams.update({'font.size':11, 'axes.spines.top':False, 'axes.spines.right':False,
                         'axes.titlepad':12, 'savefig.facecolor':'white'})
    fig, axes = plt.subplots(2,1,figsize=(16,9.5),sharex=True,sharey=True)
    x = np.arange(16)
    for ax, arm in zip(axes, ARMS):
        for j, variant in enumerate(VARIANTS):
            r = [records[s,arm,variant] for s in SCANS]
            xx = x+(j-1.5)*.13
            yy = np.array([a['distance_m'] for a in r])/1000
            ax.plot(xx,yy,'-',lw=.8,alpha=.2,color=COLORS[variant])
            ax.scatter(xx,yy,s=40,color=COLORS[variant],label=LABELS[variant],zorder=3)
            boundary = np.array([a['boundary'] for a in r])
            ax.scatter(xx[boundary],yy[boundary],marker='^',s=95,facecolors=COLORS[variant],edgecolors='black',zorder=4)
            pending = np.array([not a['converged'] for a in r])
            ax.scatter(xx[pending],yy[pending],marker='x',s=90,color='black',zorder=5)
        ax.axhline(4,color='#555555',ls=':',lw=1.5)
        ax.set_title('Fitted c' if arm=='fitted-c' else 'c = 0',loc='left',fontweight='bold')
        ax.set_ylim(-.12,4.4);ax.set_xlim(-.6,15.6)
        ax.set_ylabel('Best-found position error (km)')
        ax.set_xticks(x,SCANS);ax.grid(axis='y',alpha=.2);ax.tick_params(labelbottom=True)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.93),ncol=4,frameon=False)
    fig.suptitle('Frozen receiver-cone priors · N01–N16 independent position searches',fontsize=20,y=.987)
    fig.text(.5,.035,'Same frozen GLRT pool and search allowance; RF arms matched within each variant. Independent 4 km searches.\n'
             '▲ = imposed boundary, not an unrestricted minimum. × = stationarity check not yet passed.\n'
             'Cones learned partly from these scans: exploratory in-sample comparison, not blind validation.',ha='center',fontsize=10)
    fig.subplots_adjust(top=.83,bottom=.15,hspace=.35,left=.065,right=.98)
    fig.savefig(HERE/'position-error.png',dpi=160);plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(13,9),sharey=True)
    variants=VARIANTS[1:]
    deltas={arm:np.array([[records[s,arm,v]['distance_m']-records[s,arm,'control']['distance_m']
                          for v in variants] for s in SCANS]) for arm in ARMS}
    limit=max(100.,max(np.max(np.abs(v)) for v in deltas.values()))
    for ax,arm in zip(axes,ARMS):
        values=deltas[arm]
        im=ax.imshow(values,cmap='PiYG_r',norm=TwoSlopeNorm(vmin=-limit,vcenter=0.,vmax=limit),aspect='auto')
        for i,s in enumerate(SCANS):
            for j,v in enumerate(variants):
                uncertain=not (records[s,arm,v]['converged'] and records[s,arm,'control']['converged'])
                label=('0' if abs(values[i,j])<.5 else f'{values[i,j]:+.0f}')+(' *' if uncertain else '')
                ax.text(j,i,label,ha='center',va='center',fontsize=10,
                        color='white' if abs(values[i,j])>.63*limit else '#171717')
        ax.set_xticks(np.arange(3),['Selection only','Position only','Both'])
        ax.set_yticks(np.arange(16),SCANS);ax.tick_params(labelleft=True)
        ax.set_title('Fitted c' if arm=='fitted-c' else 'c = 0',fontsize=15)
    fig.suptitle('Position-error change versus the matched control',fontsize=20,y=.985)
    fig.text(.5,.94,'Negative / green = closer to the known roof. Positive / pink = farther away.',ha='center',fontsize=12)
    cb=fig.colorbar(im,ax=axes,location='right',fraction=.025,pad=.04)
    cb.set_label('Cone variant − control position error (m)')
    fig.text(.5,.025,'* At least one fit in the pair has not passed stationarity. Boundary-constrained results remain included.\n'
             'Four-kilometer searches; lower errors are not evidence of correct satellite identities.',ha='center',fontsize=10)
    fig.subplots_adjust(top=.86,bottom=.1,left=.07,right=.82,wspace=.15)
    cb.ax.set_position([.87,.13,.022,.67])
    fig.savefig(HERE/'position-error-change.png',dpi=160);plt.close(fig)

    fig,axes=plt.subplots(3,1,figsize=(15,10),sharex=True)
    for label,color,shift,title in [('base','#555555',-.18,'Control selection'),('sky','#d55e00',.18,'Cone selection')]:
        axes[0].bar(x+shift,[100*receipts[s]['inputs'][label]['coverage'] for s in SCANS],.34,color=color,label=title)
    axes[0].set_ylim(0,112);axes[0].set_yticks(np.arange(0,101,20))
    axes[0].set_ylabel('Assigned top-one windows (%)');axes[0].legend(ncol=2,frameon=False,loc='upper left')
    for key,color,shift in [('lost','#d55e00',-.25),('gained','#009e73',0),('relabeled','#0072b2',.25)]:
        axes[1].bar(x+shift,[receipts[s][key] for s in SCANS],.24,color=color,label=key.capitalize())
    axes[1].set_ylabel('Windows affected');axes[1].legend(ncol=3,frameon=False)
    for label,color,title in [('base','#555555','Control selection'),('sky','#d55e00','Cone selection')]:
        axes[2].plot(x,[receipts[s]['inputs'][label]['rms_hz'] for s in SCANS],
                     '-o',color=color,label=title,ms=5)
    axes[2].set_ylabel('Selection-stage RMS (Hz)')
    axes[2].set_title('Doppler residuals before position fitting; frozen roof calibration',fontsize=11)
    for ax in axes:ax.grid(axis='y',alpha=.2);ax.set_xticks(x,SCANS);ax.set_axisbelow(True)
    fig.suptitle('What the cone selection prior changed',fontsize=20)
    fig.text(.5,.025,'Coverage denominator: all passing top-refined-score receiver/channel windows in each scan.\n'
             'Relabeled = still assigned, but to a different satellite. Position-only uses the control assignments.\n'
             'The two RF ablation arms use identical selection results; no negative peer-receiver evidence is invented.',ha='center',fontsize=10)
    fig.subplots_adjust(top=.92,bottom=.15,hspace=.3,left=.08,right=.98)
    fig.savefig(HERE/'selection-impact.png',dpi=160);plt.close(fig)


def write_outputs(protocol,receipts,records,rows,summary):
    with (HERE/'results.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    selection=[]
    for scan in SCANS:
        r=receipts[scan]
        selection.append(dict(scan=scan,**{key:r[key] for key in ('lost','gained','relabeled')},
            **{f'{label}_{k}':r['inputs'][label][k] for label in ('base','sky')
               for k in ('windows','satellites','coverage','rms_hz','replacement_converged')}))
    with (HERE/'selection.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(selection[0]));writer.writeheader();writer.writerows(selection)
    denominator=sum(json_read(HERE/'inputs'/s/'base-selection.json')['final']['denominator'] for s in SCANS)
    aggregate=dict(denominator=denominator,
        **{f'{kind}_windows':sum(r['inputs'][kind]['windows'] for r in receipts.values()) for kind in ('base','sky')},
        **{key:sum(r[key] for r in receipts.values()) for key in ('lost','gained','relabeled')},
        **{f'{kind}_mean_scan_rms_hz':float(np.mean([r['inputs'][kind]['rms_hz'] for r in receipts.values()]))
           for kind in ('base','sky')})
    result=dict(summary=summary,selection=selection,selection_aggregate=aggregate,protocol=protocol,
                audit=dict(cases=128,scans=16,zero_strength_exact_parity=True,
                  matched_rf_rows_and_bank=True,all_selected_windows_fit_and_eval=True,no_holdout=True),
                additional_matched_polish_allowance_s=20.,
                result_sources={str(RESULTS/f'{s}-{a}-{v}.json'):digest(RESULTS/f'{s}-{a}-{v}.json')
                                for s,a,v in records})
    (HERE/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    def table(head,body):
        return '<table><thead><tr>'+''.join('<th>'+html.escape(str(x))+'</th>' for x in head)+'</tr></thead><tbody>'+''.join(
            '<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in body)+'</tbody></table>'
    summary_table=table(['RF arm','Variant','Median error (m)','Mean (m)','<1 km','Improved >10 m','Worsened >10 m','Boundary','Converged'],[
        [r['arm'],LABELS[r['variant']],round(r['median_error_m']),round(r['mean_error_m']),f"{r['below_1km']}/16",
         r['improved_gt_10m'],r['worsened_gt_10m'],r['boundary'],f"{r['converged']}/16"] for r in summary])
    detail=table(['Scan','RF arm','Variant','Error (m)','Δ error (m)','Windows','Satellites','Owner RMS (Hz)','Boundary','Converged'],[
        [r['scan'],r['arm'],LABELS[r['variant']],round(r['distance_m']),round(r['delta_distance_m']),r['windows'],r['satellites'],
         round(r['owner_rms_hz'],1),r['boundary'],r['converged']] for r in rows])
    lookup={(r['arm'],r['variant']):r for r in summary}
    position=lookup['fitted-c','position'];combined=lookup['fitted-c','combined']
    interpretation=f'''<p><b>Interpretation:</b> the position-only prior is a small, mixed change:
mean fitted-c error changes by {position['mean_delta_m']:+.1f} m, with {position['improved_gt_10m']} scans improving
and {position['worsened_gt_10m']} worsening by more than 10 m. The combined model improves
{combined['improved_gt_10m']}/16 fitted-c scans, but its mean error increases by {combined['mean_delta_m']:.1f} m
because several regressions are large. A count of wins alone therefore gives a different impression from mean or median absolute error.</p>
<p>Keep the control as the default. The weak position-only prior is worth further validation, but this cone-based
selection score is not a safe automatic replacement rule. The next selector experiment should combine geometry
with continuous frequency-fit evidence and timing costs, rather than allowing cone evidence to override the old
frequency-residual tie-break. Do not tune that follow-up to these scans and then call it independent validation.</p>'''
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Receiver-cone localization prototype</title>
<style>body{font:16px/1.6 system-ui,sans-serif;max-width:1300px;margin:35px auto;padding:0 25px;color:#20242b}h1,h2{line-height:1.2}img{width:100%;height:auto}table{border-collapse:collapse;font-size:14px;width:100%}th,td{padding:7px 10px;border-bottom:1px solid #ddd;text-align:right}th:first-child,td:first-child{text-align:left}thead{background:#eef2f5}code{background:#eee;padding:2px 5px}.note{background:#fff3d9;padding:15px;border-left:4px solid #db9400}section{margin:45px 0}.scroll{overflow:auto}a{color:#00699c}</style>
<h1>Frozen receiver-cone priors: N01–N16</h1>
<p>Four prototype variants × sixteen independent scans × two controlled RF-calibration arms = <b>128 scan/model cases</b>, each evaluated with multiple optimization starts.
All use the same 4 km radius, current full-data calibration, archived candidate timing-mode pool, top refined GLRT candidate per passing window, and ordinary C1 frequency likelihood with a smooth 0–1° horizon.</p>
<p class="note">Exploratory in-sample test: the frozen cones and evidence-support mask were learned from 20 scans including these sixteen, using known-roof directions and previous associations. These results are not blind localization validation, proof of identity, or global-minimum certificates. The prior was not tuned to this experiment’s position errors.</p>
<section><h2>Position accuracy</h2>'''+summary_table+interpretation+'''
<p>All 16 best-found results are included in each row, even when boundary-constrained or not stationary. Improvement counts use a 10 m tolerance to avoid interpreting tiny numerical changes. Frequency-fit scores are not used as a proxy for localization accuracy.</p>
<img src="position-error.png" alt="Absolute position errors"><img src="position-error-change.png" alt="Paired position-error changes"></section>
<section><h2>What is being tested?</h2><ol>
<li><b>Matched control:</b> no cone term. Zero-strength selection reproduces the stored full-data greedy-plus-replacement result exactly. The final objective reproduces the existing ordinary-Q1 model.</li>
<li><b>Selection only:</b> maximize assigned windows − 10 × satellites + receiver-cone evidence. For each satellite, average the observed receiver’s log marginal-probability ratio within each 5 s block, then sum blocks. Strength 1; log odds clipped to ±3; unsupported sky neutral. Keep the 600 Hz frequency gate, timing-mode bank, coherence requirements and replacement neighborhood unchanged.</li>
<li><b>Position only:</b> keep the original selected observations and candidate bank. Tilt per-window candidate probabilities by <code>(0.1 + 0.9 P(receiver present | at least one receiver))^(0.5 × support)</code>, then renormalize to preserve their sum (the expected detection count). This does not preserve the probability of at least one detection: that finite-set normalizer is recomputed exactly. Recompute directions at each trial position and satellite timing. This is a candidate-prior change inside the normalized likelihood, not a whole-window residual weight.</li>
<li><b>Combined:</b> apply both changes.</li></ol>
<p>Positive detections only: choosing one top candidate per receiver/channel window cannot prove the same satellite was absent on the other receiver. This prototype therefore does not fabricate RX-only labels or use missing peer detections as penalties. Cone shape, rolls and support mask stay frozen.</p>
<p>The selection prior and final-model prior use different likelihood constructions and strengths; they are separate heuristics, not two estimates of the same calibrated posterior.</p></section>
<section><h2>Coverage and association changes</h2>'''+f'''
<p>Across {denominator:,} passing top-one windows, assignments change from {aggregate['base_windows']:,}
({100*aggregate['base_windows']/denominator:.2f}%) to {aggregate['sky_windows']:,}
({100*aggregate['sky_windows']/denominator:.2f}%). There are {aggregate['gained']:,} newly assigned,
{aggregate['lost']:,} lost, and {aggregate['relabeled']:,} relabeled windows.
Mean per-scan selection-stage Doppler RMS changes from {aggregate['base_mean_scan_rms_hz']:.1f} to
{aggregate['sky_mean_scan_rms_hz']:.1f} Hz.</p>'''+'''
<img src="selection-impact.png" alt="Coverage and association changes">
<p>The additive selection prototype can favor a geometrically plausible candidate even when its Doppler residual is worse: the previous residual criterion was only a tie-break after coverage. This is a limitation of this particular score, not evidence that the cone-preferred identity is correct. Any follow-up selector should protect frequency-fit evidence rather than treating all residuals inside the 600 Hz gate as equally good.</p>
<p>Both RF arms share fitted-c-derived selection inputs and the fixed fitted-c receiver baseline. The c = 0 ablation removes only the final-model RF coefficient; it does not independently rerun upstream calibration without c. Coverage is the selection-stage assigned-window count, not the soft posterior count after position fitting.</p></section>
<section><h2>Data and optimization safeguards</h2><ul>
<li>No new GLRT refinement, IQ acquisition, folds or holdout fitting. All selected top-one windows are used for both parameter fitting and diagnostic scoring. Unassigned windows are not part of this established final-position loss.</li>
<li>Final frequency width 200 Hz; detection budget 0.8; clutter rate 2; common timing σ = 10 s; relative timing σ = 1/3 s; total satellite timing constrained to ±20 s. Receiver offset/drift, final RF coefficient and timing are refitted; the saved nonlinear receiver baseline stays fixed.</li>
<li>Common archived starts, both selection timing starts, three local search starts, and cross-variant start repricing. Every case then receives the same additional 20 s convergence allowance, stopping immediately if already stationary. Start selection uses objective value, never known-roof error. Numerically tied scores within 64 relative machine epsilons use the lower KKT residual. Maximum wall-time budgets are matched; the solver also stops at stationarity. Searches are not global certificates.</li>
<li>Triangles mark the imposed 4 km boundary. Crosses mark KKT residual > 0.001. A boundary result does not locate the unrestricted minimum.</li>
<li>Source SHA-256 checks, exact zero-strength baseline checks for all sixteen scans, matched RF observations/candidate-bank checks, probability-mass tests, and numerical gradient checks.</li></ul>
<p>Raw NLLs are comparable only for the same observations and likelihood definition. Selection variants may change observations or candidate banks; their raw total NLLs should not be ranked against control as if they were identical tasks. Owner RMS is descriptive and depends on both the selected assignments and fitted nuisance parameters.</p></section>
<section><h2>Per-case results</h2><p><a href="results.csv">Results CSV</a> · <a href="selection.csv">Selection CSV</a> · <a href="summary.json">Summary and provenance</a> · <a href="protocol.json">Frozen protocol</a> · <a href="experiment.py">Experiment script</a></p>
<div class="scroll">'''+detail+'</div></section></html>'
    (HERE/'report.html').write_text(page)


def main():
    protocol,receipts,records,rows=audit()
    summary=statistics(rows)
    figures(records,receipts);write_outputs(protocol,receipts,records,rows,summary)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
