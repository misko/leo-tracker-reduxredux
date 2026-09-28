"""Gaussian model unchanged; isolate measured-boundary search-policy repair."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import pickle
import time
import numpy as np
import run_search as base
from measured_search import search

HERE = Path(__file__).resolve().parent


def run(index):
    start = time.monotonic()
    inventory = json.loads((base.SOURCE/'evaluation_inventory.json').read_text())
    entry = [x for x in inventory if x['split'] == 'holdout'][index]
    sid = entry['session_id']
    target = HERE/f'measured-search-{sid}.json'
    if target.exists():
        raise FileExistsError('measured search output already exists')
    payload = Path(entry['cache_file']).read_bytes()
    if base.digest(payload) != entry['cache_sha256']:
        raise ValueError('tracking input cache digest mismatch')
    d, c, variance, endpoints, calibration = base.frozen_models_and_endpoints()
    if json.loads((HERE/'calibration.json').read_text()) != calibration:
        raise ValueError('frozen reception calibration changed')
    prepared = base.prepare_adaptive_tle_position_inputs(sid, inputs=base.CachedInput(pickle.loads(payload)),
        archive=base.TleArchiveReader(Path('/var/lib/leo/tle')))
    reception = base.reception_inputs(prepared, endpoints[sid], d, c)
    banks, receipt = base.build_prediction_banks(prepared.catalogue, prepared.candidate_indices,
        prepared.start_utc_ns, prepared.tracks, taus_s=np.array([0.]))
    print('BANK_READY', sid, round(time.monotonic()-start, 1), flush=True)
    out = dict(session_id=sid, finished=False, protocol=dict(
        question='Search-policy repair only; unchanged original Gaussian likelihood and RX model',
        priors=base.PRIORS, levels_km=base.LEVELS, budget_per_arm=160, arms=base.ARMS,
        frequency_sigma_hz=100, timing_s=0, top_k=3, track_weight='occupied one-second bins',
        search='Every queued cell measured, boundary representative inside cell and prior disk',
        truth_access='none; distance scoring after completion', cohort_status='development follow-up'),
        evidence_sha256=prepared.evidence_sha256, snapshot_digest=prepared.snapshot_digest,
        input_manifest_sha256=prepared.input_manifest_sha256, analysis_manifest_sha256=prepared.analysis_manifest_sha256,
        calibration_sha256=base.digest((HERE/'calibration.json').read_bytes()),
        prediction_receipt=asdict(receipt), tracks=len(prepared.tracks), branches={})
    for name, (lat, lon, radius) in base.PRIORS.items():
        evaluator = base.BranchEvaluator(banks, (lat, lon), reception, variance)
        branch = dict(origin=[lat, lon], radius_km=radius, arms={})
        for arm in base.ARMS:
            result = search(evaluator.for_arm(arm), radius_km=radius, levels_km=base.LEVELS, budget_points=160)
            selected = result.global_incumbent
            chosen = evaluator.cache[(selected.east_km, selected.north_km)]
            branch['arms'][arm] = dict(selected=chosen, stop_reason=result.stop_reason, complete=result.complete,
                evaluated_points=len(result.all_evaluations), finest_points=len(result.finest_evaluations),
                selection='global best evaluated objective', trace=list(result.trace))
            print('ARM_DONE', sid, name, arm, chosen['latitude_deg'], chosen['longitude_deg'], chosen['scores'], flush=True)
        branch['common_inventory_best'] = {arm: min(evaluator.cache.values(),
            key=lambda r: (r['scores'][arm], r['east_km'], r['north_km']))
            for arm in ('D', 'D_plus_detection', 'D_plus_geometry', 'D_plus_reversed_geometry')}
        branch['point_components'] = [{k: v for k, v in row.items() if k != 'tracks'} for row in evaluator.cache.values()]
        out['branches'][name] = branch
        out['elapsed_s'] = time.monotonic()-start
        base.atomic(target, out)
    out['finished'] = True
    out['elapsed_s'] = time.monotonic()-start
    out['code_sha256'] = {name: base.digest((HERE/name).read_bytes()) for name in
        ('run_measured_search.py', 'measured_search.py', 'run_search.py', 'location_core.py')}
    base.atomic(target, out)
    print('SCAN_DONE', sid, round(out['elapsed_s'], 1), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scan-index', required=True, type=int)
    run(parser.parse_args().scan_index)
