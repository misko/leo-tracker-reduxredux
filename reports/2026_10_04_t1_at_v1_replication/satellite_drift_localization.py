"""Full-data conditional localization with regularized per-satellite drift.

Keep all original associated top-one windows, satellites, ephemerides and the
archived fold-derived receiver baseline fixed. Add one slope per satellite,
shared across receivers/channels and scaled by observed RF / 11.085 GHz.
Slope priors are independent N(0, 2^2 Hz^2/s^2), fixed across the cohort before
running it. This is a model-discrepancy diagnostic, not a claim of TX drift.
No held-out rows, satellite reselection, location prior or truth-based tuning.
"""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from leave_one_satellite_out import HERE, load
from subset_positions import enable_research_model, serial
from timing_bound_comparison import digest, feasible_start
from convergence_fisher import fit
from resume_position_convergence import best_record

enable_research_model()
from rf_calibration_diagnostic import CalibrationObjective
from soft_likelihood import SoftLikelihood
from soft_solvers import _fisher_system

OUT = HERE/'satellite-drift-localization'
SOURCE = HERE/'frequency-regularized-selection/polished'
SCANS = tuple(f'N{i:02}' for i in range(1,17))
ARMS = ('fitted-c','zero-c')
MODES = ('control','satellite-drift')
REFERENCE_RF_HZ = 11.085e9
SLOPE_SIGMA_HZ_S = 2.
BUDGET = dict(roof=6., probe=.5, search=8., polish=8., final_polish=20.)


def drift_features(times, rf, owners, numbers):
    """Frozen owner time centers; no receiver-specific satellite drift."""
    times, rf = np.asarray(times,float), np.asarray(rf,float)
    owners, numbers = np.asarray(owners), np.asarray(numbers)
    if times.ndim != 1 or times.shape != rf.shape or times.shape != owners.shape:
        raise ValueError('Mismatched observation vectors')
    if not len(times) or not np.all(np.isfinite(times)) or not np.all(np.isfinite(rf)) or np.any(rf<=0):
        raise ValueError('Finite times and positive RF required')
    if len(set(numbers)) != len(numbers) or not set(owners) <= set(numbers):
        raise ValueError('Invalid satellite bank or owner')
    if any(not np.any(owners==n) for n in numbers):
        raise ValueError('Every selected satellite requires original owner evidence')
    centers = np.array([np.mean(times[owners==n]) for n in numbers])
    return (times[:,None]-centers)*rf[:,None]/REFERENCE_RF_HZ, centers


class DriftLikelihood(SoftLikelihood):
    def __init__(self, prepared, probability, rf_features, slope_features):
        super().__init__(prepared, probability)
        self.rf_features = rf_features
        self.slope_features = slope_features
        self.slopes = np.zeros(slope_features.shape[1])
        self.coefficient = 0.

    def correction(self):
        return self.slope_features*self.slopes + self.rf_features*self.coefficient

    def evaluate(self, predicted, visible, **options):
        return super().evaluate(predicted+self.correction(), visible, **options)


class SatelliteDriftObjective(CalibrationObjective):
    # Vector: timing model, Ns slope coefficients, c. Timing-model size is
    # unchanged so the common/relative timing constraint map remains valid.
    def __init__(self, data, center, arm, mode):
        if arm not in ARMS or mode not in MODES:
            raise ValueError('Unknown RF arm or drift mode')
        super().__init__(data, data.initial, np.arange(len(data.numbers)), False, 60.)
        self.center = center
        self.features = ((data.rf-center)/1e9)[:,None]
        self.slope_features, self.time_centers = drift_features(data.times,data.rf,data.owners,data.numbers)
        self.n_satellites = len(data.numbers)
        self.likelihood = DriftLikelihood(self.likelihood.prepared, .8/self.n_satellites,
                                         self.features, self.slope_features)
        self.base.likelihood = self.likelihood
        self.initial = np.r_[self.initial[:self.size], np.zeros(self.n_satellites), 0.]
        slope_bounds = [(None,None)]*self.n_satellites if mode=='satellite-drift' else [(0.,0.)]*self.n_satellites
        self.bounds = self.bounds[:self.size]+slope_bounds+([(0.,0.)] if arm=='zero-c' else [(-5000.,5000.)])
        self.scale = np.r_[self.scale[:self.size], np.full(self.n_satellites,SLOPE_SIGMA_HZ_S), 1000.]
        self.base.minimum_shift_s = max(self.base.minimum_shift_s,-20.)
        self.base.maximum_shift_s = min(self.base.maximum_shift_s,20.)
        self.base.deadline = float('inf')

    def evaluate(self, vector):
        vector = np.asarray(vector)
        slopes = vector[self.size:-1]
        self.likelihood.slopes = slopes.copy()
        self.likelihood.coefficient = float(vector[-1])
        value, gradient = self.base.evaluate(vector[:self.size])
        if self.base.last is None:
            return value, np.r_[gradient,np.zeros(self.n_satellites+1)]
        pg = self.likelihood.last_result['prediction_gradient']
        slope_gradient = -np.sum(pg*self.slope_features,axis=0)+slopes/SLOPE_SIGMA_HZ_S**2
        cgradient = -np.sum(pg*self.features)
        penalty = .5*np.sum((slopes/SLOPE_SIGMA_HZ_S)**2)
        return value+penalty, np.r_[gradient,slope_gradient,cgradient]

    def curvature(self, vector):
        base_vector = vector[:self.size]
        h = np.zeros((len(vector),len(vector)))
        h[:self.size,:self.size] = _fisher_system(self.base,base_vector,self.base.last)[0]
        _, visible, jac = self.base.predict(base_vector,with_jacobian=True)
        w = self.likelihood.last_result['row_association_probability']*visible/self.base.sigma_hz**2
        temporary = np.zeros_like(w)
        for j in range(self.n_satellites):
            temporary[:,j] = w[:,j]*self.slope_features[:,j]
            cross = self.base.vector_gradient(jac.transpose_multiply(temporary.ravel()),base_vector)
            h[:self.size,self.size+j] = cross
            h[self.size+j,:self.size] = cross
            temporary[:,j] = 0.
        cross = self.base.vector_gradient(jac.transpose_multiply((w*self.features).ravel()),base_vector)
        h[:self.size,-1] = cross
        h[-1,:self.size] = cross
        h[self.size:-1,self.size:-1] = np.diag(np.sum(w*self.slope_features**2,axis=0)+1/SLOPE_SIGMA_HZ_S**2)
        cross = np.sum(w*self.slope_features*self.features,axis=0)
        h[self.size:-1,-1] = cross
        h[-1,self.size:-1] = cross
        h[-1,-1] = np.sum(w*self.features**2)
        return h


def start_vector(obj, seed, arm):
    start = feasible_start(obj,seed,20.,arm)
    return np.r_[start[:obj.size],seed.get('satellite_drift_hz_s',np.zeros(obj.n_satellites)),start[-1]]


def diagnostics(obj, data, record):
    from render_leave_one_satellite_out import check_stationarity
    obj.base.deadline = float('inf')
    v = np.asarray(record['vector'])
    score, kkt = check_stationarity(obj,record,4.)
    probability = obj.likelihood.last_result['row_association_probability'].copy()
    data_nll = -obj.likelihood.last_result['total_log_likelihood']
    timing = obj.base.penalty(v[:obj.size])[0]
    drift = .5*np.sum((v[obj.size:-1]/SLOPE_SIGMA_HZ_S)**2)
    np.testing.assert_allclose(score,data_nll+timing+drift,atol=1e-7,rtol=0)
    predicted, visible = obj.base.predict(v[:obj.size])
    predicted += obj.likelihood.correction()
    alias = obj.likelihood.alias_hz
    residual = (data.measured[:,None]-predicted+alias/2)%alias-alias/2
    owner = np.array([np.flatnonzero(data.numbers==n)[0] for n in data.owners])
    row = np.arange(len(owner))
    return dict(objective=float(score), data_nll=float(data_nll), timing_prior_nll=float(timing),
        drift_prior_nll=float(drift), kkt=float(kkt),
        distance_m=float(1000*np.linalg.norm(record['point_km'])),
        converged=bool(kkt<=1e-3 and not record['fixed_location']),
        boundary=bool(np.linalg.norm(record['point_km'])>=3.9999),
        owner_rms_hz=float(np.sqrt(np.mean(residual[row,owner]**2))),
        posterior_weighted_rms_hz=float(np.sqrt(np.sum(probability*residual**2)/np.sum(probability))),
        strong_original_owner_windows=int(sum(probability[row,owner]>.5)),
        strong_soft_windows=int(sum(probability.max(axis=1)>.5)),
        visible_original_owner_windows=int(sum(visible[row,owner])),
        satellite_drift_rms_hz_s=float(np.sqrt(np.mean(v[obj.size:-1]**2))),
        satellite_drift_max_abs_hz_s=float(np.max(abs(v[obj.size:-1]))))


def run(task):
    scan, arm, mode = task
    target = OUT/f'{scan}-{arm}-{mode}.json'
    if target.exists():
        return str(target)
    data, meta, older = load(scan)
    source = SOURCE/scan/f'{arm}-count-control-position.json'
    previous = json.loads(source.read_text())
    # The preceding selection control reserialized the original arrays into a
    # different NPZ container. Verify values/row identity, not container bytes.
    from regularized_localization import read_input, FIELDS
    control, control_meta = read_input(scan,'count-control')
    assert previous['input_sha256']==control_meta['input_sha256']
    for key in FIELDS:
        np.testing.assert_allclose(getattr(data,key),getattr(control,key),atol=1e-7,rtol=0,err_msg=key)
    obj = SatelliteDriftObjective(data,meta['rf_center_hz'],arm,mode)
    records = []
    def fitted(stage, seed, point, budget, fixed=False):
        r = fit(obj,start_vector(obj,seed,arm),point,budget,fixed,radius_km=4.)
        r.update(stage=stage,satellite_drift_hz_s=r['vector'][obj.size:-1])
        records.append(r)
        return r
    association_seed = dict(parameters=data.initial,coefficient=meta['seed_coefficient'],point_km=[0.,0.])
    seeds = [older['arms'][arm]['roof'],previous['best'],association_seed]
    roofs = [fitted(f'roof-{i}',s,[0.,0.],BUDGET['roof'],True) for i,s in enumerate(seeds)]
    roof = min(roofs,key=lambda r:r['objective'])
    probes = []
    for i,angle in enumerate(np.arange(4)*np.pi/2):
        point = 3.2*np.array([np.cos(angle),np.sin(angle)])
        probes.append(fitted(f'probe-{i}',roof,point,BUDGET['probe'],True))
    starts = [roof,previous['best'],min(probes,key=lambda r:r['objective'])]
    for i,seed in enumerate(starts):
        fitted(f'search-{i}',seed,seed['point_km'],BUDGET['search'])
    for stage in ('polish','final_polish'):
        best = best_record(records)
        fitted(stage,best,best['point_km'],BUDGET[stage])
    best = best_record(records)
    metrics = diagnostics(obj,data,best)
    np.testing.assert_allclose(metrics['objective'],best['objective'],atol=1e-7,rtol=0)
    np.testing.assert_allclose(metrics['kkt'],best['kkt_residual'],atol=1e-7,rtol=0)
    assert np.linalg.norm(best['point_km'])<=4.+1e-7
    assert np.max(abs(np.asarray(best['parameters'])[6:]))<=20.+1e-7
    if mode=='control':
        assert metrics['objective']<=previous['objective']+1e-7
    result = dict(scope=__doc__,scan=scan,arm=arm,mode=mode,input_sha256=meta['input_sha256'],
        source=str(source),source_sha256=digest(source),implementation_sha256=digest(Path(__file__)),
        numbers=data.numbers,windows=len(data.times),fit_original_rows=data.original_rows,
        evaluation_original_rows=data.original_rows,heldout_original_rows=[],
        maximum_budgets_s=BUDGET,roof_starts=3,spatial_starts=3,radius_km=4.,
        total_timing_bound_s=20.,common_timing_bound_s=10.,slope_prior_sigma_hz_s=SLOPE_SIGMA_HZ_S,
        slope_time_centers_s=obj.time_centers,slope_reference_rf_hz=REFERENCE_RF_HZ,
        best=best,roof=roof,records=records,**metrics)
    target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
    print('SATELLITE DRIFT',scan,arm,mode,round(metrics['distance_m']),best['status'],
          'drift RMS',round(metrics['satellite_drift_rms_hz_s'],2),flush=True)
    return str(target)


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scans',nargs='+',default=SCANS,choices=SCANS)
    parser.add_argument('--modes',nargs='+',default=MODES,choices=MODES)
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=4) as pool:
        tasks = [(s,a,m) for s in args.scans for a in ARMS for m in args.modes]
        for f in as_completed([pool.submit(run,t) for t in tasks]):
            f.result()
