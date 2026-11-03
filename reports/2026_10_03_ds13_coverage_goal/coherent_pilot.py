"""Common complex source amplitudes across frames; conditional model check."""
import numpy as np


def fit_frames(y,design,train_frames):
    train_frames=np.asarray(train_frames,bool)
    beta=np.linalg.lstsq(design[train_frames].reshape(-1,design.shape[-1]),y[train_frames].ravel(),rcond=None)[0]
    prediction=design@beta
    return (float(np.sum(abs(y[train_frames]-prediction[train_frames])**2)),
            float(np.sum(abs(y[~train_frames]-prediction[~train_frames])**2)),beta)


def compare_frames(y,reference,times,train_frames,frequencies,refine=False):
    def design(freq):return reference[None,:,None]*np.exp(2j*np.pi*times[:,:,None]*np.array(freq)[None,None,:])
    center=float(np.mean(frequencies));best=None
    for freq in center+np.arange(-1000.,1000.001,10.):
        fit=fit_frames(y,design([freq]),train_frames)
        if best is None or fit[0]<best[0]:best=(*fit,float(freq))
    if refine:
        from scipy.optimize import minimize_scalar
        objective=lambda freq:fit_frames(y,design([freq]),train_frames)[0]
        optimum=minimize_scalar(objective,bounds=(max(center-1000,best[3]-10),min(center+1000,best[3]+10)),
            method='bounded',options={'xatol':.001})
        fitted=fit_frames(y,design([optimum.x]),train_frames)
        if fitted[0]<best[0]:best=(*fitted,float(optimum.x))
    two=design(frequencies);two_train,two_test,beta=fit_frames(y,two,train_frames)
    normalized=two[train_frames].reshape(-1,2);normalized=normalized/np.linalg.norm(normalized,axis=0)
    zero=float(np.sum(abs(y[~train_frames])**2))
    return dict(one_train_sse=best[0],one_test_sse=best[1],one_cfo_hz=best[3],
        one_frequency_grid_boundary=abs(best[3]-center)>=999.9,two_train_sse=two_train,two_test_sse=two_test,
        two_over_one_test_sse=two_test/best[1],template_correlation=float(abs(np.vdot(normalized[:,0],normalized[:,1]))),
        normalized_design_condition=float(np.linalg.cond(normalized)),zero_prediction_test_sse=zero,
        one_test_gain_fraction_vs_zero=(zero-best[1])/zero,two_test_gain_fraction_vs_zero=(zero-two_test)/zero,
        one_amplitude=float(abs(best[2][0])),two_amplitudes=abs(beta).tolist())
