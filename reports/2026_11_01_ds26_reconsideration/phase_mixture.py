"""Whole-family prior prediction integrates unknown phase instead of linearizing it."""
import argparse
import numpy as np
from scipy.special import logsumexp
from reconsider import *
from transfer import gaussian_predict
from ds23_height_problem import geometry_features

def run(case):
    result=read(OUT/case/'result.json');rec=next(r for r in result['records'] if r['hypothesis']['name']==result['selected']);h=rec['hypothesis'];n=rec['target']
    z=read(INPUT/(case+'.json'));original=reconstruct(z);extended,_=extend_history(original,z,case,set(h['mapping'].values()),OUT/case/'mixture_history');updated,_=apply_hypothesis(extended,z,case,h,OUT/case)
    screen=read(OUT/case/str(n)/'screen.json');rows=[]
    for context,d,target,file in [('incumbent',original,n,'transfer_refreshed.json'),('replacement',updated,h['norad'],'transfer_selected_refreshed.json')]:
        source=read(OUT/case/file)['rows']
        for a in ARMS:
            saved=next(r for r in source if r['target']==target and r['arm']==a and r['model']=='full' and r['split']=='whole_family')
            point=np.array(screen['cavity'][a]['x']);p,_=build(d,z,a,np.array(saved['phase']));begin=p.hardware.shape[1]+p.smooth.shape[1]
            local=p.labels.index(list(p.scan.norads).index(target));coordinate=begin+local
            test=np.zeros(len(p.values),bool)
            for r,sl in zip(p.rows,p.slices):
                if r['candidate_norad']==target:test[sl]=p.keep[sl]
            train=p.keep&~test;full_grid=np.linspace(-30,30,151)
            target_times=p.flat_times[p.flat_labels==local]
            lower=max(-30.,float(min(p.sky['time_s'])-min(target_times)+.02))
            upper=min(30.,float(max(p.sky['time_s'])-max(target_times)-.02))
            phases=full_grid[(full_grid>=lower)&(full_grid<=upper)];cost=[];rms=[]
            for phi in phases:
                p.reference[local]=phi;g=geometry_features(p,point,0);mean=np.zeros(g['features'].shape[1]);mean[begin:begin+len(p.labels)]=d['means']/p.phase_sigma;mean[coordinate]=phi/p.phase_sigma[local]
                scale=np.ones(len(mean));scale[-len(p.members):]=.3;scale[coordinate]=0
                raw=p.values-p.q*g['intercept']-g['features']@mean
                v=gaussian_predict(raw,g['features']*scale,train,test,powers=d['powers'][p.noise_groups]);cost.append(v['score']);rms.append(v['rms_hz'])
            full_prior=-.5*((full_grid-d['means'][local])/p.phase_sigma[local])**2
            prior=-.5*((phases-d['means'][local])/p.phase_sigma[local])**2;prior-=logsumexp(full_prior)
            evidence=float(-2*logsumexp(prior-.5*np.array(cost)));post=prior-.5*np.array(cost);post-=logsumexp(post);best=int(np.argmax(post))
            rows.append(dict(context=context,norad=target,arm=a,phase_grid=phases,conditional_scores=cost,log_prior=prior,log_posterior=post,
                prior_predictive_score=evidence,valid_phase_bounds_s=[lower,upper],included_prior_mass=float(np.exp(logsumexp(prior))),phase_mean_s=float(d['means'][local]),phase_sigma_s=float(p.phase_sigma[local]),
                diagnostic_phase_map_s=float(phases[best]),diagnostic_rms_at_phase_map_hz=float(rms[best]),held_points=int(test.sum()),position=point))
            print(case,context,a,evidence,'MAP',phases[best],flush=True)
    write(OUT/case/'phase_mixture.json',dict(case=case,rows=rows,scope='whole family held; target phase integrated under causal prior, other phases refreshed using training data only; fixed family-omitted position; Gaussian physical-mode uncertainty; conditional model check, not independent satellite discovery'))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('case');run(parser.parse_args().case)
