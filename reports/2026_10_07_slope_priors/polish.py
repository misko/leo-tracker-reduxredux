"""One matched continuation per own-option/own-arm basin; retain screen floors."""

import argparse
import copy
import json
from pathlib import Path
import time

import run as screen
import numpy as np

HERE = Path(__file__).resolve().parent
SECONDS = 18.
ITERATIONS = 600


def inside(vector, prior_radius, center):
    value = np.asarray(vector, float).copy()
    for origin, radius in [(np.zeros(2), prior_radius), (np.asarray(center), 25.)]:
        delta = value[:2] - origin
        distance = np.linalg.norm(delta)
        if distance > radius:
            assert distance - radius < 1e-6
            value[:2] = origin + delta * ((radius - 1e-8) / distance)
    return value


def main(option):
    source = HERE / option / 'results.json'
    previous_raw = source.read_bytes()
    previous = json.loads(previous_raw)
    assert previous['status'] == 'complete' and previous['option'] == option
    manifest_path = HERE / 'inputs/manifest.json'
    assert previous['manifest_sha256'] == screen.digest(manifest_path.read_bytes())
    for filename, digest in previous['source_hashes'].items():
        assert screen.digest(Path(filename).read_bytes()) == digest
    manifest = json.loads(manifest_path.read_text())
    destination = HERE / 'polished' / option
    destination.mkdir(parents=True, exist_ok=True)
    assert not (destination/'progress.json').exists() and not (destination/'results.json').exists()
    begun = time.monotonic()
    output = {key: copy.deepcopy(value) for key,value in previous.items()
              if key not in ['runs', 'seeds', 'selections', 'nested_search_gaps', 'elapsed_s', 'fit_elapsed_s']}
    output.update(status='running', phase='own-option-continuation', seconds_per_fit=SECONDS,
                  maximum_iterations=ITERATIONS, parent_receipt_sha256=screen.digest(previous_raw),
                  continuation_protocol_sha256=screen.digest((HERE/'polish_protocol.txt').read_bytes()),
                  continuation_source_sha256=screen.digest(Path(__file__).read_bytes()),
                  runs=[], seeds=[], selections=[], nested_search_gaps=[])

    def save():
        temporary = destination/'progress.tmp'
        temporary.write_text(json.dumps(output,indent=2,default=screen.encode)+'\n')
        temporary.replace(destination/'progress.json')

    save()
    for case in manifest['cases']:
        cid = case['case']
        for method, basins in case['methods'].items():
            for basin in basins:
                region = case['basins'][basin]
                obj = screen.load_objective(manifest_path.parent,case,basin,method)
                for arm in screen.ARMS:
                    eligible = [r for r in previous['candidates'] if r['case']==cid and r['method']==method
                                and r['arm']==arm and r['basin']==basin and r['feasible']]
                    source_row = min(eligible,key=lambda r:(r['selection_score'],r['origin']))
                    seed = inside(source_row['vector'],obj.prior.radius_km,region['center_km'])
                    metadata = dict(case=cid, fixture_sha256=region['sha256'],
                                    association_seed_sha256=source_row['association_seed_sha256'],
                                    shared_seed_sha256=source_row['shared_seed_sha256'],
                                    seed_sha256=screen.vector_digest(seed),
                                    parent_seed_sha256=screen.vector_digest(source_row['vector']),
                                    parent_origin=source_row['origin'])
                    output['seeds'].append(dict(option=option,method=method,basin=basin,arm=arm,
                                                origin='own-best',vector=seed.tolist(),**metadata))
                    try:
                        fit = screen.fit_position(obj,seed,rf_arm=arm,maximum_seconds=SECONDS,
                                                  maximum_iterations=ITERATIONS,local_center=np.asarray(region['center_km']),
                                                  local_radius_km=25.,slope_half_width_hz_s=screen.OPTIONS[option])
                    except (TimeoutError,ValueError,ArithmeticError) as error:
                        output['runs'].append(dict(option=option,case=cid,method=method,basin=basin,arm=arm,
                                                    origin='polish:own-best',status='failed',error=str(error),elapsed_s=None,
                                                    **{k:v for k,v in metadata.items() if k!='case'}))
                        save()
                        continue
                    row = screen.candidate(obj,region,fit.vector,option,arm,basin,method,'polish:own-best',
                                           elapsed_s=fit.elapsed_s,evaluations=fit.evaluations,stop_reason=fit.stop_reason,
                                           status='complete',solver_stationarity=fit.stationarity,**metadata)
                    np.testing.assert_allclose(row['objective'],fit.objective,atol=1e-6,rtol=0)
                    np.testing.assert_allclose(row['stationarity'],fit.stationarity,atol=1e-5,rtol=0)
                    output['runs'].append(row)
                    if row['feasible']:
                        output['candidates'].append(row)
                    save()
                    print(option,cid,method,basin,arm,round(row['selection_score'],3),row['converged'],flush=True)
            for arm in screen.ARMS:
                output['selections'].append(screen.select(output['candidates'],cid,method,arm))
            zero, free = [screen.select(output['candidates'],cid,method,arm) for arm in screen.ARMS]
            gap = max(0.,free['selection_score']-zero['selection_score'])
            output['nested_search_gaps'].append(dict(case=cid,method=method,gap=gap,incomplete_search=bool(gap>1e-6)))
        ref = case['evaluation_reference']
        a,b = np.radians([ref['latitude_deg'],ref['longitude_deg']])
        for row in output['candidates']:
            if row['case'] != cid:
                continue
            lat,lon = np.radians(screen.coordinates(screen.RegionalPrior(**case['prior']),row['vector'][:2]))
            h = np.sin((lat-a)/2)**2 + np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
            row['horizontal_error_m'] = float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
        save()
    output.update(status='complete',elapsed_s=time.monotonic()-begun,
                  fit_elapsed_s=sum(r['elapsed_s'] or 0. for r in output['runs']))
    save()
    (destination/'results.json').write_text(json.dumps(output,indent=2,default=screen.encode)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--option',required=True,choices=screen.OPTIONS)
    main(parser.parse_args().option)
