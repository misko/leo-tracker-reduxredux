"""Separate robust joint-likelihood development search; no test truth inputs."""
from __future__ import annotations
import argparse
from collections import defaultdict
from dataclasses import asdict
import json
from pathlib import Path
import pickle
import time
import numpy as np

import run_search as base
from robust_core import train_shortlist, joint_heldout_score
from measured_search import search

HERE = Path(__file__).resolve().parent


class RobustBranchEvaluator(base.BranchEvaluator):
    def __init__(self, banks, origin, reception, ratio_variance, parameters):
        super().__init__(banks, origin, reception, ratio_variance)
        self.parameters = parameters

    def evaluate(self, east, north):
        key = (float(east), float(north))
        if key in self.cache:
            return self.cache[key]
        lat, lon = base.coordinates(*self.origin, *key)
        receiver = base.point(lat, lon).ecef_km
        east_axis = np.array([-np.sin(np.deg2rad(lon)), np.cos(np.deg2rad(lon)), 0.])
        blocks = defaultdict(list)
        for block in self.predictions(*key):
            blocks[block.track_id].append(block)
        totals = defaultdict(float)
        weight_sum = 0
        details = []
        for tid, bank in self.banks.items():
            chunks = blocks[tid]
            track = bank.source
            predictions = np.concatenate([b.predictions_hz[:, 0, :] for b in chunks])
            ids = np.concatenate([b.candidate_ids for b in chunks])
            visible = np.concatenate([b.visible for b in chunks])
            shortlist = train_shortlist(predictions, track.measured_hz, track.training_mask, visible,
                scale_hz=self.parameters['scale_hz'], df=self.parameters['degrees_of_freedom'])
            indices = np.asarray(shortlist['candidate_indices'])
            chosen_ids = ids[indices]
            short = dict(shortlist, candidate_indices=list(range(len(indices))))
            positions = bank.position_km[[self.index[tid][int(cid)] for cid in chosen_ids], 0, :, :]
            delta = positions - receiver
            direction = delta / np.linalg.norm(delta, axis=-1, keepdims=True)
            result = joint_heldout_score(predictions[indices], np.sum(direction * east_axis, axis=-1),
                track.measured_hz, track.training_mask, short, self.reception[tid], ratio_variance=self.ratio_variance)
            weight = len(np.unique(np.floor(track.times_s)))
            values = result['scores']
            for name, value in values.items():
                totals[name] += weight * value
            weight_sum += weight
            details.append(dict(track_id=tid, weight_seconds=weight,
                candidate_ids=chosen_ids.astype(int).tolist(), weights=short['weights'],
                training_rms_hz=short['training_rms_hz'],
                map_test_rms_hz=result['map_heldout_rms_hz'], scores=values))
        row = dict(east_km=key[0], north_km=key[1], latitude_deg=lat, longitude_deg=lon,
                   scores={k: v/weight_sum for k, v in totals.items()}, weight_seconds=weight_sum, tracks=details)
        self.cache[key] = row
        if len(self.cache) % 20 == 0:
            print('POINTS', self.origin, len(self.cache), 'seconds', round(time.monotonic()-self.started, 1), flush=True)
        return row


def run_scan(index, budget):
    start = time.monotonic()
    inventory = json.loads((base.SOURCE/'evaluation_inventory.json').read_text())
    entry = [x for x in inventory if x['split'] == 'holdout'][index]
    sid = entry['session_id']
    target = HERE/f'robust-search-{sid}.json'
    if target.exists():
        raise FileExistsError('robust output already exists; review before rerunning')
    parameter_bytes = (HERE/'fixedpoint_parameters.json').read_bytes()
    calibration = json.loads(parameter_bytes)
    if not calibration.get('converged'):
        raise ValueError('robust calibration has not reached the declared consistency tolerance')
    for filename, key in (('robust_core.py', 'robust_core_sha256'), ('fit_frequency.py', 'fit_frequency_sha256')):
        if calibration[key] != base.digest((HERE/filename).read_bytes()):
            raise ValueError('calibration implementation changed after extraction')
    allowed = sorted(x['session_id'] for x in inventory if x['split'] == 'calibration')
    if calibration['calibration_sessions'] != allowed:
        raise ValueError('frequency calibration membership mismatch')
    extraction_name = calibration['extraction_file']
    if Path(extraction_name).name != extraction_name:
        raise ValueError('extraction must be a named artifact in this report directory')
    if calibration['extraction_sha256'] != base.digest((HERE/extraction_name).read_bytes()):
        raise ValueError('frequency extraction digest mismatch')
    parameters = calibration['parameters']
    if not parameters['optimizer_success']:
        raise ValueError('invalid frequency calibration')
    payload = Path(entry['cache_file']).read_bytes()
    if base.digest(payload) != entry['cache_sha256']:
        raise ValueError('tracking input cache digest mismatch')
    raw = pickle.loads(payload)
    d, c, variance, endpoints, reception_calibration = base.frozen_models_and_endpoints()
    if json.loads((HERE/'calibration.json').read_text()) != reception_calibration:
        raise ValueError('reception calibration changed')
    prepared = base.prepare_adaptive_tle_position_inputs(sid, inputs=base.CachedInput(raw),
        archive=base.TleArchiveReader(Path('/var/lib/leo/tle')))
    reception = base.reception_inputs(prepared, endpoints[sid], d, c)
    banks, receipt = base.build_prediction_banks(prepared.catalogue, prepared.candidate_indices,
        prepared.start_utc_ns, prepared.tracks, taus_s=np.array([0.]))
    print('BANK_READY', sid, 'seconds', round(time.monotonic()-start, 1), flush=True)
    out = dict(session_id=sid, finished=False, protocol=dict(priors=base.PRIORS, levels_km=base.LEVELS,
        budget_per_arm=budget, arms=base.ARMS, timing_s=0, top_k=3, parameters=parameters,
        track_weight='occupied one-second bins', identity='shared across track and joint evidence',
        search='measured-priority best-first; boundary representative inside cell and prior disk',
        cohort_status='development; original Gaussian outcomes inspected before robust iteration',
        truth_access='none; final distance reporting is separate',
        candidate_policy='full causal catalogue independently at every point; no fitted candidates shared between priors'),
        evidence_sha256=prepared.evidence_sha256, snapshot_digest=prepared.snapshot_digest,
        input_manifest_sha256=prepared.input_manifest_sha256, analysis_manifest_sha256=prepared.analysis_manifest_sha256,
        frequency_parameters_sha256=base.digest(parameter_bytes),
        calibration_sha256=base.digest((HERE/'calibration.json').read_bytes()),
        prediction_receipt=asdict(receipt), tracks=len(prepared.tracks), branches={})
    for name, (lat, lon, radius) in base.PRIORS.items():
        evaluator = RobustBranchEvaluator(banks, (lat, lon), reception, variance, parameters)
        branch = dict(origin=[lat, lon], radius_km=radius, arms={})
        for arm in base.ARMS:
            result = search(evaluator.for_arm(arm), radius_km=radius,
                levels_km=base.LEVELS, budget_points=budget)
            selected = result.global_incumbent
            chosen = evaluator.cache[(selected.east_km, selected.north_km)]
            branch['arms'][arm] = dict(selected=chosen, stop_reason=result.stop_reason, complete=result.complete,
                evaluated_points=len(result.all_evaluations), finest_points=len(result.finest_evaluations),
                selection='global best evaluated objective', trace=list(result.trace))
            print('ARM_DONE', sid, name, arm, chosen['latitude_deg'], chosen['longitude_deg'], chosen['scores'], flush=True)
        branch['common_inventory_best'] = {arm: min(evaluator.cache.values(),
            key=lambda r: (r['scores'][arm], r['east_km'], r['north_km']))
            for arm in ('D', 'D_plus_detection', 'D_plus_geometry', 'D_plus_reversed_geometry')}
        branch['point_components'] = [{k: v for k, v in r.items() if k != 'tracks'} for r in evaluator.cache.values()]
        out['branches'][name] = branch
        out['elapsed_s'] = time.monotonic()-start
        base.atomic(target, out)
    out['finished'] = True
    out['elapsed_s'] = time.monotonic()-start
    out['code_sha256'] = {name: base.digest((HERE/name).read_bytes())
        for name in ('run_robust_search.py', 'robust_core.py', 'run_search.py', 'measured_search.py')}
    base.atomic(target, out)
    print('SCAN_DONE', sid, round(out['elapsed_s'], 1), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scan-index', type=int, required=True)
    parser.add_argument('--budget', type=int, default=160)
    args = parser.parse_args()
    run_scan(args.scan_index, args.budget)
