"""Summarize exact fold/phase precision measurements without changing the solver."""

import argparse
import hashlib
import json
import statistics
from pathlib import Path


def main(root):
    out = Path(__file__).resolve().parent
    result = json.loads((root / 'result.json').read_bytes())
    for name, sha in result['plan']['bindings'].items():
        choices = [Path(name)]
        if '/src/' in name:
            choices.append(out / 'candidate-src' / name.split('/src/', 1)[1])
        assert any(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == sha
                   for p in choices), name
    assert result['exact'] and all(r['exact'] for r in result['results'])
    rows = []
    for trial in result['results']:
        if trial['side'] != 'observed':
            continue
        calls = [r for r in trial['calls'] if r['phase'] != 'signature']
        phases = {i: [r for r in calls if r['phase'] == i] for i in range(5)}
        assert sum(map(len, phases.values())) == len(calls)
        rows.append(dict(fold=trial['fold'], arm=trial['arm'], seed=trial['seed'],
                         points=sorted({r['points'] for r in calls}),
                         widths=sorted({r['width'] for r in calls}),
                         seconds=trial['seconds'], calls=len(calls),
                         mean_iterations=statistics.mean(r['iterations'] for r in calls),
                         total_iterations=sum(r['iterations'] for r in calls),
                         at_limit=sum(r['iterations'] == 256 for r in calls),
                         unconverged=sum(r['iterations'] == 256 and r['final_change'] >= 1e-5
                                         for r in calls),
                         first_phase_seconds=sum(r['seconds'] for r in phases[0]),
                         phase_iterations=[sum(r['iterations'] for r in phases[i])
                                           for i in range(5)]))
    assert len(rows) == 6
    (out / 'convergence.json').write_bytes((root / 'result.json').read_bytes())
    (out / 'convergence-summary.json').write_text(json.dumps(rows, indent=2) + '\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    labels = [f'Fold {r["fold"]} / {r["arm"]}' for r in rows]
    bars = axes[0].barh(labels, [r['calls'] for r in rows], color='#4485a7')
    axes[0].bar_label(bars, padding=3)
    axes[0].set(xlabel='Likelihood evaluations', xlim=(0, 410),
                title='The difficult fold makes more likelihood calls')
    axes[0].invert_yaxis()
    left = [0] * len(rows)
    for phase in range(5):
        values = [r['phase_iterations'][phase] for r in rows]
        axes[1].barh(labels, values, left=left, label=f'Phase round {phase+1}')
        left = [a+b for a, b in zip(left, values, strict=True)]
    axes[1].set(xlabel='Total precision iterations',
                title='Almost all slow-fold work is in its first round')
    axes[1].invert_yaxis()
    axes[1].legend(fontsize=8, loc='lower right')
    fig.suptitle('DS26-0066 target 1: same 175 / 176 nuisance columns across folds')
    fig.tight_layout()
    fig.savefig(out / 'convergence.png', dpi=160)
    plt.close(fig)
    table = '\n'.join(f'| {r["fold"]} | {r["arm"]} | {r["calls"]} | '
                       f'{r["mean_iterations"]:.1f} | {r["at_limit"]} | '
                       f'{r["unconverged"]} | {r["seconds"]:.3f} |' for r in rows)
    (out / 'convergence.md').write_text(f'''# Why one predictive fold dominates

The matrix dimensions are constant across folds: 175 nuisance columns for c=0
and 176 for fitted-c. The expensive fold evaluates more positions, and each
evaluation usually takes far more precision iterations. It spends almost all
that work in its first phase round, with a zero phase reference.

![Calls and precision iterations by fold and phase](convergence.png)

| Fold | Arm | Calls | Mean precision iterations | Reached 256 | Still unconverged | Fit s |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{table}

Fold 1's first phase round makes 269 likelihood calls in **each** arm. Of these,
220 reach 256 precision iterations; 219 c=0 calls and all 220 fitted-c calls
still exceed the unchanged 1e-5 stopping threshold. Reaching iteration 256 alone
does not prove nonconvergence, hence the separate counts. The maximum remaining
log-precision changes are about 0.0558 / 0.0568. Later rounds generally take
10 iterations per call. The first round accounts for 98.7% / 99.0% of all
precision iterations, and its likelihood calls consume 57.492 / 53.149 seconds
of the observed 60.687 / 55.693-second fits.

This identifies a computational bottleneck, not its full statistical cause.
The same matrix size rules out dimension alone. Fold membership changes the
evidence and conditioning; the first phase reference and initial position can
also make the provisional nuisance model difficult to fit. Distinguishing those
causes needs a further controlled diagnostic. These observations do not show
that a smaller iteration budget, warm start or altered prior preserves results.

All six observed complete fit signatures match. Folds 0 and 2 have fresh
unobserved controls; fold 1 uses the previous qualified complete signatures in
both arms. Signatures cover phase/optimizer history, endpoint and final state.
Context construction is outside fit timing. Final signature-only calls are
recorded separately and excluded from this table. Profiling timings are not
baseline/candidate speed measurements. [All calls and bindings](convergence.json).

The observer has two passing tests covering exact returned-object identity,
phase attribution, alias restoration and failure restoration; they are included
in the 1,492-test suite. It changes no source, data, split, budget, prior or
acceptance rule. The compiled-assembly candidate is active during this profile;
the full signatures still agree with the independent pre-assembly reference.

The next useful diagnostic is to retain the first-round objective/precision
trajectory and compare its successful versus capped evaluations. Check whether
the expensive trajectories repeat across both arms or different recovery
targets before implementing a cache. Any reuse must account for complete model
state and mutable audit receipts; raw position alone is insufficient. Alternative
stopping rules or initialization would be algorithm changes, outside the current
identical-output optimization contract.

Reproduce with `tools/profile_algo07v3_training_convergence.py --request REQUEST
--expected-root QUALIFIED_TRAINING_ROOT --output FRESH_ROOT`, pinned to one CPU,
one BLAS thread and an external 600-second bound. This renderer takes `--root`.
''')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    main(parser.parse_args().root)
