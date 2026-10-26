"""Frozen synthetic pilot-only control at the historical public detector port."""
import hashlib
import json
from pathlib import Path
import signal
import time
from types import SimpleNamespace
import numpy as np

HERE = Path(__file__).resolve().parent
OLD = Path('/srv/bulk/leo/research/ds24-ambiguity-policy-r01')
FIXTURE = Path('/home/mouse9911/gits/leo-tracker-reduxredux/tests/fixtures/qin_edge_pilots_appendix_a_v1.json')
RATE = 10_000_000
COUNT = RATE // 50
FRAME_SAMPLES = RATE / 750.
SEEDS = (20261026, 20261027)
NOISE_RMS = 300.
CODE = 'sha256:124afbbc81870a4079b272bd828d4a99f716e54624a073d9cb13acc2a1b7fe16'
ENV = 'sha256:8ccb220369bccb42b7bea5dcd3bfa546e132d2250a674e6eac7388a2a425e3b9'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source(cfo=100000., amplitude=1000., epoch=127.25, phase=.3, rate=0.):
    return dict(cfo_hz=cfo, amplitude=amplitude, epoch_samples=epoch,
                phase_radians=phase, rate_hz_s=rate)


SCENARIOS = [
    ('noise', []), ('strong', [source()]), ('weak', [source(amplitude=75.)]),
    ('coincident_500', [source(), source(cfo=100500., amplitude=600., phase=-.8)]),
    ('coincident_3000', [source(), source(cfo=103000., amplitude=600., phase=-.8)]),
    ('separated_500', [source(), source(cfo=100500., amplitude=600., epoch=811.75, phase=-.8)]),
    ('separated_3000', [source(), source(cfo=103000., amplitude=600., epoch=811.75, phase=-.8)]),
    ('chirp', [source(rate=10000.)]),
]


def pilot(samples, epoch):
    """Evaluate the fixture's continuous pilot law, independently of template sampling."""
    fixture = json.loads(FIXTURE.read_text())['sequences']
    indices = np.arange(488, 496)
    states = np.array([[(int(fixture[str(j)], 16) >> (2*(299-i))) & 3
                        for j in indices] for i in range(300)])
    symbols = np.exp(.5j*np.pi*(states+.5))
    u = np.asarray(samples, float)-epoch
    frame = np.floor(u/FRAME_SAMPLES)
    local = u-frame*FRAME_SAMPLES
    symbol = np.floor(local/44.+1e-10).astype(int)
    valid = (symbol >= 2) & (symbol < 302)
    out = np.zeros(len(u), np.complex128)
    t = (local[valid]-44*symbol[valid])/RATE - 2/15*1e-6
    offsets = (indices-indices.mean())*234375.
    out[valid] = np.sum(symbols[symbol[valid]-2] *
                        np.exp(2j*np.pi*t[:, None]*offsets), axis=1)/np.sqrt(8)
    return out


def synthesize(sources, seed):
    n = np.arange(COUNT); t = n/RATE
    clean = np.zeros(COUNT, np.complex128)
    for s in sources:
        clean += s['amplitude']*pilot(n, s['epoch_samples'])*np.exp(
            1j*s['phase_radians'] + 2j*np.pi*(s['cfo_hz']*t+.5*s['rate_hz_s']*t*t))
    rng = np.random.default_rng(seed)
    noise = NOISE_RMS/np.sqrt(2)*(rng.normal(size=(COUNT, 2)) +
                                  1j*rng.normal(size=(COUNT, 2)))
    values = clean[:, None]+noise
    iq = np.stack((values.real, values.imag), axis=-1)
    clipping = int(np.count_nonzero((iq < -32768) | (iq > 32767)))
    if clipping:
        raise ValueError('synthetic input would clip')
    iq = np.rint(iq).astype('<i2')
    return iq, dict(signal_power=float(np.mean(np.abs(clean)**2)),
                    noise_power_by_receiver=np.mean(np.abs(noise)**2, axis=0).tolist(),
                    clipping_samples=clipping,
                    iq_sha256=hashlib.sha256(iq.tobytes()).hexdigest())


def summarize(candidates, sources):
    fractional = [c for c in candidates if c['fractional_epoch_status'] == 'complete'
                  and all(c[k] is not None for k in ('fractional_margin',
                          'fractional_epoch_offset_samples', 'fractional_tracking_cfo_hz'))]
    accepted = [c for c in fractional if c['fractional_margin'] >= .025]
    selected = max(accepted, key=lambda c: c['fractional_margin']) if accepted else None
    summaries = []
    for s in sources:
        def distance(c):
            epoch = c['epoch_sample'] + c['fractional_epoch_offset_samples']
            return abs((epoch-s['epoch_samples']+FRAME_SAMPLES/2) % FRAME_SAMPLES-FRAME_SAMPLES/2)
        near = [c for c in fractional if distance(c) <= 3]
        summaries.append(dict(source=s, epoch_near_candidates=[dict(
            rank=c['candidate_rank'], accepted=c['fractional_margin'] >= .025,
            cfo_hz=c['fractional_tracking_cfo_hz'],
            cfo_minus_midpoint_hz=c['fractional_tracking_cfo_hz']-(s['cfo_hz']+.01*s['rate_hz_s']),
            margin=c['fractional_margin'], epoch_error_samples=distance(c)) for c in near]))
    return dict(accepted_count=len(accepted), fractional_count=len(fractional),
                highest_margin_accepted=selected, sources=summaries)


def alarm(seconds):
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('frozen control deadline')))
    signal.setitimer(signal.ITIMER_REAL, max(.001, seconds))


def main():
    began = time.monotonic(); deadline = began+120
    if (HERE/'results.json').exists() or any(HERE.glob('*_2026102?.json')):
        raise FileExistsError('the frozen synthetic slots must not be overwritten')
    protocol = json.loads((HERE/'protocol.json').read_text())
    for path, digest in protocol['files'].items():
        if sha(path) != digest:
            raise ValueError('frozen input changed: '+path)
    audit = json.loads((HERE.parent/'audit/iq_preflight.json').read_text())
    if not audit['all_passed'] or audit['protocol_sha256'] != sha(HERE/'protocol.json'):
        raise ValueError('exact amended-scope preflight required')
    from leo.processing.fast_scan import implementation_identity
    from leo.scanner.fast_scan_analysis import production_glrt
    assert implementation_identity() == (CODE, ENV)
    meta = json.loads((OLD/'replay_metadata.json').read_text())
    target = next(t for t in meta['segment_document']['configuration']['targets']
                  if t['target_id'] == meta['first_index']['target_id'])
    acquisition = dict(actual_if_center_hz=meta['first_index']['acquisition']['actual_if_center_hz'])
    slots = []
    for name, sources in SCENARIOS:
        for seed in SEEDS:
            slot = dict(scenario=name, seed=seed, sources=sources, synthetic=True)
            try:
                if time.monotonic() >= deadline:
                    raise TimeoutError('total deadline exhausted')
                alarm(min(20., deadline-time.monotonic()))
                iq, details = synthesize(sources, seed)
                window = SimpleNamespace(target=target, acquisition=acquisition,
                                         samples=iq, sample_rate_hz=RATE)
                started = time.monotonic()
                receivers = production_glrt(window, (0, 1))
                slot.update(status='complete', detector_seconds=time.monotonic()-started,
                            input=details, receivers=[])
                for receiver in receivers:
                    values = receiver.model_dump(mode='json')
                    slot['receivers'].append(dict(**values, summary=summarize(values['candidates'], sources)))
            except Exception as exc:
                slot.update(status='failed', error=repr(exc))
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
            slots.append(slot)
            (HERE/f'{name}_{seed}.json').write_text(json.dumps(slot, indent=2, allow_nan=False)+'\n')
    assert implementation_identity() == (CODE, ENV)
    result = dict(slots=slots, elapsed_seconds=time.monotonic()-began, total_slots=16,
                  prototype_only=True, original_IQ_read=False, new_RF=False,
                  graph_tracking=False, position_fit=False, code_digest=CODE, environment_digest=ENV)
    (HERE/'results.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(complete=sum(s['status']=='complete' for s in slots), slots=16,
                         seconds=result['elapsed_seconds'])))


if __name__ == '__main__':
    main()
