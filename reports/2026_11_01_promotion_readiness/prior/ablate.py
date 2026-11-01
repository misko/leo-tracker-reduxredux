"""Frozen component interventions for DS26-0058; research outputs only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[2]
SOURCE = REPO / 'reports/2026_11_01_reconsideration_population'
sys.path.insert(0, str(SOURCE))
import evaluate as e
from build_dsx01_orbit_modes import build_modes

COMPONENTS = ('mean', 'width', 'radial', 'cross', 'predictive')
CELLS = {'original': [], **{k: [k] for k in COMPONENTS},
         'phase': ['mean', 'width'], 'shape': ['radial', 'cross'],
         'all_without_predictive': list(COMPONENTS[:-1]), 'complete': list(COMPONENTS)}


def freeze():
    path = OUT / 'spec.json'
    if path.exists():
        raise FileExistsError(path)
    inputs = [SOURCE/'evaluate.py', SOURCE/'DS26-0058/baseline.json',
              SOURCE/'DS26-0058/history_candidate.json',
              SOURCE/'DS26-0058/history_control.json',
              SOURCE/'DS26-0058/incumbent_history/previous.tle',
              SOURCE/'DS26-0058/incumbent_history/previous_receipt.json',
              SOURCE/'DS26-0058/incumbent_history/export.json']
    e.write(path, dict(case='DS26-0058', cells=CELLS, components=COMPONENTS,
        created_utc_ns=time.time_ns(), revision=subprocess.check_output(
            ['git','rev-parse','HEAD'], cwd=REPO, text=True).strip(),
        hashes={str(p):e.sha(p) for p in inputs+[Path(__file__)]},
        causal='Original 72h causal ALGO06 observations and fixed identities; cached causal history completion; no later elements',
        starts='Published fitted-c and c0 endpoints, identical two starts for every cell and both arms',
        fit=dict(phase_rounds=15, SLSQP_iterations=40, phase_tolerance_s=.01),
        mean='Only calibration family phase mean vector from completed history',
        width='Only calibration family phase width vector from completed history',
        radial='Only mode 0 physical mean-motion/radial uncertainty from completed history',
        cross='Only physical inclination/RAAN uncertainty modes 1 and 2 from completed history',
        predictive='Only standalone NewFamily mixture priors/modes from completed history; shared receiver covariance stays integrated once',
        scoring='Inherited normalized hierarchical ELBO plus predictive density, including determinant/prior normalizations; choose qualified start by RF objective within each cell',
        comparison='Every cell is diagnostic; no post-hoc cell promotion or GPS-based model selection; report both c arms and all failed fits',
        truth='Endpoint reporter only, after fitting; never starts, priors, cell selection or search',
        no_production_change=True))


def contexts():
    e.rec.CATALOGUES=e.ROOTS['DS26']/'catalogues'
    d,z,replay=e.load_case('DS26-0058')
    # complete_history can recreate private cache files only in this new output.
    folder=OUT/'history'
    folder.mkdir(parents=True, exist_ok=True)
    export=SOURCE/'DS26-0058/incumbent_history/export.json'
    if not (folder/'export.json').exists():
        e.write(folder/'export.json',e.read(export))
    hd,history=e.complete_history(d,z,'DS26-0058',e.active_ids(d),folder)
    return d,hd,z,replay,history


def mixed(d,hd,z,components):
    base=d['problems']['fitted_c'][0]
    labels, supported=base.labels,base.supported
    scan=copy.copy(hd['scan'])
    # The cache is the narrow intervention point used by the existing factory.
    widths=e.phase_widths((hd if 'width' in components else d)['scan'],labels)[0]
    scan.diagnostic_phase_width_cache={tuple(labels):widths.copy()}
    ob,om=build_modes(d['scan'],labels,supported,'physical')
    nb,nm=build_modes(hd['scan'],labels,supported,'physical')
    bank={k:np.array(v,copy=True) for k,v in ob.items()}
    for k in ('position_km','velocity_km_s'):
        if 'radial' in components:bank[k][0::3]=nb[k][0::3]
        if 'cross' in components:
            bank[k][1::3]=nb[k][1::3];bank[k][2::3]=nb[k][2::3]
    meta=copy.deepcopy(om)
    for j in meta:
        for fields,component in ((('radial_sigma_km','mean_motion_sigma_rev_day'),'radial'),
                (('cross_sigma_km','inclination_sigma_deg','raan_sigma_deg'),'cross')):
            if component in components:
                for field in fields:meta[j][field]=nm[j][field]
    scan.causal_uncertainty_modes={(tuple(labels),tuple(supported),'physical'):(bank,meta)}
    dd=dict(d,scan=scan,means=(hd if 'mean' in components else d)['means'].copy(),
        families=(hd if 'predictive' in components else d)['families'],problems=dict(d['problems']))
    # Rebuild both arms under the same original phase reference and candidate set.
    for a,(p,x) in d['problems'].items():dd['problems'][a]=(e.build(dd,z,a,p.reference)[0],x)
    return dd


def audit(d,hd,z):
    receipts={}
    for name,parts in CELLS.items():
        dd=mixed(d,hd,z,parts);rows={}
        for a,(p,x) in dd['problems'].items():
            c=p.calculate(x)
            rows[a]=dict(objective=e.objective(p,dd,x),
                curved_objective=c.get('curved_negative_twice_elbo',c['negative_twice_elbo']),
                predictive_objective=c.get('linear_predictive_objective'),
                mixture_objective=e.position.family_score(dd['families'],dd,p,x),
                means=dd['means'],widths=p.phase_sigma,metadata=p.mode_metadata,
                families=[f.receipt for f in dd['families']],
                native_keep_sha256=hashlib.sha256(p.keep.tobytes()).hexdigest(),
                normalization_constant=c['normalization_constant'])
        receipts[name]=rows
    for name,target in [('original',d),('complete',hd)]:
        for a,(p,x) in target['problems'].items():
            delta=receipts[name][a]['objective']-e.objective(p,target,x)
            if abs(delta)>1e-5:raise ValueError(f'Component replay mismatch {name} {a}: {delta}')
    e.write(OUT/'intervention_audit.json',receipts)
    return receipts


def run():
    spec=e.read(OUT/'spec.json')
    hashes=dict(spec['hashes'])
    amendment=OUT/'execution_amendment.json'
    if amendment.exists():hashes.update(e.read(amendment)['hashes'])
    for path,digest in hashes.items():
        if e.sha(path)!=digest:raise ValueError('Frozen input changed: '+path)
    d,hd,z,replay,history=contexts()
    e.write(OUT/'replay.json',dict(replay=replay,history=history))
    receipts=audit(d,hd,z)
    starts={a:d['problems'][a][1] for a in e.ARMS}
    for cell,parts in CELLS.items():
        path=OUT/'results'/f'{cell}.json'
        if path.exists():continue
        began=time.monotonic();dd=mixed(d,hd,z,parts)
        rows=e.fit_rows(dd,z,starts,set(),OUT/'fits'/f'{cell}.json')
        pair=e.paired(rows)
        digest={a:None if r is None else {k:r.get(k) for k in (
            'x','objective','error_m','rms_hz','qualified','start','seconds',
            'all_gates_pass','optimizer_success','phase_closed','parameters',
            'native_ids_sha256','owners_sha256')} for a,r in pair.items()}
        e.write(path,dict(cell=cell,components=parts,pair=digest,seconds=time.monotonic()-began))
        print(cell,{a:None if r is None else dict(error_m=r['error_m'],objective=r['objective'],rms_hz=r['rms_hz'],start=r['start']) for a,r in pair.items()},flush=True)


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    {'freeze':freeze,'run':run}[sys.argv[1]]()
