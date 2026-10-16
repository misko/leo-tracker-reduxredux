"""Prediction-space B orbit/timing versus frozen calibration decomposition."""

import numpy as np

from leo.analysis.channel_group_calibration import GroupCalibrationObjective
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.hard60_joint_clock import JointClockObjective
from leo.analysis.hard60_score import likelihood, predict_orbits
from leo.analysis.regional_position_score import circular
from leo.analysis.research.band_assignment_audit import compare_assignments


def summary(values):
    a = np.asarray(values,float)
    if not a.size or not np.isfinite(a).all():
        raise ValueError("Finite nonempty diagnostic values required")
    return dict(mean=float(a.mean()),rms=float(np.sqrt(np.mean(a*a))),
                maximum_abs=float(np.max(abs(a))))


def probabilities(terms):
    return np.column_stack((terms.responsibilities,terms.clutter_probability))


def score(measured,prediction,visible,policy):
    terms = likelihood(measured,prediction,visible,policy)
    return dict(nll=float(terms.nll),signal_mass=float(terms.responsibilities.sum()),
                clutter_mass=float(terms.clutter_probability.sum()),
                candidate_occupancy=terms.responsibilities.sum(axis=0).tolist()),terms


def original(model,fit,*,on_objective=None):
    if (not isinstance(model,GroupCalibrationObjective)
            or not isinstance(model.base,JointClockObjective)
            or model.base.likelihood_port is not likelihood
            or model.drift_count or model.group_clock_count):
        raise ValueError("Original B Gaussian/common-clock/constant-group objective required")
    v,n = np.asarray(fit["vector"],float),np.asarray(fit["nuisance"],float)
    if on_objective is not None:
        on_objective()
    value,_,_,terms = model.evaluate_joint(v,n)
    if (not fit["converged"] or abs(value-fit["objective"])>1e-7
            or abs(terms.nll-fit["likelihood_nll"])>1e-7):
        raise ValueError("Original stationary B objective/NLL replay failed")
    obs = model.observations
    frozen = freeze_group_calibration(model,fit)
    correction = frozen.predict(obs.times_s,obs.rf_hz,obs.receiver,obs.channel>=5)
    closure = float(np.max(abs(correction-model.correction(v,n))))
    relative = model.basis@v[8:]
    orbit,visible,_,_ = predict_orbits(model.bank,obs,model.prior,v[:2],v[7]+relative,
                                     derivatives=False)
    _,direct = score(obs.measured_hz,orbit+correction[:,None],visible,model.score)
    if abs(direct.nll-terms.nll)>1e-7:
        raise ValueError("Frozen correction plus original orbit does not close own likelihood")
    clock,group = model.split(n)
    priors = dict(common_timing=float(.5*(v[7]/model.score.common_sigma_s)**2),
                  relative_timing=float(.5*np.sum((relative/model.score.relative_sigma_s)**2)),
                  clock=float(.5*clock@model.base.precision@clock),
                  group=float(.5*group@model.group_precision@group))
    if abs(sum(priors.values())+terms.nll-value)>1e-7:
        raise ValueError("Original B physical priors do not close")
    components = dict(baseline=model.base.baseline,receiver_linear=model.design@v[2:7],
                      clock=model.base.clock_design@clock,group=model.group_design@group)
    if np.max(abs(sum(components.values())-correction))>1e-6:
        raise ValueError("Frozen correction components do not close")
    drift = model.group_design*(obs.times_s-model.group_time_center_s)[:,None]
    row = dict(objective=float(value),nll=float(terms.nll),priors=priors,
               correction_closure_max_hz=closure,point_km=v[:2].tolist(),
               common_timing_s=float(v[7]),relative_timing_s=relative.tolist(),
               fitted_c_hz_per_ghz=float(v[6]),time_center_s=float(obs.time_center_s),
               rf_center_hz=float(obs.rf_center_hz),group_receivers=list(model.frame.receivers),
               group_high_fractions=list(model.frame.high_fractions),
               differential_drift_score_per_hz_s=(drift.T@terms.prediction_gradient.sum(axis=1)).tolist(),
               drift_score_scope="Added drift is zero; zero-centered prior derivative is zero",
               candidate_occupancy=terms.responsibilities.sum(axis=0).tolist())
    return dict(row=row,orbit=orbit,visible=visible,correction=correction,
                frozen=frozen,components=components,terms=terms)


def diagnose(models,fits,*,on_objective=None):
    if set(models)!={"all","low","high"} or set(fits)!=set(models):
        raise ValueError("All three own-view B winners required")
    full = models["all"]
    for m in models.values():
        if (m.prior!=full.prior or m.score!=full.score or any(not np.array_equal(
                getattr(m.bank,k),getattr(full.bank,k)) for k in
                ("numbers","nodes_s","position_km","velocity_km_s"))):
            raise ValueError("Exact shared candidate bank, physical prior and score required")
    states = {v:original(models[v],fits[v],on_objective=on_objective)
              for v in ("all","low","high")}
    ids = list(full.observations.window_ids)
    if len(set(ids))!=len(ids):
        raise ValueError("Unique full-view windows required")
    index = {k:i for i,k in enumerate(ids)}
    halves,results = [],{}
    for view in ("low","high"):
        m,s = models[view],states[view]
        obs,ownids = m.observations,list(m.observations.window_ids)
        if any(k not in index for k in ownids):
            raise ValueError("Half window outside original all observations")
        rows = np.array([index[k] for k in ownids])
        if len(set(ownids))!=len(ownids):
            raise ValueError("Unique half-view windows required")
        for field in ("times_s","rf_hz","receiver","channel","measured_hz"):
            if not np.array_equal(getattr(full.observations,field)[rows],getattr(obs,field)):
                raise ValueError("Same physical timestamp/RF/receiver/channel/measurement required")
        if not np.all((obs.channel<=4) if view=="low" else (obs.channel>=5)):
            raise ValueError("Designated channel halves required")
        halves.append(set(ownids))
        # Evaluate both original frozen functions at precisely the same physical rows.
        arguments = obs.times_s,obs.rf_hz,obs.receiver,obs.channel>=5
        c_all,c_half = (states[v]["frozen"].predict(*arguments) for v in ("all",view))
        if (np.max(abs(c_all-states["all"]["correction"][rows]))>1e-6
                or np.max(abs(c_half-s["correction"]))>1e-6):
            raise ValueError("Original full/half frozen correction functions changed")
        combos = {}
        for orbit_name,orbit,visible in (("all",states["all"]["orbit"][rows],
                                         states["all"]["visible"][rows]),
                                        ("half",s["orbit"],s["visible"])):
            for cal_name,calibration in (("all",c_all),("half",c_half)):
                name = f"orbit-{orbit_name}_calibration-{cal_name}"
                row,terms = score(obs.measured_hz,orbit+calibration[:,None],visible,m.score)
                row["assignment_vs_all"] = compare_assignments(
                    ids,probabilities(states["all"]["terms"]),ownids,probabilities(terms))
                combos[name] = row
        own = combos["orbit-half_calibration-half"]
        if abs(own["nll"]-s["row"]["nll"])>1e-7:
            raise ValueError("Own half combination must replay half likelihood")
        results[view] = dict(combinations=combos,
            total_correction_difference_hz=summary(c_half-c_all),
            wrapped_correction_difference_hz=summary(circular(c_half-c_all)),
            component_difference_hz={k:summary(s["components"][k]-values[rows])
                                      for k,values in states["all"]["components"].items()},
            orbit_difference_hz=summary(s["orbit"]-states["all"]["orbit"][rows]),
            relative_timing_difference_s=summary(np.array(s["row"]["relative_timing_s"])-
                         np.array(states["all"]["row"]["relative_timing_s"])))
    if halves[0]&halves[1] or halves[0]|halves[1]!=set(ids):
        raise ValueError("Disjoint half windows must partition all evidence")
    baseline = sum(r["combinations"]["orbit-all_calibration-all"]["nll"] for r in results.values())
    if abs(baseline-states["all"]["row"]["nll"])>1e-7:
        raise ValueError("Band NLL decomposition must reproduce full likelihood")
    return dict(replay={k:s["row"] for k,s in states.items()},bands=results,
        candidate_numbers=full.bank.numbers.tolist(),objective_calls=3,extra_orbit_calls=3,
        extra_likelihood_calls=11,optimizer_calls=0,reference_usage="none",held_usage="none",
        interpretation="Orbit block combines geography and satellite timing. Hybrid likelihoods "
            "are prediction-space diagnostics, not calibrated-model evidence or feasible states; "
            "physical priors stay separate. Added drift score gives a direction, not accuracy.")
