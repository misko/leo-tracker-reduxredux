"""Matched RF-arm discovery over every archived near-visible satellite.

Conditional known-roof candidate search. Five-fold receiver calibration is
frozen; satellite timing discovery and selection use the whole scan. This is
not a held-out identity test or proof that every recovered window is genuine.
"""
import argparse
import inspect
import json
import time
from pathlib import Path

import numpy as np

from calibration import blocked_folds, serial
from cohort import digest
from numeric_data import load, view
from refinement import circular

ARMS = ('fitted-c', 'zero-c')
GATE = 900.


def roots(offset, residual, rate, visible, gate=GATE):
    safe = abs(rate)>1.
    root = offset + np.divide(residual,rate,out=np.zeros_like(residual),where=safe)
    ok = visible & safe & (abs(residual)<=abs(rate)*.75+gate) & (abs(root)<=20.)
    return root, ok


def timing_modes(offsets, groups, minimum=10):
    """Count each window once in a +/-0.1 s timing neighborhood."""
    if not len(offsets):
        return []
    offsets, groups = np.asarray(offsets), np.asarray(groups)
    bins = np.rint(offsets/.05).astype(int)
    pairs = np.unique(np.column_stack([bins,groups]),axis=0)
    grid = np.arange(-400,401)
    counts = np.array([len(np.unique(pairs[abs(pairs[:,0]-b)<=2,1])) for b in grid])
    answer = []
    while counts.max(initial=0)>=minimum:
        j = int(np.argmax(counts))
        b = grid[j]
        answer.append(float(np.median(offsets[abs(bins-b)<=2])))
        counts[abs(grid-b)<=4] = 0
    return answer


class FoldCalibration:
    def __init__(self, directory, *, permit_warning=False):
        self.data = load(directory, top_only=False)
        d = self.data
        from prediction_jacobian import paired_prediction_jacobian
        self.predictor = paired_prediction_jacobian
        self.sources = dict(d.sources)
        self.sources[str(Path(inspect.getfile(paired_prediction_jacobian)))] = digest(Path(inspect.getfile(paired_prediction_jacobian)).read_bytes())
        # Acquisition hypotheses can carry slightly different support epochs
        # inside one 20 ms probe. Share only *identical* prediction features.
        features = np.column_stack([d.group,d.times,d.rf,d.receiver,d.channel])
        _, representatives, self.inverse = np.unique(features,axis=0,return_index=True,return_inverse=True)
        grouped = view(d, representatives)
        # All alternatives in a window must have identical prediction features.
        for key in ('times','rf','receiver','channel'):
            if not np.array_equal(getattr(d,key),getattr(grouped,key)[self.inverse]):
                raise ValueError('window prediction features differ between alternatives')
        self.parts = []
        self.warnings = []
        for fold in range(5):
            path = directory/'calibration-v2'/f'fold-{fold}.json'
            saved = json.loads(path.read_text())
            if saved['signature']['observations'] != d.sources:
                raise ValueError('calibration input binding mismatch')
            # The pre-c=0 fit is only an initializer, never a frozen model.
            # Require convergence of every model actually used for prediction
            # or spline training; retain all earlier attempt statuses verbatim.
            required_converged = (saved['pre_fit_attempts']['fitted-c'][-1]['success']
                                  and all(saved['arms'][a]['success'] for a in ARMS))
            if not required_converged:
                self.warnings.append(dict(fold=fold,pre_fitted_c_converged=bool(saved['pre_fit_attempts']['fitted-c'][-1]['success']),
                                          final_arm_convergence={a:bool(saved['arms'][a]['success']) for a in ARMS}))
                if not permit_warning:
                    raise ValueError(f'nonconverged calibration fold {fold}; review before discovery')
            self.sources[str(path)] = digest(path.read_bytes())
            lookup = {int(r):int(g) for r,g in zip(d.original_rows,d.group)}
            test_groups = {lookup[r] for r in saved['test_original_rows']}
            rows = np.flatnonzero(np.isin(grouped.group,list(test_groups)))
            part = view(grouped,rows)
            if set(part.original_rows) != set(saved['test_original_rows']):
                # Representatives are arbitrary alternatives; compare groups via
                # full row inventory, not candidate IDs chosen for calibration.
                if set(part.group) != {lookup[r] for r in saved['test_original_rows']}:
                    raise ValueError('held-out fold membership mismatch')
            correction = np.zeros(len(rows))
            for rx in (0,1):
                mask = part.receiver==rx
                correction[mask] = np.interp(part.times[mask], saved['spline_nodes_s'], saved['correction_knots_hz'][rx])
            models = {}
            for arm in ARMS:
                fit = saved['arms'][arm]
                params = np.asarray(fit['parameters'])
                common = float(np.mean(params[6+np.asarray(saved['satellite_indices'],int)]))
                models[arm] = (params,common,correction+fit['coefficient']*(part.rf-saved['rf_center_hz'])/1e9)
            self.parts.append((rows,part,models))
        self.group_count = len(grouped.times)

    def predict(self, arm, ids, offset):
        shape = (self.group_count,len(ids))
        pred, visible, rate = np.empty(shape), np.empty(shape,bool), np.empty(shape)
        for destination,part,models in self.parts:
            parameters,common,correction = models[arm]
            trial = parameters.copy()
            timing = common+offset
            trial[6+ids] = np.clip(timing,-20,20)
            rows = np.repeat(np.arange(len(part.times)),len(ids))
            satellites = np.tile(ids,len(part.times))
            p,v,j = self.predictor(part,trial,rows,satellites)
            pred[destination] = p.reshape(len(part.times),-1)+correction[:,None]
            visible[destination] = v.reshape(len(part.times),-1) & (abs(timing)<=20.)
            rate[destination] = j.tau.reshape(len(part.times),-1)
        return pred[self.inverse], visible[self.inverse], rate[self.inverse]

    def residual(self, arm, index, offset):
        p,v,r = self.predict(arm,np.array([index]),offset)
        return circular(self.data.measured-p[:,0]),v[:,0],r[:,0]


def refine_mode(cal, arm, index, offset):
    d = cal.data
    for _ in range(3):
        e,v,r = cal.residual(arm,index,offset)
        ix = np.flatnonzero(v & (abs(e)<=GATE))
        ix = ix[np.lexsort((ix,abs(e[ix])))]
        _, first = np.unique(d.group[ix],return_index=True)
        ix = ix[first]
        if len(ix)<10:
            break
        step = (np.sum(r[ix]*e[ix])/200**2-offset)/(np.sum(r[ix]**2)/200**2+1.)
        offset = float(np.clip(offset+np.clip(step,-.1,.1),-20,20))
        if abs(step)<1e-5:
            break
    return offset


def run(directory, *, maximum_batches=None, permit_warning=False):
    started = time.monotonic()
    cal = FoldCalibration(directory,permit_warning=permit_warning)
    d = cal.data
    folder = directory/'discovery'
    folder.mkdir(exist_ok=True)
    signature = dict(sources=cal.sources,implementation=digest(Path(__file__).read_bytes()),
                     permit_calibration_warning=permit_warning,calibration_warnings=cal.warnings,
                     gate_hz=GATE,relative_timing_bound_s=20,absolute_timing_bound_s=20,
                     coarse_spacing_s=1,mode_bin_s=.05)
    all_records = {a:[] for a in ARMS}
    inventory, completed, new_batches = [], 0, 0
    for begin in range(0,len(d.numbers),16):
        target = folder/f'batch-{begin:04d}.json'
        if target.exists():
            saved = json.loads(target.read_text())
            if saved['signature'] != signature:
                raise ValueError('discovery cache signature mismatch')
        else:
            if maximum_batches is not None and new_batches>=maximum_batches:
                break
            ids = np.arange(begin,min(begin+16,len(d.numbers)))
            offsets = {int(i):[] for i in ids}
            for arm in ARMS:
                votes = [[] for _ in ids]
                groups = [[] for _ in ids]
                for coarse in np.arange(-20.,20.001):
                    p,v,r = cal.predict(arm,ids,coarse)
                    root,ok = roots(coarse,circular(d.measured[:,None]-p),r,v)
                    for j in range(len(ids)):
                        votes[j].extend(root[ok[:,j],j])
                        groups[j].extend(d.group[ok[:,j]])
                for j,index in enumerate(ids):
                    for offset in timing_modes(votes[j],groups[j]):
                        offsets[int(index)].append(refine_mode(cal,arm,index,offset))
            records = {a:[] for a in ARMS}
            batch_inventory = []
            for index in ids:
                union = sorted(set(offsets[int(index)]))
                batch_inventory.append(dict(catalog_number=int(d.numbers[index]),timing_modes=len(union)))
                for offset in union:
                    for arm in ARMS:
                        e,v,_ = cal.residual(arm,index,offset)
                        rows = np.flatnonzero(v & (abs(e)<=GATE))
                        records[arm].append(dict(catalog_number=int(d.numbers[index]),satellite_index=int(index),
                                                 offset_s=offset,eligible_rows=rows.tolist(),residual_hz=e[rows].tolist()))
            saved = dict(signature=signature,inventory=batch_inventory,arms=records)
            with target.open('x') as stream:
                json.dump(saved,stream,default=serial,allow_nan=False)
            new_batches += 1
        inventory.extend(saved['inventory'])
        for arm in ARMS:
            all_records[arm].extend(saved['arms'][arm])
        completed += len(saved['inventory'])
        print('DISCOVERY',directory.name,completed,'/',len(d.numbers),'modes',len(all_records[ARMS[0]]),
              'elapsed',round(time.monotonic()-started,1),flush=True)
    if completed==len(d.numbers):
        keys = [[(r['catalog_number'],r['offset_s']) for r in all_records[a]] for a in ARMS]
        if keys[0]!=keys[1]:
            raise AssertionError('RF arms must share exact timing/identity hypothesis bank')
        target = folder/'candidate-pool.json'
        result = dict(signature=signature,inventory=inventory,arms=all_records,
                      original_rows=d.original_rows.tolist(),scope=__doc__,
                      status='complete',elapsed_s=time.monotonic()-started)
        if not target.exists():
            with target.open('x') as stream:
                json.dump(result,stream,default=serial,allow_nan=False)
    return completed


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--maximum-new-batches',type=int)
    parser.add_argument('--permit-calibration-warning',action='store_true',help='Retain and propagate failed optimizer status; association diagnostics only, not a validated minimum.')
    args = parser.parse_args()
    run(args.directory,maximum_batches=args.maximum_new_batches,permit_warning=args.permit_calibration_warning)
