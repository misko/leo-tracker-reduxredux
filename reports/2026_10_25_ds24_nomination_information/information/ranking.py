"""Conditional local Gaussian design information; never an identity gate."""

import argparse
import copy
import csv
import json
from pathlib import Path
import signal
import sys
import time
import traceback

import numpy as np
from scipy.linalg import solve_triangular

import inventory as inv

REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
RECOVERY = Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')
sys.path.insert(0, str(RECOVERY))
import recovery as r
from build_dsx01_orbit_modes import build_modes
from ds23_height_problem import geometry_features
from ds23_new_family_prediction import orbit_terms
from ds23_position_information import marginal_position_information
from ds23_predictive_linear import linear_geometry
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from prototype_dsx01_continuous_position import latlon

HERE = inv.HERE


def solve(root, rhs):
    return solve_triangular(root.T, solve_triangular(root, rhs, lower=True), lower=False)


def mean_derivative(fun, x, step):
    return np.column_stack([(fun(x + d) - fun(x - d))/(2*step)
                            for d in np.eye(2)*step])


def gain(j, h, noise_variance, extra, root, response):
    """Target conditional on ALL old data; source-local priors are integrated."""
    whitened = solve_triangular(root, h.T, lower=True).T
    covariance = np.diag(noise_variance) + whitened@whitened.T + extra@extra.T
    effective = j - h@response
    ch = np.linalg.cholesky((covariance+covariance.T)/2)
    wj = solve_triangular(ch, effective, lower=True)
    information = wj.T@wj
    return (information+information.T)/2, covariance, effective


def parent_design(d, arm):
    saved = d['arms'][arm]
    p = r.build(d, arm, saved['phase_reference'])
    x = np.asarray(saved['endpoint_east_north_km'])
    total = p.calculate(x)
    if abs(total['negative_twice_elbo']-saved['negative_twice_elbo']) >= 1e-3:
        raise ValueError('saved parent objective replay failed')
    c = dict(p.curved_calculate(x) if d['entries'] else total)
    if not np.isfinite(c['final_log_precision_change']) or c['final_log_precision_change'] > 1e-5:
        raise ValueError('parent Gamma precision not converged')
    coef = c['coefficient'].copy()
    def curved_mean(z):
        geo = geometry_features(p, z, 0.)
        return (p.q*geo['intercept'] + geo['features']@coef)[p.keep]
    j = mean_derivative(curved_mean, x, .02)
    check = mean_derivative(curved_mean, x, .01)
    prior = np.asarray(c['coefficient_prior_precision'])
    u = c['features'][p.keep].copy()
    groups = p.noise_groups[p.keep]
    weights = d['powers'][groups]*c['noise_precision'][groups]/p.point_noise[p.keep]**2
    columns = [f'parent:{i}' for i in range(len(prior))]
    if d['entries']:
        view, _, sigma, eg, _ = linear_geometry(p, d['entries'])
        def predictive_mean(z):
            geo = geometry_features(view, z, 0.)
            return view.q*geo['intercept'] + geo['features']@coef
        je = mean_derivative(predictive_mean, x, .02)
        ce = mean_derivative(predictive_mean, x, .01)
        he = geometry_features(view, x, 0.)['features']
        constants = 300.*np.eye(len(d['entries']))[eg]
        u = np.vstack((np.column_stack((u, np.zeros((len(u),len(d['entries']))))),
                       np.column_stack((he, constants))))
        j = np.vstack((j, je)); check = np.vstack((check, ce))
        weights = np.r_[weights, 1/(2*sigma**2)]
        prior = np.r_[prior, np.ones(len(d['entries']))]
        columns += [f'old_predictive_constant:{e["component"]}' for e in d['entries']]
    relative = float(np.linalg.norm(j-check)/np.linalg.norm(j))
    if relative > 1e-5:
        raise ValueError('parent derivative did not converge')
    information = marginal_position_information(j, u, weights, prior)
    eigenvalues, axes = np.linalg.eigh(information)
    if not np.isfinite(information).all() or eigenvalues[0] <= 0:
        raise ValueError('nonpositive parent information')
    gram = np.diag(prior) + u.T@(weights[:,None]*u)
    root = np.linalg.cholesky(gram)
    cross = u.T@(weights[:,None]*j)
    response = solve(root, cross)
    weak = axes[:,0]
    # This map records scientific roles, rather than implying unnamed columns
    # are independent sources or qualified physical parameters.
    nh, ns = p.hardware.shape[1], p.smooth.shape[1]
    role_map = dict(hardware=list(range(nh)), receiver_smooth=list(range(nh,nh+ns)),
        phase={str(int(d['scan'].norads[k])):nh+ns+i for i,k in enumerate(p.labels)},
        physical_modes={str(int(d['scan'].norads[k])):list(range(nh+ns+len(p.labels)+3*i,nh+ns+len(p.labels)+3*i+3))
                        for i,k in enumerate(p.supported)},
        curved_constants=list(range(nh+ns+len(p.labels)+3*len(p.supported),len(coef))),
        old_predictive_constants=list(range(len(coef),len(prior))))
    return dict(p=p, x=x, coefficient=coef, prior=prior, u=u, j=j, weights=weights,
                root=root, gram=gram, cross=cross, response=response, information=information,
                weak=weak, variance=float(weak@np.linalg.solve(information,weak)),
                derivative_error=relative, columns=columns, role_map=role_map,
                final_log_precision_change=float(c['final_log_precision_change']),
                parent_objective_difference=float(total['negative_twice_elbo']-saved['negative_twice_elbo']))


def target_design(d, base, row):
    p, x, coef = base['p'], base['x'], base['coefficient']
    i, candidate = row['track_index'], row['candidate_index']
    track = d['scan'].tracks[i]
    if track['key'] != row['component'] or track['observation_ids'] != row['observation_ids']:
        raise ValueError('frozen source ownership changed')
    entry = dict(row, norad=row['candidate_norad'])
    # Dummy family is used only for original radio/noise construction when the
    # family has no active parent likelihood. Physical columns are target-local.
    active = row['family_has_parent_likelihood']
    dummy = entry if active else dict(entry,candidate_index=p.labels[0])
    view, _, sigma, _, _ = linear_geometry(p,[dummy])
    if active:
        if candidate not in p.supported:
            raise ValueError('active family lacks full parent physical modes; no zero-shape shortcut')
        def prediction(z):
            geo = geometry_features(view,z,0.)
            return view.q*geo['intercept']+geo['features']@coef
        features = geometry_features(view,x,0.)['features']
        extra = np.full((len(sigma),1),300.)
        el = geometry_features(view,x,0.)['elevation']
        kind = 'shares original parent phase and full physical modes'
        phase_reference = float(p.reference[p.labels.index(candidate)])
    else:
        sky = dict(time_s=d['scan'].sky['time_s'],
                   position_km=d['scan'].sky['position_km'][[candidate]],
                   velocity_km_s=d['scan'].sky['velocity_km_s'][[candidate]])
        modes, _ = build_modes(d['scan'],[candidate],[candidate],'physical')
        phase_reference = float(d['all_means'][candidate])
        width = float(d['widths'][candidate])
        if not np.isfinite(width) or width <= 0:
            raise ValueError('positive finite causal phase width required')
        q = track['rf_hz']/11.5e9
        radio_width = p.hardware.shape[1]+p.smooth.shape[1]
        features = geometry_features(view,x,0.)['features'].copy()
        features[:,radio_width:] = 0.
        def physical(z):
            return orbit_terms(sky,track['times'],phase_reference,*latlon(z))
        def prediction(z):
            return q*physical(z)[0]+features@coef
        _,el,derivative = physical(x)
        shape = q*paired_frequency_modes(sky,modes,track['times'],np.zeros(len(sigma),int),
                                         np.array([phase_reference]),*latlon(x))
        extra = np.column_stack((q*derivative*width,shape,np.full(len(sigma),300.)))
        kind = 'target-local causal-width Gaussian phase plus full three physical modes; dormant parent slots zero'
    if min(el) < 0 or not np.isfinite(extra).all():
        raise ValueError('target visibility/numerical failure')
    h = np.column_stack((features,np.zeros((len(sigma),len(base['prior'])-len(coef)))))
    j = mean_derivative(prediction,x,.02)
    check = mean_derivative(prediction,x,.01)
    relative = float(np.linalg.norm(j-check)/max(1e-30,np.linalg.norm(j)))
    if relative > 1e-5:
        raise ValueError('target derivative did not converge')
    # No target noise/Gamma is fitted. Original fixed per-ID noise and the
    # explicit unseen Gamma(2,2) inverse-moment factor are retained.
    return dict(j=j,h=h,variance=2*sigma**2,extra=extra,kind=kind,
                phase_reference_s=phase_reference,minimum_elevation_deg=float(min(el)),
                derivative_error=relative)


def redacted_target(d, base, row):
    """Copy only the candidate values; no parent/scan cache is mutated."""
    scan = copy.copy(d['scan'])
    scan.tracks = list(scan.tracks)
    i = row['track_index']
    track = dict(scan.tracks[i])
    track['values'] = np.asarray(track['values']) + 1e5*np.cos(np.arange(len(track['values'])))
    scan.tracks[i] = track
    p = copy.copy(base['p']); p.scan = scan
    return target_design(dict(d,scan=scan),dict(base,p=p),row)


def run():
    protocol = inv.read(HERE/'protocol.json')
    approval = inv.read(HERE/'independent_preflight.json')
    if not approval['all_passed'] or approval['protocol_sha256'] != inv.sha(HERE/'protocol.json'):
        raise ValueError('matching independent review required')
    for path,digest in protocol['source_and_input_bindings'].items():
        if inv.sha(path) != digest:
            raise ValueError(f'frozen source/input changed: {path}')
    inventory = inv.read(HERE/'inventory.json')
    began = time.monotonic(); rows=[]; parents=[]
    preparation_seconds = inventory['seconds']+protocol['test_seconds']+protocol['freeze_seconds']
    remaining = 600.-preparation_seconds
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('600s cumulative numerical cap')))
    signal.setitimer(signal.ITIMER_REAL,remaining)
    try:
        for case in inv.CASES:
            case_start=time.monotonic()
            signal.setitimer(signal.ITIMER_REAL,min(120.,remaining-(case_start-began)))
            d=r.context(case)
            frozen=next(c for c in inventory['cases'] if c['case']==case)
            ownership=inv.read(frozen['parent_ownership_path'])
            if inv.sha(frozen['parent_ownership_path']) != frozen['parent_ownership_sha256']:
                raise ValueError('full parent accepted-ID ledger changed')
            candidates=[q for q in inventory['sources'] if q['case']==case and q['eligible']]
            bases={}
            for arm in inv.ARMS:
                base=parent_design(d,arm);bases[arm]=base
                output=HERE/'arrays'/f'{case}_{arm}_parent.npz';output.parent.mkdir(exist_ok=True)
                if output.exists():raise FileExistsError(output)
                np.savez_compressed(output,gram=base['gram'],cross=base['cross'],root=base['root'],
                    response=base['response'],information=base['information'],weak=base['weak'],
                    prior=base['prior'],position_design=base['j'],nuisance_design=base['u'],weights=base['weights'])
                parents.append(dict(case=case,arm=arm,information=base['information'],weak=base['weak'],
                    weak_variance_km2=base['variance'],role_map=base['role_map'],columns=base['columns'],
                    array_path=str(output),array_sha256=inv.sha(output),
                    derivative_error=base['derivative_error'],parent_objective_difference=base['parent_objective_difference'],
                    final_log_precision_change=base['final_log_precision_change']))
            for candidate in candidates:
                record=dict(candidate,arms={},status='complete')
                for arm in inv.ARMS:
                    base=bases[arm]
                    try:
                        target=target_design(d,base,candidate)
                        redacted=redacted_target(d,base,candidate)
                        redaction=max(float(np.max(np.abs(target[k]-redacted[k]))) for k in ('j','h','variance','extra'))
                        if redaction != 0:
                            raise ValueError('target CFO values alter conditional design information')
                        info,cov,effective=gain(target['j'],target['h'],target['variance'],target['extra'],base['root'],base['response'])
                        augmented=base['information']+info
                        if not np.isfinite(augmented).all() or np.linalg.eigvalsh(augmented)[0]<=0:
                            raise ValueError('non-PD augmented position information')
                        variance=float(base['weak']@np.linalg.solve(augmented,base['weak']))
                        reduction=1-variance/base['variance']
                        if reduction < -1e-10 or reduction > 1+1e-10:
                            raise ValueError('invalid conditional variance reduction')
                        output=HERE/'arrays'/f'{case}_row{candidate["row_index"]:03d}_{arm}.npz'
                        if output.exists():raise FileExistsError(output)
                        np.savez_compressed(output,j=target['j'],h=target['h'],noise_variance=target['variance'],
                                            extra=target['extra'],conditional_covariance=cov,effective_j=effective,
                                            information_gain=info)
                        record['arms'][arm]=dict(status='complete',information_gain=info,augmented_information=augmented,
                            baseline_weak_variance_km2=base['variance'],augmented_baseline_weak_variance_km2=variance,
                            fractional_weak_variance_reduction=float(reduction),
                            weak_information_gain=float(base['weak']@info@base['weak']),
                            conditional_logdet_gain=float(np.linalg.slogdet(augmented)[1]-np.linalg.slogdet(base['information'])[1]),
                            covariance_semantics=target['kind'],minimum_elevation_deg=target['minimum_elevation_deg'],
                            phase_reference_s=target['phase_reference_s'],derivative_error=target['derivative_error'],
                            target_CFO_redaction_maximum_difference=redaction,
                            array_path=str(output),array_sha256=inv.sha(output))
                    except TimeoutError:raise
                    except Exception as exc:
                        record['arms'][arm]=dict(status='blocked',error=repr(exc),traceback=traceback.format_exc());record['status']='blocked'
                if record['status']=='complete':
                    record['paired_ranking_score']=min(a['fractional_weak_variance_reduction'] for a in record['arms'].values())
                rows.append(record)
                if time.monotonic()-case_start>120:
                    raise TimeoutError('120s per-case cap')
        for case in inv.CASES:
            pool=[q for q in rows if q['case']==case]
            for rank,q in enumerate(sorted(pool,key=lambda q:(-q['points'],-q['span_s'],q['component'])),1):q['count_rank']=rank
            for rank,q in enumerate(sorted(pool,key=lambda q:(-q['span_s'],-q['points'],q['component'])),1):q['duration_rank']=rank
            for rank,q in enumerate(sorted([q for q in pool if q['status']=='complete'],key=lambda q:(-q['paired_ranking_score'],-q['points'],-q['span_s'],q['component'])),1):q['information_rank']=rank
        status='complete'
    except Exception as exc:
        status='failed';error=dict(error=repr(exc),traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    result=dict(status=status,parents=parents,rows=rows,seconds=time.monotonic()-began,
                cumulative_numerical_seconds=preparation_seconds+time.monotonic()-began,
                no_position_fit=True,no_GPS_or_error=True,identity_qualified=False,
                protocol_sha256=inv.sha(HERE/'protocol.json'))
    if status!='complete':result.update(error)
    r.write_new(HERE/'results.json',result)
    r.write_new(HERE/'scientific_seal.json',dict(files={str(p):inv.sha(p) for p in sorted(HERE.rglob('*'))
                 if p.is_file() and '__pycache__' not in p.parts},no_position_fit=True,no_GPS_or_error=True))
    print(json.dumps(dict(status=status,rows=len(rows),seconds=result['seconds'])))


if __name__=='__main__':
    run()
