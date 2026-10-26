"""Same-arm full precision packets through the existing frozen Gaussian port."""
from pathlib import Path
import sys
import numpy as np

PREVIOUS=Path('/srv/bulk/leo/research/ds24-complete-owner-refinement-r01/position')
sys.path.insert(0,str(PREVIOUS))
import run as previous
from replacement import inject,digest
from ds23_frozen_precision import arm_prior_precision,make_frozen_problem
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from audit_ds23_algo01_coverage import retained_metrics
from evaluate_ds23_phase_refreshed import extend_associations
r=previous.r


def helper_prior(full,arm):
    full=np.asarray(full,float)
    if full.ndim!=1 or not np.isfinite(full).all() or np.any(full<=0):raise ValueError('positive same-arm full prior packet required')
    if arm=='fitted_c':
        if len(full)<=8 or full[8]!=1.:raise ValueError('helper cannot represent nonunit fitted-c slot8; no overwrite')
        reduced=np.delete(full,8)
    elif arm=='c0':reduced=full.copy()
    else:raise ValueError('unknown c arm')
    if not np.array_equal(arm_prior_precision(reduced,arm=='fitted_c'),full):raise ValueError('same-arm full packet mapping changed')
    return reduced


def layout(p):
    nb=p.hardware.shape[1];ns=p.smooth.shape[1];np_=len(p.labels);no=3*len(p.supported);nc=len(p.members)
    bounds=np.r_[0,np.cumsum([nb,ns,np_,no,nc])]
    return dict(hardware=[int(bounds[0]),int(bounds[1])],smooth=[int(bounds[1]),int(bounds[2])],
        phase=[int(bounds[2]),int(bounds[3])],physical_modes=[int(bounds[3]),int(bounds[4])],
        source_constants=[int(bounds[4]),int(bounds[5])],width=int(bounds[-1]),
        labels=[int(j) for j in p.labels],supported=[int(j) for j in p.supported],members=[int(i) for i in p.members])


def packet(case,arm,method):
    path=PREVIOUS/case/method/arm/'raw_endpoint.json';raw=r.read(path)
    return dict(case=case,arm=arm,origin=method,source_path=str(path),source_sha256=r.sha(path),
        noise_precision=raw['noise_precision'],coefficient_prior_precision=raw['coefficient_prior_precision'],
        final_phase_reference=raw['summary']['phase_reference'],source_endpoint=raw['summary']['endpoint_east_north_km'])


def build(d,arm,reference,precision):
    if precision['case']!=d['case'] or precision['arm']!=arm:raise ValueError('packet case/arm mismatch')
    full=np.asarray(precision['coefficient_prior_precision'],float);noise=np.asarray(precision['noise_precision'],float)
    reduced=helper_prior(full,arm)
    def factory(scan,node,keep,passed_arm,passed_reference,powers,means,multiplier,nu):
        if passed_arm!=arm or multiplier!=d['model']['multiplier'] or nu!=d['model']['nu']:raise ValueError('base-factory contract differs')
        p=make_frozen_problem(scan,node,keep,arm,passed_reference,powers,means,d['model'],noise,reduced,1.)
        contract=layout(p)
        if contract['width']!=len(full) or len(noise)!=len(p.members):raise ValueError('packet width/order mismatch')
        if precision.get('layout') is not None and contract!=precision['layout']:raise ValueError('packet column map differs')
        if not np.isfinite(noise).all() or np.any(noise[np.unique(p.noise_groups[p.keep])]<=0):raise ValueError('active fragment precision must be positive')
        p.precision_layout=contract
        return p
    p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(reference),d['powers'],d['means'],d['model'],[],base_problem_factory=factory)
    attach_event_predictive(p,d['entries'],d['powers'])
    p.packet=precision
    return cached(p)


def membership(p,x,d):
    """Use THIS conditional posterior; never reconstruct the VI parent."""
    metrics=retained_metrics(p,x);extension=extend_associations(p,x,metrics)
    current=summary(p,x,d['entries']);lookup={t['key']:t for t in p.scan.tracks}
    curved=[oid for i,sl in zip(p.members,p.slices,strict=True)
            for oid,on in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if on]
    predictive=[oid for e in d['entries'] for oid in e['observation_ids']]
    if len(curved+predictive)!=len(set(curved+predictive)):raise ValueError('overlapping likelihood ownership')
    rows=[];explicit=set(predictive)
    for row in extension['tracks']:
        if not row['compatible']:continue
        ids=row.get('observation_ids',lookup[row['component']]['observation_ids'])
        if set(ids)&explicit:continue
        rows.append(dict(row,observation_ids=ids))
    rows +=[dict(e,compatible=g['compatible'],association_source='explicit_predictive') for e,g in zip(d['entries'],current['linear_gates'],strict=True)]
    ownership=[oid for row in rows if row['compatible'] for oid in row['observation_ids']]
    if len(ownership)!=len(set(ownership)):raise ValueError('duplicate accepted ownership')
    accepted=set(ownership)|set(curved+predictive);allids={o['observation_id'] for o in d['observations']}
    if not accepted<=allids:raise ValueError('unknown accepted native ID')
    return dict(accepted_observation_ids=sorted(accepted),curved_observation_ids=sorted(curved),
        predictive_observation_ids=sorted(predictive),postfit_only_observation_ids=sorted(accepted-set(curved+predictive)),
        total_GLRT=len(allids),associated=len(accepted),percent=100*len(accepted)/len(allids),
        curved_points=len(curved),predictive_points=len(predictive),likelihood_points=len(curved)+len(predictive),
        likelihood_IDs_sha256=digest(sorted(curved+predictive)),associations=rows,gates=metrics,
        calibration_supported_slots=list(p.supported),posterior_kind='same_frozen_conditional_Gaussian_instance',
        VI_parent_rebuilt=False),current
