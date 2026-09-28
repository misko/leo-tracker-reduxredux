"""Post-confirmation development search; no reference coordinates are loaded."""
import argparse
import json
from pathlib import Path
import pickle
import time
import numpy as np
import run_topology_confirmation as frozen
from depth_balanced_search import search

HERE = Path(__file__).resolve().parent
base = frozen.base


def run(index):
    start = time.monotonic()
    entries, manifest_sha, inventory_sha = frozen.original.confirmation_entries()
    entry = entries[index]; sid = entry['session_id']
    target = HERE/f'balanced-development-{sid}.json'
    if target.exists():
        raise FileExistsError(target)
    prior_bytes = (HERE/f'topology-search-{sid}.json').read_bytes()
    prior_result = json.loads(prior_bytes)
    assert prior_result['finished']
    audit, audit_sha = frozen.frozen_audit()
    frequency, detection, continuous, variance, bias, models = frozen.frozen_models(audit, audit_sha)
    assert all(prior_result[key] == value for key, value in models.items())
    payload = Path(entry['cache_file']).read_bytes()
    assert base.digest(payload) == entry['cache_sha256']
    raw = pickle.loads(payload)
    prepared = base.prepare_adaptive_tle_position_inputs(sid, inputs=base.CachedInput(raw),
        archive=base.TleArchiveReader(Path('/var/lib/leo/tle')))
    assert prepared.input_manifest_sha256 == entry['input_manifest_sha256']
    assert prepared.analysis_manifest_sha256 == entry['analysis_manifest_sha256']
    prepared, receipt = frozen.filter_prepared(prepared, frozen.resolve(raw))
    assert receipt == prior_result['topology_receipt']
    rows = frozen.original.reception_endpoints.build(raw, prepared, bias_hz=bias)
    reception, _ = frozen.original.reception_inputs(prepared, rows, detection, continuous)
    banks, _ = base.build_prediction_banks(prepared.catalogue, prepared.candidate_indices,
        prepared.start_utc_ns, prepared.tracks, taus_s=np.array([0.]))
    out = dict(session_id=sid, finished=False, branches={}, manifest_sha256=manifest_sha,
        inventory_sha256=inventory_sha, topology_audit_sha256=audit_sha, model_hashes=models,
        original_search_sha256=base.digest(prior_bytes),
        scope='Exploratory development after confirmation unblinding. Search reads no reference or other-prior coordinates/IDs.',
        protocol=dict(budget_per_arm=160, timing_s=0, search='cyclic depth-balanced measured priorities',
            priors=base.PRIORS, levels_km=base.LEVELS))
    for name, (lat, lon, radius) in base.PRIORS.items():
        evaluator = frozen.original.RobustBranchEvaluator(banks, (lat, lon), reception, variance, frequency['parameters'])
        branch = dict(origin=[lat, lon], radius_km=radius, arms={})
        for arm in base.ARMS:
            result = search(evaluator.for_arm(arm), radius_km=radius,
                levels_km=base.LEVELS, budget_points=160)
            selected = result.global_incumbent
            branch['arms'][arm] = dict(selected=evaluator.cache[(selected.east_km, selected.north_km)],
                evaluated_points=len(result.all_evaluations), finest_points=len(result.finest_evaluations),
                stop_reason=result.stop_reason, trace=list(result.trace))
            print('ARM_DONE', sid, name, arm, flush=True)
        branch['point_components'] = [{k:v for k,v in p.items() if k!='tracks'} for p in evaluator.cache.values()]
        branch['geometry_guided_doppler'] = frozen.select_rx_guided_doppler(branch)
        out['branches'][name] = branch
        base.atomic(target, out)
    out['finished'] = True; out['elapsed_s'] = time.monotonic()-start
    out['code_sha256'] = {str(path):base.digest(path.read_bytes()) for path in (
        Path(__file__), frozen.original.LOCATION/'depth_balanced_search.py',
        frozen.original.LOCATION/'measured_search.py', frozen.original.LOCATION/'run_robust_search.py')}
    base.atomic(target, out)
    print('SCAN_DONE', sid, round(out['elapsed_s'], 1), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scan-index', type=int, required=True, choices=range(4))
    run(parser.parse_args().scan_index)
