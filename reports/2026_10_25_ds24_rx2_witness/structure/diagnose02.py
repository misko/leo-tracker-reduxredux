"""Complete-owner descriptive polynomial diagnostics, never source selection."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import time

import numpy as np

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent.parent
SOURCE = RESEARCH / 'ds25-20261024/DS24-0013'
INPUTS = dict(pool=RESEARCH / 'ds24-identity-support-r01/witness/whole_scan_inventory.json',
              tracks=SOURCE / 'tracks.json', observations=SOURCE / 'observations.json',
              tracking=SOURCE / 'tracking.json', archived=HERE.parent / 'archived/summary.json')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def fit_polynomial(times, values, degree):
    t, y = np.asarray(times), np.asarray(values)
    center = .5 * (t.min() + t.max())
    scale = .5 * np.ptp(t)
    design = np.polynomial.legendre.legvander((t - center) / scale, degree)
    q, r = np.linalg.qr(design, mode='reduced')
    coefficient = np.linalg.solve(r, q.T @ y)
    residual = y - design @ coefficient
    leverage = np.sum(q * q, axis=1)
    if np.any(1 - leverage <= 1e-10):
        raise ValueError('leave-one-out denominator numerically singular')
    loo = residual / (1 - leverage)
    second = np.polynomial.legendre.legder(coefficient, m=2)
    curvature = float(np.polynomial.legendre.legval(0., second) / scale**2)
    return dict(coefficient=coefficient, center=center, scale=scale, residual=residual,
                leverage=leverage, loo=loo, curvature=curvature, design=design)


def direct_loo(times, values, degree):
    t, y = np.asarray(times), np.asarray(values)
    center, scale = .5 * (t.min() + t.max()), .5 * np.ptp(t)
    full_design = np.polynomial.legendre.legvander((t - center) / scale, degree)
    residual, curvature = [], []
    for i in range(len(t)):
        keep = np.arange(len(t)) != i
        coefficient = np.linalg.lstsq(full_design[keep], y[keep], rcond=None)[0]
        residual.append(float(y[i] - full_design[i] @ coefficient))
        derivative = np.polynomial.legendre.legder(coefficient, m=2)
        curvature.append(float(np.polynomial.legendre.legval(0., derivative) / scale**2))
    return np.asarray(residual), np.asarray(curvature)


def freeze():
    paths = INPUTS | dict(source=Path(__file__), tests=HERE / 'test_diagnose02.py',
                         design=HERE / 'PROTOCOL.md',
                         public_point_port=Path('/home/mouse9911/gits/leo-tracker-reduxredux/src/leo/analysis/glrt_frequency_input.py'))
    write('protocol02.json', dict(files={str(path): sha(path) for path in paths.values()},
        degree_orders=[1, 2, 3, 4], all_three_complete_sources=True,
        direct_LOO_maximum_error_hz=1e-5, selected_endpoint_inspection=True,
        maximum_processing_seconds=30, earlier_processing_upper_bound_seconds=2,
        repair='Use original fast-export frequency_evidence port; public_tracking_points needs absent embedded timing. No observation or polynomial rule changes.',
        position_fits=0, new_candidate_scores=0, GPS_used=False))


def main():
    began = time.monotonic()
    protocol = read(HERE / 'protocol02.json')
    assert all(sha(path) == digest for path, digest in protocol['files'].items())
    pool = read(INPUTS['pool'])['selected']
    tracks = {row['key']: row for row in read(INPUTS['tracks'])}
    observations = {row['observation_id']: row for row in read(INPUTS['observations'])}
    archived = {row['component']: row for row in read(INPUTS['archived'])['rows']}
    # Public research port exactly reproduces native IDs and device-counter times.
    from leo.analysis.glrt_frequency_input import frequency_evidence
    document=read(INPUTS['tracking'])
    public_source=document['source']
    evidence, _, public_metadata=frequency_evidence(document)
    public_rows=[]
    for index,probe in enumerate(public_source['probes']):
        passed=[c for c in probe['candidates'] if c['passed_fractional_margin_gate'] is True]
        if not passed: continue
        chosen=max(passed,key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
        start=probe['valid_start_counter']+round(probe['probe_start_ms']*public_source['sample_rate_hz']/1000)
        public_rows.append(dict(observation_id='sha256:'+hashlib.sha256(evidence.ids[index].encode()).hexdigest(),
            time_s=float(evidence.time_s[index]), measured_cfo_hz=chosen['fractional_tracking_cfo_hz'],
            native_receiver_id=probe['receiver_id'], visit_index=probe['visit_index'],
            probe_index=probe['probe_index'], valid_start_counter=start,
            fractional_margin=chosen['fractional_margin']))
    native = {row['observation_id']: row for row in public_rows}
    assert len(native) == len(public_rows)
    details, summaries, arrays = [], [], []
    for source in pool:
        track = tracks[source['component']]
        ids = source['observation_ids']
        assert track['observation_ids'] == ids and track['times'] == source['times_s']
        t, y = np.asarray(track['times']), np.asarray(track['values'])
        measured = np.asarray([observations[oid]['measured_cfo_hz'] for oid in ids])
        assert np.max(abs((y - measured) - (y[0] - measured[0]))) < 1e-7
        assert all(native[oid]['time_s'] == stamp and
                   native[oid]['measured_cfo_hz'] == value
                   for oid, stamp, value in zip(ids, t, measured, strict=True))
        gaps = np.diff(t)
        orders = []
        for degree in (1, 2, 3, 4):
            fit = fit_polynomial(t, y, degree)
            direct, curvature = direct_loo(t, y, degree)
            error = float(np.max(abs(fit['loo'] - direct)))
            assert error <= protocol['direct_LOO_maximum_error_hz']
            residual = fit['residual']
            correlation = float(np.corrcoef(residual[:-1], residual[1:])[0, 1])
            rms = lambda values: float(np.sqrt(np.mean(np.asarray(values)**2)))
            order = dict(degree=degree, RMS_hz=rms(residual), LOO_RMS_hz=rms(fit['loo']),
                lag_one_residual_correlation=correlation,
                curvature_at_fixed_source_center_hz_per_s2=fit['curvature'],
                maximum_leverage=float(fit['leverage'].max()),
                maximum_leverage_index=int(np.argmax(fit['leverage'])),
                final_point_leverage=float(fit['leverage'][-1]),
                final_point_LOO_residual_hz=float(fit['loo'][-1]),
                final_point_omitted_curvature_hz_per_s2=float(curvature[-1]),
                maximum_direct_LOO_error_hz=error,
                coefficients_hz=fit['coefficient'].tolist(), reference_time_s=fit['center'], time_scale_s=fit['scale'])
            orders.append(order)
            for i, oid in enumerate(ids):
                details.append(dict(component=source['component'], degree=degree, index=i,
                    observation_id=oid, time_s=float(t[i]), graph_CFO_hz=float(y[i]),
                    residual_hz=float(residual[i]), leverage=float(fit['leverage'][i]),
                    LOO_residual_hz=float(fit['loo'][i]),
                    omitted_curvature_hz_per_s2=float(curvature[i]),
                    previous_gap_s=float(t[i]-t[i-1]) if i else None))
            if degree == 2:
                arrays.append((source, t, residual, fit['leverage']))
        endpoint_provenance = []
        for oid in ids[-2:]:
            point = native[oid]
            fs = public_source['sample_rate_hz']
            matching = [probe for probe in public_source['probes']
                if probe['receiver_id'] == point['native_receiver_id'] and
                probe['valid_start_counter'] + round(probe['probe_start_ms']*fs/1000) == point['valid_start_counter']]
            assert len(matching) == 1
            probe = matching[0]
            passed = [c for c in probe['candidates'] if c['passed_fractional_margin_gate'] is True]
            chosen = max(passed, key=lambda c:(c['fractional_margin'], -c['candidate_rank']))
            assert chosen['fractional_tracking_cfo_hz'] == point['measured_cfo_hz']
            endpoint_provenance.append({key: point[key] for key in
                ('observation_id', 'time_s', 'visit_index', 'probe_index',
                 'valid_start_counter', 'native_receiver_id', 'fractional_margin')} |
                 dict(chosen_candidate_rank=chosen['candidate_rank'], eligible_peak_count=len(passed),
                      probe_start_ms=probe['probe_start_ms'], probe_duration_ms=public_source['probe_ms']))
        summaries.append(dict(component=source['component'], points=len(ids),
            gap_s=gaps.tolist(), median_gap_s=float(np.median(gaps)),
            largest_gap_s=float(gaps.max()), largest_gap_ending_index=int(np.argmax(gaps)+1),
            final_gap_s=float(gaps[-1]), archived=archived[source['component']],
            piece_metadata=[{key: piece[key] for key in ('degree', 'start_s', 'end_s', 'indices')}
                            for piece in track['pieces']],
            endpoint_provenance=endpoint_provenance, orders=orders))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 2, figsize=(11, 9), layout='constrained')
    for i, (source, times, residual, leverage) in enumerate(arrays):
        ax = axes[i, 0]
        ax.plot(times, residual, color='#176da3', linewidth=.8)
        ax.scatter(times, residual, s=15+100*leverage, color='#176da3')
        ax.scatter(times[-1], residual[-1], facecolor='none', edgecolor='#c0392b', s=90)
        ax.axhline(0, color='grey', linewidth=.7)
        ax.set(title=f'RX2 CH{source["channel"]}: complete quadratic residual',
               xlabel='Scan time (s)', ylabel='CFO residual (Hz)')
        order=summaries[i]['orders']
        axes[i, 1].plot([x['degree'] for x in order], [x['RMS_hz'] for x in order], marker='o', label='Complete fit')
        axes[i, 1].plot([x['degree'] for x in order], [x['LOO_RMS_hz'] for x in order], marker='s', label='Leave one out')
        axes[i, 1].set(yscale='log', xticks=[1, 2, 3, 4], xlabel='Polynomial degree', ylabel='RMS (Hz)')
        for axis in axes[i]: axis.grid(alpha=.2)
    axes[0, 1].legend()
    fig.suptitle('Complete-source structure diagnostics: all points retained\n'
                 'Exploratory after archived endpoint inspection; marker area reflects leverage')
    fig.savefig(HERE / 'polynomial_structure.png', dpi=160)
    plt.close(fig)
    assert time.monotonic()-began + protocol['earlier_processing_upper_bound_seconds'] < 30
    assert all(sha(path) == digest for path, digest in protocol['files'].items())
    write('results.json', dict(rows=summaries, seconds=time.monotonic()-began,
        public_observation_policy='Original fast-export frequency_evidence IDs/times; one maximum-margin gate-passing peak per probe',
        cumulative_processing_upper_bound_seconds=time.monotonic()-began+protocol['earlier_processing_upper_bound_seconds'],
        all_source_points_retained=True, selected_after_archived_inspection=True,
        new_candidate_scores=0, position_fits=0, GPS_used=False, protocol_sha256=sha(HERE / 'protocol02.json')))
    with (HERE / 'point_diagnostics.csv').open('x', newline='') as stream:
        writer=csv.DictWriter(stream, fieldnames=list(details[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(details)
    names=('diagnose02.py','test_diagnose02.py','PROTOCOL.md','protocol02.json',
           'results.json','point_diagnostics.csv','polynomial_structure.png')
    write('seal02.json', dict(files={name:sha(HERE/name) for name in names}))
    print(json.dumps(dict(seconds=read(HERE/'results.json')['seconds'], rows=summaries),indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true')
    if parser.parse_args().freeze: freeze()
    else: main()
