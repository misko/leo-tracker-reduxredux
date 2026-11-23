"""One saved dense mixed-detector run with the portable original final fit."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
STAGED = Path('/dev/shm/leo-held-anchor-selected-dense-01')
PREVIOUS = Path('/dev/shm/leo-cumulative-grid-projection-01')
REQUEST_PIN = '8abec0e2f60def947cd03883662611c3fcfdbd5f255eb0ba60e8306085abf502'
PRIOR_PIN = '1ac1eacb47a49aa4fccdcd50e65df4f5a66f3a78c599010b8fabb4cb63181993'
PRIOR_ROWS_PIN = 'f378b41ceaf7a874aeb2b7cb02636647fa01b32c0ddc70efb65fd566a724182f'
ORIGINAL_V3_PIN = '51521b26848532823922cc43a198b7f91d59d3f1d81e155e5862b04b53193f38'
HELD_PIN = '8122a666c1ff164b58d674e284c22fc06708906644bb8eb024116ab770d18705'
PROTOCOL = HERE / 'mixed-named-finish-0008-protocol.md'
ARMS = ('c0', 'fitted_c')


def assigned():
    from aperture_trial import archive_identity
    from combined_frontier_run import BLOCK_SHA
    from empty_bootstrap import checked
    from full_short_raw import RECIPE_SHA
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from grid_feature_projection import LIBRARY_SHA
    from named_constrained_research import inventory_binding
    from unified_short_bootstrap import LAYOUT_SHA256

    def checked_path(path, pin):
        checked(path, pin)
        return path

    source = json.loads(checked(STAGED / 'request.json', REQUEST_PIN))
    selected = json.loads(checked(STAGED / 'route-decision.json', source['selection_sha256']))
    native = source['original']['native_sha256']
    packet = checked_path(Path(source['original']['file']), native[7:])
    if (selected['choice']['route'] != 'unfiltered' or source['selected']['native_sha256'] != native
            or source['original']['detector'] != RECIPE_SHA):
        raise ValueError('Expected the original unfiltered mixed receiver packet')
    inventory_path = STAGED / 'selected/fast-scan-inputs' / (source['session'] + '.json')
    inventory = inventory_binding(Path(source['recording']), checked_path(inventory_path, source['inventory'][7:]),
                                  source['session'], source['inventory'])
    if inventory(None, Path(source['recording']), verify_windows=False)[2]['window_count'] != 6772:
        raise ValueError('Unexpected signed visit count')
    archive = source['archive']
    observed = archive_identity(Path(archive['root']))
    if observed != {key: archive[key] for key in observed}:
        raise ValueError('The original causal archive changed')
    region = checked_path(Path(source['offer']), source['offer_sha256'])
    pins = dict(frontier_block_library=BLOCK_SHA, geographic_library=GEOGRAPHIC_SHA,
                regional_track_library=TRACK_SCORES_SHA)
    libraries = {key: str(checked_path(Path(source['libraries'][key]), pin)) for key, pin in pins.items()}
    projection = checked_path(PREVIOUS / 'projection.so', LIBRARY_SHA)
    checked(HERE / 'one_pass_web_png.py', LAYOUT_SHA256)
    return dict(recording=source['recording'], region=str(region), offer_sha256=source['offer_sha256'],
                authority=source['authority'], session=source['session'], inventory=source['inventory'],
                archive=archive, issued=6772, native=native, packet=str(packet), cutoff_utc_ns=source['cutoff_utc_ns'],
                libraries=libraries, projection=str(projection), saved_inventory=str(inventory_path),
                pins=dict(libraries=pins, projection=LIBRARY_SHA, layout=LAYOUT_SHA256, staging=REQUEST_PIN,
                          route=source['selection_sha256'], protocol=sha256(PROTOCOL.read_bytes()).hexdigest(),
                          sources={name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
                              'mixed_named_finish_0008.py', 'cumulative_grid_projection.py', 'named_survivor_fit.py',
                              'unified_short_bootstrap.py', 'isolated_salvage.py', 'endpoint_track_repair.py',
                          )}))


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(['findmnt', '-no', 'FSTYPE', '-T', root.parent], text=True).strip() != 'tmpfs':
        raise ValueError('Use a fresh private tmpfs root')
    request = assigned()
    root.mkdir()
    (root / 'tmp').mkdir()
    job = root / 'binding.json'
    write(job, dict(request, machine=machine))
    env = environment(root)
    env['TMPDIR'] = str(root / 'tmp')
    python = RELEASE / 'venv/bin/python'
    subprocess.run([python, '-Bc', "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    target = root / 'candidate'
    command = ['/usr/bin/timeout', '--kill-after=2s', '90s', python, '-IB', HERE / 'cumulative_grid_projection.py',
               'worker', job, 'combined', target, '--named-survivor-finish']
    clock = measure(command, env, target)
    write(root / 'clock.json', dict(timing=clock, command=list(map(str, command))))
    if clock['exit_code']:
        raise RuntimeError(f"Saved publication exited {clock['exit_code']}: {clock['stderr_tail']}")


def sidecars(store, run, images):
    from leo.contracts.digests import canonical_digest

    grid, path = store.position_grid(run), store.position_path(run)
    stages = path['stages']
    if (len(images) != 8 or not grid['complete'] or grid['evaluated_points'] != 179
            or len(grid['points']) != 179 or not stages or any(
                set(stage['arms']) != set(ARMS) or any(not row['endpoint'] for row in stage['arms'].values())
                for stage in stages)):
        raise ValueError('A completed fix must have its full grid, path and eight figures')
    bindings = {name: document['binding']['position_png_sha256']
                for name, document in (('grid', grid), ('path', path))}
    if any(digest != images['position']['sha256'] for digest in bindings.values()):
        raise ValueError('Position evidence must bind its own published PNG')
    return grid, dict(position_png=bindings, grid_points=179, path_stages=len(stages),
                      grid_sha256=canonical_digest(grid), path_sha256=canonical_digest(path))


def score(root):
    from aperture_trial import read, write
    from causal_pre_refit_0155 import compare_grid
    from cumulative_grid_projection import proof_fields
    from empty_bootstrap import checked
    from full_short_raw import RECIPE_SHA
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    request, launch_record = read(root / 'binding.json'), read(root / 'clock.json')
    clock = launch_record['timing']
    if clock['exit_code'] or '--named-survivor-finish' not in launch_record['command']:
        raise ValueError('No successful timed portable named finish')
    output = root / 'candidate'
    worker, research = (read(output / name) for name in ('cumulative-grid-worker.json', 'joint-research-receipt.json'))
    receipt = worker['receipt']
    run = receipt['run_id']
    store = FastStandardAnalysisStore(output)
    detail = store.detail(run)
    workspace = FastScanStore(output).automatic_workspace(run, create=False)
    terminal = read(workspace / 'terminal.json')
    native_path, = workspace.parent.glob('*/detections.json')
    native = json.loads(checked(native_path, request['native'][7:]))
    source = native['source']
    analysis = canonical_digest(['cancellation', request['authority'], RECIPE_SHA, source['probes']])
    checked(output / 'fast-scan-inputs' / (request['session'] + '.json'), request['inventory'][7:])
    science = evidence(output, receipt, clock['started_unix_ns'], read_only=True)
    if (not worker['staged_inventory'] or worker['handoffs'] != 1 or worker['waveform_calls'] != 0
            or not worker['graph']['enabled'] or not worker['named_survivor_finish']['requested']
            or receipt != research['receipt'] or receipt['session_id'] != request['session']
            or receipt['window_count'] != request['issued'] or receipt['region'] != read(Path(request['region']))
            or receipt['counts'] != dict(processed=6765, invalid_capture=7, skipped_fast_score=0)
            or terminal['native_sha256'] != request['native'] or detail['input_sha256'] != request['native']
            or source['session_id'] != request['session'] or source['input_manifest_sha256'] != request['inventory']
            or source['analysis_manifest_sha256'] != analysis or len(source['probes']) != 13530
            or native['provenance']['detector_sha256'] != 'sha256:'+RECIPE_SHA
            or source['raw_recording_authority_digest'] != request['authority']
            or science['raw_authority'] != request['authority']
            or native['clock_anchor']['before']['realtime_ns'] != request['cutoff_utc_ns']):
        raise ValueError('The publication changed the signed detector, inventory, offer, cutoff or requested settings')
    figures = artifacts(output, receipt)['images']
    rows = research['selected_rows']
    (regional,) = research['early_regional']
    prior_root = PREVIOUS / 'dense-pair'
    prior_document = json.loads(checked(prior_root / 'result.json', PRIOR_PIN))
    prior = prior_document['runs']['combined']
    prior_research = json.loads(checked(prior_root / 'combined/joint-research-receipt.json', PRIOR_ROWS_PIN))
    held = json.loads(checked(STAGED / 'result.json', HELD_PIN))
    named_archive = json.loads(gzip.decompress(checked(HERE / 'measurements/dense-full-short-raw.json.gz', ORIGINAL_V3_PIN)))
    named = named_archive['baseline']
    if (prior_document['inputs']['native'] != request['native'] or held['inputs']['selected']['native_sha256'] != request['native']
            or prior_document['inputs']['offer_sha256'] != request['offer_sha256']
            or prior_document['inputs']['archive']['snapshots_sha256'] != request['archive']['snapshots_sha256']
            or prior['science']['raw_authority'] != request['authority'] or named['authority'] != request['authority']
            or named['receipt']['region'] != receipt['region'] or named['receipt']['counts'] != receipt['counts']):
        raise ValueError('The archived comparators do not bind the original recording, offer and paid support')
    reference, = (row for row in json.loads(checked(REFERENCE, REFERENCE_SHA256))['cases']
                  if row['dataset_label'] == 'DS30-0008' and row['authority_eligible']
                  and row['sealed_metadata_digests_verified'])
    truth = [reference['reference'][key] for key in ('latitude_deg','longitude_deg')]

    def arms(values):
        if set(values) != set(ARMS):
            raise ValueError('The scientific evidence must retain both calibration arms')
        return {arm: dict(values[arm], position_error_km=distance_km(truth, values[arm]['latlon'])) for arm in ARMS}

    fit = arms(science['arms'])
    ordinary, named_arms = arms(prior['science']['arms']), arms(named['arms'])
    comparisons = {name: {arm: {field: (fit[arm][field]-other[arm][field] if fit[arm]['latlon'] else None)
                                     for field in ('position_error_km','rf_rms_hz')} for arm in ARMS}
                   for name, other in (('previous_mixed', ordinary), ('earlier_named_raw', named_arms))}
    images = {name: dict(file_equal=figures[name]['sha256'] == baseline['sha256'],
                         pixels_equal=figures[name]['rgba_sha256'] == baseline['rgba_sha256'])
              for name, baseline in prior['images'].items() if name in figures}
    media = {}
    if receipt['decision'] == 'complete':
        grid, media = sidecars(store, run, figures)
        calls = worker['projection']['calls']
        graph = worker['graph']['graph']
        if (calls.get('grids') != 1 or calls.get('native_projection', 0) <= 0 or calls.get('native_selection') != 356
                or any(value for key, value in calls.items() if 'fallback' in key)
                or any(graph[key] != prior['worker']['graph']['graph'][key]
                       for key in ('calls','edge_lanes','edges','assigned','tracks'))
                or worker['layout']['work'] != prior['worker']['layout']['work']):
            raise ValueError('The trial changed the measured Graph, grid or figure layout settings')
        prior_store = FastStandardAnalysisStore(prior_root / 'combined')
        old_grid, media['previous_mixed'] = sidecars(prior_store, prior['worker']['receipt']['run_id'], prior['images'])
        media['grid_comparison'] = compare_grid(old_grid, grid)
        if set(rows) != set(ARMS) or any(not row for row in rows.values()):
            raise ValueError('A completed publication requires both owned rosters')
    else:
        if rows or figures or not science['reason'] or any(fit[arm]['latlon'] for arm in ARMS):
            raise ValueError('Invalid withheld saved publication')
    deltas = {arm: owner_delta(prior_research['selected_rows'][arm], rows.get(arm, [])) for arm in ARMS}
    details = research['route_details'] or {}
    stages = {name: value for name, value in details.items()
              if name.endswith('_clocks') or name in ('decision','named_survivor_fit','provisional_salvage','endpoint_trim')}
    stages['signed_status'] = details.get('signed', {}).get('status')
    signed = details.get('warm_signed_fit', {})
    stages['later_guard'] = {key: signed[key] for key in ('accepted','reasons') if key in signed}
    result = dict(case='DS30-0008', verified=True, inputs=request, launch=launch_record, worker=worker,
                  stages=stages, solution=fit, decision=receipt['decision'], reason=science['reason'],
                  terminal_sha256=receipt['terminal_sha256'], figures=figures, media=media,
                  scientific_digests=science['scientific_digests'], regional=proof_fields(regional),
                  same_regional_proof=proof_fields(regional) == prior['regional'], image_comparison=images,
                  deltas=comparisons, same_owner_order=all(delta['identical_ordered_rows'] for delta in deltas.values()),
                  ownership={arm: dict(science_sha256=science['owners'].get(arm),
                                       ordered_sha256=canonical_digest(rows.get(arm, [])), **deltas[arm]) for arm in ARMS},
                  previous_mixed=dict(arms=ordinary, clock=prior['clock'], solve=prior['worker']['solve'],
                                      graph=prior['worker']['graph'], decision=prior['science']['receipt']['decision'],
                                      held_clock=held['runs']['selected']['process'], owners=prior['science']['owners']),
                  earlier_named_raw=dict(arms=named_arms, clocks=named['clocks'], owners=named['owners'],
                                         decision=named['receipt']['decision']),
                  comparator_sha256=dict(previous_mixed=PRIOR_PIN, previous_mixed_rows=PRIOR_ROWS_PIN,
                                         held=HELD_PIN, named_raw=ORIGINAL_V3_PIN, reference=REFERENCE_SHA256),
                  scorer_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    write(root / 'result.json', result)
    return result


if __name__ == '__main__':
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['launch','score'])
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    {'launch':launch, 'score':score}[args.command](args.root)
