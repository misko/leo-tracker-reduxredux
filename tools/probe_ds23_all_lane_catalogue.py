"""Full causal catalogue proposals for each independently selected RF lane."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import numpy as np

from ds23_causal_phase_location import adjust_means
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_differential_catalogue import pair_screen
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_all_lane_components import OUT as RF_REPORT, BULK
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency

OUT = BULK/'catalogue'


def run(selected):
    case, group = selected['case'], selected['group']
    path = OUT/(group+'.json')
    if path.exists():
        return read(path)
    def timeout(*_):
        raise TimeoutError('180 second all-lane catalogue budget exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(180)
    try:
        evaluation = read(BULK/'evaluation.json')
        ids = {j['probe'] for j in read(BULK/'protocol.json')['jobs'] if j['group'] == group}
        rows = sorted([r for r in evaluation['rows'] if r['case'] == case and r['probe'] in ids and
                       r['status'] == 'complete' and r['two_components_qualified']], key=lambda r: r['time_s'])
        stat = next(s for s in evaluation['summary'] if s['group'] == group).get('RF_qualified_statistics')
        if stat is None:
            return dict(case=case, group=group, status='no_offer', reason='fewer_than16_supported_components')
        scan, node, mask, powers, ordinary, hyper, entries, signed, _ = context_signed(case)
        labels = list(range(len(scan.norads)))
        widths, receipts = phase_widths(scan, labels)
        means = forecast_phase_mean(receipts, hyper['shrinkage'])
        if signed['accepted']:
            means = adjust_means(means, receipts, hyper, signed['selection'])
        widths, means = np.asarray(widths)*hyper['multiplier'], np.asarray(means)
        t = np.array([r['time_s'] for r in rows])
        values = np.array([r['refined_second_value']-r['refined_first_value'] for r in rows])
        times, flat_labels = np.tile(t, len(labels)), np.repeat(np.arange(len(labels)), len(t))
        results = {}
        for name, position in [('regional_centre', np.zeros(2)),
                               ('current_scan_RF_mode', np.asarray(signed['policy_arms']['c0']['endpoint_east_north_km']))]:
            def geometry(phases):
                f, e = paired_phase_frequency(scan.sky, times, flat_labels, phases, *latlon(position))
                return f.reshape(len(labels), -1)*selected['lane'][2]/11.5e9, e.reshape(len(labels), -1)
            f, e = geometry(means); plus, _ = geometry(means+.01); minus, _ = geometry(means-.01)
            derivative = (plus-minus)/.02
            visible = np.flatnonzero(e.min(axis=1) >= 0)
            screen = pair_screen(values, f[visible], derivative[visible], widths[visible], stat['difference_sigma_hz'])
            first_phase = means[visible[screen['first']]]+widths[visible[screen['first']]]*screen['coefficient'][:, 0]
            second_phase = means[visible[screen['second']]]+widths[visible[screen['second']]]*screen['coefficient'][:, 1]
            screen['cost'][(abs(first_phase) > 15) | (abs(second_phase) > 15)] = np.inf
            candidates = []
            for k in np.argsort(screen['cost'])[:20]:
                if not np.isfinite(screen['cost'][k]):
                    continue
                first, second = int(visible[screen['first'][k]]), int(visible[screen['second'][k]])
                candidates.append(dict(first_index=first, second_index=second, first_norad=int(scan.norads[first]),
                    second_norad=int(scan.norads[second]), score=float(screen['cost'][k]), RMS_hz=float(screen['residual_RMS_hz'][k]),
                    phase_first_s=float(first_phase[k]), phase_second_s=float(second_phase[k]),
                    difference_alias=int(screen['alias'][k]), relative_bias_hz=float(1000*screen['coefficient'][k, 2])))
            results[name] = dict(candidates=candidates, visible_candidates=len(visible), ordered_distinct_pairs=len(visible)*(len(visible)-1))
        record = dict(case=case, group=group, status='complete', results=results,
                      RF_evaluation_sha256=sha(BULK/'evaluation.json'), all_visible_causal_candidates_considered=True,
                      no_satellite_whitelist=True, no_GPS_used=True, nomination_not_verified_identity=True,
                      phase_tangent_proposal_omits_physical_modes=True)
        print(group, [(r['first_norad'], r['second_norad']) for r in results['current_scan_RF_mode']['candidates'][:2]], flush=True)
    except Exception as exc:
        record = dict(case=case, group=group, status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    write(path, record)
    return record


def main():
    OUT.mkdir(exist_ok=True)
    rf = read(BULK/'protocol.json')
    protocol = dict(groups=[s['group'] for s in rf['selected']], RF_evaluation_sha256=sha(BULK/'evaluation.json'),
                    workers=6, per_group_seconds=180, full_causal_catalogue=True, no_GPS_used=True,
                    source_sha256=sha(Path(__file__)))
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('all-lane catalogue protocol changed')
    if not path.exists():
        write(path, protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, selected) for selected in rf['selected']])]
    write(OUT/'execution.json', dict(rows=rows, all_terminal=True))


if __name__ == '__main__':
    main()
