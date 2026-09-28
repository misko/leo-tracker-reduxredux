"""Accounting and fixed-model comparison for four added DS5 scans."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent


def main():
    original=json.loads((HERE/'results.json').read_text())
    selection=json.loads((HERE/'additional_selection.json').read_text())
    shards=[json.loads((HERE/f'additional_shard_{i}.json').read_text()) for i in (0,1)]
    for shard in shards:
        for key in ('source_sha256','calibration_sha256','core_sha256'):assert shard[key]==original[key]
        assert set(shard['requested_sessions'])=={s['session_id'] for s in shard['scans']}
    added=sorted([s for p in shards for s in p['scans']],key=lambda s:s['capture_start_utc'])
    expected={s['session_id'] for s in selection['selected']}
    assert len(added)==4 and {s['session_id'] for s in added}==expected
    assert not expected&{s['session_id'] for s in original['scans']}
    inventory={s['session_id']:s for s in json.loads((HERE.parent/'2026_09_26_ds5_probabilistic/input_audit.json').read_text())['captures']}
    lines=['# Four additional DS5 scans: frozen joint model','',
        'Selected before new-model evaluation by fixed hash ranking, one per sample rate, excluding three original cases and two prior development examples. Model/core and calibration hashes match the original run. Locations and original masks remain reused: retrospective fixed-site evaluation, not fresh geographic validation.','',
        '| UTC | MS/s | Tracks | Sacramento error (km) | Reno error (km) |',
        '|---|---:|---:|---:|---:|']
    for s in added:
        inp=inventory[s['session_id']];assert s['evidence_sha256']==inp['evidence_sha256']
        e=inp['original_location_errors_m']
        lines.append(f"| {s['capture_start_utc'][11:16]} | {inp['sample_rate_hz']/1e6:g} | {s['track_count']} | {e['sacramento']/1000:.2f} | {e['reno']/1000:.2f} |")
    lines+=['','## Joint assignment + clock predictive scores','',
        'Composite negative log predictive density per evaluation block; lower is better. Not RMS or a location probability.','',
        '| UTC | Noise (Hz) | Known location | Sacramento | Reno | Lowest score | Max chain score spread | Max assignment TV |',
        '|---|---:|---:|---:|---:|---|---:|---:|']
    for s in added:
        for noise in ('100.0','200.0'):
            rr={site:s['results'][site][noise] for site in ('reference','sacramento','reno')}
            scores={site:r['joint']['composite_nll_per_test_block'] for site,r in rr.items()}
            spread=max(max(r['chain_nll'])-min(r['chain_nll']) for r in rr.values())
            tv=max(r['max_chain_assignment_total_variation'] for r in rr.values())
            lines.append(f"| {s['capture_start_utc'][11:16]} | {noise} | "+' | '.join(f'{v:.4f}' for v in scores.values())+
                f" | {min(scores,key=scores.get)} | {spread:.4f} | {tv:.3f} |")
    lines+=['','**Inference warning:** these are nominal combined-chain scores, not converged posterior results. '
        'At 11:20 / 100 Hz, reference and Sacramento chain scores differ dramatically and the location ordering changes by initialization. '
        'At 09:00 / 200 Hz, known-versus-Reno ordering also changes by chain. At 12:40, the reference chains disagree substantially at both noise settings. '
        'Equal pooling of nonconverged chains does not establish correct posterior mode weights; pooled predictive scores can be better than both chain totals because different tracks benefit from different modes. '
        'Do not interpret the following win counts as validated accuracy.','',
        '## Matched control comparisons','',
        '| Scope | Noise (Hz) | Model | Known beats Sacramento | Known beats Reno | Known lowest of three |',
        '|---|---:|---|---:|---:|---:|']
    summaries=[]
    for scope,scans in [('Additional four',added),('All seven',original['scans']+added)]:
        for noise in ('100.0','200.0'):
            for mode in ('frozen_no_clock','joint_no_clock','joint'):
                wins={'sacramento':0,'reno':0};best=0
                for s in scans:
                    scores={site:r[noise][mode]['composite_nll_per_test_block'] for site,r in s['results'].items()}
                    for site in wins:wins[site]+=scores['reference']<scores[site]
                    best+=scores['reference']<min(scores['sacramento'],scores['reno'])
                summaries.append({'scope':scope,'noise':noise,'model':mode,'scans':len(scans),'reference_wins':wins,'reference_best':best})
                lines.append(f"| {scope} | {noise} | {mode} | {wins['sacramento']}/{len(scans)} | {wins['reno']}/{len(scans)} | {best}/{len(scans)} |")
    lines+=['','## Limits','',
        'The two chains can disagree on individual assignments; a favorable aggregate score is not convergence evidence. No inference settings or hyperparameters were changed to favor the added scans. The known location is not guaranteed to have the smallest score, especially against nearby estimates under an imperfect model. Numerical support remains ±120s, and dependence/GLRT calibration is unchanged.','',
        f"Largest omitted historical timing prior mass among the added scans: {100*max(s['max_prior_mass_outside_support'] for s in added):.2f}%.",
        f"Largest posterior mean unexplained-track fraction in the added scans: {100*max(r['joint']['mean_null_probability'] for s in added for site in s['results'].values() for r in site.values()):.2f}%.",
        '', '## Decision', '',
        'Do not expand or deploy this sampler as-is. The frozen-ID timing-marginalized control favors the known location over Reno in all four additions (all seven total), versus only two of four additions (five of seven total) for the nominal joint scores. '
        'Fix posterior exploration and verify it on these bounded cases before attributing the ranking changes to the model or changing its priors/weights. '
        'The numerical core and historical calibration are unchanged; five tests pass, including the deterministic, score-independent scan-selection test.']
    (HERE/'ADDITIONAL_RESULTS.md').write_text('\n'.join(lines)+'\n')
    (HERE/'additional_summary.json').write_text(json.dumps({'selection':selection,'summaries':summaries,'scans':added},indent=2)+'\n')
    print('\n'.join(lines))


if __name__=='__main__':main()
