"""Target-excluded, family-balanced residual predictions at requested times."""
import numpy as np


def time_pairs(left,right,tolerance_s=1.):
    a,b=np.asarray(left,float),np.asarray(right,float)
    if a.ndim!=1 or b.ndim!=1 or not np.isfinite(np.r_[a,b,tolerance_s]).all() or tolerance_s<0:
        raise ValueError('finite time vectors and nonnegative tolerance required')
    offers=sorted((abs(x-y),i,j) for i,x in enumerate(a) for j,y in enumerate(b) if abs(x-y)<=tolerance_s)
    used_a=set();used_b=set();pairs=[]
    for _,i,j in offers:
        if i not in used_a and j not in used_b:pairs.append((i,j));used_a.add(i);used_b.add(j)
    return np.asarray(sorted(pairs),int).reshape(-1,2)


def predict(target,witnesses,*,width_s,relation='same_receiver',scaling='hz',minimum_families=2):
    if not np.isfinite(width_s) or width_s<=0 or scaling not in ('hz','fractional') or relation not in ('same_receiver','same_receiver_band','other_receiver','same_satellite'):
        raise ValueError('valid kernel width, scaling and witness relation required')
    if minimum_families<1:raise ValueError('positive family requirement needed')
    times=np.asarray(target['times_s'],float);families={}
    if times.ndim!=1 or not len(times) or not np.isfinite(times).all() or not np.isfinite(target['rf_hz']) or target['rf_hz']<=0:
        raise ValueError('finite target times and positive frequency required')
    for w in witnesses:
        if w['component']==target['component']:continue
        same=w['norad']==target['norad']
        if relation=='same_satellite':eligible=same
        else:
            eligible=not same and ((w['receiver']!=target['receiver']) if relation=='other_receiver' else w['receiver']==target['receiver'])
            if relation=='same_receiver_band':eligible &= (w['channel']>4)==(target['channel']>4)
        if not eligible:continue
        t=np.asarray(w['times_s']);r=np.asarray(w['residual_hz'])
        if not len(t):continue
        if t.shape!=r.shape or not np.isfinite(np.r_[t,r]).all():raise ValueError('finite matching witness observations required')
        if not np.isfinite(w['rf_hz']) or w['rf_hz']<=0:raise ValueError('positive witness frequency required')
        weight=np.exp(-.5*((times[:,None]-t)/width_s)**2)
        weight[abs(times[:,None]-t)>3*width_s]=0
        value=r/(w['rf_hz']/11.5e9 if scaling=='fractional' else 1.)
        num,den=families.setdefault(w['norad'],(np.zeros(len(times)),np.zeros(len(times))))
        num+=weight@value;den+=weight.sum(axis=1)
    forecasts=[];available=[]
    for num,den in families.values():
        mask=den>1e-12;forecasts.append(np.divide(num,den,out=np.zeros_like(num),where=mask));available.append(mask)
    if forecasts:
        count=np.sum(available,axis=0);estimate=np.sum(forecasts,axis=0)/np.maximum(count,1)
    else:count=np.zeros(len(times),int);estimate=np.zeros(len(times))
    if scaling=='fractional':estimate*=target['rf_hz']/11.5e9
    qualified=count>=minimum_families;estimate[~qualified]=0
    return dict(prediction_hz=estimate,distinct_families=count,qualified=qualified,
                witness_families=sorted(families),fallback='zero correction when family support is insufficient')
