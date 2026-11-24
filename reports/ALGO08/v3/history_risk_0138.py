"""One staged full-20 ms DS30-0138 transfer through ordinary saved publication."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RELEASE_ROOT = Path('/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c')
PAYLOAD_ROOT = Path('/opt/leo-algo08/algo08v3/payload')
sys.path[:0] = list(map(str, (HERE, ROOT, RELEASE_ROOT/'src', RELEASE_ROOT, PAYLOAD_ROOT)))

from causal_0138 import ADMITTED, ARCHIVE, AUTHORITY, CASE, CUTOFF, INVENTORY, ISSUED, NATIVE_PIN, OFFER, SESSION, SHM, checked


STAGE = SHM/'leo-v3-causal-0138-stage01'
REQUEST_PIN = '16826e2aa70e6baf377ef3d3efc847bdfdff1f569ed4b64289b6861a580b4797'
KEY = '0138'
ORDER = ('routed', 'named')
PROTOCOL = HERE/'history-risk-0138-protocol.md'
DRIVER = Path(__file__).resolve()
REFERENCE = ROOT/'reports/2026_11_21_ds30_full/reference-audit.json'
REFERENCE_PIN = 'c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5'


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def source_pins():
    from exact_named_route import SOURCES

    files = (*SOURCES, PROTOCOL, DRIVER, HERE/'history_risk_route_trial.py', HERE/'history_risk_route.py')
    return {p.name: digest(p) for p in files}


def bound_request():
    from exact_named_route import resident_path
    from exact_solver_0057 import ARTIFACT, ARTIFACT_SHA, PRODUCER_SHA

    path = STAGE/'request.json'
    req = json.loads(checked(path, REQUEST_PIN))
    artifact = resident_path(ARTIFACT)
    producer_path = artifact.parent/'artifact-bind.json'
    producer = json.loads(checked(producer_path, PRODUCER_SHA))
    inventory_path = STAGE/'inventory.json'
    pins = {inventory_path: INVENTORY, STAGE/'operator-offer.json': OFFER, STAGE/'named-detections.json': NATIVE_PIN,
            artifact: ARTIFACT_SHA[7:]}
    for location, pin in pins.items():
        checked(resident_path(location), pin)
    if (req['case'] != CASE or req['session'] != SESSION or req['inventory'] != 'sha256:'+INVENTORY
            or req['native_file'] != str(STAGE/'named-detections.json') or req['native_sha256'] != NATIVE_PIN
            or req['offer_file'] != str(STAGE/'operator-offer.json') or req['offer_sha256'] != OFFER
            or req['local_archive']['root'] != str(STAGE/'tle') or req['original_archive']['snapshots_sha256'] != ARCHIVE
            or req['raw_authority'] != AUTHORITY or req['causal_cutoff_utc_ns'] != CUTOFF
            or producer['source']['cutoff_utc_ns'] >= CUTOFF or producer['portable_sha256'] != ARTIFACT_SHA):
        raise ValueError('Saved request or independent earlier portable artifact changed')
    return dict(case=CASE, stage=str(STAGE), request=str(path), archive=str(STAGE/'tle'), inventory=str(inventory_path),
                packets={str(k): v for k,v in pins.items()}, issued=ISSUED, admitted=ADMITTED, sources=source_pins(),
                portable=[str(artifact), ARTIFACT_SHA, PRODUCER_SHA]), req


def worker(root, arm):
    from prospective_0316_solver import worker as saved

    bound = json.loads((root/'binding.json').read_bytes())['input']
    if bound['sources'][DRIVER.name] != digest(DRIVER) or digest(Path(bound['request'])) != REQUEST_PIN:
        raise ValueError('Frozen worker source or staged request changed')
    if arm == 'routed':
        import history_risk_route_trial as trial

        req = trial.exact.read(Path(bound['request']))
        with patch.object(trial, 'request_binding', return_value=(bound, req)):
            trial.worker(KEY, root)
    else:
        saved(Path(bound['request']), 'stock', root/'candidate', source_pins={}, native_sha=NATIVE_PIN,
              windows=ISSUED, admitted=ADMITTED, inventory_file=Path(bound['inventory']), audit_name='worker.json')


def commands(root, release):
    return {arm: [str(v) for v in ('/usr/bin/timeout', '--kill-after=2s', '110s', release/'venv/bin/python',
                                  '-IB', DRIVER, 'worker', root/arm, arm)] for arm in ORDER}


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure
    import history_risk_route_trial as trial

    if trial.exact.resident_path(root.parent) != SHM or root.exists():
        raise ValueError('Use a fresh private tmpfs pair root')
    t0, cpu0 = perf_counter_ns(), process_time_ns()
    machine = host()
    bound, req = bound_request()
    _archive, refs = trial.exact.checked_catalogue(bound, req, TleArchiveReader, canonical_digest)
    resident = json.loads(subprocess.check_output(
        ['fincore', '--json', '--bytes', '-o', 'RES,SIZE', *(ref.path for ref in refs)], text=True))['fincore']
    if len(resident) != len(refs) or any(row['res'] < row['size'] for row in resident):
        raise ValueError('Expected both saved workers to have the exact projected catalogue resident')
    root.mkdir(mode=0o700)
    for folder in ('fonts', 'tmp', *ORDER):
        (root/folder).mkdir()
    fonts = SHM/'leo-v3-saved-0155-pair-01/fonts'
    font_sources = {}
    for path in sorted(fonts.glob('fontlist-*.json')):
        os.link(trial.exact.resident_path(path), root/'fonts'/path.name)
        font_sources[path.name] = digest(path)
    if not font_sources:
        raise ValueError('The common sealed saved-publication font cache is absent')
    run = commands(root, RELEASE)
    preflight = dict(elapsed_ns=perf_counter_ns()-t0, cpu_ns=process_time_ns()-cpu0)
    write(root/'pair-binding.json', dict(input=bound, order=ORDER, commands=run, preflight=preflight, machine=machine,
          common_font_cache=font_sources, resident_archive_bytes=sum(row['size'] for row in resident),
          resident_snapshots=len(refs), projection_sha256=digest(STAGE/'projection.json'),
          protocol_sha256=digest(PROTOCOL), ordinary_renderer=True, waveform_reads=0, original_archive_reads=0))
    for arm in ORDER:
        write(root/arm/'binding.json', dict(input=bound, command=run[arm]))
    write(root/'routed/route-binding.json', dict(cutoff_utc_ns=CUTOFF, sources=trial.sources(KEY), preflight=preflight))
    env = environment(root) | {'TMPDIR': str(root/'tmp'), 'XDG_CACHE_HOME': str(root/'tmp')}
    for arm in ORDER:
        clock = measure(run[arm], env, root/arm/'candidate')
        write(root/arm/'clock.json', clock)
        if clock['exit_code']:
            raise ValueError(f'{arm} stopped; its external exit clock is sealed')


def check_output(row):
    receipt = row['worker']['receipt']
    if (receipt['window_count'] != ISSUED or receipt['counts']['processed'] != ADMITTED
            or receipt['counts']['invalid_capture'] != ISSUED-ADMITTED):
        raise ValueError('The full original opportunities changed')
    if receipt['decision'] == 'complete':
        if (row['sample'] is None or not row['sample']['complete'] or len(row['products']['images']) != 8
                or any(not arm['latlon'] or arm.get('rf_rms_hz') is None for arm in row['terminal']['arms'].values())):
            raise ValueError('A complete fit must publish both calibrations, full grid, path and eight figures')
    elif (receipt['decision'] != 'withheld' or not row['terminal']['reason'] or row['products']['images']
          or row['sample'] is not None or row['path'] is not None
          or any(arm['latlon'] is not None or arm.get('rf_rms_hz') is not None for arm in row['terminal']['arms'].values())):
        raise ValueError('Withheld runs require the original reason, null results and no position products')


def score(root):
    from aperture_trial import write
    from duration_heldout import PAIR_PIN, PANEL
    from exact_named_route_score import parity
    from held_adaptive_0160_score import verified
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.scoring import distance_km
    import history_risk_route_trial as trial

    binding = trial.exact.read(root/'pair-binding.json')
    req = json.loads(checked(Path(binding['input']['request']), REQUEST_PIN))
    results, hashes = {}, {}
    for arm in ORDER:
        folder = root/arm
        clock = trial.exact.read(folder/'clock.json')
        actual = verified(folder/'candidate', clock, 'worker.json', req)
        check_output(actual)
        results[arm] = actual
        hashes[arm] = {name: digest(folder/name) for name in ('binding.json', 'clock.json', 'candidate/worker.json',
                                                               'candidate/joint-research-receipt.json')}
    named, routed = (results[arm] for arm in ('named', 'routed'))
    if any(named['worker']['receipt'][key] != routed['worker']['receipt'][key] for key in ('counts','region','session_id')):
        raise ValueError('Paired inputs or original offered region differ')
    audit = json.loads(checked(REFERENCE, REFERENCE_PIN))
    ref, = [row for row in audit['cases'] if row['dataset_label'] == CASE]
    if not ref['authority_eligible'] or not ref['sealed_metadata_digests_verified']:
        raise ValueError('Original operator reference is ineligible')
    location = [ref['reference'][k] for k in ('latitude_deg', 'longitude_deg')]
    measures = {}
    for arm, row in results.items():
        arms = row['terminal']['arms']
        measures[arm] = dict(horizontal_error_km={key: distance_km(location, val['latlon']) for key,val in arms.items()},
                             rf_rms_hz={key: val.get('rf_rms_hz') for key,val in arms.items()})
    prior = json.loads(checked(PANEL/'pair.json', PAIR_PIN))['runs']['candidate']
    prior_terminal = prior['receipt']['terminal_sha256']
    routes, = trial.exact.read(root/'routed/risk-route.json')['solves']
    ports = trial.exact.read(root/'routed/candidate/ports.json')
    if (not routes['inference_calls'] or ports['history']['solves'] != 1 or not ports['history']['prepare']
            or not named['trace']['stock_control']):
        raise ValueError('Expected installed stock boundary and one routed numerical publication')
    owner_changes = {key: owner_delta(named['rows'].get(key, []), routed['rows'].get(key, []))
                     for key in ('c0', 'fitted_c')}
    same = parity(named, routed)
    if routes['choice']['route'] == 'named' and (not all(same.values()) or routes['lean_attempts']):
        raise ValueError('Flagged route diverged from the paired installed results')
    write(root/'result.json', dict(case=CASE, binding=binding, clock=routed['clock'], archive_stock_clock=named['clock'],
          named_parity=same, prior_named_terminal_equal=named['worker']['receipt']['terminal_sha256'] == prior_terminal,
          scientific=dict(runs=measures, authority_revision=ref['authority_revision'], reference_audit_sha256=REFERENCE_PIN),
          coverage={arm: dict(decision=row['worker']['receipt']['decision'], reason=row['terminal']['reason'],
                              owner_count={k: len(v) for k,v in row['rows'].items()},
                              grid_points=None if row['sample'] is None else row['sample']['evaluated_points'],
                              figures=row['products']['images'], path=row['path'] is not None, solve=row['worker']['solve'])
                    for arm,row in results.items()}, owners=owner_changes, route=routes['choice'],
          signed_final_arms={k: v['status'] for k,v in routes.get('lean_final_fit', {}).get('arms', {}).items() if 'status' in v},
          prep_timing=ports['history'], route_inferences=routes['inference_calls'], sides_sha256=hashes,
          binds={k: digest(root/k) for k in ('pair-binding.json', 'routed/route-binding.json', 'routed/risk-route.json', 'routed/candidate/ports.json')},
          no_waveform=True, saved_only=True))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('launch', 'worker', 'score'))
    p.add_argument('root', type=Path)
    p.add_argument('arm', choices=ORDER, nargs='?')
    options = p.parse_args()
    if options.action == 'worker':
        worker(options.root, options.arm)
    else:
        {'launch': launch, 'score': score}[options.action](options.root)
