"""Metadata-only source panel, immutable sparse forecasts and donor authority."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import time
import predictor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TRACK = Path('/srv/bulk/leo/research/ds25-20261024')
CHANNELS = [1, 4, 5, 6, 7, 8]
FRACTIONS = [.2, .4, .6, .8]
MAPPER = Path('/srv/bulk/leo/research/ds24-detector-response-r01/influence/raw_metadata.py')


def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def bound(check=True):
    for key in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
        if os.environ.get(key) != '1': raise ValueError('BLAS1 required')
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('580-second bound')))
    signal.alarm(580)
    if check:
        for path, digest in read(HERE / 'protocol.json')['files'].items():
            if sha(path) != digest: raise ValueError('frozen source changed: ' + path)


def request(slot, probe):
    return dict(request_id=slot['request_id'], source_input=slot['source_input'],
        probe=dict(probe, duration_samples=200000, window_start_counter=probe['valid_start_counter']))


def prepare():
    began = time.monotonic(); bound(False)
    split = read(ROOT / 'split.json')
    mapper = module('frozen_public_metadata_mapper', MAPPER)
    files = {str(p): sha(p) for p in [ROOT / 'split.json', MAPPER] +
             [HERE / n for n in ['PROTOCOL.md', 'predictor.py', 'study.py', 'survey.py', 'test_predictor.py']]}
    slots = []; evaluation = []
    for case in split['development']:
        track_path = TRACK / case / 'tracking.json'; data = read(track_path); source = data['source']
        if source['sample_rate_hz'] != 10000000 or source['probe_ms'] != 20: raise ValueError('unhandled native geometry')
        input_path = Path('/srv/bulk/leo/fast-scan-inputs') / (source['session_id'] + '.json')
        files[str(track_path)] = sha(track_path); files[str(input_path)] = sha(input_path)
        tracking_digest=files[str(track_path)]; input_digest=files[str(input_path)]
        probes = source['probes']
        low = min(p['valid_start_counter'] for p in probes); high = max(p['valid_start_counter'] for p in probes)
        for channel in CHANNELS:
            visits = [p for p in probes if p['channel'] == channel and p['receiver_id'] == 0]
            for fraction in FRACTIONS:
                slot = dict(request_id=f'{case}-CH{channel}-F{int(100*fraction)}', case=case, channel=channel,
                    fraction=fraction, status='missing', cells=[],
                    tracking=dict(path=str(track_path), sha256=tracking_digest),
                    source_input=dict(path=str(input_path), sha256='sha256:' + input_digest))
                chosen = min(visits, key=lambda p: (abs(p['valid_start_counter'] - (low + fraction*(high-low))),
                                                    p['valid_start_counter']), default=None)
                if chosen is None:
                    slot['reason'] = 'no processed channel visit'; slots.append(slot); continue
                slot['probe_metadata'] = {k:v for k,v in chosen.items() if k != 'candidates'}
                slot['status'] = 'nominated'
                try: slot['raw_authority'] = mapper.one(request(slot, chosen))
                except Exception as exc: slot.update(status='missing', reason=repr(exc))
                for rx in [0, 1]:
                    same = [p for p in probes if p['channel'] == channel and p['edge'] == chosen['edge'] and p['receiver_id'] == rx]
                    target = next((p for p in same if p['visit_index'] == chosen['visit_index']), None)
                    header = dict(prediction_id=f"{slot['request_id']}/RX{rx}", request_id=slot['request_id'],
                        case=case, channel=channel, receiver_id=rx, edge=chosen['edge'], fraction=fraction,
                        sample_rate_hz=source['sample_rate_hz'], window_samples=200000,
                        start_counter=chosen['valid_start_counter'], stop_counter=chosen['valid_start_counter']+200000,
                        visit_index=chosen['visit_index'], probe_index=chosen['probe_index'],
                        generation=source['stream_generation'], source_id=source['session_id'],
                        actual_rf_hz=chosen['actual_rf_hz'], tracking_sha256=tracking_digest,
                        raw_recording_authority_digest=source['raw_recording_authority_digest'])
                    history = sorted([p for p in same if p['valid_start_counter']+200000 <= header['start_counter'] and
                        0 < (header['start_counter']-p['valid_start_counter'])/source['sample_rate_hz'] <= predictor.HORIZON_S],
                        key=lambda p:p['valid_start_counter'])[-predictor.HISTORY_VISITS:]
                    slot['cells'].append(dict(header=header, history=history))
                    evaluation.append(dict(prediction_id=header['prediction_id'], target_original=target,
                                           original_fullwindow_acquisition_exposed=True))
                slots.append(slot)
        print(case, 'metadata nominated', flush=True)
    write(HERE / 'panel.json', dict(schema='sparse-development-panel/v1', selection='metadata-only native-counter fractions',
        development=split['development'], validation_target_files_opened=False, fractions=FRACTIONS,
        requested_windows=288, requested_receiver_cells=576, slots=slots))
    write(HERE / 'evaluation_targets.json', dict(schema='archived-target-evaluation-only/v1', rows=evaluation,
        target_values_excluded_from_prediction_inputs=True))
    for name in ['panel.json', 'evaluation_targets.json']: files[str(HERE / name)] = sha(HERE / name)
    write(HERE / 'protocol.json', dict(schema=predictor.VERSION, frozen_utc_ns=time.time_ns(), files=files,
        predictor_version=predictor.VERSION, no_validation_target_files=True, target_outcomes_analyzed_before_freeze=False,
        raw_IQ_reads=0, process_bound_seconds=580, BLAS_threads=1, metadata_seconds=time.monotonic()-began,
        nominal_CFO_reference='window midpoint', timing_phase_reference='window origin'))
    print('frozen', sha(HERE / 'protocol.json'), flush=True)


def predict():
    began = time.monotonic(); bound(); rows=[]
    for slot in read(HERE / 'panel.json')['slots']:
        for cell in slot['cells']:
            row = dict(header=cell['header'], status='failed')
            try: row.update(status='complete', forecast=predictor.predict(cell['header'], cell['history']))
            except Exception as exc: row['error'] = repr(exc)
            rows.append(row)
    write(HERE / 'predictions.json', dict(schema=predictor.VERSION, protocol_sha256=sha(HERE / 'protocol.json'),
        panel_sha256=sha(HERE / 'panel.json'), rows=rows, target_responses_read=False,
        validation_target_outcomes_opened=False, seconds=time.monotonic()-began))
    print('predictions', len(rows), sha(HERE / 'predictions.json'), flush=True)


def authority():
    began=time.monotonic(); bound(); mapper=module('public_selected_donor_metadata', MAPPER)
    panel=read(HERE/'panel.json'); slots={s['request_id']:s for s in panel['slots']}
    unique={}
    for row in read(HERE/'predictions.json')['rows']:
        if row['status']!='complete':continue
        for mode in row['forecast']['modes']:
            for donor in mode['donors']:
                key=(row['header']['case'], donor['visit_index'])
                unique.setdefault(key,(row['header'],donor))
    rows=[]
    for (case,visit),(h,d) in sorted(unique.items()):
        slot=slots[h['request_id']]
        probe=next(p for c in slot['cells'] for p in c['history'] if p['visit_index']==visit)
        item=dict(case=case,visit_index=visit,status='failed')
        try:item.update(status='metadata_verified',raw_authority=mapper.one(request(slot,probe)))
        except Exception as exc:item['error']=repr(exc)
        rows.append(item)
    write(HERE/'donor_authority.json',dict(predictions_sha256=sha(HERE/'predictions.json'),rows=rows,
        requested_donor_windows=len(unique),raw_IQ_reads=0,seconds=time.monotonic()-began))
    print('donor authority',len(rows),round(time.monotonic()-began,2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','predict','authority']);a=p.parse_args()
    dict(prepare=prepare,predict=predict,authority=authority)[a.action]()
