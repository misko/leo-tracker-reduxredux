"""Read-only sky-geometry audit of the 18 frozen all-100 association inputs.

No selection, calibration, timing, or location fit is changed. Geometry uses
capture-bound roof coordinates, sea-level altitude, and saved association timing.
Fitted-c owners are the common input to both position arms. A hemisphere test is
not a measured antenna beam mask. Every passing assigned window counts once.
"""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from plot_assigned_vs_position import HERE, SCANS, read_points

ROOT = HERE.parent / '2026_10_04_ds13_18_scan_benchmark'
INPUT = Path('/srv/bulk/leo/t1-at-v1-subset-positions-20261004')
OUT = HERE / 'east-west-sanity'
GUARD = 10.0


def sha(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def enu_frame(lat, lon):
    lat, lon = np.deg2rad([lat, lon])
    e2 = (1 / 298.257223563) * (2 - 1 / 298.257223563)
    n = 6378.137 / np.sqrt(1 - e2 * np.sin(lat)**2)
    observer = np.array([n*np.cos(lat)*np.cos(lon), n*np.cos(lat)*np.sin(lon), n*(1-e2)*np.sin(lat)])
    rotation = np.array([[-np.sin(lon), np.cos(lon), 0.],
                         [-np.sin(lat)*np.cos(lon), -np.sin(lat)*np.sin(lon), np.cos(lat)],
                         [np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)]])
    return observer, rotation


def sky(nodes, positions, times, observer, rotation):
    if np.min(times) < nodes[0] or np.max(times) > nodes[-1]:
        raise ValueError('Do not extrapolate orbit bank')
    xyz = np.column_stack([np.interp(times, nodes, positions[:, i]) for i in range(3)])
    relative = xyz - observer
    unit = relative @ rotation.T / np.linalg.norm(relative, axis=1)[:, None]
    beta = np.rad2deg(np.arcsin(np.clip(unit[:, 0], -1, 1)))
    elevation = np.rad2deg(np.arcsin(np.clip(unit[:, 2], -1, 1)))
    tilt = np.deg2rad(20.)
    axes = np.array([[-np.sin(tilt), 0., np.cos(tilt)], [np.sin(tilt), 0., np.cos(tilt)]])
    off = np.rad2deg(np.arccos(np.clip(unit @ axes.T, -1, 1)))
    return beta, elevation, off


def path_class(beta):
    signs = np.sign(beta)
    signs = signs[signs != 0]
    if np.sum(signs[1:] != signs[:-1]) > 1:
        return 'Multiple crossings'
    if np.min(beta) < 0 < np.max(beta):
        return 'W→E' if beta[-1] > beta[0] else 'E→W'
    return 'East only' if np.min(beta) >= 0 else 'West only'


def wrong_side(beta, receiver, guard=0.):
    return np.where(receiver == 0, beta > guard, beta < -guard)


def crossing_order(cls, t0, t1):
    if cls not in ('W→E', 'E→W') or min(len(t0), len(t1)) < 10:
        return 'not testable'
    med0, med1 = float(np.median(t0)), float(np.median(t1))
    if abs(med0-med1) <= .020:
        return 'tied within 20 ms'
    return 'consistent' if (med0 < med1 if cls == 'W→E' else med1 < med0) else 'reversed'


def write_csv(name, rows):
    with (OUT / name).open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run():
    OUT.mkdir(exist_ok=True)
    cohort = json.loads((ROOT / 'cohort-v2.json').read_text())
    metadata = {r['label']: r for r in cohort['scans']}
    position_rows = read_points(HERE / 'cohort-positions.csv')
    summaries, satellites, tracks, provenance, examples = [], [], [], [], {}
    point_arrays = {k: [] for k in ['scan_index', 'satellite', 'receiver', 'time_s', 'beta_deg', 'elevation_deg', 'own_off_deg', 'other_off_deg']}
    for scan_index, scan in enumerate(SCANS):
        meta = metadata[scan]
        pose_path = Path(meta['pose_path'])
        pose = json.loads(pose_path.read_text())
        assert pose['session_id'] == meta['session_id']
        assert 'sha256:' + hashlib.sha256(canonical({k:v for k,v in pose.items() if k != 'binding_digest'})).hexdigest() == pose['binding_digest']
        authority = pose['pose_authority']
        assert 'sha256:' + hashlib.sha256(canonical(authority)).hexdigest() == pose['pose_authority_digest']
        assert pose['binding_digest'] == meta['pose_binding_digest']
        assert {r['receiver_id']: r['azimuth_deg'] for r in authority['receivers']} == {0:270., 1:90.}
        observer, rotation = enu_frame(authority['latitude_deg'], authority['longitude_deg'])
        source = INPUT / scan / 'input.npz'
        receipt = json.loads(source.with_suffix('.json').read_text())
        assert sha(source) == receipt['input_sha256']
        provenance.append(dict(scan=scan, session_id=meta['session_id'], pose_path=str(pose_path),
                               pose_sha256=sha(pose_path), authority=authority,
                               input_path=str(source), input_sha256=sha(source)))
        with np.load(source, allow_pickle=False) as d:
            times, owners, rx = d['times'], d['owners'], d['receiver']
            assert {len(times)} == {int(r['windows']) for r in position_rows if r['scan'] == scan}
            assert len(np.unique(d['group'])) == len(times)
            all_beta, all_unshifted = np.zeros(len(times)), np.zeros(len(times))
            all_elev, all_own, all_other = [np.zeros(len(times)) for _ in range(3)]
            for sid, sat in enumerate(d['numbers']):
                sat = int(sat)
                mask = owners == sat
                t, receiver = times[mask], rx[mask]
                shift = float(d['initial'][6 + sid])
                beta, elev, off = sky(d['nodes'], d['position'][sid], t + shift, observer, rotation)
                beta0 = sky(d['nodes'], d['position'][sid], t, observer, rotation)[0]
                grid = np.linspace(0., 300., 1201)
                gb, ge, _ = sky(d['nodes'], d['position'][sid], grid + shift, observer, rotation)
                span_grid = np.linspace(t.min(), t.max(), max(2, int(np.ptp(t)*4)+1))
                sb, se, _ = sky(d['nodes'], d['position'][sid], span_grid + shift, observer, rotation)
                cls = path_class(sb)
                n0, n1 = int(sum(receiver == 0)), int(sum(receiver == 1))
                pattern = 'Both RX' if n0 and n1 else 'RX0 only' if n0 else 'RX1 only'
                med0 = float(np.median(t[receiver == 0])) if n0 else None
                med1 = float(np.median(t[receiver == 1])) if n1 else None
                order = crossing_order(cls, t[receiver==0], t[receiver==1])
                wrong = wrong_side(beta, receiver)
                far_wrong = wrong_side(beta, receiver, GUARD)
                own, other = off[np.arange(len(t)), receiver], off[np.arange(len(t)), 1-receiver]
                row = dict(scan=scan, satellite=sat, windows=len(t), rx0_windows=n0, rx1_windows=n1,
                           receiver_pattern=pattern, both_rx_at_least_10=min(n0,n1)>=10,
                           start_s=float(t.min()), end_s=float(t.max()), timing_s=shift,
                           observed_span_path=cls, full_scan_visible_path=path_class(gb[ge>0]) if np.any(ge>0) else 'below horizon',
                           span_beta_min_deg=float(sb.min()), span_beta_max_deg=float(sb.max()),
                           wrong_windows=int(sum(wrong)), far_wrong_windows=int(sum(far_wrong)),
                           wrong_fraction=float(np.mean(wrong)), far_wrong_fraction=float(np.mean(far_wrong)),
                           rx0_median_time_s=med0, rx1_median_time_s=med1, crossing_median_order=order,
                           min_elevation_deg=float(elev.min()), max_elevation_deg=float(elev.max()),
                           median_own_off_axis_deg=float(np.median(own)), median_other_off_axis_deg=float(np.median(other)),
                           own_over_90_windows=int(sum(own>90)), unshifted_wrong_windows=int(sum(wrong_side(beta0,receiver))))
                satellites.append(row)
                examples[(scan,sat)] = (row, t, receiver, beta, grid, gb, ge)
                for r in (0,1):
                    m = receiver == r
                    if not np.any(m): continue
                    tracks.append(dict(scan=scan, satellite=sat, receiver=r, windows=int(sum(m)),
                                       start_s=float(t[m].min()), end_s=float(t[m].max()),
                                       wrong_fraction=float(np.mean(wrong[m])), far_wrong_fraction=float(np.mean(far_wrong[m])),
                                       beta_min_deg=float(beta[m].min()), beta_max_deg=float(beta[m].max()),
                                       median_own_off_axis_deg=float(np.median(own[m])), median_other_off_axis_deg=float(np.median(other[m])),
                                       below_horizon_windows=int(sum(elev[m]<0))))
                all_beta[mask], all_unshifted[mask], all_elev[mask] = beta, beta0, elev
                all_own[mask], all_other[mask] = own, other
            near = np.abs(all_beta) <= GUARD
            wrong = wrong_side(all_beta,rx)
            far_wrong = wrong_side(all_beta,rx,GUARD)
            ss = [r for r in satellites if r['scan']==scan]
            summaries.append(dict(scan=scan, windows=len(times), satellites=len(ss),
                                  rx0_windows=int(sum(rx==0)), rx1_windows=int(sum(rx==1)),
                                  wrong_windows=int(sum(wrong)), wrong_pct=100*float(np.mean(wrong)),
                                  near_meridian_windows=int(sum(near)), near_meridian_pct=100*float(np.mean(near)),
                                  far_wrong_windows=int(sum(far_wrong)), far_wrong_pct=100*float(np.mean(far_wrong)),
                                  far_correct_windows=int(sum(~wrong & ~near)),
                                  unshifted_wrong_pct=100*float(np.mean(wrong_side(all_unshifted,rx))),
                                  side_flips_with_timing=int(sum(wrong != wrong_side(all_unshifted,rx))),
                                  below_horizon_windows=int(sum(all_elev<0)), behind_nominal_axis_windows=int(sum(all_own>90)),
                                  other_axis_better_over_10_windows=int(sum(all_own-all_other>10)),
                                  single_side_both_rx=sum(r['observed_span_path'] in ('East only','West only') and r['receiver_pattern']=='Both RX' for r in ss),
                                  crossing_both_rx=sum(r['observed_span_path'] in ('W→E','E→W') and r['receiver_pattern']=='Both RX' for r in ss),
                                  crossing_order_consistent=sum(r['crossing_median_order']=='consistent' for r in ss),
                                  crossing_order_tied=sum(r['crossing_median_order']=='tied within 20 ms' for r in ss),
                                  crossing_order_reversed=sum(r['crossing_median_order']=='reversed' for r in ss)))
            values = [np.full(len(times),scan_index), owners,rx,times,all_beta,all_elev,all_own,all_other]
            for key,value in zip(point_arrays,values): point_arrays[key].append(value)
    write_csv('scan-summary.csv',summaries)
    write_csv('satellites.csv',satellites)
    write_csv('receiver-tracks.csv',tracks)
    np.savez_compressed(OUT/'detection-geometry.npz',**{k:np.concatenate(v) for k,v in point_arrays.items()})
    receipt = dict(scope=__doc__, scans=SCANS, meridian_guard_deg=GUARD,
                   guard_note='Diagnostic buffer, not antenna beam width.',
                   classification='Dense 0.25 s or finer trajectory over first-to-last assigned detection; full-scan above-horizon class separately recorded.',
                   median_order='Crossing observed span, >=10 windows on each RX; expected RX0 before RX1 for W→E, reversed for E→W; medians within 20 ms are tied. Not a sensitivity-controlled handoff test.',
                   nominal_axis='Level fixture assumption: RX0 az270/el70; RX1 az90/el70. Beamwidth/elevation unmeasured; connector mapping provisional.',
                   provenance=provenance,
                   totals={k:sum(r[k] for r in summaries) for k in ('windows','satellites','wrong_windows','far_wrong_windows','near_meridian_windows','below_horizon_windows','behind_nominal_axis_windows','side_flips_with_timing','single_side_both_rx','crossing_both_rx','crossing_order_consistent','crossing_order_tied','crossing_order_reversed')})
    (OUT/'audit.json').write_text(json.dumps(receipt,indent=2))
    render(summaries,satellites,examples)
    print(json.dumps(receipt['totals'],indent=2))


def render(summaries,satellites,examples):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors = ['#0077ad','#d9d9d9','#d55e00']
    fig,axes=plt.subplots(1,2,figsize=(15,8),gridspec_kw={'width_ratios':[1.25,1]})
    y=np.arange(len(SCANS));left=np.zeros(len(y))
    for key,label,color in zip(['far_correct_windows','near_meridian_windows','far_wrong_windows'],
                               ['Expected receiver side (>10°)','Within ±10° of dividing plane','Opposite receiver side (>10°)'],colors):
        values=np.array([100*r[key]/r['windows'] for r in summaries])
        axes[0].barh(y,values,left=left,color=color,label=label)
        left+=values
    axes[0].set_yticks(y,SCANS);axes[0].invert_yaxis();axes[0].set_xlim(0,100)
    axes[0].set_xlabel('Share of associated top-candidate GLRT windows (%)')
    axes[0].set_title('Receiver side at each actual detection time')
    axes[0].legend(loc='upper center',bbox_to_anchor=(.5,-.09),fontsize=9)
    classes=['West only','East only','W→E','E→W'];patterns=['RX0 only','Both RX','RX1 only']
    if any(r['observed_span_path']=='Multiple crossings' for r in satellites): classes.append('Multiple crossings')
    counts=np.array([[sum(r['observed_span_path']==c and r['receiver_pattern']==p for r in satellites) for p in patterns] for c in classes])
    axes[1].imshow(counts,cmap='Blues',aspect='auto',vmin=0)
    for i in range(len(classes)):
        for j in range(3):
            axes[1].text(j,i,str(counts[i,j]),ha='center',va='center',fontsize=21,color='white' if counts[i,j]>.55*counts.max() else '#222')
    axes[1].set_xticks(range(3),patterns);axes[1].set_yticks(range(len(classes)),classes)
    axes[1].set_title('Satellite/scan associations: path vs receivers\nPath evaluated over the observed track span')
    fig.suptitle('T1-AT v1 · east/west receiver sanity check · all 18 scans',fontsize=18)
    fig.text(.5,.025,'RX0 nominally west; RX1 nominally east. Channels pooled; frozen fitted-c owners used in both localization arms.\n'
             '10° is a diagnostic buffer, not a beam cutoff. A 40° axis separation does not establish disjoint fields of view. No associations removed or refitted.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.12,1,.95));fig.savefig(OUT/'east-west-summary.png',dpi=170);plt.close(fig)
    one_side=[r for r in satellites if r['full_scan_visible_path'] in ('West only','East only')]
    consistent=[r for r in satellites if r['crossing_median_order']=='consistent']
    reversed_rows=[r for r in satellites if r['crossing_median_order']=='reversed']
    selected=[]
    for pool in [[r for r in satellites if r['scan']=='A' and r['satellite']==60412],
                 sorted(one_side,key=lambda r:-r['far_wrong_windows']),
                 sorted(consistent,key=lambda r:r['wrong_fraction']),
                 sorted(reversed_rows,key=lambda r:-r['windows'])]:
        row=next((r for r in pool if (r['scan'],r['satellite']) not in selected),None)
        if row:selected.append((row['scan'],row['satellite']))
    fig,axes=plt.subplots(2,2,figsize=(14,9),sharex=True,sharey=True)
    for ax,key in zip(axes.flat,selected):
        row,t,rx,beta,grid,gb,ge=examples[key]
        ax.axhspan(-10,10,color='.93');ax.axhline(0,color='.5',lw=.8)
        ax.plot(grid,np.where(ge>0,gb,np.nan),color='.25',lw=1.1,label='Timing-adjusted orbit')
        for receiver,color in [(0,'#0077ad'),(1,'#df6900')]:
            m=rx==receiver
            if receiver == 0:
                ax.scatter(t[m],beta[m],s=34,facecolors='none',edgecolors=color,linewidths=1.,label=f'RX{receiver} ({sum(m)} windows)',zorder=4)
            else:
                ax.scatter(t[m],beta[m],s=20,marker='+',color=color,label=f'RX{receiver} ({sum(m)} windows)',zorder=5)
        ax.set_title(f'{row["scan"]} · {row["satellite"]} · {row["observed_span_path"]} during detected span\n'
                     f'{100*row["far_wrong_fraction"]:.1f}% opposite side beyond 10°; median order: {row["crossing_median_order"]}',fontsize=10)
        ax.set_xlim(0,300);ax.set_ylim(-90,90);ax.grid(alpha=.15);ax.legend(fontsize=8,loc='best')
        ax.set_xlabel('Receive time (s)');ax.set_ylabel('Angle east of north–south vertical plane (°)')
    for ax in list(axes.flat)[len(selected):]:ax.set_visible(False)
    fig.suptitle('Example associations · west is negative, east is positive',fontsize=17)
    fig.text(.5,.025,'Blue RX0 is nominally west; orange RX1 east. Gray band = ±10° diagnostic buffer. Dots show assigned detections on their predicted orbit.\n'
             'Examples selected to show flagged one-sided tracks, consistent crossing, and reversed receiver timing—not a random sample. Geometry is not identity proof.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.075,1,.95));fig.savefig(OUT/'east-west-examples.png',dpi=170);plt.close(fig)
    (OUT/'examples.json').write_text(json.dumps([examples[k][0] for k in selected],indent=2))


if __name__=='__main__':
    run()
