"""Full-parent versus old union-cavity diagnostics, no position/evidence fit."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback

START = time.monotonic()
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PRIOR = Path('/srv/bulk/leo/research/ds24-ambiguity-policy-r01/qualification')
sys.path.insert(0, str(PRIOR))
import qualify as previous
import inventory

r, w, k, sr = previous.r, previous.w, previous.k, previous.sr
adequacy = previous.adequacy
CASE, NORAD, CAP = inventory.CASE, inventory.NORAD, 300.
ARMS = ('c0', 'fitted_c')
CONTEXTS = ('full_parent', 'old_union_cavity')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name, value):
    r.write_new(HERE / name, value)


def save_arrays(name, **arrays):
    path = HERE / name
    with path.open('xb') as stream:
        np.savez_compressed(stream, **arrays)


def threads():
    if any(os.environ.get(key) != '1' for key in
           ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        raise ValueError('Single-threaded BLAS required')


def compare_backgrounds(full, cavity):
    if not np.array_equal(full['q'], cavity['q']):
        raise ValueError('RF normalization changed')
    difference = cavity['raw'] - full['raw']  # full radio mean minus cavity radio mean
    change = full['covariance'] - cavity['covariance']
    return dict(full_minus_cavity_radio_mean_Hz=difference,
        radio_mean_change_RMS_Hz=float(np.sqrt(np.mean(difference ** 2))),
        radio_mean_change_average_Hz=float(np.mean(difference)),
        radio_mean_change_range_Hz=[float(np.min(difference)), float(np.max(difference))],
        covariance_relative_Frobenius_change=float(np.linalg.norm(change) / np.linalg.norm(cavity['covariance'])),
        full_predictive_SD_Hz=np.sqrt(np.diag(full['covariance'])),
        cavity_predictive_SD_Hz=np.sqrt(np.diag(cavity['covariance'])))


def input_context():
    d = r.context(CASE)
    x = np.asarray(d['arms']['c0']['endpoint_east_north_km'])
    d = w.at_common_position(d, x)
    family = int(np.flatnonzero(d['scan'].norads == NORAD)[0])
    if family in d['original_protected']:
        raise ValueError('68904 has active incumbent family state; fresh target prior would duplicate it')
    if any(e['candidate_index'] == family for e in d['entries']):
        raise ValueError('68904 already in parent prediction')
    target = next(q for q in read(PRIOR / 'metadata.json')['targets'] if q['case'] == CASE)
    entry = previous.entry_for(d, target)
    if entry['component'] != inventory.D or entry['points'] != 29:
        raise ValueError('Frozen complete29-ID D changed')
    return d, x, family, target, entry


def prepare():
    threads()
    sr.alarm(120.)
    inv = read(HERE / 'inventory.json')
    if inv['potential_separate_owner_count'] != 0:
        raise ValueError('No-witness protocol requires zero eligible archived separate owners; do not silently discard a witness')
    d, x, family, target, entry = input_context()
    pool = read(PRIOR / CASE / 'c0_screen.json')['candidate_indices']
    records = []
    for arm in ARMS:
        for context in CONTEXTS:
            cd, info = k.cavity(d, [] if context == 'full_parent' else pool, arm)
            if not w.hard_parent(info):
                raise ValueError('Hard original parent prerequisite failed')
            if context == 'full_parent' and (info['removed_curved_ids'] or info['removed_predictive_ids']):
                raise ValueError('Full parent lost incumbent observations')
            if context == 'old_union_cavity' and (len(info['removed_curved_ids']) != 480 or info['removed_predictive_ids']):
                raise ValueError('Original480-point cavity changed')
            cd['_arm'] = arm
            comp = previous.component(cd, x, entry)
            old_path = PRIOR / CASE / (arm + ('_original.npz' if context == 'full_parent' else '_conditional.npz'))
            old = np.load(old_path)
            replay = {key: float(np.max(abs(old[key] - comp[key]))) for key in ('raw', 'covariance', 'q')}
            if max(replay.values()) > 1e-8:
                raise ValueError('Previous full-parent/cavity input replay failed')
            red = copy.copy(cd)
            scan = copy.copy(cd['scan'])
            scan.tracks = list(scan.tracks)
            track = dict(scan.tracks[entry['track_index']])
            track['values'] = np.asarray(track['values']) + 1000.
            scan.tracks[entry['track_index']] = track
            red['scan'] = scan
            test = previous.component(red, x, entry)
            redaction = {key: float(np.max(abs(test[key] - comp[key]))) for key in
                         ('covariance', 'parent_coefficients', 'parent_noise')}
            redaction['raw_shift'] = float(np.max(abs(test['raw'] - comp['raw'] - 1000.)))
            if max(redaction.values()) > 1e-8:
                raise ValueError('D response changed parent calibration/noise')
            prefix = arm + '_' + context
            save_arrays(prefix + '.npz', raw=comp['raw'], covariance=comp['covariance'],
                q=comp['q'], x=x, parent_coefficients=comp['parent_coefficients'], parent_noise=comp['parent_noise'],
                values=d['scan'].tracks[entry['track_index']]['values'], times=d['scan'].tracks[entry['track_index']]['times'],
                native_ids=np.asarray(entry['observation_ids']))
            write(prefix + '_parent.json', info)
            records.append(dict(arm=arm, context=context, replay_error=replay, target_redaction_error=redaction,
                removed_curved_points=len(info['removed_curved_ids']), removed_predictive_points=len(info['removed_predictive_ids']),
                original_remaining_gates_pass=info['original_remaining_gates_pass']))
    signal.setitimer(signal.ITIMER_REAL, 0)
    write('preparation.json', dict(seconds=time.monotonic() - START, contexts=records,
        family_index=family, target_family_absent_from_active_curved_and_predictive=True,
        no_new_target_fit_or_evidence_scores=True))
    # Exact actual closure; previously bound input hashes are recursively checked.
    bindings = dict(read(PRIOR / 'protocol.json')['source_input_hashes'])
    bindings.update(read(HERE / 'inventory.json')['bindings'])
    for path in (HERE / 'PROTOCOL.md', HERE / 'contrast.py', HERE / 'inventory.py',
                 HERE / 'test_contrast.py', HERE / 'test_receipt.json', HERE / 'inventory.json',
                 HERE / 'preparation.json', ROOT / 'COORDINATOR_PLAN.md'):
        bindings[str(path)] = sha(path)
    for path in HERE.glob('*.npz'):
        bindings[str(path)] = sha(path)
    for path in HERE.glob('*_parent.json'):
        bindings[str(path)] = sha(path)
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and path.endswith('.py') and path.startswith((str(r.REPO), '/srv/bulk/leo/research/')):
            bindings[path] = sha(path)
    for path, expected in bindings.items():
        if sha(path) != expected:
            raise ValueError('Prior binding changed: ' + path)
    write('protocol.json', dict(schema='full-parent-cavity-MAP/v1', bindings=bindings,
        case=CASE, norad=NORAD, complete_D_IDs=entry['observation_ids'], pool=pool,
        arms=ARMS, contexts=CONTEXTS, maximum_diagnostic_slots=4,
        separate_witnesses=[], no_witness_prediction=True,
        phase_MAP='same641uniformgrid+causalmean/top3localrefinements as previous diagnostic, not certifiedglobalMAP',
        phase_law='original causal Studentnu3/SDsqrt3 conditioned[-15,15]; same nativealiases-4..4/fullBphi; original normalization',
        full_parent='all incumbent curved+predictive observations at common savedc0x, same5 phase refreshes; not original optimizer replay',
        preparation_seconds=read(HERE / 'preparation.json')['seconds'],
        inventory_seconds=inv['seconds'], test_seconds=read(HERE / 'test_receipt.json')['seconds'],
        cap_worker_seconds=CAP, numerical_workers=1, BLAS_threads=1,
        position_fits=0, new_catalogue_scores=0, physical_identity_admissions=0))
    print('PREPARED', sha(HERE / 'protocol.json'), flush=True)


def verify():
    protocol = read(HERE / 'protocol.json')
    for path, expected in protocol['bindings'].items():
        if sha(path) != expected:
            raise ValueError('Frozen source/input changed: ' + path)
    receipt = read(ROOT / 'audit/witness_preflight.json')
    if not receipt['all_passed'] or receipt['protocol_sha256'] != sha(HERE / 'protocol.json'):
        raise ValueError('Matching independent preflight required')
    return protocol


def at_fixed_phase(candidate, comp, phase, alias, d, entry):
    geometry = k.m.q.phase_geometry(candidate, comp['x'], np.asarray([phase]))
    raw = comp['raw'] + alias * k.PERIOD - geometry['frequency_hz'][0] * comp['q']
    B = geometry['shape_columns_hz'][0] * comp['q'][:, None]
    coefficient = adequacy.mode_mean(raw, comp['covariance'], B)
    times = d['scan'].tracks[entry['track_index']]['times']
    white = d['scan'].white[entry['track_index']]
    elevation = geometry['elevation_deg'][0]
    return dict(phase_s=float(phase), whole_alias=int(alias), mode_coefficient=coefficient,
        conservative_gate=adequacy.source_gate(raw, times, white, elevation),
        fullmode_gate=adequacy.source_gate(raw - B @ coefficient, times, white, elevation))


def run():
    threads()
    protocol = verify()
    prefix = protocol['preparation_seconds'] + protocol['test_seconds'] + protocol['inventory_seconds']
    began = time.monotonic()
    sr.alarm(CAP - prefix)
    write('execution_started.json', dict(protocol_sha256=sha(HERE / 'protocol.json'), prefix_worker_seconds=prefix))
    slots = []
    try:
        d, x, family, target, entry = input_context()
        candidate = k.candidate(w.owner_context(d, entry), NORAD)
        if not np.array_equal(candidate['target_sky']['time_s'], candidate['target_mode_bank']['time_s']):
            raise ValueError('Causal sky/mode grids changed')
        for arm in ARMS:
            comps, results = {}, {}
            for context in CONTEXTS:
                start = time.monotonic()
                prefix_path = HERE / (arm + '_' + context)
                arrays = np.load(str(prefix_path) + '.npz')
                comp = {key: arrays[key] for key in arrays.files}
                comp['d'] = w.owner_context(d, entry)
                aliases, shifts = k.alias_vectors(np.zeros(len(comp['raw']), int), np.arange(-4, 5))
                comp.update(aliases=aliases, shifts=shifts)
                best = dict(norad=NORAD, candidate_index=family)
                diagnostic = previous.diagnose(d, candidate, comp, entry, target, best)
                parent = read(Path(str(prefix_path) + '_parent.json'))
                result = dict(arm=arm, context=context, status='complete', source_diagnostic=diagnostic,
                    old_parent_gates_pass=parent['original_remaining_gates_pass'],
                    target_not_in_parent_calibration=True, original_full_parent=(context == 'full_parent'),
                    independent_identity_validation=False, no_witness_available_in_archived_audited_fields=True,
                    seconds=time.monotonic() - start)
                write(arm + '_' + context + '_result.json', result)
                slots.append(dict(arm=arm, context=context, status='complete', seconds=result['seconds']))
                comps[context], results[context] = comp, diagnostic
            comparison = compare_backgrounds(comps['full_parent'], comps['old_union_cavity'])
            comparison['MAP_mode_coefficient_difference'] = np.asarray(results['full_parent']['mode_coefficient']) - results['old_union_cavity']['mode_coefficient']
            comparison['MAP_phase_difference_s'] = results['full_parent']['phase_s'] - results['old_union_cavity']['phase_s']
            comparison['fixed_old_cavity_MAP'] = {context: at_fixed_phase(candidate, comps[context],
                results['old_union_cavity']['phase_s'], results['old_union_cavity']['alias'], d, entry) for context in CONTEXTS}
            write(arm + '_comparison.json', comparison)
    except Exception as exc:
        write('failure.json', dict(error=repr(exc), traceback=traceback.format_exc(), completed_slots=slots))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    complete = {(q['arm'], q['context']) for q in slots}
    slots += [dict(arm=arm, context=context, status='unavailable') for arm in ARMS for context in CONTEXTS if (arm, context) not in complete]
    write('execution.json', dict(slots=slots, cumulative_worker_seconds=prefix + time.monotonic() - began,
        run_wall_seconds=time.monotonic() - began, numerical_workers=1, max_slots=4,
        new_evidence_integrals=0, position_fits=0, GPS_used=False, identity_admissions=0))
    verify()
    write('RF_seal.json', dict(protocol_sha256=sha(HERE / 'protocol.json'),
        files={str(path): sha(path) for path in sorted(HERE.rglob('*')) if path.is_file()
               and '__pycache__' not in path.parts and '.pytest_cache' not in path.parts}))
    print('TERMINAL', read(HERE / 'execution.json')['cumulative_worker_seconds'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'run'])
    globals()[parser.parse_args().action]()
