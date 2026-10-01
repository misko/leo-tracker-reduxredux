"""Geometry derivatives for the existing Hermite-position visibility calculation."""
import numpy as np
from elevation_geometry import elevation_jacobian


def hermite_position_rate(bank,times,offsets):
    query=np.asarray(times)[None,:]+np.asarray(offsets)[:,None]
    spacing=bank.times_s[1]-bank.times_s[0]
    if np.any(query<bank.times_s[1]) or np.any(query>bank.times_s[-2]):
        raise ValueError('prediction time lacks four-knot orbit support')
    interval=np.floor((query-bank.times_s[0])/spacing).astype(int)
    interval=np.clip(interval,0,len(bank.times_s)-2);sat=np.arange(len(offsets))[:,None]
    u=(query-bank.times_s[interval])/spacing
    p0=bank.positions_ecef_km[sat,interval];p1=bank.positions_ecef_km[sat,interval+1]
    v0=bank.velocities_ecef_km_s[sat,interval];v1=bank.velocities_ecef_km_s[sat,interval+1]
    return ((6*u*u-6*u)[...,None]*p0/spacing+(3*u*u-4*u+1)[...,None]*v0
            +(-6*u*u+6*u)[...,None]*p1/spacing+(3*u*u-2*u)[...,None]*v1)


def visibility_geometry(likelihood,state,receiver_mapping,ellipsoid_scales,spatial_step=.001):
    state=np.asarray(state,dtype=float)
    receiver=receiver_mapping(state[0],state[1]);receiver_jac=np.zeros((3,3))
    for d in [0,1]:
        delta=np.zeros(2);delta[d]=spatial_step
        receiver_jac[:,d]=(receiver_mapping(*(state[:2]+delta))-receiver_mapping(*(state[:2]-delta)))/(2*spatial_step)
    offsets=state[2]+state[5:]
    position,_=likelihood._orbit_states_per_satellite(offsets)
    rate=hermite_position_rate(likelihood.bank,likelihood.times,offsets)
    line=position-receiver
    dl=np.broadcast_to(-receiver_jac,line.shape+(3,)).copy();dl[...,2]=rate
    normal=np.broadcast_to(receiver/ellipsoid_scales,line.shape)
    dn=np.broadcast_to(receiver_jac/ellipsoid_scales[:,None],dl.shape)
    margins,jac=elevation_jacobian(line,normal,dl,dn)
    return margins+likelihood.config.horizon_margin_deg,jac
