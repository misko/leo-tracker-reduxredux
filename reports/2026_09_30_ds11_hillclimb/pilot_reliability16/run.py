"""Bounded, training-symbol-only stability diagnostics for frozen pilot fits."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
WAVE = HERE.parent/'waveform_replication16'
spec = importlib.util.spec_from_file_location('reliability_wave', WAVE/'run.py')
wave = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wave)


def read(p):
    return json.loads(Path(p).read_text())


def write(p, value):
    with Path(p).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def prepare():
    manifest, _ = wave.load_plan()
    files = [WAVE/'manifest.json', WAVE/'local/extraction.json', WAVE/'local/measurements.json',
             Path(__file__), HERE/'test_run.py', HERE/'PROTOCOL.md']
    sources = dict(manifest['sources'])
    sources.update({str(p):wave.digest(p) for p in files})
    write(HERE/'plan.json', dict(schema='ds11-pilot-stability-plan/v1', rows=124,
                                reference_used=False, position_fit=False, sources=sources))


def metrics(frames, indices, fit):
    full = float(fit(frames, indices))
    alternating = [float(fit(frames[k::2], indices)) for k in (0, 1)]
    values = frames[:, indices]
    corrected = values*np.exp(-2j*np.pi*full*indices*4.4e-6)[None, :, None]
    coherent = float(np.sum(abs(np.mean(corrected, axis=1))**2))
    energy = float(np.sum(np.mean(abs(values)**2, axis=1)))
    return dict(full_native_hz=full, alternating_native_hz=alternating,
                alternating_disagreement_hz=abs(alternating[0]-alternating[1]),
                alternating_search_boundaries=[abs(f)>=1499.999 for f in alternating],
                coherent_energy_fraction=coherent/max(energy, 1e-30))


def frames_for(row, saved, helpers):
    remove_phase, _, _, demodulate, geometry, references = helpers
    assert wave.digest(saved['path']) == saved['sha256']
    iq = np.load(saved['path'], allow_pickle=False)
    assert iq.shape == (100000, 2) and iq.dtype == np.dtype('<i2')
    assert hashlib.sha256(iq.tobytes()).hexdigest() == saved['array_sha256']
    samples = iq[:, 0].astype(float)+1j*iq[:, 1]
    _, bins, center = geometry(row['edge'])
    _, _, pilot = references(row['edge'])
    c = row['candidate']; cached = c['fractional_tracking_cfo_hz']
    epoch = c['integer_epoch_sample']+c['fractional_epoch_offset_samples']
    keep = abs(np.fft.fftfreq(1024, 1/240e6)[bins]-center+cached) <= .45*5e6
    bins, pilot = bins[keep], pilot[:, keep]
    assert len(bins) >= 2
    frames = []
    for frame in range(8):
        ep = epoch+frame*5e6/750
        start = max(0, int(ep)-50); stop = start+6850
        assert stop <= len(samples)
        symbols = demodulate(samples[start:stop], 5000000, ep-start, cached, center)[1:]
        frames.append(remove_phase(symbols[:300, bins]/pilot, center))
    return np.asarray(frames)


def worker():
    plan = read(HERE/'plan.json')
    for p,h in plan['sources'].items():
        assert wave.digest(p) == h, p
    manifest = read(WAVE/'manifest.json')
    extraction = read(WAVE/'local/extraction.json')
    measured = read(WAVE/'local/measurements.json')
    assert extraction['plan_sha256'] == measured['plan_sha256'] == wave.digest(WAVE/'manifest.json')
    assert measured['extraction_sha256'] == wave.digest(WAVE/'local/extraction.json')
    assert len(manifest['rows']) == len(extraction['rows']) == len(measured['rows']) == 124
    helpers = wave.load_waveform_helpers()
    for row, saved, old in zip(manifest['rows'], extraction['rows'], measured['rows'], strict=True):
        assert all(row[k] == saved[k] == old[k] for k in ('ordinal', 'track_id', 'observation_index', 'visit'))
        assert saved['status'] == old['status'] == 'ok'
        number = row['ordinal']
        write(HERE/'rows'/f'{number:03d}.active.json', dict(ordinal=number, status='active'))
        result = dict(ordinal=number, track_id=row['track_id'], receiver_id=row['receiver_id'],
                      visit=row['visit'], arms={})
        try:
            frames = frames_for(row, saved, helpers)
            for arm, indices in (('pilot_2_65', np.arange(64)), ('pilot_22_221', np.arange(20, 220))):
                result['arms'][arm] = metrics(frames, indices, helpers[2])
                discrepancy = abs(result['arms'][arm]['full_native_hz']-old['arms'][arm]['native_residual_hz'])
                assert discrepancy < 1e-6, 'full-estimate replay discrepancy'
                result['arms'][arm]['replay_discrepancy_hz'] = discrepancy
            result['status'] = 'ok'
        except Exception as error:
            result.update(status='failed', reason=f'{type(error).__name__}: {error}')
        write(HERE/'rows'/f'{number:03d}.json', result)


def batch():
    (HERE/'rows').mkdir()
    start = time.monotonic()
    command = ['timeout', '--kill-after=5s', '180s', 'nice', '-n', '19', sys.executable, str(Path(__file__)), 'worker']
    with (HERE/'worker.log').open('x') as log:
        done = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    receipt = dict(exit_code=done.returncode, elapsed_s=time.monotonic()-start,
                   command=command, plan_sha256=wave.digest(HERE/'plan.json'))
    write(HERE/'receipt.json', receipt)
    rows = []
    for ordinal in range(124):
        p = HERE/'rows'/f'{ordinal:03d}.json'
        rows.append(read(p) if p.exists() else dict(ordinal=ordinal,
                    status='failed' if (HERE/'rows'/f'{ordinal:03d}.active.json').exists() else 'not_attempted'))
    files = [HERE/'plan.json', HERE/'receipt.json']+sorted((HERE/'rows').glob('*.json'))
    write(HERE/'outcome.json', dict(rows=rows, sources={str(p):wave.digest(p) for p in files},
                                   position_fits=0, reference_used=False))
    print(json.dumps(dict(receipt=receipt, counts={s:sum(r['status']==s for r in rows) for s in ('ok','failed','not_attempted')})))


if __name__ == '__main__':
    {'prepare':prepare, 'worker':worker, 'batch':batch}[sys.argv[1]]()
