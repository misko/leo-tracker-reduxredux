"""Report-local, orbit-only anisotropic covariance; no RF/GPS estimation.

History is a correlated TLE-disagreement proxy, not independent orbit truth.
The baseline three physical directions and zero-mean Gaussian are retained.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np

POLICY = dict(
    version="causal-anisotropic-v1", minimum_epochs=3, minimum_span_hours=12,
    epoch_spacing_hours=6, maximum_age_hours=72, shrinkage_to_identity=.5,
    covariance_eigenvalue_bounds=[1., 16.], minimum_represented_energy_fraction=.5,
    sample_times="minimum, midpoint, maximum timestamp of all native observations", maximum_alignment_s=120.,
    alignment_maximum_steps=8, alignment_tolerance_s=1e-7,
    historical_distribution="uncentered coefficient second moment; zero prior mean",
    temporal_correlation="not independent; no sample-count precision or confidence claim",
    baseline_history_reuse="replace by shrunk second moment, never add independent information",
    unsupported_variance="report residual; no additional modes; fallback if less than half represented",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def element_sha(lines):
    return hashlib.sha256(("\n".join(lines)+"\n").encode()).hexdigest()


def tle_epoch(lines):
    from sgp4.api import Satrec
    sat = Satrec.twoline2rv(*lines)
    return int(round((sat.jdsatepoch-2440587.5+sat.jdsatepochF)*86400e9))


def validate_and_select(raw, nominal, cutoff, origin, family):
    """Require availability receipts, not element epoch alone; thin updates."""
    if raw["cutoff_utc_ns"] != cutoff or raw["origin_utc_ns"] != origin or cutoff > origin:
        raise ValueError("History timing differs from scan cutoff/origin")
    from sgp4.api import Satrec
    p = nominal.get("provenance", nominal)
    if int(Satrec.twoline2rv(*nominal["lines"]).satnum) != int(family):
        raise ValueError("Nominal TLE satellite number differs from selected family")
    epoch = tle_epoch(nominal["lines"])
    digest = p.get("snapshot_digest", "").removeprefix("sha256:")
    if not (p.get("collected_utc_ns", cutoff+1) <= cutoff and epoch <= cutoff
            and len(digest) == 64):
        raise ValueError("Nominal element availability or snapshot digest unverified")
    sources = {(s["collected_utc_ns"], s["sha256"].removeprefix("sha256:"))
               for s in raw["sources"]}
    nominal_sources = [collected for collected,source_digest in sources
                       if source_digest==digest and collected<=p["collected_utc_ns"]]
    if not nominal_sources:
        raise ValueError("Nominal availability and snapshot digest not bound by history source ledger")
    if abs(p.get("element_epoch_utc_ns",epoch)-epoch)>2048:
        raise ValueError("Nominal provenance epoch differs from actual TLE bytes")
    records = raw["past_versions"].get(str(family), [])
    by_epoch = {}
    excluded = []
    oldest = cutoff-int(POLICY["maximum_age_hours"]*3.6e12)
    for r in records:
        ep, collected = r["epoch"], r.get("collected_utc_ns")
        sd = r.get("snapshot_sha256", "").removeprefix("sha256:")
        if collected is None or ep > cutoff or collected > cutoff:
            raise ValueError("History contains unavailable or post-cutoff element")
        if (collected, sd) not in sources or len(sd) != 64:
            raise ValueError("History source receipt does not bind collection and hash")
        if int(Satrec.twoline2rv(*r["lines"]).satnum) != int(family):
            raise ValueError("Historical TLE satellite number differs from selected family")
        if abs(tle_epoch(r["lines"])-ep) > 2048:
            raise ValueError("History epoch differs from actual TLE bytes")
        if not oldest <= ep < epoch-1_000_000_000 or collected < oldest:
            excluded.append(dict(epoch_utc_ns=ep, reason="not older eligible 72-hour epoch"))
            continue
        if ep not in by_epoch or collected < by_epoch[ep]["collected_utc_ns"]:
            by_epoch[ep] = r
    selected = []
    for r in sorted(by_epoch.values(), key=lambda x:-x["epoch"]):
        if not selected or selected[-1]["epoch"]-r["epoch"] >= int(POLICY["epoch_spacing_hours"]*3.6e12):
            selected.append(r)
    span = (selected[0]["epoch"]-selected[-1]["epoch"])/3.6e12 if selected else 0.
    info = dict(raw_target_versions=len(records), eligible_distinct_epochs=len(by_epoch),
                selected_epochs=len(selected), selected_span_hours=span, excluded=excluded,
                nominal_element_sha256=element_sha(nominal["lines"]),
                nominal_epoch_utc_ns=epoch, nominal_collected_utc_ns=p["collected_utc_ns"],
                nominal_snapshot_first_verified_collection_utc_ns=min(nominal_sources),
                nominal_receipt_policy="same snapshot bytes available no later than nominal receipt; duplicate collections may be deduplicated",
                nominal_snapshot_sha256=digest,
                history_records=[dict(element_sha256=element_sha(r["lines"]), epoch_utc_ns=r["epoch"],
                                      collected_utc_ns=r["collected_utc_ns"],
                                      snapshot_sha256=r["snapshot_sha256"]) for r in selected])
    if len(selected) < POLICY["minimum_epochs"] or span < POLICY["minimum_span_hours"]:
        return [], dict(info, unsupported_reason="insufficient separated causal history")
    return selected, info


def shrunk_covariance(coefficients):
    """PSD shrinkage with unchanged baseline floor and predeclared SD4 ceiling."""
    a = np.asarray(coefficients, float)
    if a.ndim != 2 or a.shape[1] != 3 or not len(a) or not np.isfinite(a).all():
        raise ValueError("Finite nonempty three-mode history coefficients required")
    second = a.T@a/len(a)
    raw = POLICY["shrinkage_to_identity"]*np.eye(3)+(1-POLICY["shrinkage_to_identity"])*second
    eig, vec = np.linalg.eigh(raw)
    bounded = np.clip(eig, *POLICY["covariance_eigenvalue_bounds"])
    covariance = (vec*bounded)@vec.T
    covariance = (covariance+covariance.T)/2
    return covariance, dict(second_moment=second.tolist(), unbounded_eigenvalues=eig.tolist(),
                            bounded_eigenvalues=bounded.tolist(),
                            eigenvalue_clipped_count=int(np.sum(abs(eig-bounded)>1e-10)))


def _phase_states(sat, origin, times, phase=0.):
    from analyze_dsx01_fixed_site import ecef_states
    from leo.sky.propagation import ElementSetCatalogue
    from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
    cat = ElementSetCatalogue((str(sat.satnum),), (sat.satnum,), (sat,))
    p, v, valid = ecef_states(cat, origin, times+phase)
    if not valid.all():
        raise ValueError("Historical common-epoch propagation failed")
    angle = EARTH_ROTATION_RAD_S*phase
    for x in (p, v):
        first, second = x[...,0].copy(), x[...,1].copy()
        x[...,0] = np.cos(angle)*first-np.sin(angle)*second
        x[...,1] = np.sin(angle)*first+np.cos(angle)*second
    return p[0], v[0]


def _vector(p, v, tau):
    return np.r_[p.ravel(), (tau*v).ravel()]


def project_disagreements(scan, local, mode_bank, nominal, rows, times):
    """Common-epoch ECEF position/velocity projection after orbit-only phase fit."""
    from sgp4.api import Satrec
    from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
    times = np.asarray(times,float)
    origin = scan.receipt["origin_utc_ns"]
    nsat = Satrec.twoline2rv(*nominal["lines"])
    np_, nv = _phase_states(nsat, origin, times)
    inertial = nv.copy()
    inertial[:,0] -= EARTH_ROTATION_RAD_S*np_[:,1]
    inertial[:,1] += EARTH_ROTATION_RAD_S*np_[:,0]
    tau = float(np.median(np.linalg.norm(np_,axis=1)/np.linalg.norm(inertial,axis=1)))
    target = _vector(np_,nv,tau)
    plus = _phase_states(nsat,origin,times,.01)
    minus = _phase_states(nsat,origin,times,-.01)
    phase_direction = (_vector(*plus,tau)-_vector(*minus,tau))/.02
    phase_direction /= np.linalg.norm(phase_direction)
    phase_projector = np.eye(len(target))-np.outer(phase_direction,phase_direction)
    columns = []
    for k in range(3*local,3*local+3):
        p = np.stack([np.interp(times, mode_bank["time_s"], mode_bank["position_km"][k,:,j]) for j in range(3)],axis=1)
        v = np.stack([np.interp(times, mode_bank["time_s"], mode_bank["velocity_km_s"][k,:,j]) for j in range(3)],axis=1)
        columns.append(_vector(p,v,tau))
    design = phase_projector@np.asarray(columns).T
    singular = np.linalg.svd(design,compute_uv=False)
    if singular[-1] <= singular[0]*1e-8:
        raise ValueError("Three physical directions not resolved in orbital state space")
    coefficients, details, full_energy, residual_energy = [], [], 0., 0.
    for row in rows:
        sat = Satrec.twoline2rv(*row["lines"])
        phase = 0.
        converged = False
        for iteration in range(POLICY["alignment_maximum_steps"]):
            value = _vector(*_phase_states(sat,origin,times,phase),tau)
            hi = _vector(*_phase_states(sat,origin,times,phase+.01),tau)
            lo = _vector(*_phase_states(sat,origin,times,phase-.01),tau)
            derivative = (hi-lo)/.02
            step = -float((value-target)@derivative/(derivative@derivative))
            phase += step
            if abs(phase)>POLICY["maximum_alignment_s"]:
                raise ValueError("Historical orbital phase alignment exceeds declared bound")
            if abs(step)<POLICY["alignment_tolerance_s"]:
                converged = True
                break
        if not converged:
            raise ValueError("Historical orbital phase alignment did not converge within declared steps")
        delta = phase_projector@(_vector(*_phase_states(sat,origin,times,phase),tau)-target)
        a = np.linalg.lstsq(design,delta,rcond=1e-8)[0]
        residual = delta-design@a
        energy, remaining = float(delta@delta),float(residual@residual)
        full_energy += energy
        residual_energy += remaining
        coefficients.append(a)
        details.append(dict(epoch_utc_ns=row["epoch"], alignment_s=phase, alignment_converged=True,
                            alignment_steps=iteration+1, final_alignment_step_s=step,
                            coefficients=a.tolist(), phase_removed_state_energy_km2=energy,
                            projection_residual_energy_km2=remaining))
    represented = 1-residual_energy/max(full_energy,1e-30)
    return np.asarray(coefficients),dict(orbital_velocity_timescale_s=tau,
        state_design_singular_values=singular.tolist(), represented_energy_fraction=represented,
        historical_projection=details, residual_phase_tangent_removed=True,
        common_epoch_utc_ns=[origin+int(t*1e9) for t in times])


def transform_mode_bank(bank, local, covariance):
    """Right-transform exactly three columns; integrated coefficients stay N(0,I)."""
    covariance = np.asarray(covariance,float)
    if covariance.shape != (3,3) or not np.allclose(covariance,covariance.T):
        raise ValueError("Symmetric three-mode covariance required")
    root = np.linalg.cholesky(covariance)
    result = dict(bank)
    for key in ("position_km","velocity_km_s"):
        result[key] = np.asarray(bank[key]).copy()
        result[key][3*local:3*local+3] = np.einsum("ij,itk->jtk",root,result[key][3*local:3*local+3])
    return result


def candidate_context(d,z,metadata):
    """Return (context, JSON receipt); unavailable evidence is explicit fallback."""
    from algo07_science import engine as e
    receipt = dict(policy=POLICY, status="fallback", applied=False, added_columns=0,
                   RF_or_GPS_used_for_covariance=False, causal_qualification="unverified")
    try:
        family = metadata.get("selected_family")
        if family is None:
            _,eligible = e.rank_families(d,z)
            if not eligible:
                receipt["reason"] = "no generic RF influence trigger"
                return d,receipt
            family = eligible[0]
        receipt["selected_family"] = int(family)
        base = d["problems"]["fitted_c"][0]
        j = next((j for j in base.labels if int(d["scan"].norads[j])==family),None)
        if j is None or j not in base.supported:
            receipt["reason"] = "target lacks existing supported three physical modes"
            return d,receipt
        native = Path(z["native_path"])
        history_path = native.parent/"causal_phase_history"/(native.name+".json")
        nominal_path = native/"nominal_elements.json"
        receipt.update(history_path=str(history_path), nominal_elements_path=str(nominal_path))
        raw = json.loads(history_path.read_text())
        receipt.update(history_sha256=sha(history_path),nominal_elements_sha256=sha(nominal_path))
        if raw["latest_elements_sha256"] != receipt["nominal_elements_sha256"]:
            raise ValueError("History not bound to actual nominal elements file")
        scan = d["scan"]
        nominal = scan.elements[str(family)]
        original_nominal = json.loads(nominal_path.read_text())[str(family)]
        if nominal["lines"] != original_nominal["lines"]:
            raise ValueError("Context target differs from history-bound nominal element")
        rows,info = validate_and_select(raw,nominal,z["scan_receipt"]["cutoff_utc_ns"],scan.receipt["origin_utc_ns"],family)
        receipt.update(info,causal_qualification="verified epoch and archived availability receipts")
        if not rows:
            receipt["reason"] = info["unsupported_reason"]
            return d,receipt
        observations_path = native/"observations.json"
        observation_times = np.asarray([r["time_s"] for r in json.loads(observations_path.read_text())],float)
        if not len(observation_times) or not np.isfinite(observation_times).all():
            raise ValueError("Finite native observation temporal extent required")
        times = np.array([observation_times.min(),(observation_times.min()+observation_times.max())/2,
                          observation_times.max()])
        if times[0] < base.mode_bank["time_s"][0] or times[-1] > base.mode_bank["time_s"][-1]:
            raise ValueError("Native observation extent exceeds physical mode bank")
        receipt.update(temporal_extent_source=str(observations_path),temporal_extent_source_sha256=sha(observations_path),
                       projection_times_s=times.tolist())
        a,projection = project_disagreements(scan,base.labels.index(j),base.mode_bank,nominal,rows,times)
        receipt.update(projection)
        if projection["represented_energy_fraction"] < POLICY["minimum_represented_energy_fraction"]:
            receipt["reason"] = "historical discrepancy poorly represented by existing three modes"
            return d,receipt
        covariance,info = shrunk_covariance(a)
        receipt.update(info,coefficient_covariance=covariance.tolist(),
                       status="ready",applied=True,reason="separated causal history supports existing modes",
                       coefficient_prior="standard normal after mode transform; original Gaussian determinant retained")
        from probe_ds23_history_calibrated_phase import make_problem
        original = d.get("problem_factory",make_problem)
        def factory(scan,node,keep,arm,reference,powers,means,multiplier,nu):
            p = original(scan,node,keep,arm,reference,powers,means,multiplier,nu)
            target_j = next((k for k in p.labels if int(scan.norads[k])==family),None)
            if target_j is None or target_j not in p.supported:
                raise ValueError("Target physical support changed after frozen covariance construction")
            p.mode_bank = transform_mode_bank(p.mode_bank,p.labels.index(target_j),covariance)
            p.mode_metadata = copy.deepcopy(p.mode_metadata)
            p.mode_metadata[target_j]["causal_anisotropic_covariance"] = covariance.tolist()
            return p
        return dict(d,problem_factory=factory,problems=dict(d["problems"])),receipt
    except (ValueError,KeyError,OSError) as exc:
        receipt.update(reason=str(exc),applied=False,status="fallback")
        return d,receipt
