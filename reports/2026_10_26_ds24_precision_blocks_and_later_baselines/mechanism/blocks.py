"""Cross saved precision blocks without changing the conditional model."""
from pathlib import Path
import copy
import importlib.util
import numpy as np

OLD=Path('/srv/bulk/leo/research/ds24-cfo-precision-factorial-r01/solver')
spec=importlib.util.spec_from_file_location('original_factorial_model',OLD/'model.py')
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
r=model.r
CASES=('DS24-0010','DS24-0011');ARMS=('c0','fitted_c')
NEW_CELLS=(('01','original','corrected'),('10','corrected','original'))


def key(case,arm,origin):return case+'_'+arm+'_'+origin


def mixed_packet(noise_source,prior_source):
    if any(noise_source[k]!=prior_source[k] for k in ('case','arm','layout')):
        raise ValueError('mixed precision case/arm/full layout differs')
    noise=np.asarray(noise_source['noise_precision'],float)
    other=np.asarray(prior_source['noise_precision'],float)
    if noise.shape!=other.shape or not np.array_equal(noise==0,other==0):
        raise ValueError('inactive noise group masks differ')
    if not np.isfinite(noise).all() or np.any(noise<0):raise ValueError('invalid noise precision')
    prior=np.asarray(prior_source['coefficient_prior_precision'],float)
    if len(noise)!=len(noise_source['layout']['members']) or len(prior)!=noise_source['layout']['width']:
        raise ValueError('precision packet width differs')
    model.helper_prior(prior,noise_source['arm'])
    packet=copy.deepcopy(noise_source)
    packet.update(origin='noise_'+noise_source['origin']+'__prior_'+prior_source['origin'],
        noise_precision=noise.tolist(),coefficient_prior_precision=prior.tolist(),
        noise_origin=noise_source['origin'],prior_origin=prior_source['origin'],
        noise_source_sha256=model.digest(noise_source),prior_source_sha256=model.digest(prior_source),
        nuisance_means_carried=False,phase_reference_carried=False)
    # These are source provenance only. Fits always start with zero references.
    return packet


def original_context(case):
    d=r.context(case)
    if d['case']!=case:raise ValueError('wrong original context')
    return d
