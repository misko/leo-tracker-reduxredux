"""Descriptive audit of frozen published results; no model fitting or tuning."""

import csv
import datetime as dt
import json
from collections import Counter
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
EARTH_M = 6371008.8


def error_vector(latitude, longitude, reference_latitude, reference_longitude):
    """Azimuthal-equidistant east/north error; norm equals great-circle error."""
    lat, lon, ref_lat, ref_lon = np.radians(
        [latitude, longitude, reference_latitude, reference_longitude]
    )
    dlon = lon - ref_lon
    h = np.sin((lat - ref_lat) / 2)**2 + np.cos(lat) * np.cos(ref_lat) * np.sin(dlon / 2)**2
    distance = 2 * EARTH_M * np.arcsin(np.sqrt(np.clip(h, 0, 1)))
    bearing = np.arctan2(np.sin(dlon) * np.cos(lat),
                        np.cos(ref_lat) * np.sin(lat) - np.sin(ref_lat) * np.cos(lat) * np.cos(dlon))
    return np.array([distance * np.sin(bearing), distance * np.cos(bearing)])


def stats(values):
    a = np.asarray(values, float)
    if not len(a):
        return {"n": 0}
    return dict(n=len(a), median=float(np.median(a)), p90=float(np.percentile(a, 90)),
                minimum=float(a.min()), maximum=float(a.max()), mean=float(a.mean()))


def coordinates(east_km, north_km, latitude_deg=38.5816, longitude_deg=-121.4944):
    angular = np.hypot(east_km, north_km) / (EARTH_M / 1000)
    bearing = np.arctan2(east_km, north_km)
    lat, lon = np.radians([latitude_deg, longitude_deg])
    out_lat = np.arcsin(np.sin(lat)*np.cos(angular) + np.cos(lat)*np.sin(angular)*np.cos(bearing))
    out_lon = lon + np.arctan2(np.sin(bearing)*np.sin(angular)*np.cos(lat),
                             np.cos(angular)-np.sin(lat)*np.sin(out_lat))
    return np.degrees(out_lat), (np.degrees(out_lon) + 180) % 360 - 180


def alternatives(captures):
    """Diagnostic repricing of SAVED modes; T1AT chooses basin without truth."""
    output = []
    for c in captures:
        d = c.get('regional_document')
        if not d:
            continue
        t = d['methods'][0]['arms'][0]['selected']
        v = d['methods'][1]['arms'][0]['selected']
        candidates = [r for r in d['diagnostics']['final_starts']
                      if r['method'] == 'V16' and r['arm'] == 'fitted-c'
                      and r['basin'] == t['source_basin'] and r['fit']]
        best = min(candidates, key=lambda r:r['fit']['objective']+r['calibration_penalty'])
        fit = best['fit']
        lat, lon = coordinates(*fit['vector'][:2])
        error = np.linalg.norm(error_vector(lat,lon,d['reference_latitude_deg'],d['reference_longitude_deg']))
        output.append(dict(session_id=c['session_id'], capture_start_utc=c['capture_start_utc'],
                           T1AT_error_m=t['horizontal_error_m'], V16_error_m=v['horizontal_error_m'],
                           V16_in_T1AT_basin_error_m=float(error), converged=fit['converged'],
                           boundary=fit['boundary'],
                           objective_penalty=fit['objective']+best['calibration_penalty']-v['selection_score']))
    (HERE / 'basin_diagnostic.json').write_text(json.dumps(output, indent=2))
    return stats([r['V16_in_T1AT_basin_error_m'] for r in output])


def position_stats(rows):
    xy = np.array([[r['error_east_m'], r['error_north_m']] for r in rows])
    errors = np.linalg.norm(xy, axis=1)
    cumulative = np.cumsum(xy, axis=0) / np.arange(1, len(xy) + 1)[:, None]
    result = {
        'error_m': stats(errors),
        'posterior_rms_hz': stats([r['posterior_rms_hz'] for r in rows]),
        'converged': sum(r['converged'] for r in rows),
        'boundary': sum(r['boundary'] for r in rows),
        'over_10km': int(np.sum(errors > 10000)),
        'over_50km': int(np.sum(errors > 50000)),
        'under_1km': int(np.sum(errors < 1000)),
        'mean_error_vector_m': xy.mean(axis=0).tolist(),
        'static_equal_weight_mean_error_m': float(np.linalg.norm(xy.mean(axis=0))),
        'cumulative_mean_error_after_four_updates_m': stats(np.linalg.norm(cumulative[3:], axis=1)),
        'lag_one_error_correlation': {
            axis: float(np.corrcoef(xy[:-1, i], xy[1:, i])[0, 1])
            for i, axis in enumerate(['east', 'north'])
        } if len(xy) > 3 else None,
        'coefficient_hz_per_ghz': stats([r['coefficient_hz_per_ghz'] for r in rows]),
    }
    return result


def main():
    snapshot = json.loads((HERE / 'snapshot.json').read_text())
    captures = snapshot['captures']
    rows = []
    for capture in captures:
        doc = capture.get('regional_document')
        if not doc:
            continue
        for method in doc['methods']:
            for arm in method['arms']:
                selected = arm['selected']
                if not selected:
                    continue
                row = {k: v for k, v in selected.items() if k != 'satellites'}
                xy = error_vector(selected['latitude_deg'], selected['longitude_deg'],
                                  doc['reference_latitude_deg'], doc['reference_longitude_deg'])
                assert np.isclose(np.linalg.norm(xy), selected['horizontal_error_m'], atol=1e-6)
                row.update(session_id=capture['session_id'], method=method['name'], arm=arm['name'],
                           capture_start_utc=capture['capture_start_utc'],
                           capture_start_s=capture['capture_start_s'],
                           available_s=capture['regional_published_s'],
                           rate_hz=capture['timing']['sample_rate_hz'], windows=doc['windows'],
                           satellite_count=len(selected['satellites']),
                           error_east_m=float(xy[0]), error_north_m=float(xy[1]),
                           coverage=selected['associated_windows']/doc['windows'],
                           signal_fraction=selected['signal_windows']/doc['windows'],
                           tle_age_hours=(capture['capture_start_s']-doc['diagnostics']['snapshot_collected_utc_ns']/1e9)/3600,
                           deferred_cells=method['deferred_cells'],
                           search_stop_reason=method['search_stop_reason'])
                rows.append(row)
    with (HERE / 'per_scan.csv').open('w') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    grouped = {}
    for method in ['T1AT', 'V16']:
        for arm in ['fitted-c', 'zero-c']:
            group = [r for r in rows if r['method'] == method and r['arm'] == arm]
            grouped[f'{method}/{arm}'] = position_stats(group)
            accepted = [r for r in group if r['converged'] and not r['boundary']]
            grouped[f'{method}/{arm}']['converged_interior'] = position_stats(accepted) if accepted else None
            grouped[f'{method}/{arm}']['coverage'] = stats([r['coverage'] for r in group])
            grouped[f'{method}/{arm}']['signal_fraction'] = stats([r['signal_fraction'] for r in group])
            grouped[f'{method}/{arm}']['by_rate'] = {
                str(rate): stats([r['horizontal_error_m'] for r in group if r['rate_hz'] == rate])
                for rate in sorted({r['rate_hz'] for r in group})
            }
    paired = {}
    lookup = {(r['session_id'], r['method'], r['arm']): r for r in rows}
    sessions = sorted({r['session_id'] for r in rows})
    for method in ['T1AT', 'V16']:
        pairs = [(lookup[s, method, 'fitted-c'], lookup[s, method, 'zero-c']) for s in sessions]
        paired[method + '/fitted_minus_zero'] = {
            'position_delta_m': stats([a['horizontal_error_m'] - b['horizontal_error_m'] for a,b in pairs]),
            'rms_delta_hz': stats([a['posterior_rms_hz'] - b['posterior_rms_hz'] for a,b in pairs]),
            'position_improved': sum(a['horizontal_error_m'] < b['horizontal_error_m'] for a,b in pairs),
            'same_selected_basin': sum(a['source_basin'] == b['source_basin'] for a,b in pairs),
        }
    for arm in ['fitted-c', 'zero-c']:
        pairs = [(lookup[s, 'V16', arm], lookup[s, 'T1AT', arm]) for s in sessions]
        paired[arm + '/V16_minus_T1AT'] = {
            'position_delta_m': stats([a['horizontal_error_m'] - b['horizontal_error_m'] for a,b in pairs]),
            'rms_delta_hz': stats([a['posterior_rms_hz'] - b['posterior_rms_hz'] for a,b in pairs]),
            'V16_position_improved': sum(a['horizontal_error_m'] < b['horizontal_error_m'] for a,b in pairs),
            'same_selected_basin': sum(a['source_basin'] == b['source_basin'] for a,b in pairs),
        }
    complete = [c for c in captures if c['regional_status'] == 'complete']
    summary = {
        'snapshot_utc': snapshot['snapshot_utc'], 'capture_window_utc': snapshot['capture_window_utc'],
        'capture_count': len(captures), 'complete_regional_count': len(complete),
        'pending_sessions': [c['session_id'] for c in captures if c['regional_status'] != 'complete'],
        'capture_rate_counts': dict(Counter(c['timing']['sample_rate_hz'] for c in captures)),
        'capture_terminal_counts': dict(Counter(c['terminal']['state'] for c in captures)),
        'transport_missing_samples': sum(c['capture_accounting']['transport_missing_sample_count'] for c in captures),
        'valid_capture_duty_fraction': stats([c['capture_accounting']['valid_duty_ppm']/1e6 for c in captures]),
        'timing_bracket_width_ms': stats([c['timing']['first_sample_bracket_width_ns']/1e6 for c in captures]),
        'unqualified_timestamps': sum(not c['timing']['qualified'] for c in captures),
        'start_interval_minutes': stats(np.diff([c['capture_start_s'] for c in captures])/60),
        'published_latency_from_capture_end_minutes': stats([
            (c['regional_published_s']-c['timing']['terminal_realtime_ns']/1e9)/60 for c in complete]),
        'measurement_age_at_publication_minutes': stats([
            (c['regional_published_s']-c['capture_start_s']-150)/60 for c in complete]),
        'tle_age_hours': stats([r['tle_age_hours'] for r in rows[::4]]),
        'known_position_used_for_inference': sorted({c['regional_document']['known_position_used_for_inference'] for c in complete}),
        'configuration_digests': dict(Counter(c['regional_document']['configuration_sha256'] for c in complete)),
        'grouped': grouped, 'paired': paired,
        'V16_fitted_saved_solution_in_T1AT_winning_basin_error_m': alternatives(captures),
        'limitations': [
            'Static equal-weight averaging is an arithmetic diagnostic in roof-centered equidistant coordinates, not a calibrated Kalman-filter validation.',
            'Capture-order cumulative means are retrospective; publication latency and out-of-order availability are reported separately.',
            'Published estimates contain no position covariance or cross-scan covariance.',
            'RF comparison uses identical observations/candidate banks/budgets per basin but independently selected winning basins; upstream calibration includes fitted c in both arms.',
            'All error endpoints use the configured roof reference with unquantified survey uncertainty.',
        ],
    }
    (HERE / 'summary.json').write_text(json.dumps(summary, indent=2))
    plot(rows, captures)
    print(json.dumps(summary, indent=2))


def plot(rows, captures):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    colors = {'T1AT': '#1875b8', 'V16': '#dc6634'}
    for arm, ax in zip(['fitted-c', 'zero-c'], axes[0]):
        for method in ['T1AT', 'V16']:
            group = [r for r in rows if r['method'] == method and r['arm'] == arm]
            times = [dt.datetime.fromtimestamp(r['capture_start_s'], dt.UTC) for r in group]
            ax.plot(times, [r['horizontal_error_m']/1000 for r in group], 'o-', label=method, color=colors[method])
            bad = [i for i,r in enumerate(group) if not r['converged'] or r['boundary']]
            ax.scatter([times[i] for i in bad], [group[i]['horizontal_error_m']/1000 for i in bad],
                       marker='x', s=130, color='black', zorder=5)
        ax.set(title=f'{arm}: independently selected position', ylabel='Position error (km, log scale)', yscale='log')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=dt.UTC))
        ax.set_xlabel('Capture start (UTC, 6 October)');ax.legend();ax.grid(alpha=.2)
    ax = axes[1,0]
    for method in ['T1AT', 'V16']:
        for arm, style in [('fitted-c', '-'), ('zero-c', '--')]:
            group = [r for r in rows if r['method'] == method and r['arm'] == arm]
            xy = np.array([[r['error_east_m'],r['error_north_m']] for r in group])
            errors = np.linalg.norm(np.cumsum(xy,axis=0)/np.arange(1,len(xy)+1)[:,None],axis=1)/1000
            ax.plot(np.arange(1,len(xy)+1),errors,style,label=f'{method} {arm}',color=colors[method])
    ax.set(title='Static equal-weight cumulative mean (diagnostic)', xlabel='Completed scans in capture order',
           ylabel='Mean-position error (km, log scale)', yscale='log');ax.legend();ax.grid(alpha=.2)
    ax = axes[1,1]
    for c in captures:
        t = dt.datetime.fromtimestamp(c['capture_start_s'],dt.UTC)
        if 'regional_published_s' in c:
            delay = (c['regional_published_s']-c['timing']['terminal_realtime_ns']/1e9)/60
            ax.scatter(t,delay,c=('#1875b8' if c['timing']['sample_rate_hz']==2500000 else '#dc6634'))
        else:
            ax.scatter(t,0,marker='x',color='black')
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([],[],color='#1875b8',marker='o',linestyle='',label='2.5 MS/s'),
                       Line2D([],[],color='#dc6634',marker='o',linestyle='',label='10 MS/s')])
    ax.set(title='Regional-result delay after capture ends',ylabel='Minutes (pending shown at zero)',xlabel='Capture start (UTC)')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M',tz=dt.UTC));ax.grid(alpha=.2)
    fig.suptitle('Six-hour live capture review: 6 Oct 18:30–7 Oct 00:30 UTC\nTop-row black crosses: unconverged or on a search boundary',fontsize=14)
    fig.savefig(HERE/'review.png',dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    main()
