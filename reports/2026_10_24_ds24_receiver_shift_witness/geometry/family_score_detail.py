"""Decompose local normalized score into family-owned and shared terms.

This does not turn joint full-data fits into independent family votes. Shared
receiver priors, determinant, normalization and predictive covariance stay
global. Existing saved phase references are fixed while nuisance/Gamma refit.
"""
import csv
from pathlib import Path

import numpy as np

from matched_controls import digest, load_baseline, read, write
from geometry import HERE, CASES, ARMS, MODELS, blocks, build, terms


def noise_gamma_by_group(noise_precision, counts, powers, noise_nu=4.):
    counts = np.asarray(counts)
    present = counts > 0
    alpha = noise_nu/2+np.asarray(powers)[present]*counts[present]/2
    ratio = alpha/np.asarray(noise_precision)[present]/(noise_nu/2)
    cost = np.zeros(len(counts))
    cost[present] = np.maximum(0, 2*alpha*(np.log(ratio)+1/ratio-1))
    return cost


def prior_gamma_by_phase(precision, nu):
    if nu is None:
        return np.zeros(len(precision))
    v0 = nu/(nu-2)
    v = np.asarray(precision)
    return np.maximum(0, nu*(np.log(v0/v)+v/v0-1))


def owned_terms(p, x, model):
    curved = p.curved_calculate(x) if hasattr(p, 'curved_calculate') else p.calculate(x)
    latent = curved['latent_coefficient']
    precision = curved['coefficient_prior_precision']
    b = blocks(p)
    energy = latent**2*precision
    family = {str(p.scan.norads[j]):dict(weighted_data=0., noise_Gamma=0., phase_prior=0.,
                phase_Gamma=0., orbit_prior=0., fragment_prior=0., points=0)
              for j in p.labels}
    counts = np.bincount(p.noise_groups[p.keep], minlength=len(p.members))
    costs = noise_gamma_by_group(curved['noise_precision'], counts, p.analysis_powers)
    np.testing.assert_allclose(costs.sum(), curved['noise_gamma_cost'], atol=1e-7)
    for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
        out = family[str(row['candidate_norad'])]
        use = p.keep[sl]
        w = p.analysis_powers[k]*curved['noise_precision'][k]/p.point_noise[sl][use]**2
        out['weighted_data'] += float(np.sum(w*curved['conditional_residual_hz'][sl][use]**2))
        out['noise_Gamma'] += float(costs[k])
        out['fragment_prior'] += float(energy[b['fragment'][k]])
        out['points'] += int(use.sum())
    pcost = prior_gamma_by_phase(precision[b['phase']], model['nu'])
    np.testing.assert_allclose(pcost.sum(), curved['prior_gamma_cost'], atol=1e-7)
    for k,j in enumerate(p.labels):
        out = family[str(p.scan.norads[j])]
        out['phase_prior'] += float(energy[b['phase'][k]])
        out['phase_Gamma'] += float(pcost[k])
    for k,j in enumerate(p.supported):
        family[str(p.scan.norads[j])]['orbit_prior'] += float(np.sum(energy[b['orbit'][3*k:3*k+3]]))
    full_terms = terms(p,x)
    global_terms = {k:v for k,v in full_terms.items() if k not in
                    ('weighted_data','noise_Gamma','prior_phase','prior_Gamma','prior_orbit','prior_fragment')}
    owned = sum(sum(v for k,v in row.items() if k != 'points') for row in family.values())
    full = float(p.calculate(x)['negative_twice_elbo'])
    np.testing.assert_allclose(owned+sum(global_terms.values()),full,atol=1e-6)
    return family,global_terms,full


def main():
    source_hash = digest(Path(__file__))
    rows, changes, summaries = [], [], []
    seals=[]
    for case in CASES:
        path=HERE/(case+'.json');saved=read(path);seals.append(dict(path=str(path),sha256=digest(path)))
        d=load_baseline(case)
        assert d['baseline_sha256']==saved['baseline_sha256']
        for arm in ARMS:
            ar=saved['arms'][arm]
            direction=np.asarray(ar['displacement_east_north_km'])/ar['displacement_km']
            derivative_by_model={}
            for model in MODELS:
                for which in ('baseline_endpoint','rf50_endpoint'):
                    s=ar['models'][model]['endpoints'][which]['summary']
                    x=np.asarray(s['position_east_north_km'])
                    p=build(d,arm,np.asarray(s['phase_reference']),model);p.analysis_powers=d['powers']
                    fp,gp,lp=owned_terms(p,x+.01*direction,d['model'])
                    fm,gm,lm=owned_terms(p,x-.01*direction,d['model'])
                    deriv={key:{k:(fp[key][k]-fm[key][k])/.02 for k in fp[key] if k!='points'} for key in fp}
                    global_deriv={k:(gp[k]-gm[k])/.02 for k in gp}
                    full_deriv=(lp-lm)/.02
                    owned_total=sum(sum(v.values()) for v in deriv.values())
                    error=owned_total+sum(global_deriv.values())-full_deriv
                    assert abs(error)<1e-6
                    summaries.append(dict(case=case,arm=arm,model=model,location=which,
                        full_derivative_per_km=full_deriv,family_owned_derivative_sum=owned_total,
                        global_derivatives=global_deriv,reconstruction_error=error))
                    for norad,values in deriv.items():
                        rows.append(dict(case=case,arm=arm,model=model,location=which,norad=norad,
                            points=fp[norad]['points'],total_owned_derivative_per_km=sum(values.values()),
                            **{k+'_derivative_per_km':v for k,v in values.items()}))
                    derivative_by_model[(model,which)]=deriv
            for norad,values in derivative_by_model[('baseline','baseline_endpoint')].items():
                changed={k:derivative_by_model[('rf50','baseline_endpoint')][norad][k]-v for k,v in values.items()}
                changes.append(dict(case=case,arm=arm,norad=norad,
                    total_owned_derivative_change_per_km=sum(changed.values()),
                    **{k+'_derivative_change_per_km':v for k,v in changed.items()}))
    for name,data in [('family_owned_score_derivatives.csv',rows),('family_owned_score_derivative_changes.csv',changes)]:
        with (HERE/name).open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    assert digest(Path(__file__))==source_hash
    for item in seals:assert digest(item['path'])==item['sha256']
    write(HERE/'family_score_detail.json',dict(passed=True,source_sha256=source_hash,
        input_seals=seals,position_fitting=False,GPS_used=False,summaries=summaries,
        conditional_on_full_data_endpoints_labels_and_phase_linearization=True,
        shared_terms_not_assigned_as_independent_family_votes=True))


if __name__=='__main__':main()
