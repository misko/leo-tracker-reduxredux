"""DBG01 recovery diagnostics at the current two worst DS23 endpoints.

Rank scans by the published evaluation, then keep GPS out of inference. Search
unassociated curved tracks across the full causal catalogue and nine fixed
regional seeds, recalibrating the incumbent separately at each seed. Candidate
screens are hypotheses; only original paired gates can admit a final refit.
"""

import argparse
import csv
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from audit_ds23_algo01_coverage import retained_metrics
from dbg01_unassociated import ownership, remaining_indices
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_recovery_screen_geometry import prepare_screen_geometry, screen_frequency
from evaluate_ds23_phase_refreshed import extend_associations
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile
from probe_ds23_frequency_events import cached
from prototype_dsx01_continuous_position import latlon
from run_ds23_reentry_family_cavity_full import selected_with_recorded_reference
from run_algo01_ds23_sample import ROOT, read, sha, write

OUT = ROOT/'reports/2026_10_22_ds23_worst_association_bottleneck'
BENCHMARK = ROOT/'reports/2026_10_22_ds23_family_cavity_full_assessment/tables/positions.csv'
SEEDS = np.array([(east, north) for north in [-10., 0., 10.] for east in [-10., 0., 10.]])


def select_worst(rows, count=2):
    rows = [r for r in rows if r['policy'] == 'equal_assignment_priors' and r['arm'] == 'fitted_c']
    if len({r['case'] for r in rows}) != len(rows):
        raise ValueError('one benchmark row per available scan required')
    return sorted(rows, key=lambda r: (-float(r['policy_error_km']), r['case']))[:count]


def setup(case):
    d, arms = selected_with_recorded_reference(case)
    d['arms'] = arms
    roots = read(ROOT/'reports/2026_10_20_ds23_combined_recovery_full/protocol.json')['input_roots']
    d['observations_path'] = Path(roots[case])/case/'observations.json'
    d['observations'] = read(d['observations_path'])
    for element in d['scan'].elements.values():
        provenance = element['provenance']
        if max(provenance['element_epoch_utc_ns'], provenance['collected_utc_ns']) > d['scan'].receipt['cutoff_utc_ns']:
            raise ValueError('noncausal catalogue')
    return d


def build(d, arm, reference):
    p = make_event_problem(d['scan'], d['node'], d['keep'], arm, np.asarray(reference),
                           d['powers'], d['means'], d['model'], [])
    attach_event_predictive(p, d['entries'], d['powers'])
    return cached(p)


def inventory(d, arm):
    saved = d['arms'][arm]
    p = build(d, arm, saved['phase_reference'])
    x = np.asarray(saved['endpoint_east_north_km'])
    difference = p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo']
    if abs(difference) > 1e-5:
        raise ValueError('current published endpoint does not replay')
    metrics = retained_metrics(p, x)
    extension = extend_associations(p, x, metrics)
    lookup = {t['key']: t for t in d['scan'].tracks}
    rows = [dict(r, observation_ids=r.get('observation_ids', lookup[r['component']]['observation_ids']))
            for r in extension['tracks']]
    accepted = ownership(rows)
    all_ids = {o['observation_id'] for o in d['observations']}
    if len(all_ids) != len(d['observations']) or not accepted <= all_ids:
        raise ValueError('invalid physical GLRT ownership')
    graph = {o for t in d['scan'].tracks for o in t['observation_ids']}
    ranking = []
    for i, track in enumerate(d['scan'].tracks):
        indices = remaining_indices(track, accepted)
        if not len(indices):
            continue
        ranking.append(dict(track_index=i, component=track['key'], receiver=track['receiver'],
                            channel=track['channel'], points=len(indices), original_points=len(track['times']),
                            start_s=float(track['times'][indices].min()), end_s=float(track['times'][indices].max()),
                            span_s=float(np.ptp(track['times'][indices])), curved=i in d['scan'].curved,
                            pieces=len(track['pieces']), indices=indices))
    ranking.sort(key=lambda r: (-r['span_s'], -r['points'], r['component']))
    return dict(total_GLRT=len(all_ids), associated=len(accepted), percent=100*len(accepted)/len(all_ids),
                associated_tracks=len([r for r in rows if r['compatible']]),
                active_curved_points=int(d['keep'].sum()), predictive_points=sum(e['points'] for e in d['entries']),
                active_curved_families=sorted({r['candidate_norad'] for r, sl in zip(p.rows, p.slices, strict=True)
                                               if d['keep'][sl].any()}),
                unassociated_graph_points=len(graph-accepted), outside_graph_points=len(all_ids-graph),
                endpoint=x, boundary_axes=np.flatnonzero(np.isclose(abs(x), 12.5)),
                normalized_bound_replay_difference=difference, accepted_observation_ids=sorted(accepted),
                ranking=ranking, associations=extension)


def plot(d, inv, destination):
    channels = sorted({o['channel'] for o in d['observations']})
    fig, axes = plt.subplots(2, len(channels), figsize=(4*len(channels), 7), squeeze=False)
    owned = set(inv['accepted_observation_ids'])
    cmap = plt.get_cmap('tab20')
    for rx in [1, 2]:
        for col, channel in enumerate(channels):
            ax = axes[rx-1, col]
            rows = [o for o in d['observations'] if o['receiver'] == rx and o['channel'] == channel]
            missing = [o for o in rows if o['observation_id'] not in owned]
            ax.scatter([o['time_s'] for o in rows], [o['measured_cfo_hz']/1000 for o in rows], s=6, c='0.85')
            ax.scatter([o['time_s'] for o in missing], [o['measured_cfo_hz']/1000 for o in missing], s=9, c='crimson')
            for k, row in enumerate(inv['ranking']):
                if row['receiver'] != rx or row['channel'] != channel:
                    continue
                track = d['scan'].tracks[row['track_index']]
                ix = np.asarray(row['indices'])
                ax.plot(track['times'][ix], track['values'][ix]/1000, lw=1.2, color=cmap(k % 20), alpha=.85)
            ax.set_title(f'RX{rx} CH{channel}')
            ax.set_xlabel('Time in scan (s)')
            ax.set_ylabel('GLRT CFO (kHz)')
            ax.grid(alpha=.2)
    fig.suptitle(f"{d['scan'].case}: {inv['associated']}/{inv['total_GLRT']} associated ({inv['percent']:.2f}%)\n"
                 'Gray: all GLRT · red: unassociated GLRT · colored lines: remaining graph tracks')
    fig.tight_layout()
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def calibrated_at(d, position):
    reference = np.zeros(len(d['means']))
    for _ in range(5):
        p = build(d, 'c0', reference)
        phase = np.clip(p.state(position)['phases'][p.labels], -15, 15)
        change = float(np.max(abs(phase-reference)))
        reference = phase
    return p, p.state(position), change


def screen(d, inv):
    scan = d['scan']
    targets = [r for r in inv['ranking'] if r['curved'] and r['points'] >= 12][:3]
    if not targets:
        return dict(targets=[], reason='no remaining graph track with active curvature')
    seeds = [np.asarray(inv['endpoint'])]+list(SEEDS)
    calibration = [calibrated_at(d, x) for x in seeds]
    times = np.unique(np.concatenate([scan.tracks[r['track_index']]['times'][r['indices']] for r in targets]))
    stores = [[{} for _ in seeds] for _ in targets]
    corrected = []
    for row in targets:
        track = scan.tracks[row['track_index']]
        q = track['rf_hz']/11.5e9
        corrected.append([(track['values']-scan.hardware(track, state['beta'])
                           -q*scan.rx_basis[row['track_index']]@state['smooth'][track['receiver']-1])[row['indices']]
                          for _, state, _ in calibration])
    for phase in np.arange(-15., 15.001, 1.):
        geometry = prepare_screen_geometry(scan.sky, times, np.full(len(scan.norads), phase))
        for seed_index, x in enumerate(seeds):
            frequency, elevation, _ = screen_frequency(geometry, *latlon(x))
            for k, row in enumerate(targets):
                track = scan.tracks[row['track_index']]
                tt = track['times'][row['indices']]
                ix = np.searchsorted(times, tt)
                q = track['rf_hz']/11.5e9
                from leo.analysis.research.retained_track_likelihood import whitening
                terms = profile(corrected[k][seed_index], q*frequency[:, ix], *whitening(tt), bias_sigma=300.)
                visible = elevation[:, ix].min(axis=1) >= 0
                score = np.where(visible, terms['cost'], np.inf)
                for j in np.argsort(score)[:6]:
                    if not np.isfinite(score[j]):
                        continue
                    previous = stores[k][seed_index].get(int(j))
                    if previous is None or score[j] < previous['cost']:
                        noise = batch_noise_screen(terms['innovations'][[j]], tt)
                        stores[k][seed_index][int(j)] = dict(candidate_index=int(j), norad=int(scan.norads[j]),
                            phase_s=float(phase), cost=float(score[j]), rms_hz=float(terms['rms'][j]),
                            bias_hz=float(terms['bias'][j]), alias=int(terms['alias'][j]),
                            minimum_elevation_deg=float(elevation[j, ix].min()),
                            noise={name: value[0] for name, value in noise.items()},
                            passing=bool(terms['rms'][j] <= 450 and abs(terms['bias'][j]) <= 3000
                                         and noise['noise_screen_pass'][0]))
    rows = []
    for row, by_seed in zip(targets, stores, strict=True):
        rows.append(dict(target=row, seeds=[dict(position=x, calibration_phase_change_s=calibration[k][2],
                            candidates=sorted(values.values(), key=lambda v: v['cost'])[:6])
                            for k, (x, values) in enumerate(zip(seeds, by_seed, strict=True))]))
    return dict(targets=rows, catalogue_size=len(scan.norads), phase_grid_s=np.arange(-15., 15.001, 1.),
                same_complete_causal_catalogue_at_every_seed=True,
                coarse_hypotheses_need_fine_phase_and_joint_paired_validation=True,
                no_GPS_or_future_TLE_used=True)


def one(case, stage):
    out = OUT/case
    out.mkdir(exist_ok=True)
    path = out/(stage+'.json')
    if path.exists():
        raise FileExistsError('preserve completed debug evidence')
    began = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('600 s diagnostic cap')))
    signal.alarm(600)
    try:
        d = setup(case)
        if stage == 'inventory':
            arms = {a: inventory(d, a) for a in ['c0', 'fitted_c']}
            plot(d, arms['fitted_c'], out/'unassociated_GLRT.png')
            result = dict(case=case, status='complete', arms=arms, observations_sha256=sha(d['observations_path']))
        else:
            inv = read(out/'inventory.json')['arms']['c0']
            result = dict(case=case, status='complete', screen=screen(d, inv))
    except Exception as exc:
        import traceback
        result = dict(case=case, status='failed', error=repr(exc), traceback=traceback.format_exc())
    finally:
        signal.alarm(0)
    result.update(seconds=time.monotonic()-began, protocol_sha256=sha(OUT/'protocol.json'))
    write(path, result)
    print(case, stage, result['status'], round(result['seconds'], 2), result.get('error', ''), flush=True)
    return dict(case=case, status=result['status'], path=str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['inventory', 'screen'], required=True)
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    worst = select_worst(list(csv.DictReader(BENCHMARK.open())))
    protocol = dict(cases=[r['case'] for r in worst], benchmark_sha256=sha(BENCHMARK),
                    debug_priority_only_uses_reported_position_error=True,
                    inference_no_GPS_or_postscan_TLE=True,
                    goal='Increase supported GLRT associations and determine bottlenecks to position information',
                    conditional_on_current_published_curved_and_predictive_context=True,
                    regional_center=[37.906, -122.545], regional_width_km=25.,
                    regional_seeds=SEEDS.tolist(), saved_RF_endpoint_also_included=True,
                    target_selection='three longest remaining actively curved graph tracks, at least12 unassociated points',
                    prior_and_residual_gates_unchanged=True, both_c_arms_in_inventory=True,
                    phase_screen='-15..15 seconds, 1 second coarse; proposals only',
                    case_seconds=600, workers=2, source_sha256=sha(Path(__file__)))
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('preserve frozen debug protocol')
    if not path.exists():
        write(path, protocol)
    with ProcessPoolExecutor(max_workers=2) as pool:
        results = [f.result() for f in as_completed([pool.submit(one, case, args.stage) for case in protocol['cases']])]
    write(OUT/(args.stage+'_execution.json'), dict(rows=results, all_terminal=True,
                                                all_passed=all(r['status'] == 'complete' for r in results)))


if __name__ == '__main__':
    main()
