"""Read-only audit of saved top-response memberships, residual structure and sky geometry.

No membership, calibration, timing, or orbit is refitted here. OLS line/quadratic
fits are diagnostic fits to residuals only, not corrections to the orbit model.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BULK = Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    def convert(item):
        if isinstance(item, np.ndarray):
            return item.tolist()
        if isinstance(item, np.generic):
            return item.item()
        raise TypeError(type(item))
    Path(path).write_text(json.dumps(value, indent=2, default=convert, allow_nan=False))


def polynomial_audit(times, residual, channel, channel_intercepts=False):
    """Nested unweighted OLS, RMS=sqrt(SSE/n); centered/scaled time for stability."""
    times, residual, channel = map(np.asarray, (times, residual, channel))
    if not len(times) or not np.all(np.isfinite(times)) or not np.all(np.isfinite(residual)):
        raise ValueError('Finite, nonempty observations required')
    center = float(np.mean(times))
    scale = max(float(np.max(np.abs(times - center))), 1.)
    u = (times - center) / scale
    base = np.column_stack([channel == ch for ch in np.unique(channel)]) if channel_intercepts else np.ones((len(times), 1))
    out = dict(n=len(times), time_center_s=center, raw_rms_hz=float(np.sqrt(np.mean(residual**2))))
    rms = []
    for degree, name in [(1, 'linear'), (2, 'quadratic')]:
        design = np.column_stack([base] + [u**power for power in range(1, degree+1)])
        coefficients, _, rank, _ = np.linalg.lstsq(design, residual, rcond=None)
        error = residual - design @ coefficients
        result = float(np.sqrt(np.mean(error**2)))
        rms.append(result)
        out.update({f'{name}_rms_hz': result, f'{name}_rank': int(rank),
                    f'{name}_dof': len(times)-int(rank), f'{name}_full_rank': rank == design.shape[1],
                    f'{name}_slope_hz_s': float(coefficients[base.shape[1]] / scale)})
        if degree == 2:
            out['quadratic_coefficient_hz_s2'] = float(coefficients[-1] / scale**2)
    assert rms[1] <= rms[0] + 1e-8
    valid = out['linear_full_rank'] and out['quadratic_full_rank'] and out['quadratic_dof'] >= 2 and rms[1] > 1e-9
    out['ratio'] = rms[0]/rms[1] if valid else None
    out['ratio_over_1_1'] = bool(out['ratio'] > 1.1) if valid else None
    out['diagnostic_valid'] = valid
    return out


def observer_enu(latitude, longitude):
    """WGS84 sea-level observer, ECEF km, geodetic ENU rotation."""
    lat, lon = np.deg2rad([latitude, longitude])
    eccentricity = (1/298.257223563)*(2-1/298.257223563)
    radius = 6378.137/np.sqrt(1-eccentricity*np.sin(lat)**2)
    observer = np.array([radius*np.cos(lat)*np.cos(lon), radius*np.cos(lat)*np.sin(lon), radius*(1-eccentricity)*np.sin(lat)])
    rotation = np.array([[-np.sin(lon), np.cos(lon), 0],
                         [-np.sin(lat)*np.cos(lon), -np.sin(lat)*np.sin(lon), np.cos(lat)],
                         [np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)]])
    return observer, rotation


def sky_geometry(position, latitude, longitude, receiver, axes):
    observer, rotation = observer_enu(latitude, longitude)
    relative = np.asarray(position) - observer
    unit = (relative / np.linalg.norm(relative, axis=1)[:, None]) @ rotation.T
    axis = np.asarray([axes[f'RX{int(rx)}'] for rx in receiver])
    other = np.asarray([axes[f'RX{1-int(rx)}'] for rx in receiver])
    own_angle = np.degrees(np.arccos(np.clip(np.sum(unit*axis, axis=1), -1, 1)))
    other_angle = np.degrees(np.arccos(np.clip(np.sum(unit*other, axis=1), -1, 1)))
    return dict(azimuth_deg=np.degrees(np.arctan2(unit[:, 0], unit[:, 1])) % 360,
                elevation_deg=np.degrees(np.arcsin(np.clip(unit[:, 2], -1, 1))),
                east_unit=unit[:, 0], north_unit=unit[:, 1],
                own_off_axis_deg=own_angle, other_off_axis_deg=other_angle,
                own_axis_advantage_deg=other_angle-own_angle)


def interpolate_positions(nodes, position, times):
    nodes, times = np.asarray(nodes), np.asarray(times)
    if np.any(times < nodes[0]) or np.any(times >= nodes[-1]):
        raise ValueError('Orbit extrapolation forbidden')
    lower = np.searchsorted(nodes, times, side='right')-1
    fraction = (times-nodes[lower])/(nodes[lower+1]-nodes[lower])
    return position[lower]*(1-fraction[:, None]) + position[lower+1]*fraction[:, None]


def load(scan):
    sys.path.insert(0, str(BULK))
    import replay
    sys.path[:0] = [str(REPO/'reports'/name) for name in (
        '2026_10_02_ds13_timing_em', '2026_10_02_multiscan_localization',
        '2026_10_02_localization_benchmark', '2026_10_03_ds13_multitarget')]
    import greedy_pool_two_scans as greedy
    greedy.SCAN = scan
    if scan == 'A':
        from top_one_scan_A import TopOneCalibration
        cal = TopOneCalibration()
        folder = BULK/'full-scan-A-refinement/top-one'
    else:
        from position_top_2km_inputs import calibration
        cal = calibration()()
        folder = BULK/'position-top-2km/B-top'
    records = {arm: json.loads((folder/f'{arm}.json').read_text()) for arm in ('fitted-c', 'zero-c')}
    return cal, folder, records


def write_csv(path, rows):
    with Path(path).open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def audit_scan(scan, evidence):
    cal, folder, saved = load(scan)
    d = cal.d
    lookup = {int(row): i for i, row in enumerate(d.original_rows)}
    primary = saved['fitted-c']['final']
    assignments = sorted(primary['assignments'], key=lambda row: row['row_index'])
    rows = np.array([lookup[row['row_index']] for row in assignments])
    sat = np.array([row['catalog_number'] for row in assignments])
    selected = {arm: {row['catalog_number']: row for row in result['final']['selected']} for arm, result in saved.items()}
    assert set(selected['fitted-c']) == set(selected['zero-c']) == set(sat)
    assert len(rows) == len(np.unique(rows)) == {'A':3644, 'B':3460}[scan]
    residuals = {arm: np.zeros(len(rows)) for arm in saved}
    geometry = {name: np.zeros(len(rows)) for name in ('azimuth_deg', 'elevation_deg', 'east_unit', 'north_unit', 'own_off_axis_deg', 'other_off_axis_deg', 'own_axis_advantage_deg')}
    unshifted = {name: np.zeros(len(rows)) for name in geometry}
    timing = np.zeros(len(rows))
    latitude, longitude = evidence['operator_roof_lat_lon']
    axes = evidence['nominal_axes_enu']
    for number in sorted(set(sat)):
        mask = sat == number
        local_rows = rows[mask]
        index = int(np.flatnonzero(d.numbers == number)[0])
        for arm in saved:
            shift = selected[arm][int(number)]['offset_s']
            errors, visible, _ = cal.residual(arm, index, shift)
            residuals[arm][mask] = errors[local_rows]
            if arm == 'fitted-c':
                assert np.all(visible[local_rows])
                expected = [row['residual_hz'] for row in assignments if row['catalog_number'] == number]
                np.testing.assert_allclose(errors[local_rows], expected, atol=1e-6, rtol=0)
        shift = selected['fitted-c'][int(number)]['offset_s']
        timing[mask] = shift
        for offset, target in [(shift, geometry), (0., unshifted)]:
            position = interpolate_positions(d.nodes, d.position[index], d.times[local_rows]+offset)
            current = sky_geometry(position, latitude, longitude, d.receiver[local_rows], axes)
            for key, values in current.items():
                target[key][mask] = values
    np.testing.assert_allclose(residuals['fitted-c'], [r['residual_hz'] for r in assignments], atol=1e-6, rtol=0)
    data = dict(row_id=d.original_rows[rows], satellite=sat, rx=d.receiver[rows], channel=d.channel[rows],
                time_s=d.times[rows], rf_hz=d.rf[rows], measured_hz=d.measured[rows], group=d.group[rows],
                fitted_c_residual_hz=residuals['fitted-c'], zero_c_residual_hz=residuals['zero-c'], absolute_timing_s=timing,
                **geometry, **{f'unshifted_{k}': v for k,v in unshifted.items()})
    np.savez_compressed(HERE/f'{scan}-assigned-observations.npz', **data)
    metrics, lanes, satellites, pointing = [], [], [], []
    for number in sorted(set(sat)):
        satellite_mask = sat == number
        for rx in sorted(set(d.receiver[rows][satellite_mask])):
            mask = satellite_mask & (data['rx'] == rx)
            t = data['time_s'][mask]
            unique_time = np.unique(t)
            common = dict(scan=scan, satellite=int(number), rx=int(rx), n=int(sum(mask)),
                          start_s=float(min(t)), end_s=float(max(t)), span_s=float(np.ptp(t)),
                          max_gap_s=float(np.max(np.diff(unique_time))) if len(unique_time)>1 else 0.,
                          channels=','.join(str(int(c)) for c in sorted(set(data['channel'][mask]))))
            for arm in saved:
                metric = dict(**common, arm=arm)
                for controlled, prefix in [(False, 'pooled'), (True, 'channel_controlled')]:
                    result = polynomial_audit(t, residuals[arm][mask], data['channel'][mask], controlled)
                    metric.update({f'{prefix}_{k}': v for k, v in result.items() if k != 'n'})
                metrics.append(metric)
                for ch in sorted(set(data['channel'][mask])):
                    lane = mask & (data['channel'] == ch)
                    result = polynomial_audit(data['time_s'][lane], residuals[arm][lane], data['channel'][lane])
                    lanes.append(dict(scan=scan, satellite=int(number), rx=int(rx), channel=int(ch), arm=arm,
                                      start_s=float(min(data['time_s'][lane])), end_s=float(max(data['time_s'][lane])),
                                      span_s=float(np.ptp(data['time_s'][lane])), **result))
            expected_east_sign = -1 if rx == 0 else 1
            wrong = geometry['east_unit'][mask]*expected_east_sign < 0
            adv = geometry['own_axis_advantage_deg'][mask]
            unchanged = unshifted['own_axis_advantage_deg'][mask]
            record = dict(**common, absolute_timing_s=float(timing[mask][0]),
                          wrong_hemisphere_n=int(sum(wrong)), wrong_hemisphere_pct=float(100*np.mean(wrong)),
                          other_axis_closer_n=int(sum(adv < 0)), other_axis_closer_pct=float(100*np.mean(adv < 0)),
                          median_own_axis_advantage_deg=float(np.median(adv)),
                          minimum_advantage_deg=float(min(adv)), maximum_advantage_deg=float(max(adv)),
                          p05_advantage_deg=float(np.quantile(adv,.05)), p95_advantage_deg=float(np.quantile(adv,.95)),
                          median_own_off_axis_deg=float(np.median(geometry['own_off_axis_deg'][mask])),
                          minimum_own_off_axis_deg=float(min(geometry['own_off_axis_deg'][mask])),
                          maximum_own_off_axis_deg=float(max(geometry['own_off_axis_deg'][mask])),
                          min_elevation_deg=float(min(geometry['elevation_deg'][mask])),
                          max_elevation_deg=float(max(geometry['elevation_deg'][mask])),
                          min_east_unit=float(min(geometry['east_unit'][mask])), max_east_unit=float(max(geometry['east_unit'][mask])),
                          unshifted_other_axis_closer_pct=float(100*np.mean(unchanged < 0)),
                          timing_sign_changes_n=int(sum((adv < 0) != (unchanged < 0))))
            pointing.append(record)
        for arm in saved:
            result = polynomial_audit(data['time_s'][satellite_mask], residuals[arm][satellite_mask],
                                      10*data['rx'][satellite_mask]+data['channel'][satellite_mask], True)
            satellites.append(dict(scan=scan, satellite=int(number), arm=arm,
                                   span_s=float(np.ptp(data['time_s'][satellite_mask])), **result))
    write_csv(HERE/f'{scan}-track-residual-metrics.csv', metrics)
    write_csv(HERE/f'{scan}-channel-residual-metrics.csv', lanes)
    write_csv(HERE/f'{scan}-satellite-residual-metrics.csv', satellites)
    write_csv(HERE/f'{scan}-pointing-metrics.csv', pointing)
    primary_metrics = [r for r in metrics if r['arm']=='fitted-c']
    result = dict(scan=scan, top_windows=len(d.times), assigned=len(rows), satellites=len(set(sat)),
                  receiver_tracks=len(primary_metrics), primary_membership='fitted-c greedy + replacement final',
                  pooled_ratio_over_1_1=sum(r['pooled_ratio_over_1_1'] is True for r in primary_metrics),
                  channel_controlled_ratio_over_1_1=sum(r['channel_controlled_ratio_over_1_1'] is True for r in primary_metrics),
                  wrong_hemisphere_observations=sum(r['wrong_hemisphere_n'] for r in pointing),
                  wrong_hemisphere_receiver_tracks=sum(r['wrong_hemisphere_n']>0 for r in pointing),
                  entirely_wrong_hemisphere_tracks=sum(r['wrong_hemisphere_pct']==100 for r in pointing),
                  timing_sign_changes=sum(r['timing_sign_changes_n'] for r in pointing),
                  sources={str(p):digest(p) for p in [folder/'fitted-c.json',folder/'zero-c.json',folder/'candidate-pool.json']},
                  calibration_sources=cal.sources,
                  native_hz=True, all_tracks=metrics, all_pointing=pointing)
    print(scan, {k:v for k,v in result.items() if k not in ('sources','calibration_sources','all_tracks','all_pointing')}, flush=True)
    return result


def plots(results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    max_rows = max(r['receiver_tracks'] for r in results)
    height = max(12, max_rows*.29)
    fig, axes = plt.subplots(1,2,figsize=(17,height),sharex=True)
    for ax, result in zip(axes, results):
        tracks = sorted([r for r in result['all_tracks'] if r['arm']=='fitted-c'], key=lambda r:(-r['span_s'],r['satellite'],r['rx']))
        for y, row in enumerate(tracks):
            p,q = row['pooled_ratio'],row['channel_controlled_ratio']
            if p is not None and q is not None:
                ax.plot([p,q],[y,y],color='#999999',lw=.7)
            ax.scatter([p],[y],c='#0072b2',s=26)
            ax.scatter([q],[y],c='#d55e00',marker='s',s=23)
        ax.set_yticks(range(len(tracks)), [f'{r["satellite"]} / RX{r["rx"]} · {r["span_s"]:.0f}s · n={r["n"]}' for r in tracks],fontsize=8)
        ax.axvline(1.1,c='#cc0000',ls='--',lw=1)
        ax.axvline(1,c='#777777',lw=.7)
        ax.set_ylim(len(tracks)-.4,-.7)
        ax.set(xlabel='RMS(fit + linear) / RMS(fit + quadratic)',title=f'Scan {result["scan"]} · {len(tracks)} satellite / receiver tracks')
        ax.grid(axis='x',alpha=.2)
    fig.legend(handles=[Line2D([],[],marker='o',ls='',color='#0072b2',label='Pooled channels: one intercept'),Line2D([],[],marker='s',ls='',color='#d55e00',label='Separate channel intercepts'),Line2D([],[],ls='--',color='#cc0000',label='1.1 diagnostic threshold')],loc='upper center',bbox_to_anchor=(.5,.958),ncol=3)
    fig.suptitle('Saved top-response associations · additional residual reduction from curvature',y=.992,fontsize=16)
    fig.text(.5,.017,'Same fitted-c memberships and saved orbit / calibration at the restaurant preset, not the capture-bound roof. Native Hz; in-sample OLS.\nChannel-controlled fits use channel intercepts + common linear / quadratic terms. A ratio above 1.1 is not proof of misidentification.\nTracks ordered by span, not continuity; full max-gap and degrees-of-freedom information is in the CSVs. No filtering applied.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.075,1,.935));fig.savefig(HERE/'curvature-ratios.png',dpi=150);plt.close(fig)
    fig, axes = plt.subplots(1,2,figsize=(17,height),sharex=True)
    for ax,result in zip(axes,results):
        tracks=sorted(result['all_pointing'],key=lambda r:(-r['span_s'],r['satellite'],r['rx']))
        for y,row in enumerate(tracks):
            color='#0072b2' if row['rx']==0 else '#d55e00'
            ax.plot([row['minimum_advantage_deg'],row['maximum_advantage_deg']],[y,y],color=color,alpha=.25,lw=1)
            ax.plot([row['p05_advantage_deg'],row['p95_advantage_deg']],[y,y],color=color,lw=2)
            ax.scatter([row['median_own_axis_advantage_deg']],[y],s=21,color=color)
        ax.axvspan(-41,0,color='#d55e00',alpha=.07)
        ax.axvline(0,c='black',lw=.8)
        ax.set_yticks(range(len(tracks)),[f'{r["satellite"]} / RX{r["rx"]} · {r["wrong_hemisphere_pct"]:.0f}% opposite' for r in tracks],fontsize=8)
        ax.set_ylim(len(tracks)-.4,-.7)
        ax.set(xlim=(-41,41),xlabel='Other axis angle − own axis angle (degrees)',title=f'Scan {result["scan"]} · nominal capture pointing')
        ax.grid(axis='x',alpha=.2)
    fig.suptitle('Do assigned satellite directions favor their receiving antenna?',y=.992,fontsize=17)
    fig.text(.5,.956,'Negative: closer to the other antenna axis     |     Positive: closer to its receiving antenna axis',ha='center',fontsize=11)
    fig.text(.5,.017,'RX0 nominally west, RX1 nominally east; both axes elevation 70°, separation 40°. Connector mapping is provisional; beam width unknown.\nDots = median, thick lines = 5th–95th percentile, thin lines = full range at assigned times. No binary beam or identity exclusion.\nGeometry uses capture-bound roof (sea-level assumed); orbit residuals retain the saved, different restaurant reference. Timing-shifted bank geometry.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.075,1,.937));fig.savefig(HERE/'receiver-pointing-audit.png',dpi=150);plt.close(fig)


def main():
    evidence_path=HERE/'orientation-evidence.json'
    evidence=json.loads(evidence_path.read_text())
    results=[audit_scan(scan,evidence) for scan in ('A','B')]
    receipt=dict(scope=__doc__,observations='Fixed fitted-c final assignments in both residual arms; own-arm saved absolute timing and calibration, no new optimization.',
                 caution='High coverage is conditional in-sample top-window association, not identity or position validation. Curvature and nominal pointing are diagnostics.',
                 saved_model_reference=evidence['profile_reference_lat_lon'],geometry_reference=evidence['operator_roof_lat_lon'],
                 geometry_altitude='0 km ellipsoid assumption; actual height unavailable',orientation_evidence_sha256=digest(evidence_path),
                 script_sha256=digest(Path(__file__)),scans=results)
    dump(HERE/'association-audit.json',receipt)
    plots(results)


if __name__ == '__main__':
    main()
