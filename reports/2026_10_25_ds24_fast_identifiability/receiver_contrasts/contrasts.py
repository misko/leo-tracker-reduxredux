"""Direct same-family, same-channel RX1 minus RX2 contrasts; no position fitter."""

import csv
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.linalg import solve_triangular

HERE = Path(__file__).resolve().parent
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
LEDGER = Path('/srv/bulk/leo/research/ds24-movement-policy-r01/cohort_ledger.json')
PERIOD = 1/4.4e-6
REFERENCE_RF = 11.5e9


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    def encode(v):
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, np.generic):
            return v.item()
        raise TypeError(type(v).__name__)
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, default=encode, allow_nan=False)
        stream.write('\n')


def basis(times):
    # Same width, spacing and coefficient scale as the prior receiver witness.
    return 50*np.exp(-.5*((np.asarray(times)[:, None]-np.arange(0, 301, 10))/5)**2)


def circular_rotation(seconds=75.):
    # Odd dimension gives an exactly real orthogonal fractional circular shift.
    n = 31
    phase = np.exp(-2j*np.pi*np.fft.fftfreq(n)*(seconds/10))
    matrix = np.fft.ifft(np.fft.fft(np.eye(n), axis=0)*phase[:, None], axis=0)
    assert np.max(abs(matrix.imag)) < 1e-12
    matrix = matrix.real
    np.testing.assert_allclose(matrix@matrix.T, np.eye(n), atol=1e-12, rtol=0)
    return matrix


def brackets(anchor_times, target_times, max_gap=2.):
    rows = []
    for i, t in enumerate(anchor_times):
        j = int(np.searchsorted(target_times, t))
        if j < len(target_times) and abs(target_times[j]-t) < 1e-10:
            rows.append((i, j, j, 0., 0.))
        elif 0 < j < len(target_times):
            left, right = target_times[j-1], target_times[j]
            gap = right-left
            if 0 < gap <= max_gap:
                rows.append((i, j-1, j, float((t-left)/gap), float(gap)))
    return rows


def affine_null(y, covariance, design, times):
    lower = np.linalg.cholesky(covariance)
    whitened = solve_triangular(lower, y, lower=True)
    nuisance = solve_triangular(lower, design, lower=True)
    u, singular, _ = np.linalg.svd(nuisance, full_matrices=True)
    rank = int(np.count_nonzero(singular > max(nuisance.shape)*np.finfo(float).eps*singular[0]))
    null = u[:, rank:]
    features = null.T@solve_triangular(lower, basis(times), lower=True)
    return dict(y=null.T@whitened, b=features, reconstruction=lower@null,
        nuisance_rank=rank, dimension=len(y)-rank,
        affine_leak=float(np.max(abs(null.T@nuisance))))


def posterior(train, transform=None):
    precision = np.eye(31)
    cross = np.zeros(31)
    for row in train:
        b = row['b'] if transform is None else row['b']@transform
        precision += b.T@b
        cross += b.T@row['y']
    return np.linalg.solve(precision, cross), precision


def predictive(row, mean, precision):
    y, b = row['y'], row['b']
    residual = y-b@mean
    total = precision+b.T@b
    cross = b.T@residual
    quadratic = float(residual@residual-cross@np.linalg.solve(total, cross))
    volume = float(np.linalg.slogdet(total)[1]-np.linalg.slogdet(precision)[1])
    score = float(len(y)*np.log(2*np.pi)+quadratic+volume)
    physical = row['reconstruction']@residual
    return dict(negative_twice_log_density=score, quadratic=quadratic, logvolume=volume,
        standardized_mean_square=float(residual@residual), dimension=len(y),
        projected_native_time_mean_square_hz2=float(physical@physical),
        native_time_points=len(physical)), row['reconstruction']@(b@mean)


def curvature_envelopes(case, norads):
    # Sensitivity only: nominal archived sky at nine fixed regional positions.
    # This is not an envelope for unknown phase, identity or physical orbit error.
    with np.load(SOURCE/case/'bank.npz') as bank:
        labels = {int(v):i for i, v in enumerate(bank['norad'])}
        ix = [labels[n] for n in norads]
        positions = bank['position_km'][ix]
        velocities = bank['velocity_km_s'][ix]
        grid = bank['time_s']
    values = np.zeros(len(norads))
    for east in (-12.5, 0., 12.5):
        for north in (-12.5, 0., 12.5):
            lat = np.radians(37.906+north/111)
            lon = np.radians(-122.545+east/(111.32*np.cos(np.radians(37.906))))
            receiver = 6371*np.array([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)])
            relative = positions-receiver
            frequency = -REFERENCE_RF/299792.458*np.sum(relative*velocities, axis=2)/np.linalg.norm(relative, axis=2)
            second = np.gradient(np.gradient(frequency, grid, axis=1), grid, axis=1)
            values = np.maximum(values, np.max(abs(second), axis=1))
    return dict(zip(norads, values, strict=True))


def metadata(case):
    saved = read(SOURCE/'family_cavity/position'/(case+'.json'))
    assert saved['status'] == 'complete'
    gate_maps = []
    for arm in ('c0', 'fitted_c'):
        mapping = {}
        for row in saved['policy_arms'][arm]['gates']['tracks']:
            assert row['compatible']
            mapping[row['component']] = (row['norad'], row['candidate_index'], tuple(row['observation_ids']))
        gate_maps.append(mapping)
    assert gate_maps[0] == gate_maps[1], 'Unmatched parent curved labels/IDs across c arms'
    accepted = gate_maps[0]
    node = saved['selected']['node'] if saved['accepted'] else saved['baseline_node']
    curved = {row['component']:row for row in node['seed']['rows'] if row['active_curvature']}
    tracks = read(SOURCE/case/'tracks.json')
    native = {o['observation_id']:o for o in read(SOURCE/case/'observations.json')}
    sigmas = read(SOURCE/case/'radio_noise.json')['per_observation_noise_sigma_hz']
    by_family, used = {}, set()
    for track in tracks:
        key = track['key']
        if key not in accepted:
            continue
        norad, candidate, ids = accepted[key]
        assert key in curved and curved[key]['candidate_norad'] == norad
        retain = [i for i, oid in enumerate(track['observation_ids']) if oid in set(ids)]
        assert len(retain) == len(ids)
        lookup = {track['observation_ids'][i]:i for i in retain}
        assert set(lookup) == set(ids) and not used&set(ids)
        used.update(ids)
        order = sorted(retain, key=lambda i:track['times'][i])
        times = np.asarray([track['times'][i] for i in order])
        assert np.all(np.diff(times)>0)
        points = [track['observation_ids'][i] for i in order]
        values = np.asarray([track['values'][i] for i in order])
        observed = np.asarray([native[oid]['measured_cfo_hz'] for oid in points])
        alias = (values-observed)/PERIOD
        assert np.max(abs(alias-np.rint(alias))) < 1e-7
        for oid, t in zip(points, times, strict=True):
            assert native[oid]['receiver'] == track['receiver'] and native[oid]['channel'] == track['channel']
            assert native[oid]['actual_rf_hz'] == track['rf_hz']
            assert abs(native[oid]['time_s']-t) < 1e-8
        by_family.setdefault(norad, []).append(dict(key=key, receiver=track['receiver'], channel=track['channel'],
            rf_hz=track['rf_hz'], ids=points, times=times, values=values,
            sigma=np.asarray([sigmas[oid] for oid in points])*np.sqrt(2)))
    return by_family, dict(parent_curved_points=len(used), curved_families=len(by_family),
        paired_c_metadata_identical=True, alias_lift_is_integer_period=True)


def family_contrast(case, norad, tracks, curvature):
    first = sorted((t for t in tracks if t['receiver']==1), key=lambda t:t['key'])
    second = sorted((t for t in tracks if t['receiver']==2), key=lambda t:t['key'])
    pairs, used = [], set()
    for a in first:
        for b in second:
            if (a['channel'], a['rf_hz']) != (b['channel'], b['rf_hz']):
                continue
            rows = [v for v in brackets(a['times'], b['times']) if a['ids'][v[0]] not in used]
            if len(rows)<4:
                continue
            pairs.append((a, b, rows))
            used.update(a['ids'][v[0]] for v in rows)
    if not pairs:
        return None
    source_ids = sorted({oid for a,b,rows in pairs for i,j,k,w,g in rows for oid in (a['ids'][i],b['ids'][j],b['ids'][k])})
    lookup = {oid:i for i,oid in enumerate(source_ids)}
    sigma, source_values = np.zeros(len(source_ids)), np.zeros(len(source_ids))
    for a,b,_ in pairs:
        for track in (a,b):
            for oid, value, noise in zip(track['ids'],track['values'],track['sigma'],strict=True):
                if oid in lookup:
                    source_values[lookup[oid]] = value
                    sigma[lookup[oid]] = noise
    count = sum(len(v[2]) for v in pairs)
    matrix = np.zeros((count,len(source_ids)))
    nuisance = np.zeros((count,2*len(pairs)))
    times, envelopes, ledger = [], [], []
    cursor=0
    for number,(a,b,rows) in enumerate(pairs):
        q=a['rf_hz']/REFERENCE_RF
        local_times=np.asarray([a['times'][r[0]] for r in rows])
        for local,(i,j,k,w,gap) in enumerate(rows):
            pos=cursor+local; t=a['times'][i]
            matrix[pos,lookup[a['ids'][i]]] += 1/q
            matrix[pos,lookup[b['ids'][j]]] -= (1-w)/q
            matrix[pos,lookup[b['ids'][k]]] -= w/q
            envelope=curvature*.5*(t-b['times'][j])*(b['times'][k]-t)
            nuisance[pos,2*number]=1
            nuisance[pos,2*number+1]=(t-local_times.mean())/max(np.ptp(local_times),1)
            times.append(t);envelopes.append(envelope)
            ledger.append(dict(case=case,norad=norad,pair=number,channel=a['channel'],rf_hz=a['rf_hz'],
                time_s=t,RX1_ID=a['ids'][i],RX2_left_ID=b['ids'][j],RX2_right_ID=b['ids'][k],
                RX2_left_weight=1-w,RX2_right_weight=w,interpolation_gap_s=gap,
                interpolation_nominal_envelope_hz_at_11p5GHz=envelope))
        cursor+=len(rows)
    covariance=(matrix*sigma)@(matrix*sigma).T
    y=matrix@source_values; times=np.asarray(times); envelopes=np.asarray(envelopes)
    assert len({r['RX1_ID'] for r in ledger})==len(ledger)
    variants={}
    for variant in ('measurement','nominal_curvature_sensitivity'):
        cov=covariance+(np.diag(envelopes**2) if variant!='measurement' else 0)
        variants[variant]=affine_null(y,cov,nuisance,times)
    return dict(norad=norad,times=times,variants=variants,ledger=ledger,source_IDs=source_ids,
        unique_RX1_points=len(ledger),unique_RX2_points=len(set(r['RX2_left_ID'] for r in ledger)|set(r['RX2_right_ID'] for r in ledger)),
        track_pairs=len(pairs),max_interpolation_gap_s=max(r['interpolation_gap_s'] for r in ledger),
        max_nominal_interpolation_envelope_hz=float(max(envelopes)),
        offdiagonal_interpolation_covariance_count=int(np.count_nonzero(covariance-np.diag(np.diag(covariance)))),
        covariance_min_eigenvalue=float(np.linalg.eigvalsh(covariance)[0]))


def one(case):
    by_family,audit=metadata(case)
    paired=sorted(n for n,t in by_family.items() if {v['receiver'] for v in t}=={1,2})
    envelopes=curvature_envelopes(case,paired) if paired else {}
    families=[]
    for n in paired:
        row=family_contrast(case,n,by_family[n],envelopes[n])
        if row is not None:
            families.append(row)
    all_anchors=[v['RX1_ID'] for f in families for v in f['ledger']]
    assert len(all_anchors)==len(set(all_anchors))
    predictions=[];scores=[];rotation=circular_rotation()
    for target in families:
        train=[row for row in families if row['norad']!=target['norad']]
        if not train:
            continue
        train_times=np.concatenate([v['times'] for v in train])
        nearest=np.min(abs(target['times'][:,None]-train_times),axis=1)
        for variant in target['variants']:
            data=target['variants'][variant]
            training=[v['variants'][variant] for v in train]
            zero=dict(negative_twice_log_density=float(len(data['y'])*np.log(2*np.pi)+data['y']@data['y']),
                quadratic=float(data['y']@data['y']),logvolume=0.,standardized_mean_square=float(data['y']@data['y']),
                dimension=len(data['y']),projected_native_time_mean_square_hz2=float(np.linalg.norm(data['reconstruction']@data['y'])**2),
                native_time_points=len(target['times']))
            for method in ('zero','native','reversed_polarity','shift75','prior_only'):
                if method=='zero':
                    metrics=zero;pred=np.zeros(len(target['times']))
                else:
                    transform=-np.eye(31) if method=='reversed_polarity' else rotation if method=='shift75' else None
                    mean,precision=(np.zeros(31),np.eye(31)) if method=='prior_only' else posterior(training,transform)
                    metrics,pred=predictive(data,mean,precision)
                scores.append(dict(case=case,norad=target['norad'],variant=variant,method=method,
                    train_families=len(train),held_points=len(target['times']),held_dimension=data['dimension'],
                    held_time_with_training_within_5s_fraction=float(np.mean(nearest<=5)),
                    training_time_min_s=float(min(train_times)),training_time_max_s=float(max(train_times)),
                    shift_training_basis_relative_norm=1.,gain_vs_zero=zero['negative_twice_log_density']-metrics['negative_twice_log_density'],**metrics))
                if variant=='measurement':
                    projected=data['reconstruction']@data['y']
                    for record,observed,forecast in zip(target['ledger'],projected,pred,strict=True):
                        predictions.append(dict(record,method=method,projected_differential_hz=observed,predicted_differential_hz=forecast))
    support=[{k:v for k,v in f.items() if k not in ('times','variants','ledger','source_IDs')}|
        dict(dimension=f['variants']['measurement']['dimension'],affine_rank=f['variants']['measurement']['nuisance_rank'],
             affine_leak=f['variants']['measurement']['affine_leak']) for f in families]
    return dict(case=case,audit=audit,support=support,scores=scores,predictions=predictions,
        candidate_cross_receiver_families=len(paired),eligible_paired_families=len(families),
        scored=len(families)>=2,unsupported_reason=None if len(families)>=2 else 'fewer than two same-channel paired curved families')


def csv_write(path,rows):
    if not rows:
        return
    with path.open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)


def main():
    start=time.monotonic();protocol=read(HERE/'protocol.json')
    for path,digest in protocol['file_sha256'].items():
        assert sha(path)==digest,path
    output=[]
    (HERE/'cases').mkdir(exist_ok=True)
    for case in protocol['cases']:
        assert time.monotonic()-start<1200
        result=one(case);output.append(result)
        write(HERE/'cases'/(case+'.json'),{k:v for k,v in result.items() if k!='predictions'})
        csv_write(HERE/'cases'/(case+'_native_time_contrasts.csv'),result['predictions'])
        print(case,'paired/scored',result['eligible_paired_families'],result['scored'],flush=True)
    scores=[r for v in output for r in v['scores']]
    support=[dict(case=v['case'],**r) for v in output for r in v['support']]
    csv_write(HERE/'family_scores.csv',scores);csv_write(HERE/'support.csv',support)
    cases=[]
    for result in output:
        for variant in ('measurement','nominal_curvature_sensitivity'):
            for method in ('zero','native','reversed_polarity','shift75','prior_only'):
                rows=[v for v in result['scores'] if v['variant']==variant and v['method']==method]
                cases.append(dict(case=result['case'],variant=variant,method=method,eligible_paired_families=result['eligible_paired_families'],
                    scored=result['scored'],held_family_predictions=len(rows),
                    points=sum(v['native_time_points'] for v in rows),dimension=sum(v['dimension'] for v in rows),
                    loss=sum(v['negative_twice_log_density'] for v in rows),gain=sum(v['gain_vs_zero'] for v in rows),
                    standardized_square=sum(v['standardized_mean_square'] for v in rows),
                    projected_native_time_square_hz2=sum(v['projected_native_time_mean_square_hz2'] for v in rows)))
    csv_write(HERE/'case_scores.csv',cases)
    for path,digest in protocol['file_sha256'].items():
        assert sha(path)==digest,path
    summary=dict(status='complete',all_24_retained=True,scans=24,scored_scans=sum(v['scored'] for v in output),
        paired_family_blocks=len(support),scored_family_blocks=sum(len(v['support']) for v in output if v['scored']),
        unique_RX1_anchor_points=sum(v['unique_RX1_points'] for v in support),
        elapsed_seconds=time.monotonic()-start,numerical_workers=1,BLAS_threads=1,
        no_position_fits=True,no_GPS=True,no_IQ=True,c_invariant_raw_difference=True,
        no_hardware_attribution=True,protocol_sha256=sha(HERE/'protocol.json'))
    write(HERE/'summary.json',summary)
    write(HERE/'scientific_seal.json',dict(files={str(p.relative_to(HERE)):sha(p) for p in sorted(HERE.rglob('*'))
        if p.is_file() and p.suffix in ('.json','.csv','.py') and p.name!='scientific_seal.json'}))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
