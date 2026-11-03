"""Bounded timing composite over exact physical-source assignments."""
import importlib.util
from pathlib import Path
import sys
import numpy as np

PARENT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PARENT))
sys.path.insert(0, str(PARENT/'detection_evidence'))
from epoch_pairs import delta_us
from source_partition_fast import partition


def coefficients(tids, meta, masks, branch, raw, calibration, held=False):
    observations = {}
    for tid in tids:
        grouped = {}
        for i, cid in enumerate(meta[tid]['candidate_ids']):
            if branch['assignment'].get(cid,tid) != tid or (not held and not masks[tid][i]):
                continue
            grouped.setdefault(meta[tid]['window_ids'][i],[]).append(raw[cid])
        observations[tid] = grouped
    edges = []
    for i, left in enumerate(tids):
        for j in range(i+1,len(tids)):
            right = tids[j]
            if meta[left]['receiver']==meta[right]['receiver']:
                continue
            values = []
            for window in sorted(observations[left].keys() & observations[right].keys()):
                pairs = {}
                for a, fs in observations[left][window]:
                    for b, other_fs in observations[right][window]:
                        assert fs == other_fs
                        delta = abs(delta_us(a,b,fs,750.))
                        key = (delta,a['fractional_tracking_cfo_hz'],b['fractional_tracking_cfo_hz'],a['fractional_exact_score'],b['fractional_exact_score'],a['fractional_control_score'],b['fractional_control_score'])
                        pairs[key] = calibration['event_log_ratio']['hit' if delta<=calibration['threshold_us'] else 'miss']
                values.append(sum(pairs.values())/len(pairs))
            if values:
                edges.append((i,j,sum(values)/len(values)))
    degree = np.zeros(len(tids))
    for i,j,value in edges:
        degree[i]+=1
        degree[j]+=1
    result = np.zeros((len(tids),len(tids)))
    for i,j,value in edges:
        result[i,j] = value/max(degree[i],degree[j])
    return result


def adjust(factors, matrix):
    output = []
    for support, values, gradient in factors:
        values = values.copy()
        subsets = np.arange(len(values))
        for a,i in enumerate(support):
            for b,j in enumerate(support):
                if i<j and matrix[i,j]:
                    values += (((subsets>>a)&1)*((subsets>>b)&1))*matrix[i,j]
        output.append((support,values,gradient))
    return output


def build(doc, config, bound, calibration, strength=1.):
    # Each instance owns its imported evaluator and closure; no shared patching.
    spec = importlib.util.spec_from_file_location('isolated_epoch_source',PARENT/'whole_source_position.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.WholeSourcePosition(doc,config,bound,{},'doppler')
    raw = {}
    for opportunity in bound['opportunities']:
        for rx in opportunity['receivers'].values():
            for candidate in rx['candidates']:
                cid = candidate['projected_candidate_id']
                if cid is not None:
                    assert cid not in raw
                    raw[cid] = candidate,opportunity['source_window']['sample_rate_hz']
    matrices = {}
    for held in (False,True):
        matrices[held] = [strength*coefficients(sorted(lane['left']+lane['right']),model.meta,{t:model.tracks[t]['mask'] for t in model.tracks},branch,raw,calibration,held) for lane in model.lanes for branch in lane['ownership_alternatives']]
    original = model.evaluate

    def evaluate(x, gradient=True, held=False):
        queue = iter(matrices[held])
        def modified(n,factors):
            matrix = next(queue)
            assert matrix.shape==(n,n)
            return partition(n,adjust(factors,matrix))
        module.partition = modified
        result = original(x,gradient=gradient,held=held,force_partition=True)
        assert next(queue,None) is None
        return result
    model.evaluate = evaluate
    model.timing_matrices = matrices
    return model
