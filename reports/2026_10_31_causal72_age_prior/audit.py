"""Matched input checks and half-step phase integration stability audit."""
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import run

ROOT=Path(__file__).resolve().parent


def one(case):
    run.ROOT=ROOT/'quadrature'
    return run.run_case(case,step=.05)


if __name__=='__main__':
    cases=run.read(ROOT/'protocol.json')['cases']
    with ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1) as pool:list(pool.map(one,cases))
    rows=[]
    for path in sorted((ROOT/'cases').glob('*/*.json')):
        if path.name=='failure.json':raise ValueError(path)
        a=run.read(path);b=run.read(ROOT/'quadrature'/path.relative_to(ROOT))
        def bykey(z):return {(r['arm'],r['policy']):r for r in z['summaries']}
        aa,bb=bykey(a),bykey(b)
        for key,s in aa.items():
            t=bb[key]
            rows.append(dict(case=a['source']['case'],fragment_id=a['source']['fragment_id'],arm=key[0],policy=key[1],
                             same_winner=s['winner']['norad']==t['winner']['norad'],same_runner_up=s['runner_up']['norad']==t['runner_up']['norad'],
                             winner_score_difference=t['winner']['score']-s['winner']['score'],
                             margin_difference=t['margin']-s['margin']))
        for policy in run.POLICIES:
            c0={r['norad'] for r in a['candidate_rows'] if r['policy']==policy and r['arm']=='c0'}
            cc={r['norad'] for r in a['candidate_rows'] if r['policy']==policy and r['arm']=='fitted_c'}
            if c0!=cc:raise ValueError('c arms have different candidate coverage')
        for r in a['candidate_rows']:
            if r['policy'].startswith('48') and r['age_h']>48:raise ValueError('48h membership failed')
            if r['age_h']>72:raise ValueError('72h membership failed')
        obs=a['source']['observation_ids']
        if len(obs)!=len(set(obs)) or len(obs)!=a['source']['points']:raise ValueError('Native point identity mismatch')
    run.write(ROOT/'quadrature-audit.json',dict(rows=rows,all_winners_stable=all(r['same_winner'] for r in rows),
              all_runners_stable=all(r['same_runner_up'] for r in rows),
              maximum_absolute_winner_score_difference=max(abs(r['winner_score_difference']) for r in rows),
              all_matched_input_checks_pass=True))
    print('audit complete',len(rows),'cells',flush=True)
