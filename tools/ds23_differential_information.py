"""Research geometry and value of a simultaneous two-satellite RF contrast."""

from types import SimpleNamespace
import numpy as np
from ds23_height_problem import geometry_features
from leo.analysis.research.retained_track_likelihood import PERIOD,projected_receiver_basis


def covariance_gain(covariance,gradient,sigma):
    c,h=np.asarray(covariance,float),np.asarray(gradient,float)
    if (c.ndim!=2 or c.shape[0]!=c.shape[1] or h.shape!=(len(c),) or len(c)<2
            or not np.isfinite(c).all() or not np.isfinite(h).all() or sigma<=0 or not np.isfinite(sigma)):
        raise ValueError('joint covariance, measurement gradient and positive SD required')
    cross=c@h;variance=float(h@cross+sigma*sigma)
    if variance<=0:raise ValueError('positive predictive measurement variance required')
    updated=c-np.outer(cross,cross)/variance
    return dict(gain_km2=float(cross[:2]@cross[:2]/variance),covariance=updated,
        predictive_variance_hz2=variance)


def difference_query(p,rows,time_s,rf_hz):
    if len(rows)!=2 or rows[0]==rows[1]:raise ValueError('two distinct original curved rows required')
    tracks=[p.scan.tracks[p.members[k]] for k in rows]
    if (tracks[0]['receiver'],tracks[0]['channel'])!=(tracks[1]['receiver'],tracks[1]['channel']):
        raise ValueError('simultaneous contrast requires one receiver/channel')
    rx=tracks[0]['receiver']-1;band=int(tracks[0]['channel']>4);times=np.full(2,float(time_s));q=np.full(2,rf_hz/11.5e9)
    hardware=np.zeros((2,p.hardware.shape[1]));hardware[:,2*rx+band]=PERIOD/np.sqrt(12)
    hardware[:,4+2*rx]=times-150;hardware[:,5+2*rx]=(times-150)*(-1 if band==0 else 1)*.5
    if p.fitted_c:hardware[:,8]=(rf_hz/1e9-11.5)*200000
    smooth=np.zeros((2,p.smooth.shape[1]));width=p.smooth.shape[1]//2
    basis=projected_receiver_basis(times)
    if basis.shape!=(2,width):raise ValueError('original receiver basis required for differential prototype')
    smooth[:,rx*width:(rx+1)*width]=q[:,None]*basis
    constants=np.zeros((2,len(p.members)))
    for k,row in enumerate(rows):constants[k,row]=1000.
    fields=dict(vars(p));fields.update(flat_times=times,
        flat_labels=np.array([p.labels.index(p.rows[k]['candidate_index']) for k in rows]),
        q=q,hardware=hardware,smooth=smooth,constants=constants)
    return SimpleNamespace(**fields)


def differential_gradient(p,rows,time_s,rf_hz,position,coefficient,step_km=.025):
    view=difference_query(p,rows,time_s,rf_hz);x=np.asarray(position,float)
    geometry=geometry_features(view,x,0.);u=geometry['features'][0]-geometry['features'][1]
    nb,ns=p.hardware.shape[1],p.smooth.shape[1]
    if np.max(abs(u[:nb+ns]),initial=0)>1e-10:raise ValueError('simultaneous receiver coordinates failed to cancel')
    physical=u.copy();physical[nb+ns:nb+ns+len(p.labels)]/=p.phase_sigma
    derivatives=[]
    for axis in np.eye(2)*step_km:
        values=[]
        for point in (x-axis,x+axis):
            g=geometry_features(view,point,0.)
            f=view.q*g['intercept']+g['features']@coefficient
            values.append(float(f[0]-f[1]))
        derivatives.append((values[1]-values[0])/(2*step_km))
    return np.r_[derivatives,physical]
