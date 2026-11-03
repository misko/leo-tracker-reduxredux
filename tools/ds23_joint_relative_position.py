"""Join IQ-disjoint GLRT and complete relative curves through shared orbit terms.

Original GLRT coefficient slots are preserved. New satellite phases and RF
contrast constants are appended, and linear GLRT evidence stays predictive.
"""

import numpy as np
from ds23_frequency_events import make_event_problem
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry,predictive_residual
from ds23_unanchored_relative_position import RelativeCurveProblem
from dsx01_hierarchical_bound import hierarchical_bound


def column_map(old_labels,old_supported,radio_width,old_width,rf_labels,rf_supported,groups):
    old_labels=list(old_labels);old_supported=list(old_supported);mapping=[];new_phases={};new_modes={};width=old_width
    for label in rf_labels:
        if label in old_labels:mapping.append(radio_width+old_labels.index(label))
        else:new_phases[label]=width;mapping.append(width);width+=1
    for label in rf_supported:
        if label in old_supported:mapping.extend(radio_width+len(old_labels)+3*old_supported.index(label)+np.arange(3))
        elif label not in old_labels:
            new_modes[label]=width;mapping.extend(width+np.arange(3));width+=3
        else:raise ValueError('new RF ownership must not silently enable an original-family orbit prior')
    mapping.extend(range(width,width+groups));width+=groups
    if len(set(mapping))!=len(mapping):raise ValueError('distinct RF phase/mode/constant coordinates required')
    return dict(mapping=np.array(mapping,int),width=width,new_phases=new_phases,new_modes=new_modes)


def make_joint_relative(d,arm,reference,*,include_relative=True,bias_sigma=np.sqrt(2)*300):
    labels=d['all_labels'];reference=np.asarray(reference,float)
    old_reference=np.array([reference[labels.index(j)] for j in d['old_labels']])
    p=make_event_problem(d['scan'],d['node'],d['keep'],arm,old_reference,d['powers'],d['old_means'],d['model'],[])
    nb,ns=p.hardware.shape[1],p.smooth.shape[1];phase_begin=nb+ns
    old_width=phase_begin+len(p.labels)+3*len(p.supported)+len(p.members)
    plan=column_map(p.labels,p.supported,phase_begin,old_width,d['rf_labels'],d['rf_supported'],len(d['groups']))
    width=plan['width'];mapping=plan['mapping']
    rf_reference=np.array([reference[labels.index(j)] for j in d['rf_labels']])
    rf=RelativeCurveProblem(p.scan.sky,d['rf_labels'],d['groups'],d['rf_means'],d['rf_widths'],rf_reference,d['coordinate'],
        mode_bank=d['rf_modes'],supported=d['rf_supported'],nu=d['model']['nu'],bias_sigma=bias_sigma)
    for j in set(p.labels)&set(d['rf_labels']):
        k=d['rf_labels'].index(j);old=p.labels.index(j)
        if not np.isclose(rf.phase_sigma[k],p.phase_sigma[old],rtol=0,atol=1e-12):raise ValueError('shared phase prior width changed')
    mean=np.zeros(width);mean[phase_begin:phase_begin+len(p.labels)]=d['old_means']/p.phase_sigma
    for j,index in plan['new_phases'].items():
        k=d['rf_labels'].index(j);mean[index]=d['rf_means'][k]/d['rf_widths'][k]
    scales=np.ones(width);scales[old_width-len(p.members):old_width]=.3
    prior=np.full(width,-1,int)
    if d['model']['nu'] is not None:
        phase_slots=list(range(phase_begin,phase_begin+len(p.labels)))+list(plan['new_phases'].values())
        prior[phase_slots]=np.arange(len(phase_slots))
    present=np.unique(p.noise_groups[p.keep]);original_state=p.state
    def calculate(position):
        g=geometry_features(p,position,0.);u=np.pad(g['features'],((0,0),(0,width-old_width)))
        raw=p.values-p.q*g['intercept'];features=[u[p.keep]];values=[raw[p.keep]];sigma=[p.point_noise[p.keep]]
        groups=[p.noise_groups[p.keep]];powers=[np.asarray(d['powers'])[present]]
        rg=rf.geometry(position);ru=np.zeros((len(rf.values),width));ru[:,mapping]=rg['features']
        if include_relative:
            features.append(ru);values.append(rf.values-rg['intercept']);sigma.append(rf.noise)
            groups.append(len(p.members)+rf.noise_groups);powers.append(np.ones(len(rf.groups)))
        design=np.vstack(features);y=np.concatenate(values);s=np.concatenate(sigma);noise_groups=np.concatenate(groups)
        power=np.concatenate(powers)
        bound=hierarchical_bound(y-design@mean,design*scales,s,noise_groups,powers=power,
            prior_groups=None if d['model']['nu'] is None else prior,prior_nu=4 if d['model']['nu'] is None else d['model']['nu'])
        latent=bound['coefficient'].copy();bound['coefficient']=mean+scales*latent
        precision=bound['coefficient_prior_precision']/scales**2
        _,mapped=np.unique(noise_groups,return_inverse=True)
        weight=power[mapped]*bound['noise_precision'][mapped]/s**2
        gram=np.diag(precision)+design.T@(weight[:,None]*design)
        joint_noise=bound['noise_precision'].copy()
        original_noise=np.zeros(len(p.members));original_noise[present]=joint_noise[:len(present)]
        bound.update(latent_coefficient=scales*latent,coefficient_prior_precision=precision,
            noise_precision=original_noise,joint_calibration_precision=gram,
            conditional_residual_hz=raw-u@bound['coefficient'],
            relative_residual_hz=rf.values-rg['intercept']-ru@bound['coefficient'],
            relative_elevation=rg['elevation'],relative_noise_precision=joint_noise[len(present):] if include_relative else np.array([]))
        # Preserve the original fixed-noise volume term in the GLRT objective.
        volume=float(2*np.sum(np.asarray(d['powers'])[p.noise_groups[p.keep]]*np.log(p.point_noise[p.keep]/40)))
        bound['residual']=np.r_[bound['residual'],np.sqrt(volume)]
        g.update(bound,features=u);return g
    p.calculate=calculate
    def state(position):
        result=original_state(position);c=p.calculate(position)
        for j,index in plan['new_phases'].items():result['phases'][j]=c['coefficient'][index]*d['rf_widths'][d['rf_labels'].index(j)]
        return result
    p.state=state;p.joint_all_labels=labels;p.joint_reference=reference;p.relative_problem=rf;p.relative_mapping=mapping
    p.relative_include=include_relative;p.joint_column_plan=plan;p.joint_old_width=old_width
    def exact_relative(position):
        c=p.calculate(position);coefficient=c['coefficient'][mapping];phase=coefficient[:len(rf.labels)]*rf.phase_sigma
        if np.max(abs(phase))>15:return None,None,phase
        geometry=rf.geometry(position,phase)
        return rf.values-geometry['intercept']-geometry['features']@coefficient,geometry['elevation'],phase
    p.exact_relative=exact_relative
    original_residual=p.residual
    def residual(position):
        result=original_residual(position)
        if include_relative:result=np.r_[result,np.maximum(0,-p.calculate(position)['relative_elevation'])/2]
        return result
    p.residual=residual
    return p


def attach_joint_relative_predictive(p,entries):
    if not entries:return p
    view,values,sigma,groups,slices=linear_geometry(p,entries);curved=p.calculate
    def calculate(position):
        c=curved(position);g=geometry_features(view,position,0.)
        u=np.pad(g['features'],((0,0),(0,len(c['coefficient'])-g['features'].shape[1])))
        predicted=view.q*g['intercept']+u@c['coefficient']
        bound=predictive_residual(values-predicted,u,c['joint_calibration_precision'],sigma*np.sqrt(2),groups)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo'];c['negative_twice_elbo']+=bound['objective']
        c['normalization_constant']+=bound['normalization_constant'];c['residual']=np.r_[c['residual'],bound['residual']]
        c['linear_raw_prediction_residual_hz']=values-predicted;c['linear_elevation']=g['elevation'];return c
    p.calculate=calculate;p.curved_calculate=curved;p.linear_entries=entries;p.linear_slices=slices
    return p
