"""Render fixed component comparisons, retaining failed cells and c arms."""
import csv
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())


def main():
    spec=read(OUT/'spec.json');audit=read(OUT/'intervention_audit.json')
    rows=[];results={}
    for cell,parts in spec['cells'].items():
        result=read(OUT/'results'/f'{cell}.json');results[cell]=result
        for arm in ('c0','fitted_c'):
            p=result['pair'][arm];base=results['original']['pair'][arm]
            raw=read(OUT/'fits'/f'{cell}.json')
            row=dict(cell=cell,components='+'.join(parts),arm=arm,qualified=p is not None,
                qualified_starts=sum(r.get('qualified',False) for r in raw if r['arm']==arm),
                objective=None if p is None else p['objective'],
                delta_objective=None if p is None else p['objective']-base['objective'],
                error_m=None if p is None else p['error_m'],
                delta_error_m=None if p is None else p['error_m']-base['error_m'],
                rms_hz=None if p is None else p['rms_hz'],
                delta_rms_hz=None if p is None else p['rms_hz']-base['rms_hz'],
                displacement_km=None if p is None else float(np.linalg.norm(np.array(p['x'])-base['x'])),
                selected_start=None if p is None else p['start'],
                fixed_endpoint_delta_objective=audit[cell][arm]['objective']-audit['original'][arm]['objective'])
            rows.append(row)
    with (OUT/'comparisons.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (OUT/'summary.json').write_text(json.dumps(dict(rows=rows,all_planned_cells_complete=True,
        selection='RF-best qualified start within each prespecified cell; no cross-cell model selected',
        production_changed=False),indent=2)+'\n')
    labels=list(spec['cells']);xx=np.arange(len(labels));fig,axes=plt.subplots(3,1,figsize=(11,10),sharex=True)
    for arm,offset,color in [('c0',-.18,'#2d7595'),('fitted_c',.18,'#e28834')]:
        rr=[next(r for r in rows if r['cell']==c and r['arm']==arm) for c in labels]
        for ax,key,ylabel in zip(axes,('delta_objective','delta_error_m','delta_rms_hz'),
                ('Normalized frequency objective change\nnegative is improvement',
                 'Evaluation position error change (m)\npositive is regression',
                 'Curved native CFO RMS change (Hz)')):
            ax.bar(xx+offset,[np.nan if r[key] is None else r[key] for r in rr],width=.36,label=arm,color=color)
            ax.axhline(0,color='black',lw=.7);ax.set_ylabel(ylabel);ax.grid(axis='y',alpha=.2)
    axes[0].legend();axes[-1].set_xticks(xx,labels,rotation=35,ha='right')
    fig.suptitle('DS26-0058 causal history: fixed component interventions\nSame native evidence, identities, starts and search budgets; GPS is evaluation only')
    fig.tight_layout();(OUT/'plots').mkdir(exist_ok=True);fig.savefig(OUT/'plots/component_effects.png',dpi=170);plt.close(fig)
    lines=['# DS26-0058 causal history component ablation','',
        'This is a diagnostic of one known regression, not independent population validation. All ten component cells were fixed before fitting. Each cell used the exact original ALGO06 native observations and identities, the same two published RF starts in both c arms, the inherited 15 phase rounds / 40 SLSQP iterations, and unchanged gates. The best qualified start was selected by normalized RF objective only. No cross-cell model was selected or promoted.', '',
        'The causal prior changes reach three distinct scopes: calibration phase widths, the physical radial/cross-track covariance, and the standalone 64938 predictive mixture. Phase means are exactly zero before and after because the learned shrinkage is zero; the mean-only intervention is an exact null. The original mechanism inventory omitted the 64938 mixture change: its phase prior standard deviation changes from 1 to 15 s. The mean/width cell concerns the calibration families; predictive-only changes the whole standalone mixture prior and orbital modes while retaining the shared receiver covariance once.', '',
        '| Cell | c=0 error (m) | fitted-c error (m) | c=0 objective change | fitted-c objective change | c=0 RMS change (Hz) | fitted-c RMS change (Hz) |',
        '|---|---:|---:|---:|---:|---:|---:|']
    def fmt(v):return 'unqualified' if v is None else f'{v:.3f}'
    for cell in labels:
        r=[next(r for r in rows if r['cell']==cell and r['arm']==a) for a in ('c0','fitted_c')]
        lines.append('| '+cell+' | '+' | '.join(fmt(v) for v in (r[0]['error_m'],r[1]['error_m'],r[0]['delta_objective'],r[1]['delta_objective'],r[0]['delta_rms_hz'],r[1]['delta_rms_hz']))+' |')
    def item(cell,arm='fitted_c'):
        return next(r for r in rows if r['cell']==cell and r['arm']==arm)
    lines[2:2]=[
        'The 64938 predictive-family relaxation is the main isolated source of the location regression. Predictive-only changes fitted-c error from '+fmt(item('original')['error_m'])+' to '+fmt(item('predictive')['error_m'])+' m; completing every prior gives '+fmt(item('complete')['error_m'])+' m. Calibration phase-width changes alone give '+fmt(item('width')['error_m'])+' m, and radial uncertainty alone '+fmt(item('radial')['error_m'])+' m. This is not explained by the calibration phase width alone.', '',
    ]
    lines += ['', 'Objective differences include hierarchical likelihood and predictive-density normalization. A negative objective change is better frequency evidence under that cell; it does not establish improved position accuracy. RMS covers curved native calibration data, while the objective additionally scores predictive linear data and the standalone mixture. Endpoint changes are available in [comparisons.csv](comparisons.csv); every start, including failures, is preserved in `fits/`.', '',
        'At the original fitted-c endpoint, the phase-width cell changes the objective by '+fmt(audit['width']['fitted_c']['objective']-audit['original']['fitted_c']['objective'])+', radial by '+fmt(audit['radial']['fitted_c']['objective']-audit['original']['fitted_c']['objective'])+', cross by '+fmt(audit['cross']['fitted_c']['objective']-audit['original']['fitted_c']['objective'])+', and predictive mixture by '+fmt(audit['predictive']['fitted_c']['objective']-audit['original']['fitted_c']['objective'])+'. Those fixed-position shifts are density effects and cannot alone explain which component moves the position. The matched fits and [local sensitivity](local_sensitivity.json) separate them from changes in the spatial objective.', '',
        'The intervention audit reconstructs the original and completed-history objectives to within 1e-5 at both published endpoints before any fitting. Component-owned checks verify unchanged native evidence, no unintended prior changes, matched starts, causal archive availability, and zero-mean null behavior. Causal export receipt epochs are strictly earlier than nominal; archive collection is within the original 72 h window and before the scan cutoff. Hybrid intervention mode metadata retains original provenance flags while numeric radial/cross scale fields and mode arrays take the declared sources; use `history/export.json` for the causal provenance of the supplied history.', '',
        'General safety criteria supported for further testing: audit every prior consumer rather than only calibration families; assess history-derived prior distributions with strictly causal, randomized whole-group predictive validation; require RF improvement to transfer under both c arms and perturbations of orbital and receiver priors; evaluate localization changes separately on a frozen RF-defined population. A large in-sample normalized-score gain is insufficient as a localization safety certificate. This single regression does not validate a new width cap, radial floor, covariance weight, or history-age cutoff, and supplies no basis for scan-specific prior constants.', '',
        'Limits: fixed associations and inherited graph/alias choices; no fresh catalogue discovery or RF collection. Local score stencils keep the saved phase reference fixed and are descriptive, not independent validation. Component effects can interact, so additive attribution is not assumed. No production files, public contracts, sealed results, or golden fixtures changed.', '',
        'Reproduce with the Python environment and commands in the parent manifest: `ablate.py freeze`, `ablate.py run`, `local_sensitivity.py`, `test_ablate.py`, then `render.py`. `spec.json` retains the original frozen design; `execution_amendment.json` records a prefit implementation-only correction after a KeyError, with no fit outcomes available and no cell design change. Existing `fits/` are caches, so use a fresh copied output directory for a wholly new execution. Input and code hashes are in the frozen specification and amendment.', '',
        '![Matched c-arm component effects](plots/component_effects.png)', '']
    sensitivity=read(OUT/'local_sensitivity.json')
    sub={r['cell']:r for r in sensitivity['predictive_subcells'] if r['arm']=='fitted_c'}
    lines += ['The fixed-position subablation of the 64938 mixture further isolates phase-width relaxation. Its normalized objective changes from '+fmt(sub['original']['scores'][0])+' to '+fmt(sub['width']['scores'][0])+' with width only; the full mixture-prior change gives '+fmt(sub['complete']['scores'][0])+'. The mixture spatial gradient (east, north), in objective units/km, changes from '+str([round(v,3) for v in sub['original']['gradient_per_km']])+' to '+str([round(v,3) for v in sub['width']['gradient_per_km']])+'. The wider phase distribution gives much less positional pull from this family. This is a local model mechanism; it does not prove the original prior was physically correct or the completed orbit wrong.', '']
    comparison=OUT/'rf_comparisons/spec.json'
    if comparison.exists():
        lines += ['Two additional contexts were selected by the largest minimum RF gain across c arms among accepted history-only scans, excluding DS26-0058; position errors were absent from that selection rule. Their endpoints reuse the exact saved matched fits, and the new component audit keeps each original RF position fixed. These are contextual checks, not fresh holdouts.', '',
            '| RF-selected scan | c=0 position-error change (m) | fitted-c position-error change (m) | c=0 objective change | fitted-c objective change |',
            '|---|---:|---:|---:|---:|']
        for selected in read(comparison)['selected']:
            rr=read(comparison.parent/selected['case']/'result.json')['saved_matched_endpoints']
            lines.append('| '+selected['case']+' | '+' | '.join(fmt(v) for v in (rr['c0']['delta_error_m'],rr['fitted_c']['delta_error_m'],rr['c0']['delta_objective'],rr['fitted_c']['delta_objective']))+' |')
        lines += ['', 'Their complete prior interventions and raw receipts are in [rf_comparisons](rf_comparisons/spec.json). Shared identities and nearby observations may make these contexts correlated; they do not establish independent generalization.', '']
        lines += ['DS26-0062 has a different standalone family, 67821, whose phase width grows from 1 to 4.163 s; its predictive-mixture score accounts for about 54.3 of the 63.2-unit fixed-position score gain, yet localization improves only about 6 m. DS26-0060 has no standalone mixture; its calibration phase-width change supplies about 42.9 score units, and localization improves about 132–141 m. These contexts rule out treating every history-induced widening as the same numerical mechanism or applying a universal rejection based on the DS26-0058 outcome alone.', '']
    if (OUT/'family_diagnostic.json').exists():
        lines += ['![Predictive family phase and native residuals](plots/family_phase_residuals.png)', '',
            'The family figure uses the saved RF-best qualified endpoint in each cell. It shows prior and posterior phase density and raw native CFO residuals, including every retained family point; the likelihood integrates a shared per-track bias, so raw residual means need not be zero. The phase posterior remains near -7.3 s with a roughly 0.045 s posterior standard deviation. That location is about 7.3 original-prior standard deviations from zero, versus about 0.49 after widening to 15 s. The normalized score gains largely reflect relief of this old phase-prior penalty, while its position-coupled pull also changes. This does not prove the 1 s fallback was physically right or the completed-history width physically wrong. No identity-confidence probability is inferred.', '']
    (OUT/'report.md').write_text('\n'.join(lines))
    print('Rendered comparisons and report',flush=True)


if __name__=='__main__':main()
