"""Preserve individual track timing when initializing shared receiver lines.

Versioned initialization ablation: observations, refinements, orbit banks and
subsequent fit priors are unchanged. Earlier bootstrap discarded the shape-fit
individual timing while estimating RX lines, which could move the RX intercept
by many kHz. No old numerical result is overwritten.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from cohort import digest
from numeric_data import load
from refinement import circular


def timing_seed(tracks, count):
    values=np.zeros(count)
    indices=sorted({r['satellite_index'] for r in tracks if r['accepted']})
    for index in indices:
        records=sorted([r for r in tracks if r['accepted'] and r['satellite_index']==index],key=lambda r:r['offset_s'])
        weights=np.array([r['source_groups'] for r in records],float)
        chosen=int(np.searchsorted(np.cumsum(weights),sum(weights)/2))
        values[index]=records[chosen]['offset_s']
    if not indices:
        raise ValueError('no accepted tracks')
    values[indices]-=np.mean(values[indices])
    return values,indices


def run(parent,variant_name='seed-timing-v6'):
    started=time.monotonic()
    if '/' in variant_name or not variant_name.startswith('seed-timing-'):
        raise ValueError('invalid variant name')
    target=parent/variant_name
    target.mkdir(exist_ok=True)
    for name in ('observations.json','refinement','orbit-bank'):
        source=parent/name
        destination=target/name
        if destination.exists():
            if destination.resolve()!=source.resolve():
                raise ValueError('variant input points to different data')
        else:
            destination.symlink_to(source.resolve(),target_is_directory=source.is_dir())
    data=load(target)
    previous=parent/'bootstrap.json'
    saved=json.loads(previous.read_text())
    seed,indices=timing_seed(saved['tracks'],len(data.numbers))
    from prepare_scans import ShiftedData
    from staged_fit import fit_receiver_lines
    from track_seed import loss
    rough=dict(position_km=data.initial[:2],assignments=[r for r in saved['tracks'] if r['accepted']])
    trials=[]
    for common in (-10.,-5.,0.,5.,10.):
        # Keep initial states a microsecond inside the hard ephemeris/timing
        # limits. Zero-sum basis roundoff can otherwise turn exactly 20 s into
        # 20.000000000000004 s and make the initial likelihood undefined.
        shifts=np.clip(seed+np.clip(common,-10+1e-8,10-1e-8),-20+1e-6,20-1e-6)
        parameters=fit_receiver_lines(ShiftedData(data,shifts),rough)
        parameters[6:]=shifts
        costs=[]
        for track in rough['assignments']:
            rows=np.asarray(track['rows'],int)
            pred,visible=data.predict(parameters,rows=rows,satellites=np.full(len(rows),track['satellite_index']))
            residual=circular(data.measured[rows]-pred)
            if np.any(visible):
                costs.append(float(np.mean(loss(residual[visible]))))
        trials.append(dict(common_shift_s=common,parameters=parameters.tolist(),score=float(np.mean(costs))))
    # Retain the zero-individual-timing starts too. Shape timing can itself be
    # ambiguous; augment initialization rather than forcing every scan into
    # the timing-aware family. Downstream still fits the best two starts by
    # training likelihood, with identical budgets in both RF arms.
    trials=[dict(r,initializer_family='zero-individual-timing') for r in saved['common_timing_trials']]+[
        dict(r,initializer_family='shape-individual-timing') for r in trials]
    best=min(trials,key=lambda r:r['score'])
    record={**saved,'initial_parameters':best['parameters'],'common_timing_trials':trials,
            'sources':{**data.sources,str(previous):digest(previous.read_bytes()),str(Path(__file__)):digest(Path(__file__).read_bytes())},
            'timing_seed_relative_s':seed[indices].tolist(),'timing_seed_indices':indices,
            'scope':__doc__,'elapsed_s':time.monotonic()-started}
    output=target/'bootstrap.json'
    if output.exists():
        if json.loads(output.read_text())['sources']!=record['sources']:
            raise ValueError('existing variant bootstrap source mismatch')
    else:
        with output.open('x') as stream:
            json.dump(record,stream,allow_nan=False)
    print(json.dumps(dict(scan=parent.name,target=str(target),elapsed_s=record['elapsed_s'],
                         trials=[dict(common_shift_s=r['common_shift_s'],rx=r['parameters'][2:6],score=r['score']) for r in trials])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path)
    p.add_argument('--variant-name',default='seed-timing-v6')
    a=p.parse_args()
    run(a.parent,a.variant_name)
