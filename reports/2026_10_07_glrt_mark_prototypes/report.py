"""Render the completed prototype evidence; never acquire RF or refit a model."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent


def main(association_output):
    summary=json.loads((HERE/'summary.json').read_text())
    association=json.loads((HERE/'association_summary.json').read_text())
    with (HERE/'per_scan.csv').open() as stream: rows=list(csv.DictReader(stream))
    assert len(rows)==320 and len(association)==96
    converged=sum(r['converged']=='True' for r in rows)
    table=['| Model | RF arm | Variant | Median error Δ (m) | Improved / worsened | Converged / 16 | Both converged |',
           '|---|---|---|---:|---:|---:|---:|']
    for r in summary:
        if r['mode']=='control':continue
        table.append(f"| {r['model']} | {r['arm']} | {r['mode']} | {r['median_error_change_m']:+.1f} | {r['improved']} / {r['worsened']} | {r['converged']} | {r['both_converged']} |")
    assoc_table=['| RF arm | Variant | Total gained windows | Total lost windows | Relabeled windows | Changed satellite sets / 16 |',
                 '|---|---|---:|---:|---:|---:|']
    for arm in ('fitted-c','zero-c'):
        for mode in ('weighted-support','shuffled-support'):
            selected=[r for r in association if r['arm']==arm and r['mode']==mode]
            assoc_table.append(f"| {arm} | {mode} | {sum(r['gained_windows'] for r in selected)} | {sum(r['lost_windows'] for r in selected)} | {sum(r['relabeled_windows'] for r in selected)} | {sum(bool(r['added_satellites'] or r['removed_satellites']) for r in selected)} |")
    figs=HERE/'figures'
    fig,axes=plt.subplots(1,2,figsize=(12,5),sharey=True)
    for i,arm in enumerate(('fitted-c','zero-c')):
        for mode,color in [('weighted-support','#0072B2'),('shuffled-support','#999999')]:
            selected=sorted((r for r in association if r['arm']==arm and r['mode']==mode),key=lambda r:r['scan'])
            axes[i].plot(range(1,17),[r['gained_windows']-r['lost_windows'] for r in selected],'o-',label=mode,color=color,ms=4)
        axes[i].axhline(0,color='black',lw=.8);axes[i].set(title=arm,xlabel='Scan N',ylabel='Assigned-window change',xticks=range(1,17))
    axes[0].legend(fontsize=9);fig.suptitle('Discrete greedy association: GLRT-weighted support versus control\nCoverage change does not establish correct satellite identity')
    fig.tight_layout();fig.savefig(figs/'association_changes.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4))
    rank=np.linspace(0,1,100);ax.plot(rank,2**(2*rank-1),label='Signal-odds multiplier')
    ax.plot(rank,2**(.5-rank),label='Frequency-width multiplier')
    ax.plot(rank,.5+rank,label='Discrete-support weight')
    ax.axhline(1,color='black',lw=.8);ax.set(xlabel='Within receiver/channel margin percentile',ylabel='Multiplier',title='Frozen, bounded reliability mappings — assumptions, not calibration')
    ax.legend();fig.tight_layout();fig.savefig(figs/'mark_mappings.png',dpi=160);plt.close(fig)
    input_windows=sum(int(r['windows']) for r in rows if r['model']=='T1AT' and r['arm']=='fitted-c' and r['mode']=='control')
    controls=[r for r in summary if r['mode']=='control']
    control_text='; '.join(f"{r['model']} {r['arm']}: {r['median_error_m']:.0f} m ({r['converged']}/16 converged)" for r in controls)
    fastest=sum(float(r['elapsed_s']) for r in rows)
    text=f'''# GLRT strength in final scoring and satellite association: N01–N16 prototypes

Completed October 7, 2026. **These bounded heuristics do not demonstrate a reliable position improvement.** Keep the current default. Their value is a tested way to evaluate GLRT reliability in the likelihood and in discrete selection; the shuffled control and incomplete convergence prevent a promotion claim.

## What the current pipeline does

GLRT ranks/gates raw candidates, estimates CFO and affects tracking support. In the existing T1AT/V16 final likelihood, retained windows have equal base weight: original GLRT margin is not a continuous score weight. Discrete T1AT association maximizes coherent assigned-window count minus 10 per satellite; frequency residuals and timing break ties. The earlier V16 implementation review remains in the archived analysis workspace.

Adding the same GLRT bonus to every satellite explanation of one window cannot distinguish those satellites. Useful mechanisms must instead alter signal-versus-clutter odds, frequency precision, or coherent selection support. A future satellite-conditioned IQ test would need different predicted frequency trajectories and independent confirmation evidence.

## Implemented approaches

![Bounded GLRT mark mappings](figures/mark_mappings.png)

Compute a margin midrank separately in each receiver/channel lane; tied margins get the same mark and a constant lane is neutral. Let `u` be that rank percentile and `z=2u−1`. There is no truth-based tuning or threshold selection.

1. **Signal prior:** multiply each satellite's detection odds within a window by `2**z`, bounded from 0.5 to 2. This changes signal-versus-clutter responsibilities while retaining the normalized nonempty finite-set model.
2. **Precision:** multiply frequency standard deviation by `2**(-z/2)`, bounded from 0.707 to 1.414. Stronger margins therefore impose a narrower frequency constraint. Its normalization, gradient and Fisher weights use the same per-window width.
3. **Joint:** combine those changes. **Shuffled joint** permutes marks within each lane with fixed seed 7007, preserving every lane's mark distribution while breaking its relation to the observed window.
4. **Discrete support:** replace coherent window count by the sum of `1+0.5z`, bounded from 0.5 to 1.5 and mean 1 over each lane. Keep the satellite penalty at 10, exclusivity, one timing mode per satellite, 600 Hz gate, and coherent segments with at least 10 windows, at least 5 s span and at most 5 s gaps. Compare with uniform and shuffled support.

The mappings are **assumed reliability relationships**, not measured error calibration or calibrated signal probabilities. Same-IQ score maximization and CFO estimation are coupled. Whole-scan ranks make this a retrospective prototype, not a causal online implementation.

## Matched final-score experiment

All 16 scans completed: **320 position fits**, covering T1AT/C0 and V16 × fitted-`c` and `c=0` × five variants. The {input_windows:,} frozen associated top-one windows, satellite banks, receiver baseline, observations, timing priors, hard bounds, shared 12-start archived pool and maximum search budgets stay matched. Both RF arms keep the same upstream fitted-`c` calibration baseline; this is a controlled **final RF-term ablation**, not independent `c=0` recalibration.

Every trial reprices the same 12 archived starts under its own objective, chooses two by score, runs two 1 s searches and one 1 s polish in the existing 4 km disk. Position truth is used only for evaluation. These are warm-started local prototype searches, not fresh blind localization or global-optimum certificates. The archived calibration is conditioned on the known roof. Aggregate case elapsed time was {fastest/60:.1f} process-minutes with four fit workers; no new RF collection or raw-IQ campaign ran.

Matched control median errors: {control_text}.

![Paired position changes](figures/position_changes.png)

Negative change is better. Improved/worsened counts require an absolute change greater than 1 m. The table includes all completed cases, **including unconverged ones**, as exploratory best-found outcomes.

{chr(10).join(table)}

Only **{converged}/320 fits meet the existing KKT convergence threshold**. `summary.json` also reports paired medians restricted to cases where both control and variant converged; these small, selected subsets are not a robust validation cohort. A lower objective within one method chooses its solution; raw NLL values across changed likelihoods are not comparable evidence of improvement.

![Frequency fit versus position accuracy](figures/fit_vs_position.png)

The residual RMS is posterior-weighted and its weights change with the method. `per_scan.csv` separately records original-owner RMS and repricing under the common unmarked reference likelihood. Neither better in-sample RMS nor a better common reference score establishes better localization. Soft winners and clutter responsibilities may change only within the frozen selected satellite bank; this is distinct from discrete candidate selection.

## Discrete satellite-selection prototype

All 16 scans completed: **96 greedy-selection cases** (two RF calibration arms × uniform, weighted and shuffled support). The uniform implementation exactly reproduced the archived initial greedy assignments and count objective in **32/32 controls**. Both arms reuse the same timing-mode inventory and original top-one observation IDs; their saved residual predictions differ by the archived RF arm. Membership may change here, so these diagnostics are separate from the matched-window position ablation above.

![Discrete association changes](figures/association_changes.png)

{chr(10).join(assoc_table)}

This prototype covers **greedy selection only**. It does not execute the archived one-out/many-in replacement repairs, regenerate timing hypotheses, or rerun position fitting on the newly selected banks. Changed coverage, satellite count or NORAD labels do not establish correct satellite identities; independent identity ground truth is unavailable here.

## Verification and artifacts

- Nine component tests cover neutral equivalence to the original finite-set likelihood, numerical gradients, posterior normalization, lane ties, monotonic score-transform invariance, deterministic shuffle, bounds, rejection of duplicate-window inputs, and exclusive weighted association.
- Read-only cohort verification checks **32 neutral objective/gradient/curvature comparisons** and **16 marked directional gradient comparisons** on N01 and N16. See `verification.json`.
- `marks.py` owns the likelihood, `experiment.py` runs the fit comparison, `association.py` owns the discrete selection prototype, and `report.py` renders this report and figures.
- The executed fit runner is archived in `source_snapshots/experiment_executed.py`. The final summarizer adds paired-convergence fields without changing numerical fitting. Case-level source digests describe files at receipt creation; provenance also identifies the executed runner snapshot.
- Compact outcomes: [per-scan CSV](per_scan.csv), [position summary](summary.json), [association summary](association_summary.json), [verification](verification.json), [provenance](provenance.json). Full immutable-input receipts and fit traces are under `/srv/bulk/leo/glrt-mark-n01-n16-20261007-v1`; discrete receipts are under `/srv/bulk/leo/glrt-mark-association-n01-n16-20261007-v1`.

## Next steps

Keep these as research prototypes. First calibrate frequency error and signal/clutter odds against GLRT score using independent pilot splits or independent windows, stratified by receiver, rate and edge. Freeze that calibration before a held-out scan comparison. Repeat promising cases with sufficient **matched** optimizer budgets and multiple fixed shuffle seeds, while retaining the fitted-`c` versus `c=0` ablation. Only then connect a selected method to full replacement association and evaluate position accuracy on its changed banks. The present evidence does not justify replacing the default score.

## Reproduction

Use a scientific Python environment with NumPy, SciPy, Matplotlib and pytest. Runners require the archived N01–N16 inputs and original research modules in the analysis workspace; the published report bundle contains prototype code and compact evidence, rather than the full archive and upstream dependencies. Execute from that workspace's repository root; choose fresh output directories because runners do not overwrite completed fit directories.

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python -m pytest -q reports/2026_10_07_glrt_mark_prototypes/test_marks.py
python reports/2026_10_07_glrt_mark_prototypes/verify.py
python reports/2026_10_07_glrt_mark_prototypes/experiment.py --output /path/to/new-fit-run --workers 4
python reports/2026_10_07_glrt_mark_prototypes/association.py --output /path/to/new-association-run --workers 4
python reports/2026_10_07_glrt_mark_prototypes/report.py --association-output /path/to/new-association-run
```
'''
    (HERE/'README.md').write_text(text)
    provenance=json.loads((HERE/'provenance.json').read_text())
    provenance['association_result_sha256']={str(p):'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(association_output.glob('*.json'))}
    executed=HERE/'source_snapshots/experiment_executed.py'
    provenance['executed_fit_runner_source']=dict(path=str(executed),
        sha256='sha256:'+hashlib.sha256(executed.read_bytes()).hexdigest())
    provenance['source_sha256'].update({str(HERE/p):'sha256:'+hashlib.sha256((HERE/p).read_bytes()).hexdigest()
        for p in ('report.py','association.py','verify.py','test_marks.py')})
    (HERE/'provenance.json').write_text(json.dumps(provenance,indent=2))
    print('Report complete:',HERE/'README.md')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--association-output',type=Path,
                        default=Path('/srv/bulk/leo/glrt-mark-association-n01-n16-20261007-v1'))
    main(parser.parse_args().association_output)
