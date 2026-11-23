"""Audit the complete South saved publications after both child clocks seal."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ARMS = ('c0','fitted_c')


def face_distances(offer, point):
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km, offset_km

    if point is None:
        return None
    east, north = offset_km(offer, point)
    inward = offer['width_km']/2 - east
    nearest = face_clearance_km(offer, point)
    return dict(east_km=east, north_km=north, east_face_inward_m=1000*inward,
                nearest_face_inward_m=1000*nearest, east_face_is_nearest=abs(inward-nearest) < 1e-10)


def depth_intervals(containing, omitted):
    """One depth T keeps points with clearance >= T, in the same signed frame."""
    if any(value is None for pair in (containing, omitted) for value in pair):
        return None

    def interval(lower, upper):
        return dict(lower_exclusive_m=lower, upper_inclusive_m=upper, possible=lower < upper)

    return dict(single_threshold_for_each_arm=interval(max(omitted),min(containing)),
                reject_if_either_below=interval(min(omitted),min(containing)),
                reject_if_both_below=interval(max(omitted),max(containing)),
                individual={arm:interval(lo,hi) for arm,lo,hi in zip(ARMS,omitted,containing,strict=True)})


def arm_positions(arms, offer, truth):
    from tools.pipeline_eval.scoring import distance_km

    if set(arms) != set(ARMS):
        raise ValueError('Both calibration arms are required')
    return {arm: dict(data, error_km=distance_km(truth, data['latlon']), face=face_distances(offer, data['latlon']))
            for arm, data in arms.items()}


def assess(root, mode, archived, request, truth):
    from aperture_trial import read
    from empty_bootstrap import checked
    from isolated_salvage_south import DETECTOR, decision_label
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.qualification.paired_publication import evidence

    clock = read(root/f'{mode}-clock.json')['timing']
    if clock['exit_code']:
        raise ValueError(f"The {mode} child exited {clock['exit_code']}. Its original clock is sealed.")
    target = root/mode
    worker, research = (read(target/name) for name in ('cumulative-grid-worker.json','joint-research-receipt.json'))
    receipt = worker['receipt']
    run = receipt['run_id']
    scan, store = FastScanStore(target), FastStandardAnalysisStore(target)
    workspace = scan.automatic_workspace(run, create=False)
    terminal, standard = read(workspace/'terminal.json'), store.detail(run)
    packet, = workspace.parent.glob('*/detections.json')
    checked(packet, request['native'][7:])
    checked(target/'fast-scan-inputs'/(request['session']+'.json'), request['inventory'][7:])
    offer = read(Path(request['region']))
    if (not worker['staged_inventory'] or worker['handoffs'] != 1 or worker['waveform_calls'] or worker['projection']
            or not worker['graph']['enabled'] or not worker['named_survivor_finish']['requested']
            or worker['detector'] != DETECTOR or worker['graph_proof']['proven']
            or research['input'] != 'authenticated saved named v3 20 ms acquisition' or receipt != research['receipt']
            or receipt['window_count'] != 1200 or receipt['counts'] != dict(processed=1200,invalid_capture=0,skipped_fast_score=0)
            or terminal['native_sha256'] != request['native'] or standard['input_sha256'] != request['native']
            or standard['raw_authority'] != request['authority'] or receipt['session_id'] != request['session']
            or receipt['region'] != offer or offer != archived['named_archived']['offer']):
        raise ValueError('Changed detector, authority, offer, aperture or requested signed execution')
    science = evidence(target, receipt, clock['started_unix_ns'], read_only=True)
    proof = artifacts(target, receipt)
    if json.loads(json.dumps(proof)) != research['evidence']:
        raise ValueError('The publication figures differ from independently decoded evidence')
    rows = research['selected_rows']
    docs = {}
    if receipt['decision'] == 'complete':
        path, grid = store.position_path(run), store.position_grid(run)
        if (len(proof['images']) != 8 or not path['stages'] or not grid['complete'] or grid['planned_points'] != 137
                or grid['evaluated_points'] != 137 or len(grid['points']) != 137
                or set(rows) != set(ARMS) or any(not rows[arm] for arm in ARMS)):
            raise ValueError('The completed South fix has incomplete evidence')
        for name, doc in (('grid',grid),('path',path)):
            position_sha = doc['binding']['position_png_sha256']
            if position_sha != proof['images']['position']['sha256']:
                raise ValueError('The position sidecar must bind the published PNG')
            docs[name] = dict(sha256=canonical_digest(doc), position_sha256=position_sha)
        for arm in ARMS:
            if canonical_digest({oid:sat for oid,sat,_ in rows[arm]}) != science['owners'][arm]:
                raise ValueError('The counted ordered rows differ from the terminal owner digest')
    elif rows or proof['images'] or not science['reason'] or any(science['arms'][a]['latlon'] is not None for a in ARMS):
        raise ValueError('A withheld fix requires its reason and no coordinates or images')
    warm = {arm:dict(latlon=archived['candidate'][arm]['position'],rf_rms_hz=archived['candidate'][arm]['rf_rms_hz'])
            for arm in ARMS}
    named = {arm:dict(latlon=archived['named'][arm]['position'],rf_rms_hz=archived['named'][arm]['rf_rms_hz'])
             for arm in ARMS}
    truth_face = face_distances(offer, truth)
    signs = {'containing':1,'near-omitted':-1}
    if not truth_face['east_face_is_nearest'] or abs(truth_face['east_face_inward_m'] - 100*signs[mode]) > 1.0:
        raise ValueError('Expected the original signed east-face mirror')
    route = research.get('route_details') or {}
    signed = route.get('signed',{})
    return dict(raw_status=receipt['decision'], status=decision_label(receipt['decision'],truth_face['east_face_inward_m']),
                named_status=archived['controls_status'], warm_status=archived['status'], truth_face=truth_face, offer=offer,
                arms={name:arm_positions(values,offer,truth) for name,values in (('candidate',science['arms']),('warm',warm),('named',named))},
                owners=science['owners'], named_owner_digests=archived['named_archived']['owners'],
                warm_owner_deltas={arm:owner_delta(archived['selected_rows'][arm], rows.get(arm,[])) for arm in ARMS},
                ordered_owner_sha256={arm:canonical_digest(rows.get(arm,[])) for arm in ARMS},
                selected_roles=research['selected_roles'], external_clock=clock, worker=worker, media=proof,
                publication_cpu_s=research['publication_cpu_s'], publication_elapsed_s=research['publication_elapsed_s'],
                warm_external_clock=archived['process'], warm_worker=archived['worker'], historical_named=archived['named_archived'],
                terminal_sha256=receipt['terminal_sha256'], science=science['scientific_digests'], sidecars=docs,
                image_comparison={name:dict(file_equal=figure['sha256']==archived['evidence']['images'][name]['sha256'],
                                            pixels_equal=figure['rgba_sha256']==archived['evidence']['images'][name]['rgba_sha256'])
                                  for name,figure in proof['images'].items()},
                route=research['route'], signed={k:signed[k] for k in ('status','selection','reason') if k in signed},
                paired_finish=route.get('named_survivor_fit'), signed_clock=route.get('signed_refit_clocks'),
                isolated=route.get('provisional_salvage'), endpoint=route.get('endpoint_trim'),
                early=research.get('early_regional'), exterior=route.get('exterior'), fallback=research.get('recovered_inference'))


def score(root):
    from aperture_trial import read, write
    from empty_bootstrap import checked
    from isolated_salvage_south import TRUTH_SHA
    from named_south_transfer import REQUESTS, WARM_SHA
    from tools.pipeline_eval.scoring import distance_km

    seal = read(root/'seal.json')
    for name,pin in seal['source_sha256'].items():
        checked(HERE/name,pin)
    for mode in REQUESTS:
        clock = read(root/f'{mode}-clock.json')
        if '--named-survivor-finish' not in clock['command'] or clock['timing']['exit_code']:
            raise ValueError('Both actual named-survivor children must exit before scoring')
    warm_path = HERE/'measurements/isolated-salvage-south.json.gz'
    warm_bytes = gzip.decompress(warm_path.read_bytes())
    if sha256(warm_bytes).hexdigest() != WARM_SHA:
        raise ValueError('The preceding warm and original named controls changed')
    warm = json.loads(warm_bytes)
    truth_key = json.loads(checked(HERE.parent/'regional-release/scoring-key.json',TRUTH_SHA))
    recording = Path(seal['inputs']['containing']['recording']).name
    truth, = {tuple(row['truth']) for row in truth_key['answers'].values() if row['recording'] == recording}
    results = {mode:assess(root,mode,warm['comparisons'][mode],seal['inputs'][mode],truth) for mode in REQUESTS}
    depths = [[results[mode]['arms']['candidate'][arm]['face']['east_face_inward_m']
               if results[mode]['arms']['candidate'][arm]['face'] else None for arm in ARMS] for mode in REQUESTS]
    write(root/'result.json', dict(verified=True, truth=truth, cases=results, seal=seal,
        thresholds=depth_intervals(*depths), candidate_move_between_offers_km={arm:distance_km(
            *(results[mode]['arms']['candidate'][arm]['latlon'] for mode in REQUESTS)) for arm in ARMS},
        truth_sha256=TRUTH_SHA, warm_sha256=WARM_SHA, scorer_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == '__main__':
    sys.path.insert(0,str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    score(parser.parse_args().root)
