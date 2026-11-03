"""Classical retarded geometric range rate in reception-epoch ECEF."""
import numpy as np
C=299792.458
OMEGA=7.292115e-5

def rotate(v,angle):
    c=np.cos(angle);s=np.sin(angle)
    return np.stack((c*v[...,0]+s*v[...,1],-s*v[...,0]+c*v[...,1],v[...,2]),axis=-1)

def retarded(position,velocity,acceleration,receiver,omega=OMEGA):
    delay=np.linalg.norm(position-receiver,axis=-1)/C
    for _ in range(6):
        emitted=position-velocity*delay[...,None]+.5*acceleration*delay[...,None]**2
        received=rotate(emitted,omega*delay)
        delay=np.linalg.norm(received-receiver,axis=-1)/C
    emitted=position-velocity*delay[...,None]+.5*acceleration*delay[...,None]**2
    received=rotate(emitted,omega*delay)
    vector=received-receiver;length=np.linalg.norm(vector,axis=-1);unit=vector/length[...,None]
    vel=rotate(velocity-acceleration*delay[...,None],omega*delay)
    a=np.sum(unit*vel,axis=-1)
    spin=omega*np.stack((-received[...,1],received[...,0],np.zeros_like(length)),axis=-1)
    b=np.sum(unit*spin,axis=-1)
    rate=a/(1+(a+b)/C)
    return rate,delay,length
