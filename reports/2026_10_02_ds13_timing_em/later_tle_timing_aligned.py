"""Repeat the later-TLE comparison with orbit-only timing-aligned initialization.

Keeps the original unaligned run as evidence of a local clutter-dominated basin.
Initialization matches old orbit curves, not polynomial-corrected measurements.
The final objective and all fitted freedoms remain unchanged.
"""
import json
import numpy as np
from pathlib import Path

import later_tle_comparison as comparison
from prediction_jacobian import paired_prediction_jacobian
from rf_calibration_diagnostic import CalibrationObjective
from scipy.optimize import minimize_scalar

original_refit = comparison.refit
original_save = comparison.save_json
initializations = []


def aligned_refit(data, profile, sealed, initial_vector=None):
    arrays,_,_,_ = comparison.load_archived_session(profile['session'])
    memberships = comparison.read_membership_rows(comparison.ROOT /
                    'orbit-backfill-prototype/group-summed-orbit-backfill-memberships.csv')
    label = 'A' if profile['session']==comparison.SESSIONS[0] else 'B'
    tracks = comparison.final_tracks(memberships,arrays,label)
    parameters = np.asarray(sealed['parameters']).copy()
    changes=[]
    for column,satellite in enumerate(profile['satellite_indices']):
        number = int(data.numbers[satellite])
        groups = [t['rows'] for t in tracks if t['catalog_number']==number]
        if groups:
            rows = np.unique(np.concatenate(groups))
            row_policy = 'frozen final track rows'
        else:
            rows = np.flatnonzero(arrays['posterior'][:,column] >= .8)
            row_policy = 'original high-posterior rows; no final track'
            if not len(rows):
                rows = np.arange(0,len(data.times),max(1,len(data.times)//200))
                row_policy = 'uniform scan rows; orbit-only alignment'
        target = arrays['modeled_doppler_hz'][rows,column]
        rx = data.receiver[rows]
        nuisance = parameters[2+2*rx] + parameters[3+2*rx]*(data.times[rows]-150.)
        initial_tau = float(parameters[6+satellite])
        def cost(extra):
            trial = parameters.copy()
            trial[6+satellite] = initial_tau + extra
            prediction,_,_ = paired_prediction_jacobian(data,trial,rows,np.full(len(rows),satellite))
            orbital = (prediction-nuisance)*comparison.CARRIER/data.rf[rows]
            return float(np.mean((orbital-target)**2))
        grid=np.linspace(-10.,10.,201)
        values=np.asarray([cost(x) for x in grid])
        k=int(np.argmin(values))
        refined=minimize_scalar(cost,bounds=(grid[max(0,k-1)],grid[min(len(grid)-1,k+1)]),
                                method='bounded',options={'xatol':1e-8})
        options=[(cost(0.),0.),(float(values[k]),float(grid[k])),(float(refined.fun),float(refined.x))]
        value,delta=min(options)
        parameters[6+satellite]=initial_tau+delta
        changes.append({'catalog_number':number,'original_tau_s':initial_tau,
                        'aligned_tau_s':initial_tau+delta,'extra_tau_s':delta,
                        'curve_alignment_rms_hz':np.sqrt(value),'grid_boundary':k in (0,len(grid)-1),
                        'row_policy':row_policy,'row_count':len(rows)})
    objective=CalibrationObjective(data,parameters,np.asarray(profile['satellite_indices']),False,8.)
    vector=objective.initial.copy()
    vector[objective.size:]=sealed['rf_coefficient_hz_per_ghz']
    initializations.append({'scan':label,'changes':changes})
    print(label+': orbit-aligned timing offsets '+str([(r['catalog_number'],round(r['extra_tau_s'],3)) for r in changes]),flush=True)
    return original_refit(data,profile,sealed,initial_vector=vector)


def save_with_provenance(path,value):
    if path.name=='receipt.json':
        value['timing_initializations']=initializations
        value['source_hashes'][str(Path(__file__).resolve())]=comparison.file_digest(__file__)
        previous=comparison.ROOT/'later-tle-comparison/receipt.json'
        value['source_hashes'][str(previous)]=comparison.file_digest(previous)
        value['scope'] += (' Initialization additionally aligns each new orbit to the old orbit on '
                           'frozen final rows using a +/-10s timing grid and scalar refinement; '
                           'no additional fit parameters or residual-polynomial subtraction. '
                           'Earlier unaligned local fit is preserved in sibling directory.')
    original_save(path,value)


if __name__=='__main__':
    comparison.OUTPUT=comparison.ROOT/'later-tle-timing-aligned-v2'
    comparison.refit=aligned_refit
    comparison.save_json=save_with_provenance
    comparison.run()
