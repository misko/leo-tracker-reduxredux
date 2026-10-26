"""Read-only exact satellite-state cache; receiver and inference state stay live."""
import hashlib
import json
from pathlib import Path
import numpy as np
from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.sky.frames import geodetic_to_ecef_km,ecef_to_enu_matrix,look_angles
from prototype_dsx01_continuous_position import latlon


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def array_hash(value):
    value=np.ascontiguousarray(value);h=hashlib.sha256()
    h.update(str(value.dtype).encode());h.update(str(value.shape).encode());h.update(value.tobytes())
    return h.hexdigest()


def identity(candidate,nodes):
    import leo.analysis.research.continuous_curve_fit as curve
    import leo.analysis.research.orbit_uncertainty as orbit
    import leo.sky.frames as frames
    inputs=dict(nodes=array_hash(nodes),times=array_hash(candidate['target_track']['times']),
        native_IDs=hashlib.sha256(json.dumps(candidate['target']['observation_ids']).encode()).hexdigest(),
        rf_hz=float(candidate['target_track']['rf_hz']))
    for label,bank in [('nominal',candidate['target_sky']),('modes',candidate['target_mode_bank'])]:
        for name in ('time_s','position_km','velocity_km_s'):inputs[label+'_'+name]=array_hash(bank[name])
    inputs['implementations']={str(Path(module.__file__).resolve()):sha(module.__file__) for module in (curve,orbit,frames)}
    inputs['cache_implementation_sha256']=sha(__file__)
    key=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    return key,inputs


def exact_states(candidate,phases):
    """Same broadcast/interpolation/rotation inputs as original phase_geometry."""
    phases=np.asarray(phases);times=np.asarray(candidate['target_track']['times']);n=len(phases)
    sky=dict(time_s=candidate['target_sky']['time_s']);bank=dict(time_s=candidate['target_mode_bank']['time_s'])
    for name in ('position_km','velocity_km_s'):
        sky[name]=np.broadcast_to(candidate['target_sky'][name],(n,*candidate['target_sky'][name].shape[1:]))
        source=candidate['target_mode_bank'][name]
        bank[name]=np.broadcast_to(source[None],(n,*source.shape)).reshape(n*3,*source.shape[1:])
    flat_times=np.tile(times,n);labels=np.repeat(np.arange(n),len(times))
    position,velocity=paired_phase_states(sky,flat_times,labels,phases)
    expanded=(labels[:,None]*3+np.arange(3)).ravel()
    dp,dv=paired_phase_states(bank,np.repeat(flat_times,3),expanded,np.repeat(phases,3))
    result=np.empty((n,len(times),4,2,3))
    result[:,:,0,0]=position.reshape(n,-1,3);result[:,:,0,1]=velocity.reshape(n,-1,3)
    result[:,:,1:,0]=dp.reshape(n,-1,3,3);result[:,:,1:,1]=dv.reshape(n,-1,3,3)
    return result


class StateCache:
    def __init__(self,directory):
        self.directory=Path(directory);self.maps={};self.metadata={}

    def build(self,candidate,nodes):
        key,inputs=identity(candidate,nodes);self.directory.mkdir(parents=True,exist_ok=True)
        path=self.directory/(key+'.npy');meta=self.directory/(key+'.json')
        if path.exists() or meta.exists():raise FileExistsError('cache construction never overwrites')
        states=np.lib.format.open_memmap(path,mode='w+',dtype=np.float64,shape=(len(nodes),len(candidate['target_track']['times']),4,2,3))
        for begin in range(0,len(nodes),512):states[begin:begin+512]=exact_states(candidate,nodes[begin:begin+512])
        states.flush();del states
        body=dict(key=key,inputs=inputs,states_sha256=sha(path),shape=list(np.load(path,mmap_mode='r').shape),
            q=float(candidate['target_track']['rf_hz']/11.5e9),bytes=path.stat().st_size)
        with meta.open('x') as stream:json.dump(body,stream,indent=2);stream.write('\n')
        return key,body

    def open(self,key):
        if key not in self.maps:
            self.maps[key]=np.load(self.directory/(key+'.npy'),mmap_mode='r')
            self.metadata[key]=json.loads((self.directory/(key+'.json')).read_bytes())
        return self.maps[key]

    def geometry(self,key,position,begin,end):
        states=self.open(key)[begin:end];n,m=states.shape[:2]
        p=states[:,:,0,0].reshape(-1,3);v=states[:,:,0,1].reshape(-1,3)
        dp=states[:,:,1:,0].reshape(-1,3,3);dv=states[:,:,1:,1].reshape(-1,3,3)
        coordinates=latlon(np.asarray(position));observer=geodetic_to_ecef_km(*coordinates,0.)
        _,elevation,_,rate=look_angles(p,v,observer,ecef_to_enu_matrix(*coordinates))
        line=p-observer;distance=np.linalg.norm(line,axis=1);direction=line/distance[:,None]
        mode_rate=np.sum(direction*v,axis=1)
        gradient=(v-mode_rate[:,None]*direction)/distance[:,None]
        derivative=np.einsum('nd,nkd->nk',gradient,dp)+np.einsum('nd,nkd->nk',direction,dv)
        q=self.metadata[key]['q']
        return dict(frequency_hz=(q*(-11.5e9*rate/299792.458)).reshape(n,m),
            shape_columns_hz=(q*(-11.5e9/299792.458*derivative)).reshape(n,m,3),
            elevation_deg=elevation.reshape(n,m))
