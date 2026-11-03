"""Report-only per-family audit of retained associations and receiver geometry.

No nomination, fitting, ground-truth coordinate or post-scan element enters here.
Compare direct nominal SGP4 receipts with the fitted linearized orbit geometry.
"""

import csv
from datetime import datetime, timezone

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from audit_ds23_0268_sky_visibility import angular_separation, horizon
from debug_ds23_0268_visibility_reentry import OUT as SOURCE_OUT
from probe_ds23_0268_selected_identity_split import replay_proposal
from run_algo01_ds23_sample import ROOT, read, write, sha
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.sky.frames import look_angles, geodetic_to_ecef_km, ecef_to_enu_matrix

OUT = ROOT / 'reports/2026_10_20_ds23_0268_geometry_review'
PROPOSAL = 'selected_split_all_RX1_with_CH2_constrained'


def group_geometry(rows):
    """Summarize every original measurement once, separately in each c arm."""
    groups = {}
    seen = set()
    for row in rows:
        key = (row['arm'], row['observation_id'])
        if key in seen:
            raise ValueError('duplicate original measurement in geometry audit')
        seen.add(key)
        groups.setdefault((row['arm'], row['norad'], row['receiver']), []).append(row)
    result = []
    for (arm, norad, receiver), points in sorted(groups.items()):
        result.append(dict(arm=arm, norad=norad, receiver=receiver, points=len(points),
            tracks=len({p['component'] for p in points}),
            start_s=min(p['time_s'] for p in points), end_s=max(p['time_s'] for p in points),
            minimum_nominal_elevation_deg=min(p['nominal_elevation_deg'] for p in points),
            maximum_nominal_off_axis_deg=max(p['nominal_off_axis_deg'] for p in points),
            minimum_fitted_elevation_deg=min(p['fitted_elevation_deg'] for p in points),
            maximum_fitted_off_axis_deg=max(p['fitted_off_axis_deg'] for p in points),
            maximum_direction_correction_deg=max(p['direction_correction_deg'] for p in points),
            phase_s=points[0].get('phase_s'),
            TLE_epoch_age_hours=points[0].get('TLE_epoch_age_hours'),
            maximum_phase_direction_correction_deg=max(p.get('phase_direction_correction_deg', 0.) for p in points),
            maximum_orbit_mode_direction_correction_deg=max(p.get('orbit_mode_direction_correction_deg', 0.) for p in points),
            below_nominal_horizon=sum(p['nominal_elevation_deg'] < 0 for p in points),
            below_fitted_horizon=sum(p['fitted_elevation_deg'] < 0 for p in points),
            behind_nominal_feed=sum(p['nominal_off_axis_deg'] > 90 for p in points),
            nominal_outside_45deg=sum(p['nominal_off_axis_deg'] > 45 for p in points)))
    return result


def csv_write(path, rows):
    with path.open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def plot(rows):
    figure, axes = plt.subplots(1, 2, figsize=(13, 9), sharey=True)
    chosen = [r for r in rows if r['arm'] == 'fitted_c']
    order = sorted({r['norad'] for r in chosen})
    for receiver, color, delta in ((1, '#416fa5', -.12), (2, '#bd6a3f', .12)):
        selected = [r for r in chosen if r['receiver'] == receiver]
        y = np.array([order.index(r['norad']) for r in selected]) + delta
        axes[0].scatter([r['minimum_nominal_elevation_deg'] for r in selected], y,
                        color=color, label=f'RX{receiver}', s=45)
        axes[1].scatter([r['maximum_nominal_off_axis_deg'] for r in selected], y,
                        color=color, s=45)
        for ax, field in zip(axes, ('minimum_fitted_elevation_deg', 'maximum_fitted_off_axis_deg')):
            ax.scatter([r[field] for r in selected], y, facecolors='none', edgecolors=color, s=85)
    axes[0].set_yticks(range(len(order)), [str(n) for n in order])
    axes[0].set(xlabel='Minimum elevation at associated observations (°)', ylabel='Satellite NORAD')
    axes[1].set_xlabel('Maximum separation from nominal receiver axis (°)')
    axes[0].axvline(0, color='black', lw=.8)
    axes[1].axvline(45, color='gray', ls='--', label='45° sensitivity reference')
    axes[0].legend(loc='lower right')
    axes[1].legend(loc='lower right', fontsize=8)
    for ax in axes:
        ax.grid(alpha=.2)
    figure.suptitle('DS23-0268 · all 2,316 associated observations · all 17 labels\n'
        'Solid: nominal causal TLE; open: fitted orbit · fitted-c arm\n'
        'Receiver axes provisional: west/east, 70° elevation · measured beam width unavailable')
    figure.tight_layout(rect=(0, 0, 1, .9))
    figure.savefig(OUT / 'all_satellite_geometry.png', dpi=180)
    plt.close(figure)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fit_path = SOURCE_OUT / (PROPOSAL + '.json')
    audit_path = SOURCE_OUT / (PROPOSAL + '_independent_replay_audit.json')
    points_path = SOURCE_OUT / (PROPOSAL + '_direct_nominal_sky_points.csv')
    audit, record = read(audit_path), read(fit_path)
    if audit['selected_fit_sha256'] != sha(fit_path):
        raise ValueError('independent audit is stale')
    station_path = ROOT / 'deploy/station/gauss-r20-lt3d-004b-20261001-v1.json'
    station = read(station_path)
    if audit['station_authority_sha256'] != sha(station_path):
        raise ValueError('station authority changed')
    axes = {r['receiver_id'] + 1: (r['azimuth_deg'], r['elevation_deg']
            if r['elevation_deg'] is not None else 90 - station['nominal_outward_tilt_deg'])
            for r in station['receivers']}
    with points_path.open() as handle:
        nominal = {(r['arm'], r['observation_id']): r for r in csv.DictReader(handle)
                   if r['geometry'] == 'RF_estimate'}
    coverage = read(SOURCE_OUT / 'accepted_identity_split_coverage.json')[PROPOSAL]
    points = []
    for arm in ('c0', 'fitted_c'):
        p, x = replay_proposal(record, arm)
        state = p.state(x)
        by_key = {t['key']: t for t in p.scan.tracks}
        for accepted in coverage[arm]['accepted_rows']:
            track = by_key[accepted['component']]
            owned = set(accepted.get('observation_ids', track['observation_ids']))
            use = np.array([oid in owned for oid in track['observation_ids']])
            times = track['times'][use]
            az, el = horizon(p, x, accepted['norad'], times)
            separation = angular_separation(az, el, *axes[track['receiver']])
            j = int(np.flatnonzero(p.scan.norads == accepted['norad'])[0])
            position, velocity = paired_phase_states(p.scan.sky, times,
                np.full(len(times), j), state['phases'])
            phase_az, phase_el, _, _ = look_angles(position, velocity,
                geodetic_to_ecef_km(*latlon(x), 0.), ecef_to_enu_matrix(*latlon(x)))
            age_hours = (p.scan.receipt['origin_utc_ns'] -
                p.scan.elements[str(accepted['norad'])]['provenance']['element_epoch_utc_ns']) / 3.6e12
            for oid, t, a, e, off, ap, ep in zip(np.array(track['observation_ids'])[use], times,
                    az, el, separation, phase_az, phase_el, strict=True):
                direct = nominal[(arm, oid)]
                if (int(direct['norad']), int(direct['receiver'])) != (accepted['norad'], track['receiver']):
                    raise ValueError('nominal and fitted identities disagree')
                points.append(dict(arm=arm, observation_id=oid, component=track['key'],
                    norad=accepted['norad'], receiver=track['receiver'], time_s=float(t),
                    nominal_elevation_deg=float(direct['elevation_deg']),
                    nominal_off_axis_deg=float(direct['nominal_off_axis_deg']),
                    fitted_elevation_deg=float(e), fitted_off_axis_deg=float(off),
                    phase_s=float(state['phases'][j]), TLE_epoch_age_hours=float(age_hours),
                    phase_direction_correction_deg=float(angular_separation(ap, ep,
                        float(direct['azimuth_deg']), float(direct['elevation_deg']))),
                    orbit_mode_direction_correction_deg=float(angular_separation(a, e, ap, ep)),
                    direction_correction_deg=float(angular_separation(a, e,
                        float(direct['azimuth_deg']), float(direct['elevation_deg'])))))
        expected = set(coverage[arm]['associated_observation_ids'])
        if {r['observation_id'] for r in points if r['arm'] == arm} != expected:
            raise ValueError('missing associated point in fitted geometry audit')
    grouped = group_geometry(points)
    csv_write(OUT / 'per_satellite_receiver.csv', grouped)
    csv_write(OUT / 'per_observation.csv', points)
    plot(grouped)
    checks = {arm: dict(points=sum(r['points'] for r in grouped if r['arm'] == arm),
        satellites=len({r['norad'] for r in grouped if r['arm'] == arm}),
        minimum_fitted_elevation_deg=min(r['minimum_fitted_elevation_deg'] for r in grouped if r['arm'] == arm),
        maximum_fitted_off_axis_deg=max(r['maximum_fitted_off_axis_deg'] for r in grouped if r['arm'] == arm),
        maximum_direction_correction_deg=max(r['maximum_direction_correction_deg'] for r in grouped if r['arm'] == arm),
        fitted_below_horizon=sum(r['below_fitted_horizon'] for r in grouped if r['arm'] == arm))
        for arm in ('c0', 'fitted_c')}
    write(OUT / 'audit.json', dict(created_utc=datetime.now(timezone.utc).isoformat(),
        case='DS23-0268', checks=checks, selected_fit_sha256=sha(fit_path),
        independent_replay_sha256=sha(audit_path), nominal_points_sha256=sha(points_path),
        source_sha256=sha(ROOT / 'tools/review_ds23_0268_geometry.py'),
        station_sha256=sha(station_path), no_fit_or_nomination_changes=True,
        no_GPS_or_future_TLE_used=True, actual_antenna_response_not_measured=True))
    print(checks, flush=True)


if __name__ == '__main__':
    main()
