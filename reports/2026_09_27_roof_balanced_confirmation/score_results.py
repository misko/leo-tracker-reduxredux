"""Whole-cohort distance reporting after frozen searches finish."""
import argparse
import json
from pathlib import Path
import run_balanced_confirmation as runner
from score_confirmation import distance_km, summarize
from score_balanced_development import verify_budget

HERE=Path(__file__).resolve().parent


def main(deduplicate=False):
    entries,contract=runner.inputs()
    contract_sha=runner.base.digest((HERE/'contract.json').read_bytes())
    prefix='dedup-' if deduplicate else ''
    results={};hashes={}
    for entry in entries:
        sid=entry['session_id'];path=HERE/f'{prefix}search-{sid}.json'
        if not path.exists() or not json.loads(path.read_text()).get('finished'):
            print('PENDING: whole-cohort gate; no reference errors computed');return
        payload=path.read_bytes();result=json.loads(payload)
        if result['session_id']!=sid or result['contract_sha256']!=contract_sha:
            raise ValueError('result binding mismatch')
        if result['deduplicate_reception']!=deduplicate or result['cache_sha256']!=entry['cache_sha256']:
            raise ValueError('sensitivity/input mismatch')
        if set(result['branches'])!={'sacramento','reno'}:raise ValueError('missing prior')
        for branch in result['branches'].values():
            if set(branch['arms'])!={'D','D_plus_geometry'}:raise ValueError('missing objective')
            for arm in branch['arms'].values():verify_budget(arm)
            if runner.frozen.select_rx_guided_doppler(branch)!=branch['geometry_guided_doppler']:
                raise ValueError('secondary selection mismatch')
        results[sid]=result;hashes[sid]=runner.base.digest(payload)
    manifest=json.loads((HERE/'manifest.json').read_text())
    if [x['pose']['session_id'] for x in manifest['sessions']]!=contract['session_ids']:
        raise ValueError('reference cohort mismatch')
    rows=[]
    for item in manifest['sessions']:
        sid=item['pose']['session_id'];pose=item['pose']['pose_authority']
        truth=(pose['latitude_deg'],pose['longitude_deg'])
        def error(point):return distance_km((point['latitude_deg'],point['longitude_deg']),truth)
        for prior,branch in results[sid]['branches'].items():
            d=error(branch['arms']['D']['selected']);j=error(branch['arms']['D_plus_geometry']['selected'])
            g=error(branch['geometry_guided_doppler']['selected'])
            rows.append(dict(session_id=sid,prior=prior,doppler_error_km=d,geometry_error_km=j,
                change_km=j-d,geometry_guided_doppler_error_km=g,guided_change_km=g-d))
    guided=[dict(r,geometry_error_km=r['geometry_guided_doppler_error_km'],change_km=r['guided_change_km']) for r in rows]
    out=dict(complete=True,deduplicate_reception=deduplicate,rows=rows,
        primary_aggregate=summarize(rows),secondary_aggregate=summarize(guided),
        search_sha256=hashes,contract_sha256=contract_sha,
        scope='Second outcome-blind four-recording cohort; fixed depth-balanced160-point independent-prior searches. Operator coordinate reference, not surveyed GPS. No population-wide resolution guarantee.')
    runner.base.atomic(HERE/f'{prefix}distance_results.json',out)
    print(json.dumps(out,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--deduplicate-reception',action='store_true')
    main(parser.parse_args().deduplicate_reception)
