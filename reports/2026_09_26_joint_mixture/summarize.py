"""Summarize completed fixed-site experiments without selecting favorable settings."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent


def main():
    data=json.loads((HERE/'results.json').read_text())
    lines=['# Joint mixture feasibility results','',
        'Lower composite predictive NLL per evaluation block is better. These are fixed-site retrospective comparisons, not new location estimates. See PROTOCOL.md for model assumptions and limitations.','',
        '| UTC | Block noise (Hz) | Site | Frozen IDs, no clock | Joint IDs, no clock | Joint IDs + clock | Null tracks (posterior mean %) | Chain score spread |',
        '|---|---:|---|---:|---:|---:|---:|---:|']
    for scan in data['scans']:
        utc=scan['capture_start_utc'][11:16]
        for noise in ('100.0','200.0'):
            for site in ('reference','sacramento','reno'):
                r=scan['results'][site][noise]
                scores=[r[k]['composite_nll_per_test_block'] for k in ('frozen_no_clock','joint_no_clock','joint')]
                spread=max(r['chain_nll'])-min(r['chain_nll'])
                lines.append(f'| {utc} | {noise} | {site} | '+ ' | '.join(f'{v:.4f}' for v in scores)+
                    f" | {100*r['joint']['mean_null_probability']:.1f} | {spread:.4f} |")
    lines+=['','## Inference and approximation checks','',
        '| UTC | Max omitted historical prior mass (%) | Shared train/evaluation second bins | Max assignment TV between chains |',
        '|---|---:|---:|---:|']
    for scan in data['scans']:
        tv=max(r['max_chain_assignment_total_variation'] for site in scan['results'].values() for r in site.values())
        lines.append(f"| {scan['capture_start_utc'][11:16]} | {scan['max_prior_mass_outside_support']*100:.2f} | {scan['train_eval_shared_second_bins_count']} | {tv:.3f} |")
    lines+=['','A total-variation distance of 1 means the chains assigned some track to disjoint sets of hypotheses in retained draws. This is evidence of inadequate exploration for that track, not proof of calibrated ambiguity. The zero-clock joint arm has only one chain and weaker diagnostics. None of these runs should be promoted as a converged posterior without improved exploration and additional checks.',
        '', 'Settings were fixed before inspecting these scores. No best noise setting is selected. Report all arms, including unfavorable rankings.']
    (HERE/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))


if __name__=='__main__':main()
