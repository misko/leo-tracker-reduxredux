"""Transport an existing fixed band contrast into the same joint calibration."""
import numpy as np
from leo.analysis.shared_scan_model import SmoothVisibilityModel,SharedScanObjective,donor_state


def unfreeze(frozen_model,fit,shift,joint):
    """Preserve predictions and priors; expose only the existing band offsets."""
    if (joint.group_count!=joint.offset_count or joint.sigma_hz!=50000.
            or tuple(joint.frame.receivers)!=tuple(shift.receivers)
            or frozen_model.original.group_count):
        raise ValueError('Compatible offset-only joint frame and original contrast prior required')
    if (joint.observations.window_ids!=frozen_model.observations.window_ids
            or not np.array_equal(joint.bank.numbers,frozen_model.bank.numbers)):
        raise ValueError('Same original training inventory and candidate order required')
    v=np.array(fit['vector'],float,copy=True);n=np.array(fit['nuisance'],float,copy=True)
    if v.shape!=(frozen_model.size,):raise ValueError('Original physical vector shape differs')
    frozen_model.split(n)
    for rx,fraction,offset in zip(joint.frame.receivers,joint.frame.high_fractions,shift.offsets_hz,strict=True):
        v[2+2*rx]+=fraction*offset
    nn=np.r_[n[:joint.clock_count],shift.offsets_hz,n[frozen_model.base_nuisance_count:]]
    model=SmoothVisibilityModel(joint,frozen_model.mask,width=frozen_model.visibility_width)
    old=frozen_model.evaluate_joint(fit['vector'],fit['nuisance'])
    new=model.evaluate_joint(v,nn)
    original_correction=frozen_model.original.correction(fit['vector'],n[:frozen_model.base_nuisance_count])
    new_correction=joint.correction(v,nn[:model.base_nuisance_count])
    frequency_error=float(np.max(abs(original_correction-new_correction)))
    objective_error=abs(old[0]-new[0]);likelihood_error=abs(old[3].nll-new[3].nll)
    posterior_error=float(np.max(abs(old[3].responsibilities-new[3].responsibilities)))
    if frequency_error>=1e-6 or max(objective_error,likelihood_error)>=1e-7 or posterior_error>=1e-8:
        raise ValueError('Joint initialization does not preserve the frozen physical model')
    return model,v,nn,dict(frequency_maximum_error_hz=frequency_error,
        objective_error=float(objective_error),nll_error=float(likelihood_error),
        posterior_maximum_error=posterior_error,
        initial_band_offsets_hz=np.array(shift.offsets_hz).tolist())


def freeze(model,fit):
    """Freeze fitted offsets solely for prediction, preserving the learned q tail."""
    v=np.array(fit['vector']);n=np.array(fit['nuisance'])
    raw,shift,vv,clock,error=donor_state(model.original,
        dict(vector=v,nuisance=n[:model.base_nuisance_count]))
    frozen=SharedScanObjective(raw,shift,mask=model.mask)
    nn=np.r_[clock,n[model.base_nuisance_count:]]
    before=model.evaluate_joint(v,n);after=frozen.evaluate_joint(vv,nn)
    objective_error=abs(before[0]-after[0]);nll_error=abs(before[3].nll-after[3].nll)
    posterior_error=float(np.max(abs(before[3].responsibilities-after[3].responsibilities)))
    if max(objective_error,nll_error)>=1e-7 or posterior_error>=1e-8:
        raise ValueError('Refreezing the trained joint endpoint changes its score or predictions')
    return frozen,dict(vector=vv,nuisance=nn),shift,dict(frequency_maximum_error_hz=error,
        objective_error=float(objective_error),nll_error=float(nll_error),
        posterior_maximum_error=posterior_error,band_offsets_hz=shift.offsets_hz.tolist())
