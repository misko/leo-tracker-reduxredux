"""Compare conditional same-source training residuals across RF/receiver pairs."""
import importlib.util
import itertools
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
HILL = HERE.parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def match_times(left, right, maximum=.25):
    left, right = np.asarray(left), np.asarray(right)
    if not len(left) or not len(right):
        return []
    distances = abs(left[:,None]-right[None,:])
    nearest_right = np.argmin(distances, axis=1)
    nearest_left = np.argmin(distances, axis=0)
    return [(i,int(j)) for i,j in enumerate(nearest_right)
            if nearest_left[j] == i and distances[i,j] <= maximum]


def centered_rms(values):
    values = np.asarray(values)
    return float(np.sqrt(np.mean((values-np.median(values))**2)))


def pair_statistics(left, right):
    left, right = np.asarray(left), np.asarray(right)
    assert len(left) == len(right)
    if len(left) < 6:
        return None
    a, b = left-np.median(left), right-np.median(right)
    correlation = float(np.corrcoef(a,b)[0,1]) if np.std(a)>0 and np.std(b)>0 else None
    return dict(pearson=correlation, left_centered_rms_hz=centered_rms(left),
                right_centered_rms_hz=centered_rms(right),
                common_component_rms_hz=float(np.sqrt(np.mean(((a+b)/2)**2))),
                differential_component_rms_hz=float(np.sqrt(np.mean(((a-b)/2)**2))),
                centered_difference_rms_hz=centered_rms(left-right))


def main(index):
    p = module(f'pair_position_{index}', HILL/f'pilot_fallback{index:02d}'/'run.py')
    plan_path = p.HERE/'plan.json'
    plan = p.read(plan_path)
    documents, fast, _, _ = p.context(plan)
    diagnosis_path = HILL/'source_loo/diagnose.py'
    diagnosis = p.module(f'pair_diagnosis_{index}', diagnosis_path)
    _, _, _, verified, sidecar, mappings = diagnosis.validate_inputs(index)
    assert [t['track_id'] for t in documents[0]['tracks']] == [t['track_id'] for t in verified[0]['tracks']]
    target_ids = sorted({r['track_id'] for r in plan['corrections']['pilot_22_221']})
    target_norad = {0:65512,16:67103}[index]
    x = np.asarray(plan['control']['x'])
    results = {}
    for arm in ('cached', 'pilot_22_221'):
        docs = documents if arm == 'cached' else p.patch_documents(documents, plan['corrections'][arm])
        geometry = fast.Stationary(docs[0], plan['config'])
        tracks = {}
        for track in docs[0]['tracks']:
            tid = track['track_id']
            if tid not in target_ids:
                continue
            j = mappings[0][tid].index(target_norad)
            predictions, _ = geometry.prediction(track,x)
            residual = track['y'][None,:]-predictions[j:j+1]
            _, _, audits, offsets = fast.profile(residual,track['mask'])
            assert all(a['converged'] for a in audits)
            take = np.flatnonzero(track['mask'])
            tracks[tid] = dict(receiver=int(track['receiver_id']),rf_hz=float(track['rf_hz']),
                               times=np.asarray(track['times_s'])[take], indices=take,
                               visits=np.asarray(track['visits'])[take],
                               measured=track['y'][take], predicted=predictions[j,take],
                               residual=residual[0,take]-offsets[0], profiled_cfo_hz=float(offsets[0]))
        pairs=[]
        for a,b in itertools.combinations(target_ids,2):
            left,right=tracks[a],tracks[b]
            matched=match_times(left['times'],right['times'])
            raw=[dict(left_index=int(left['indices'][i]),right_index=int(right['indices'][j]),
                      left_visit=int(left['visits'][i]),right_visit=int(right['visits'][j]),
                      time_difference_s=float(left['times'][i]-right['times'][j]),
                      left_residual_hz=float(left['residual'][i]),right_residual_hz=float(right['residual'][j]),
                      measured_difference_hz=float(left['measured'][i]-right['measured'][j]),
                      predicted_difference_hz=float(left['predicted'][i]-right['predicted'][j])) for i,j in matched]
            pair=dict(left_track=a,right_track=b,left_receiver=left['receiver'],right_receiver=right['receiver'],
                      left_rf_hz=left['rf_hz'],right_rf_hz=right['rf_hz'],matches=len(raw),rows=raw,
                      residual_statistics=pair_statistics([r['left_residual_hz'] for r in raw],[r['right_residual_hz'] for r in raw]))
            if raw:
                pair.update(maximum_time_separation_s=max(abs(r['time_difference_s']) for r in raw),
                            same_visit_pairs=sum(r['left_visit']==r['right_visit'] for r in raw),
                            measured_difference_centered_rms_hz=centered_rms([r['measured_difference_hz'] for r in raw]),
                            predicted_difference_centered_rms_hz=centered_rms([r['predicted_difference_hz'] for r in raw]))
            pairs.append(pair)
        results[arm]=pairs
    sources=dict(plan['sources'])
    for path in (plan_path,Path(__file__),HERE/'test_run.py',HERE/'PROTOCOL.md',sidecar,diagnosis_path):
        sources[str(path)]=p.digest(path)
    output=dict(schema='ds11-conditional-source-residual-pairs/v1',scan_index=index,conditional_norad=target_norad,
                reference_used=False,position_fits=0,endpoint='frozen original IID for both measurement arms',
                results=results,sources=sources)
    p.write(HERE/f'{index:02d}.json',output)
    print(json.dumps({arm:[{k:v for k,v in row.items() if k!='rows'} for row in pairs] for arm,pairs in results.items()},indent=2))


if __name__=='__main__':
    main(int(sys.argv[1]))
