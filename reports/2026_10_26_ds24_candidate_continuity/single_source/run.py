"""Known-single-source detector control in the frozen historical runtime."""
import time
STARTED = time.monotonic()
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parent
OLD = Path('/srv/bulk/leo/research/ds24-measurement-continuity-r01/measurement')
spec = importlib.util.spec_from_file_location('prior_measurement_fixture', OLD/'experiment.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
SOURCE = dict(name='A', cfo0=100000., rate=200., amplitude=1000., phase=.3, epoch=127)
SEED = 2026102603
VISITS = tuple(range(24))
CAP = 120.


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    fixture.write(path, data)


def synthesize(visit):
    if visit not in VISITS:
        raise ValueError('outside declared schedule')
    samples = np.arange(fixture.COUNT)/fixture.RATE
    pilot = fixture.waveform('sampled_deployed', SOURCE['epoch'])
    clean = SOURCE['amplitude']*pilot*fixture.carrier(SOURCE, visit+samples)
    rng = np.random.default_rng(np.random.SeedSequence([SEED, visit]))
    noise = 300/np.sqrt(2)*(rng.normal(size=(fixture.COUNT,2)) + 1j*rng.normal(size=(fixture.COUNT,2)))
    combined = clean[:,None]+noise
    before = np.stack([combined.real,combined.imag],axis=-1)
    clipping = int(np.count_nonzero((before < -32768) | (before > 32767)))
    if clipping:
        raise ValueError('ADC clipping')
    iq = np.rint(before).astype('<i2')
    return iq, dict(iq_sha256=hashlib.sha256(iq.tobytes()).hexdigest(),
                    noise_sha256=hashlib.sha256(noise.tobytes()).hexdigest(),
                    clipping_samples=clipping, sources=[SOURCE], seed=[SEED,visit],
                    global_start_seconds=float(visit), source_count=1)


def prepare():
    if (ROOT/'protocol.json').exists():
        raise FileExistsError('preserve frozen preparation')
    identity=fixture.detector_identity()
    suite=unittest.defaultTestLoader.discover(str(ROOT),pattern='test_single.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError('owned tests failed')
    preparation=dict(all_passed=True, tests=result.testsRun, identity=identity,
                     preparation_seconds=time.monotonic()-STARTED, detector_calls=0)
    write(ROOT/'preparation.json',preparation)
    paths=[ROOT/'run.py',ROOT/'test_single.py',ROOT/'PROTOCOL.md',ROOT/'preparation.json',
           OLD/'experiment.py',OLD/'protocol.json',OLD/'detector_identity.json',
           ROOT.parent/'prototype/protocol.json',ROOT.parent/'prototype/continuity.py',
           ROOT.parent/'prototype/experiment.py',
           fixture.AUTH/'replay_metadata.json',fixture.OLD/'control.py']
    bindings={str(p):sha(p) for p in paths}
    bindings.update(identity['actual_imported_sources'])
    write(ROOT/'protocol.json',dict(bindings=bindings,visits=list(VISITS),source=SOURCE,
        seed=SEED,cap_seconds=CAP,detector_calls=24,receivers=2,law='sampled_deployed',
        initial_preparation_seconds=preparation['preparation_seconds'],no_position_fit=True,
        selector_protocol_sha256=sha(ROOT.parent/'prototype/protocol.json')))
    print(json.dumps(dict(preparation=preparation,protocol_sha256=sha(ROOT/'protocol.json'))))


def run():
    from leo.scanner.fast_scan_analysis import production_glrt
    if (ROOT/'slots').exists():
        raise FileExistsError('no detector rerun')
    protocol=json.loads((ROOT/'protocol.json').read_text())
    for path,digest in protocol['bindings'].items():
        assert sha(path)==digest,path
    identity=fixture.detector_identity()
    deadline=STARTED+CAP-protocol['initial_preparation_seconds']
    (ROOT/'slots').mkdir()
    slots=[]
    for visit in VISITS:
        began=time.monotonic()
        row=dict(name='single_source_sampled_deployed',law='sampled_deployed',
                 time_s=float(visit),visit=visit,sources=[SOURCE])
        try:
            fixture.alarm(min(20.,deadline-time.monotonic()))
            iq,details=synthesize(visit)
            row['input']=details
            result=production_glrt(fixture.window(iq),(0,1))
            row.update(status='complete',receivers=[x.model_dump(mode='json') for x in result])
        except Exception as exc:
            row.update(status='failed',error=repr(exc))
        finally:
            signal.setitimer(signal.ITIMER_REAL,0)
        row['worker_seconds']=time.monotonic()-began
        write(ROOT/'slots'/f'single_source_{visit:02}.json',row)
        slots.append(row)
        if (visit+1)%8==0:
            print(json.dumps(dict(done=visit+1,complete=sum(x['status']=='complete' for x in slots))),flush=True)
    after=fixture.detector_identity()
    assert identity==after
    execution=dict(complete=sum(x['status']=='complete' for x in slots),slots=len(slots),
                   identity_before=identity,identity_after=after,
                   run_seconds=time.monotonic()-STARTED,
                   cumulative_worker_seconds=time.monotonic()-STARTED+protocol['initial_preparation_seconds'],
                   detector_calls_attempted=sum('input' in x for x in slots),position_fits=0)
    write(ROOT/'execution.json',execution)
    paths=[ROOT/'protocol.json',ROOT/'execution.json',*sorted((ROOT/'slots').glob('*.json'))]
    write(ROOT/'RF_seal.json',dict(files={str(p):sha(p) for p in paths},complete=execution['complete']))
    print(json.dumps(execution),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','run'])
    args=parser.parse_args()
    (prepare if args.command=='prepare' else run)()
