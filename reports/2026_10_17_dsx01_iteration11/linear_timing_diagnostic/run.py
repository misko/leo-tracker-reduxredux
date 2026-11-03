"""One bounded exact-orbit/linear-timing diagnostic; no likelihood or fit calls."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace

import numpy as np

from diagnostic import CallLedger, DELTAS_S, select_training_rows, summarize

HERE = Path(__file__).resolve().parent
PREPARATION = HERE.parent / 'population_point_preparation'


def digest(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def verify_manifest(path):
    manifest = json.loads(Path(path).read_text())
    if manifest.get('sealed') is not True:
        raise ValueError('Sealed prediction producer required')
    for row in manifest['files']:
        candidate = Path(path).parent / row['path']
        if digest(candidate) != row['sha256']:
            raise ValueError('Frozen producer file changed: ' + str(candidate))
    return manifest


def load_preparation():
    path = PREPARATION / 'prepare.py'
    spec = importlib.util.spec_from_file_location('linear_diagnostic_preparation', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run():
    begun = time.monotonic()
    manifest_path = PREPARATION / 'manifest.json'
    verify_manifest(manifest_path)
    prediction_seal = json.loads((PREPARATION / 'predictions_seal.json').read_text())
    if prediction_seal.get('all_two_sealed') is not True or [row['case'] for row in
            prediction_seal['predictions']] != ['old_fitted-c', 'old_zero-c']:
        raise ValueError('Both declared OLD prediction arms must be sealed')
    for row in prediction_seal['predictions']:
        if digest(row['path']) != row['sha256']:
            raise ValueError('Frozen producer prediction changed')
    producer = load_preparation()
    inputs = producer.load_inputs()
    bank, prior, metadata = (inputs[name] for name in ('bank', 'prior', 'metadata'))
    if len(bank.numbers) != 800 or np.any(metadata.measured_hz != 0):
        raise ValueError('Exact unsupported800 and blank metadata required')
    arms = ('fitted-c', 'zero-c')
    prepared = {}
    for arm in arms:
        path = PREPARATION / f'prepared_old_{arm}.npz'
        with np.load(path, allow_pickle=False) as archive:
            prepared[arm] = {name: archive[name].copy() for name in archive.files}
        item = prepared[arm]
        if float(item['sigma_hz']) != 125. or float(item['visibility_width']) != 1e-5:
            raise ValueError('Original125Hz/compact-horizon working model required')
        np.testing.assert_array_equal(item['unsupported_number'], bank.numbers)
        for field, actual in [('observation_id', metadata.window_ids), ('times_s', metadata.times_s),
                              ('rf_hz', metadata.rf_hz), ('receiver', metadata.receiver),
                              ('channel', metadata.channel)]:
            np.testing.assert_array_equal(item[field], actual)
    np.testing.assert_array_equal(prepared[arms[0]]['train_mask'], prepared[arms[1]]['train_mask'])
    rows = select_training_rows(metadata, prepared[arms[0]]['train_mask'])
    subset = SimpleNamespace(window_ids=tuple(metadata.window_ids[i] for i in rows),
                             measured_hz=np.zeros(len(rows)), margin=np.ones(len(rows)),
                             **{field: np.asarray(getattr(metadata, field))[rows].copy() for field in
                                ('times_s', 'rf_hz', 'receiver', 'channel')})
    source_paths = [HERE / name for name in ('PROTOCOL.md', 'diagnostic.py', 'test_diagnostic.py', 'run.py')]
    source_paths += [manifest_path, PREPARATION / 'prepare.py', PREPARATION / 'predictions_seal.json']
    source_paths += [PREPARATION / f'prepared_old_{arm}.npz' for arm in arms]
    source_hashes = {str(path): digest(path) for path in source_paths}
    save(HERE / 'frozen_inventory.json', dict(source_sha256=source_hashes,
         producer_authority=inputs['authority'], deltas_s=DELTAS_S,
         rows=rows.tolist(), observation_id=list(subset.window_ids),
         times_s=subset.times_s.tolist(), receiver=subset.receiver.tolist(),
         channel=subset.channel.tolist(), actual_rf_hz=subset.rf_hz.tolist(),
         unsupported_number=bank.numbers.tolist(), maximum_orbit_calls=18,
         maximum_elevation_calls=18, maximum_horizon_calls=18,
         held_CFO_read=False, station_reference_read=False,
         propagation_calls=0, objective_calls=0, fit_calls=0))
    ledger_path = HERE / 'call-ledger.json'
    def persist(records):
        temporary = HERE / 'call-ledger.tmp'
        temporary.write_text(json.dumps(dict(calls=records), indent=2) + '\n')
        temporary.replace(ledger_path)
    ledger = CallLedger(persist)
    from leo.analysis.hard60_score import predict_orbits
    from leo.analysis.shared_scan_model import elevation_geometry, horizon_weight
    summaries = []
    horizon_calls = 0
    try:
        for arm in arms:
            item = prepared[arm]
            v = np.asarray(inputs['arms']['old_' + arm]['vector'], float)
            if arm == 'zero-c' and v[6] != 0:
                raise ValueError('Saved OLD c0 endpoint must have c=0')
            common = float(item['common_timing_s'])
            if common != float(v[7]):
                raise ValueError('Saved common timing changed')
            mean = item['unsupported_mean_hz'][rows]
            slope = item['unsupported_timing_slope_hz_s'][rows]
            zero_weight = item['unsupported_visibility_weight'][rows]
            correction = item['correction_hz'][rows, None]
            raw = {}
            for delta in DELTAS_S:
                if time.monotonic() - begun >= 58:
                    raise TimeoutError('Declared60-second diagnostic allowance')
                shifts = np.full(len(bank.numbers), common + delta)
                prediction = ledger.call('orbit', arm, delta, predict_orbits,
                                         bank, subset, prior, v[:2], shifts, derivatives=True)
                sine = ledger.call('elevation', arm, delta, elevation_geometry,
                                   bank, subset, prior, v[:2], shifts)[0]
                horizon_calls += 1
                weight = horizon_weight(sine, 1e-5)[0]
                exact = prediction[0] + correction
                linear = mean + slope * delta
                arrays = dict(exact_hz=exact, linear_hz=linear, error_hz=exact-linear,
                              exact_timing_slope_hz_s=prediction[3], linear_timing_slope_hz_s=slope,
                              sine_elevation=sine, visibility_weight=weight,
                              zero_visibility_weight=zero_weight,
                              observation_id=np.asarray(subset.window_ids),
                              unsupported_number=bank.numbers.copy())
                path = HERE / f'raw_{arm}_delta{delta:+g}.npz'
                with path.open('xb') as stream:
                    np.savez_compressed(stream, **arrays)
                raw[delta] = arrays
            zero_sine = raw[0.]['sine_elevation']
            for delta in DELTAS_S:
                arrays = raw[delta]
                summaries.append(dict(arm=arm, delta_s=delta,
                    maximum_timing_slope_change_hz_s=float(np.max(abs(
                        arrays['exact_timing_slope_hz_s']-slope))),
                    **summarize(arrays['exact_hz'], arrays['linear_hz'], arrays['sine_elevation'],
                                zero_sine, arrays['visibility_weight'], zero_weight)))
        producer.verify()
        verify_manifest(manifest_path)
        if any(digest(path) != hashed for path, hashed in source_hashes.items()):
            raise ValueError('Diagnostic source authority changed')
        save(HERE / 'results.json', dict(passed_execution=True, summaries=summaries,
             elapsed_seconds=time.monotonic()-begun, orbit_calls=18, elevation_calls=18,
             horizon_calls=horizon_calls,
             maximum_rows=32, actual_rows=len(rows), candidates=len(bank.numbers),
             objective_calls=0, propagation_calls=0, fit_calls=0,
             held_CFO_read=False, station_reference_read=False,
             selection_unchanged=True, physical_accuracy_threshold=None))
    except BaseException as error:
        save(HERE / 'failure.json', dict(type=type(error).__name__, message=str(error),
             traceback=traceback.format_exc(), calls=ledger.calls, horizon_calls=horizon_calls,
             elapsed_seconds=time.monotonic()-begun, automatic_retry=False))
        raise


if __name__ == '__main__':
    try:
        run()
    except BaseException as error:
        if not (HERE / 'failure.json').exists():
            save(HERE / 'failure.json', dict(type=type(error).__name__, message=str(error),
                 traceback=traceback.format_exc(), automatic_retry=False,
                 phase='before_or_outside_declared_calls'))
        raise
