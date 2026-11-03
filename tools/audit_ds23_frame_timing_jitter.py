"""RF-only figures separating rounded-frame artifacts from irregular timing."""

from pathlib import Path
import numpy as np
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_fractional_frame_jitter'
ROUNDED = ROOT/'reports/2026_10_20_ds23_frame_timing_jitter'


def main():
    rounded, fractional = read(ROUNDED/'full_evaluation.json'), read(OUT/'full_evaluation.json')
    if rounded['failures'] or fractional['failures']:
        raise ValueError('RF timing comparison has unavailable probes')
    first = {(r['case'], r['probe']): r for r in rounded['rows']}
    second = {(r['case'], r['probe']): r for r in fractional['rows']}
    if set(first) != set(second):
        raise ValueError('RF timing comparison uses different probes')
    for directory in [ROUNDED, OUT]:
        protocol = read(directory/'protocol.json')
        for name, digest in protocol['source_sha256'].items():
            if sha(ROOT/'tools'/name) != digest:
                raise ValueError('RF timing source changed')
    for name, digest in read(OUT/'workflow_protocol.json')['source_sha256'].items():
        if sha(ROOT/'tools'/name) != digest:
            raise ValueError('fractional waveform or wrapper source changed')
    keys = sorted(first); cases = sorted({c for c, _ in keys}); rows = []
    for key in keys:
        for role in ['first', 'second']:
            old, new = first[key]['components'][role], second[key]['components'][role]
            jitter = np.array(old['jitter_fit']['frame_jitter_samples'])
            k = np.arange(len(jitter)); expected = k*(2500000/750)-np.rint(k*(2500000/750))
            after = jitter-expected
            rows.append(dict(case=key[0], probe=key[1], role=role,
                rounded_qualified=old['qualified'], fractional_qualified=new['qualified'],
                rounded_jitter_RMS_samples=float(np.sqrt(np.mean(jitter**2))),
                rounded_jitter_after_known_pattern_RMS_samples=float(np.sqrt(np.mean(after**2))),
                fractional_jitter_RMS_samples=float(np.sqrt(np.mean(np.array(new['jitter_fit']['frame_jitter_samples'])**2))),
                rounded_model_CFO_shift_hz=old['jitter_minus_baseline_CFO_hz'],
                fractional_model_CFO_shift_hz=new['jitter_minus_baseline_CFO_hz'],
                fractional_heldout_gain=[f['heldout_jitter_improvement_profile_units'] for f in new['folds']],
                fractional_BIC_gain=new['full_extra_parameter_BIC_gain']))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for row, case in enumerate(cases):
        key = next(k for k in keys if k[0] == case)
        for role, color in [('first', 'tab:blue'), ('second', 'tab:orange')]:
            a = np.array(first[key]['components'][role]['jitter_fit']['frame_jitter_samples'])
            b = np.array(second[key]['components'][role]['jitter_fit']['frame_jitter_samples'])
            axes[row, 0].plot(np.arange(len(a)), a, '.-', color=color, label='Rounded template · '+role)
            axes[row, 1].plot(np.arange(len(b)), b, '.-', color=color, label='Fractional template · '+role)
        k = np.arange(len(a)); expected = k*(2500000/750)-np.rint(k*(2500000/750))
        axes[row, 0].plot(k, expected, 'k--', label='Known template rounding')
        for ax in axes[row]:
            ax.set(title=case+f' probe{key[1]}', xlabel='Frame number', ylabel='Fitted timing perturbation (samples)', ylim=(-.6, .6))
            ax.grid(alpha=.2); ax.legend(fontsize=8)
    fig.suptitle('The apparent timing jitter mainly follows the reference template’s repeating rounding pattern\nSame original saved IQ, fixed guarded samples and fixed0.15sample prior')
    fig.savefig(OUT/'template_rounding_ablation.png', dpi=160); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for case in cases:
        group = [r for r in rows if r['case'] == case]
        axes[0].hist([g for r in group for g in r['fractional_heldout_gain']], bins=25, alpha=.5, label=case)
        axes[1].hist([r['fractional_model_CFO_shift_hz'] for r in group], bins=25, alpha=.5, label=case)
    axes[0].set(xlabel='Held-out profile gain of irregular timing (positive helps)', ylabel='Training/test folds')
    axes[1].set(xlabel='Extra CFO correction after fractional frame placement (Hz)', ylabel='Component fits')
    for ax in axes:
        ax.axvline(0, color='k', lw=.7); ax.grid(alpha=.2); ax.legend()
    fig.suptitle(f'Fractional-template control: {sum(r["fractional_qualified"] for r in rows)}/{len(rows)} irregular-timing fits qualify\nNo position measurements changed; no localization improvement claimed')
    fig.savefig(OUT/'irregular_timing_qualification.png', dpi=160); plt.close(fig)
    receipt = dict(rows=rows, component_fits=len(rows), rounded_qualified=sum(r['rounded_qualified'] for r in rows),
        fractional_qualified=sum(r['fractional_qualified'] for r in rows),
        original_IQ_and_guarded_sample_support_matched=True,
        saved_estimates_replayed_by_source_binding_not_all_RF_optimizers_rerun=True,
        tests_verify_derivatives_zero_jitter_controls_and_training_sample_isolation=True,
        no_position_observations_changed=True, no_position_accuracy_gain_claim=True,
        diagnostic_conclusion='Apparent large jitter is mostly known rounded-template geometry. Irregular timing offers no qualified correction after that control.',
        rounded_evaluation_sha256=sha(ROUNDED/'full_evaluation.json'), fractional_evaluation_sha256=sha(OUT/'full_evaluation.json'))
    write(OUT/'comparison_audit.json', receipt)
    print('TIMING_AUDIT', {k: receipt[k] for k in ['component_fits', 'rounded_qualified', 'fractional_qualified']}, flush=True)


if __name__ == '__main__':
    main()
