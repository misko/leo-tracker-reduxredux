"""Bounded differential frame-phase screening on existing saved IQ panels."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import json
import signal
import numpy as np
from ds23_differential_frame_phase import extract_phases, heldout_phase_frequency
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_differential_frame_phase_v2'
BULK = Path('/srv/bulk/leo/research/ds23-differential-frame-phase-v2-20261021')
SOURCES = [Path('/srv/bulk/leo/research/ds23-all-lane-components-20261020'),
           Path('/srv/bulk/leo/research/ds23-multilane-confirmation-20261020')]


def jobs():
    result = []
    for source in SOURCES:
        protocol, evaluation = read(source/'protocol.json'), read(source/'evaluation.json')
        fits = {(r['case'], r['probe']): r for r in evaluation['rows'] if r['status'] == 'complete' and r['two_components_qualified']}
        groups = {}
        for j in protocol['jobs']:
            if (j['case'], j['probe']) in fits:
                groups.setdefault(j['group'], []).append(j)
        # Fixed first/middle/last probes per lane; never ranked by phase or position error.
        for group in sorted(groups):
            group_jobs = sorted(groups[group], key=lambda j: j['time_s'])
            for k in sorted({0, len(group_jobs)//2, len(group_jobs)-1}):
                j = group_jobs[k]
                result.append(dict(job=j, fit=fits[j['case'], j['probe']], source=str(source)))
    return result


def one(item):
    j, fit, source = item['job'], item['fit'], Path(item['source'])
    target = BULK/(j['group']+f"_probe{j['probe']:06d}.json")
    if target.exists():
        return read(target)
    def timeout(*_):
        raise TimeoutError('45-second saved-IQ frame-phase analysis cap exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(45)
    record = dict(case=j['case'], group=j['group'], probe=j['probe'], source=str(source))
    try:
        with np.load(source/'panels'/(j['case']+'.npz'), allow_pickle=False) as z:
            meta = json.loads(str(z['metadata_json'])); point = next(p for p in meta['points'] if p['probe'] == j['probe'])
            v = z[point['window_key']][:, point['receiver_offset']]
            y = v[:, 0].astype(float)+1j*v[:, 1].astype(float)
        result = extract_phases(y, meta['sample_rate_hz'], j['edge'], j['first']['epoch'], fit['first_fit'], j['second']['epoch'], fit['second_fit'])
        a, b = result['first'], result['second']; train = result['train_frames']
        differential_weight = 1/(1/a['phase_weight']+1/b['phase_weight'])
        models = {}
        for index, (name, phasor, weight) in enumerate([
                ('first', a['gain'], a['phase_weight']), ('second', b['gain'], b['phase_weight']),
                ('differential', a['gain']*b['gain'].conj(), differential_weight)]):
            models[name] = heldout_phase_frequency(result['time_s'], phasor, weight, train,
                                                  controls=256, seed=2026102100+j['probe']*3+index)
        extraction = dict(time_s=result['time_s'], frame_pairs=result['frame_pairs'],
            first_phase_rad=np.angle(a['gain']), second_phase_rad=np.angle(b['gain']),
            first_phase_weight=a['phase_weight'], second_phase_weight=b['phase_weight'],
            first_training_rank_one_energy_fraction=a['training_rank_one_energy_fraction'],
            second_training_rank_one_energy_fraction=b['training_rank_one_energy_fraction'])
        record.update(status='complete', frames=len(result['time_s']), train_frames=train,
                      models=models, extraction=extraction)
    except Exception as exc:
        record.update(status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    write(target, record)
    return record


def main():
    OUT.mkdir(exist_ok=True); BULK.mkdir(exist_ok=True)
    selected = jobs()
    protocol = dict(jobs=selected, workers=8, cap_seconds_per_probe=45, new_RF_collection=False,
        selection='first/middle/last qualified probe per archived simultaneous-component lane',
        no_GPS_or_satellite_catalogue_used=True, CFO_epoch_rate_conditioned_on_prior_whole_probe_RF_fit=True,
        no_frame_continuity_assumed_by_extraction=True, no_frequency_correction_or_position_fit=True,
        no_surrogate_familywise_claim_across_probes=True,
        saved_panel_sha256={str(p): sha(p) for p in sorted({Path(j['source'])/'panels'/(j['job']['case']+'.npz') for j in selected})},
        source_bindings={str(p): sha(p) for source in SOURCES for p in [source/'protocol.json', source/'evaluation.json']},
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_differential_frame_phase.py',
                                              ROOT/'tools/ds23_conditional_pilot_components.py', ROOT/'tools/frequency_selective_pilot.py']})
    target = OUT/'protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('differential frame-phase protocol changed')
    if not target.exists(): write(target, protocol)
    rows = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(one, j) for j in selected]):
            r = future.result(); rows.append(r)
            print(r['group'], r['probe'], r['status'],
                  {k: round(v['continuity_score'], 3) for k, v in r.get('models', {}).items()}, r.get('error'), flush=True)
    complete = [r for r in rows if r['status'] == 'complete']
    summary = {name: dict(probes=len(complete), median_continuity_score=float(np.median([r['models'][name]['continuity_score'] for r in complete])),
        candidates=[dict(case=r['case'], group=r['group'], probe=r['probe']) for r in complete if r['models'][name]['candidate_for_independent_replication']])
        for name in ['first', 'second', 'differential']}
    write(OUT/'evaluation.json', dict(summary=summary, rows=rows, protocol_sha256=sha(target),
        only_RF_diagnostic_not_position_improvement=True, null_does_not_validate_transmitter_identity_or_orbit=True))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    for name in summary:
        values = [r['models'][name]['continuity_score'] for r in complete]
        axes[0].hist(values, bins=np.linspace(-1, 1, 21), histtype='step', label=name)
    axes[0].set(xlabel='Minimum training coherence / held-frame predictive cosine', ylabel='Probes', title='Independent transmitter frame resets retained')
    axes[0].axvline(.85, color='gray', ls=':'); axes[0].legend()
    for r in complete:
        axes[1].scatter(max(r['models']['first']['continuity_score'], r['models']['second']['continuity_score']),
                        r['models']['differential']['continuity_score'], s=14, alpha=.5)
    axes[1].set(xlabel='Better individual-signal continuity score', ylabel='Differential continuity score',
                title='Does subtracting simultaneous phases recover continuity?')
    axes[1].plot([-1, 1], [-1, 1], 'k:', lw=.8); axes[1].grid(alpha=.2)
    fig.suptitle('Saved-IQ differential carrier phase: training and held-out matched frames\nCFO/timing conditioned on earlier whole-probe fits; no phase correction applied')
    fig.savefig(OUT/'differential_frame_phase.png', dpi=160); plt.close(fig)
    print('SUMMARY', summary, flush=True)


if __name__ == '__main__': main()
