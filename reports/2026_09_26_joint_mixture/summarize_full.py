"""Independent accounting and scores for all DS5 joint-model cases."""
import argparse,json,statistics,math
from pathlib import Path
from run_full import plan,EXISTING,HERE


def summarize(scans,inventory,previous):
    inputs={r['session_id']:r for r in inventory['captures']};seen=set();buckets={};diagnostics=[];cases=[]
    for scan in scans:
        sid=scan['session_id']
        if sid in seen:raise ValueError('duplicate scan')
        seen.add(sid);inp=inputs[sid]
        if scan['evidence_sha256']!=inp['evidence_sha256']:raise ValueError('evidence mismatch')
        if scan['track_count']!=inp['track_count']:raise ValueError('track count mismatch')
        scopes=['all42']
        if sid not in previous:scopes.append('new35')
        if sid not in {'scan-fw-d86e8f23c0624bac','scan-fw-dc1153010e57ac76'}:scopes.append('excluding_two_development')
        scopes.append(f'rate_{inp["sample_rate_hz"]}')
        for noise in ('100.0','200.0'):
            r={site:scan['results'][site][noise] for site in ('reference','sacramento','reno')}
            for site_result in r.values():
                if not all(math.isfinite(x) for x in site_result['chain_nll']):raise ValueError('nonfinite chain score')
                for mode in ('frozen_no_clock','joint_no_clock','joint'):
                    fit=site_result[mode];tracks=fit['tracks'];denom=sum(t['test_blocks'] for t in tracks)
                    score=fit['composite_nll_per_test_block']
                    if denom<=0 or not math.isfinite(score):raise ValueError('invalid score')
                    recomputed=-sum(t['predictive_log_score'] for t in tracks)/denom
                    if not math.isfinite(recomputed) or abs(score-recomputed)>1e-9:raise ValueError('score accounting mismatch')
                    for track in tracks:
                        probabilities=list(track['probabilities'].values())
                        if not all(math.isfinite(p) and 0<=p<=1 for p in probabilities) or abs(sum(probabilities)-1)>1e-8:
                            raise ValueError('unnormalized assignment probabilities')
            tracksets=[{t['track_id'] for t in x['joint']['tracks']} for x in r.values()]
            if not all(t==tracksets[0] and len(t)==scan['track_count'] for t in tracksets):raise ValueError('track membership mismatch')
            n=[sum(t['test_blocks'] for t in x['joint']['tracks']) for x in r.values()]
            if len(set(n))!=1:raise ValueError('evaluation denominator mismatch')
            chain_winners=[min(r,key=lambda s:r[s]['chain_nll'][c]) for c in (0,1)]
            diag={'session_id':sid,'utc':scan['capture_start_utc'][11:16],'noise_hz':float(noise),
                'chain_winners':chain_winners,'chain_winner_disagreement':chain_winners[0]!=chain_winners[1],
                'max_chain_score_spread':max(abs(x['chain_nll'][0]-x['chain_nll'][1]) for x in r.values()),
                'max_assignment_tv':max(x['max_chain_assignment_total_variation'] for x in r.values()),
                'max_null_probability':max(x['joint']['mean_null_probability'] for x in r.values()),
                'max_prior_mass_omitted':scan['max_prior_mass_outside_support']}
            diagnostics.append(diag)
            for mode in ('frozen_no_clock','joint_no_clock','joint'):
                score={s:x[mode]['composite_nll_per_test_block'] for s,x in r.items()}
                for site in ('sacramento','reno'):
                    gap=score['reference']-score[site]
                    applicable=scopes+(['error_ge100km'] if inp['original_location_errors_m'][site]>=100000 else [])
                    for scope in applicable:buckets.setdefault((scope,noise,mode,site),[]).append((gap,n[0]))
                if mode=='joint':cases.append({'session_id':sid,'utc':diag['utc'],'noise_hz':float(noise),'scores':score,
                    'winner':min(score,key=score.get),'location_errors_m':inp['original_location_errors_m'],**{k:v for k,v in diag.items() if k not in ('session_id','utc','noise_hz')}})
    summaries=[]
    for (scope,noise,mode,site),rr in sorted(buckets.items()):
        gaps=[r[0] for r in rr]
        summaries.append({'scope':scope,'noise_hz':float(noise),'model':mode,'site':site,'scans':len(rr),
            'reference_wins':sum(g<-1e-10 for g in gaps),'ties':sum(abs(g)<=1e-10 for g in gaps),
            'mean_gap':statistics.mean(gaps),'median_gap':statistics.median(gaps),
            'block_weighted_gap':sum(g*n for g,n in rr)/sum(n for _,n in rr)})
    return {'completed':len(seen),'missing':sorted(set(inputs)-seen),'tracks':sum(s['track_count'] for s in scans),
        'summaries':summaries,'diagnostics':diagnostics,'cases':cases}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--allow-partial',action='store_true');args=parser.parse_args()
    expected,done,baseline=plan();scans=[];previous=set()
    for name in EXISTING:
        p=json.loads((HERE/name).read_text());scans+=p['scans'];previous|={s['session_id'] for s in p['scans']}
    for path in sorted((HERE/'full_scans').glob('*.json')):scans+=json.loads(path.read_text())['scans']
    inventory=json.loads((HERE.parent/'2026_09_26_ds5_probabilistic/input_audit.json').read_text())
    out=summarize(scans,inventory,previous)
    if not args.allow_partial:assert out['completed']==42 and not out['missing']
    out['scope']='Retrospective fixed-site composite predictive scores; pooled nonconverged chains are exploratory.'
    (HERE/'full_summary.json').write_text(json.dumps(out,indent=2)+'\n')
    (HERE/'full_results.json').write_text(json.dumps({'core_sha256':baseline['core_sha256'],
        'calibration_sha256':baseline['calibration_sha256'],'scans':sorted(scans,key=lambda s:s['capture_start_utc'])},indent=2)+'\n')
    lines=['# DS5 joint mixture: full evaluation','',f"Completed {out['completed']}/42 scans, {out['tracks']} tracks.",'',
        'All settings frozen from the original three-scan prototype. Seven completed scans reused after hash checks; remaining 35 evaluated with identical numerical core and calibration. Independent site-specific shortlists; no geographic search, new RF collection or production changes.','',
        'Lower composite predictive NLL is better. Gaps are known-location minus estimate: negative favors known location. These are not RMS values, geographic fixes, or calibrated location probabilities.','',
        '| Scope | Noise Hz | Model | Comparison | Known wins | Mean gap | Median gap |',
        '|---|---:|---|---|---:|---:|---:|']
    for r in out['summaries']:
        if r['scope'] not in ('all42','new35','error_ge100km'):continue
        lines.append(f"| {r['scope']} | {r['noise_hz']:g} | {r['model']} | {r['site']} | {r['reference_wins']}/{r['scans']} | {r['mean_gap']:.4f} | {r['median_gap']:.4f} |")
    lines+=['','## Inference reliability','',
        '| Noise Hz | Scans with different chain winners | Scans with max assignment TV >0.9 | Largest chain score spread |',
        '|---|---:|---:|---:|']
    for noise in (100.,200.):
        rr=[r for r in out['diagnostics'] if r['noise_hz']==noise]
        lines.append(f"| {noise:g} | {sum(r['chain_winner_disagreement'] for r in rr)}/{len(rr)} | {sum(r['max_assignment_tv']>.9 for r in rr)}/{len(rr)} | {max(r['max_chain_score_spread'] for r in rr):.4f} |")
    lines+=['','**Do not interpret nominal win counts as validated accuracy.** Equal pooling of chains with different modes does not estimate correct mode probabilities when sampling has not converged. Averaging predictive densities can yield an attractive pooled score even when individual chains disagree badly. The no-clock joint control has only one chain.','',
        'The model still conditions historical timing priors on ±120 seconds, uses an uncalibrated scan-clock prior and Gaussian 100/200 Hz block noise, and retains correlated train/evaluation time bins and receiver/track dependence. All published location estimates and original masks are reused. No parameters were tuned on these scores.','',
        'Full per-scan/site/track results and provenance are in full_results.json. full_summary.json additionally records sample-rate strata, development exclusions, large-error cases, score gaps and chain diagnostics. Per-scan logs and return codes are retained.']
    (HERE/'FULL_DS5_REPORT.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))


if __name__=='__main__':main()
