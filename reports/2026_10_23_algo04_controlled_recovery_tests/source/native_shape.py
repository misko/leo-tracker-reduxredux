"""Satellite-free polynomial diagnostic; no points removed or tracks changed."""
from pathlib import Path
import numpy as np
from experiment import OUT,CASES,context,PERIOD
from run_algo01_ds23_sample import read,write,sha


def polynomial(times,values,sigma):
    z=(times-times.mean())/max(float(np.ptp(times)),1.)
    fits=[]
    for degree in range(1,min(4,len(times)-3)+1):
        design=np.polynomial.polynomial.polyvander(z,degree)
        coefficient=np.linalg.lstsq(design/sigma[:,None],values/sigma,rcond=None)[0]
        residual=values-design@coefficient
        fits.append(dict(degree=degree,BIC=float(np.sum((residual/sigma)**2)+(degree+1)*np.log(len(times))),
            residual_hz=residual,RMS_hz=float(np.sqrt(np.mean(residual**2))),max_standardized_residual=float(np.max(abs(residual/sigma)))))
    return min(fits,key=lambda r:r['BIC'])


def main():
    rows=[]
    for case in CASES[:3]:
        data=read(OUT/'raw'/case/'physical.json')
        original,_=context(case)
        by_key={t['key']:t for t in original['scan'].tracks}
        for t in data['tracks']:
            if not t['added']:continue
            times=np.array(t['times']);values=np.array(by_key[t['component']]['values']);sigma=np.array(t['sigma_hz'])
            assert np.array_equal(times,by_key[t['component']]['times'])
            alias=(np.asarray(t['native_CFO_hz'])-values)/PERIOD
            assert np.max(abs(alias-np.rint(alias)))<1e-6
            whole=polynomial(times,values,sigma);splits=[]
            for cut in range(8,len(times)-7):
                left=polynomial(times[:cut],values[:cut],sigma[:cut]);right=polynomial(times[cut:],values[cut:],sigma[cut:])
                # Use common total n for parameter penalties, plus split search.
                chi2=sum(np.sum((v['residual_hz']/s)**2) for v,s in [(left,sigma[:cut]),(right,sigma[cut:])])
                bic=float(chi2+(left['degree']+right['degree']+2)*np.log(len(times))+2*np.log(max(1,len(times)-15)))
                splits.append(dict(cut=cut,time_s=float((times[cut-1]+times[cut])/2),BIC=bic,left_degree=left['degree'],right_degree=right['degree']))
            best=min(splits,key=lambda r:r['BIC']) if splits else None
            row=dict(case=case,component=t['component'],norad=t['norad'],points=len(times),persisted_pieces=len(t['pieces']),
                times=times,whole=whole,best_split=best,split_BIC_gain=whole['BIC']-best['BIC'] if best else None,
                last_point_standardized_residual=float(whole['residual_hz'][-1]/sigma[-1]),
                no_orbit_or_radio_model_used=True,no_join_or_split_adopted=True)
            rows.append(row);print(case,t['component'],'degree',whole['degree'],'maxz',whole['max_standardized_residual'],'lastz',row['last_point_standardized_residual'],'splitgain',row['split_BIC_gain'])
    write(OUT/'evidence/native_shape.json',dict(rows=rows,source_sha256=sha(Path(__file__)),
        alias_unwrapped_graph_CFO_matches_native_modulo_PERIOD=True,
        known_nominal_noise_and_BIC_diagnostic_not_independent_validation=True,
        two_piece_fit_does_not_impose_continuity=True,no_points_trimmed=True))


if __name__=='__main__':main()
