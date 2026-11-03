"""Batch independent track shape calculations without changing their score."""
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from scipy.optimize import least_squares

from leo.analysis.regional_position_bootstrap import (
    BootstrapMatch,PositionBootstrap,observation_subset,
)
from leo.analysis.regional_position_score import ALIAS_HZ,circular,predict_orbits,zero_sum_basis


def shape_statistics(residual,visible):
    """The original ten-step pseudo-Huber location, independently per track."""
    location=np.median(residual,axis=1)
    active=np.ones(len(residual),bool)
    for _ in range(10):
        weights=1/np.sqrt(1+((residual-location[:,None,:])/200)**2)
        updated=np.sum(weights*residual,axis=1)/weights.sum(axis=1)
        active &= np.max(abs(updated-location),axis=1)>=.01
        location=np.where(active[:,None],updated,location)
        if not active.any():break
    centered=residual-location[:,None,:]
    cost=np.mean(2*200**2*(np.sqrt(1+(centered/200)**2)-1),axis=1)
    cost[np.mean(visible,axis=1)<.9]=np.inf
    rms=np.sqrt(np.mean(centered**2,axis=1))
    return cost,rms


def bootstrap_position(observations,bank,prior,point,tracks,*,maximum_seconds=5.,
                       samples_per_track=6,orbit_predictor=predict_orbits,workers=4):
    if not np.isfinite(maximum_seconds) or not 0<maximum_seconds<=1800 or samples_per_track<3 or not 1<=workers<=4:
        raise ValueError('Invalid bootstrap work bounds')
    begun=time.monotonic();sampled=[];values=[]
    for track in tracks:
        rows=np.asarray(track,int)
        if rows.ndim!=1 or len(rows)<3 or len(np.unique(rows))!=len(rows) or np.any(rows<0) or np.any(rows>=len(observations.window_ids)):
            raise ValueError('Invalid bootstrap track indices')
        if len(np.unique(observations.receiver[rows]))!=1 or len(np.unique(observations.rf_hz[rows]))!=1 or np.any(np.diff(observations.times_s[rows])<=0):
            raise ValueError('Bootstrap track must be ordered in one receiver/RF lane')
        take=np.unique(np.linspace(0,len(rows)-1,min(samples_per_track,len(rows))).astype(int))
        sampled.append(rows[take])
        values.append(np.unwrap(observations.measured_hz[rows]*2*np.pi/ALIAS_HZ)[take]*ALIAS_HZ/(2*np.pi))
    if not sampled:raise ValueError('No bootstrap tracks')
    all_rows=np.concatenate(sampled);unique,inverse=np.unique(all_rows,return_inverse=True)
    sparse=observation_subset(observations,unique);offset=np.r_[0,np.cumsum([len(r) for r in sampled])]
    best=[None]*len(tracks)
    # Group by sample count, avoiding padding, approximation or NaN arithmetic.
    groups=[]
    for length in sorted({len(rows) for rows in sampled}):
        ix=np.array([i for i,rows in enumerate(sampled) if len(rows)==length])
        gather=np.array([inverse[offset[i]:offset[i+1]] for i in ix])
        yy=np.array([values[i] for i in ix])
        groups.append((ix,gather,yy))
    def evaluate_timing(timing):
        prediction,visible,_,_=orbit_predictor(bank,sparse,prior,point,np.full(len(bank.numbers),timing),derivatives=False)
        output=[]
        for ix,gather,yy in groups:
            cost,rms=shape_statistics(yy[:,:,None]-prediction[gather],visible[gather])
            # Bank order need not be catalogue-number order; reproduce the
            # original catalogue-number tie-break explicitly.
            order=np.argsort(bank.numbers,kind='stable');chosen=order[np.argmin(cost[:,order],axis=1)]
            for local,k in enumerate(chosen):
                if not np.isfinite(cost[local,k]):continue
                i=int(ix[local]);key=(float(cost[local,k]),abs(timing),int(bank.numbers[k]),timing)
                output.append((i,key,BootstrapMatch(tuple(tracks[i]),int(k),float(timing),float(rms[local,k]),float(cost[local,k]))))
        return output
    grid=np.arange(-20.,20.001,2.)
    # At most four independent, pure numerical queries are live at once.
    # Consume in original grid order, preserving every tie-break. A bounded
    # cohort finishes before checking the next cohort's work allowance.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0,len(grid),workers):
            if time.monotonic()-begun>=maximum_seconds:
                raise TimeoutError(f'Batched regional bootstrap time budget after {start}/21 timings')
            futures=[pool.submit(evaluate_timing,t) for t in grid[start:start+workers]]
            for future in futures:
                for i,key,match in future.result():
                    if best[i] is None or key<best[i][0]:best[i]=(key,match)
    matches=tuple(row[1] for row in best if row is not None and row[1].shape_rms_hz<2000)
    if {int(observations.receiver[m.rows[0]]) for m in matches}!={0,1}:
        raise ValueError('No accepted bootstrap shapes on both receivers at this point')
    indices=tuple(sorted({m.satellite_index for m in matches},key=lambda i:bank.numbers[i]))
    if len(indices)<2:raise ValueError('Fewer than two bootstrap satellite candidates')
    shifts=np.array([np.median([m.timing_s for m in matches if m.satellite_index==i]) for i in indices])
    common=np.clip(np.mean(shifts),-10,10);shifts=shifts-np.mean(shifts)+common
    shifts*=min(1.,20/max(20,float(np.max(abs(shifts)))));common=float(shifts.mean())
    predicted=orbit_predictor(bank.select(list(indices)),observations,prior,point,shifts,derivatives=False)[0]
    vector=np.zeros(8+len(indices)-1);vector[:2]=point;vector[7]=common;vector[8:]=zero_sum_basis(len(indices)).T@shifts
    centered_time=observations.times_s-observations.time_center_s
    for rx in (0,1):
        rows=[];residuals=[];weights=[]
        for match in matches:
            if observations.receiver[match.rows[0]]!=rx:continue
            ix=np.array(match.rows);rows.extend(ix)
            residuals.extend(circular(observations.measured_hz[ix]-predicted[ix,indices.index(match.satellite_index)]))
            weights.extend([np.sqrt(min(len(ix),100))/len(ix)]*len(ix))
        residuals=np.array(residuals);weights=np.sqrt(weights);times=centered_time[rows]
        counts,edges=np.histogram(residuals,bins=128,range=(-ALIAS_HZ/2,ALIAS_HZ/2));centers=(edges[:-1]+edges[1:])/2
        fits=[]
        for index in np.argsort(-counts,kind='stable')[:3]:
            for slope in (-20.,0.,20.):
                if time.monotonic()-begun>=maximum_seconds:raise TimeoutError('Batched regional receiver-line bootstrap time budget')
                fits.append(least_squares(lambda v,w=weights,r=residuals,t=times:w*circular(r-v[0]-v[1]*t)/200,
                    [centers[index],slope],bounds=([-np.inf,-50],[np.inf,50]),loss='soft_l1',max_nfev=80,x_scale=[200,2]))
        chosen=min(fits,key=lambda f:f.cost);vector[2+2*rx:4+2*rx]=chosen.x
    return PositionBootstrap(indices,vector,matches)
