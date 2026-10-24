"""Bounded DS24 full-data, fixed-assignment restarts from half-data endpoints."""
import argparse
import json
from pathlib import Path
import signal
import time

import numpy as np

import ds24_engine as engine
from algo02_scan import pair_passes
from ds23_family_cavity import unused_student_gap
from investigate_dsx01_localization_failures import fit
from probe_ds23_family_cavity_position import unused_count
from probe_ds23_frequency_events import summary
from probe_ds23_graph_seeded_paths import build
from run_algo01_ds23_sample import read, write, sha

OUT = Path(__file__).resolve().parent
FULL = Path('/srv/bulk/leo/research/ds25-20261024')
HALF = Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')
ARMS = ('c0', 'fitted_c')
STARTS = ('incumbent', 'ch1_4', 'ch5_8')


def refit(d, arm, start):
    reference = np.zeros(len(d['means']))
    x = np.asarray(start, float)
    history = []
    for epoch in range(5):
        p = build(d, 'default', arm, reference)
        fitted = fit(p, x, iterations=48)
        x = np.asarray(fitted['parameters'])
        phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        history.append(dict(epoch=epoch, fit=fitted,
            phase_change_s=float(np.max(abs(phase-reference)))))
        reference = phase
    result = summary(p, x, d['entries'])
    result.update(history=history, final_phase_change_s=history[-1]['phase_change_s'],
        corrected_selection_loss=result['negative_twice_elbo']
            - unused_count(p, d['entries']) * unused_student_gap(d['model']['nu']))
    return result


def main(case):
    destination = OUT / (case + '_fixed.json')
    if destination.exists():
        print(case, 'cached', flush=True)
        return
    began = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('240s fixed-restart cap')))
    signal.alarm(240)
    d = engine.cavity_context(case, root=FULL)
    original = d['arms']
    source = {'incumbent': original}
    for group in STARTS[1:]:
        source[group] = read(HALF / group / 'family_cavity/position' / (case+'.json'))['policy_arms']
    # Replay each actual endpoint; context.x may predate cavity selection.
    replay = {}
    for arm in ARMS:
        saved = original[arm]
        p = build(d, 'default', arm, saved['phase_reference'])
        delta = p.calculate(saved['endpoint_east_north_km'])['negative_twice_elbo'] - saved['negative_twice_elbo']
        assert abs(delta) < 1e-5, (arm, delta)
        replay[arm] = float(delta)
    trials = []
    for name in STARTS:
        arms = {}
        for arm in ARMS:
            start = source[name][arm]['endpoint_east_north_km']
            assert np.isfinite(start).all() and np.max(abs(np.asarray(start))) <= 12.5
            arms[arm] = refit(d, arm, start)
            print(case, name, arm, 'gain', original[arm]['negative_twice_elbo']-arms[arm]['negative_twice_elbo'],
                'km', np.linalg.norm(np.asarray(arms[arm]['endpoint_east_north_km'])-original[arm]['endpoint_east_north_km']), flush=True)
        valid = bool(pair_passes(arms, include_linear=True)
            and all(r['final_phase_change_s'] <= .01 for r in arms.values()))
        trials.append(dict(name=name, starts={a:source[name][a]['endpoint_east_north_km'] for a in ARMS},
            arms=arms, paired_valid=valid))
    eligible = [t for t in trials if t['paired_valid']]
    best = min(eligible, key=lambda t:t['arms']['c0']['corrected_selection_loss']) if eligible else None
    # Numerical-scale changes are recorded, never treated as a scientific gain.
    gain = original['c0']['negative_twice_elbo'] - best['arms']['c0']['negative_twice_elbo'] if best else None
    selection = dict(best=best['name'] if best else None, gain_c0=gain,
        meaningful_improvement=bool(gain is not None and gain > 1e-4),
        rule='minimum full same-assignment c0 objective among paired-valid restarts; improvement >1e-4',
        no_geographic_error_or_GPS_accessed=True)
    result = dict(case=case, status='complete', original=original, replay_difference=replay,
        fixed_assignments_aliases_mask_weights_priors_and_predictive_entries=True,
        phase_rounds=5, position_steps_per_round=48, starts=STARTS,
        trials=trials, RF_selection=selection, seconds=time.monotonic()-began,
        source_sha256=sha(Path(__file__)), full_source=str(FULL), half_source=str(HALF))
    write(destination, result)
    signal.alarm(0)
    print(case, 'complete', result['seconds'], selection, flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('case')
    main(parser.parse_args().case)
