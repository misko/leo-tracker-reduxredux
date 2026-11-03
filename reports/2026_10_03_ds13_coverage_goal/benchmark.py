"""Frozen denominator, evidence rules, and group-safe cross-validation splits."""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / '2026_10_03_ds13_multitarget'
ALIAS_HZ = 1 / 4.4e-6
SESSIONS = {'A':'scan-fw-911c4e5db9243281','B':'scan-fw-ffa1cc19d8d7c09f'}
PROTOCOL = {
    'version': 1,
    'goal': 'At least one of activity, history/MHT, tracklet reaches >=0.90 defensible assigned coverage in EACH development scan; all three compared.',
    'position': 'Known roof, fixed; association experiment only.',
    'denominator': 'All retained raw peak rows except exact-period copies within the SAME original probe group. Nearby but distinct frequencies are NOT merged or excluded.',
    'alias_hz': ALIAS_HZ,
    'minimum_distinct_groups_per_satellite': 10,
    'coherence': {'minimum_groups_per_lane_segment':10,'minimum_span_s':5.,'maximum_observed_support_gap_s':5.,
                  'lane':'receiver and RF channel; CV embargo/test periods are not non-detection opportunities'},
    'native_noise_sigma_hz':200.,
    'maximum_counted_native_residual_hz':600.,
    'minimum_satellite_log_likelihood_margin':float(np.log(10.)),
    'ambiguity_policy':'Compare feasible competing track labels using the same physical/noise model. Count unresolved identities separately, not toward target. Local margins are not calibrated posterior probabilities.',
    'exclusivity':'At most one distinct peak per satellite per original group and at most one satellite per peak.',
    'physical_parameters':'Satellite timing shared across its RX/channel tracks, with existing zero-centered timing priors. Shared RX offsets/drifts and optional common RF coefficient. No per-track polynomial removal.',
    'timing_search':{'initial_half_range_s':20.,'adaptive_refinement':True,'boundary_hits':'flag and extend only with valid ephemeris support'},
    'cross_validation':{'folds':5,'block_s':10.,'embargo_s':1.,'assignment':'floor(group median receive time / 10) modulo 5',
                        'fit_policy':'Candidate selection, nuisance fitting and hyperparameter decisions exclude evaluation blocks and their embargo. Same folds for all methods and RF arms.',
                        'prediction_policy':'Report strict training-only predictive likelihood separately from decoding test observations with frozen parameters.'},
    'negative_controls':{'replicates':20,'rng_seed':20261003,'policy':'Permute complete frequency-peak sets between probe groups within the same RX/channel, preserving original within-group alias structure; rerun discovery/selection, not just score real-data tracks.',
                         'maximum_mean_false_assigned_coverage':0.05},
    'heldout_quality':'Full-point predictive log likelihood must improve over clutter-only and not worsen versus the corresponding training-only baseline. RMS compared on identical points as well as each method membership.',
    'additional_scans':['scan-fw-ebe22947697c8bf8','scan-fw-43153e12c5888719'],
    'additional_scan_policy':'Freeze settings before evaluation; selected by first two session IDs in pre-existing archived inventory order, not performance. Previously used in other analyses, not pristine external data.',
    'rf_ablation':'Fitted-c and c=0: matched observations, union of training-only candidate proposals, priors, budgets, folds; both nuisance arms refit.',
    'success':'90% in each development scan after evidence gates, blocked prediction and negative-control checks, matched three-model/RF comparison, additional-scan evaluation and requested artifacts. In-sample 90% alone is insufficient.',
    'limits':'Existing corpus only; QNAP read-only; preserve prior artifacts. Bounded individual experiments, no new recording.'
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_rows(measured, groups):
    """Stable exact-period collapse; do not collapse nearby alternative peaks."""
    measured=np.asarray(measured,float);groups=np.asarray(groups)
    if measured.ndim!=1 or groups.shape!=measured.shape or not np.all(np.isfinite(measured)):
        raise ValueError('Invalid observation arrays')
    mapping=np.empty(len(measured),int)
    for group in np.unique(groups):
        kept=[]
        for row in np.flatnonzero(groups==group):
            for representative in kept:
                r=(measured[row]-measured[representative]+ALIAS_HZ/2)%ALIAS_HZ-ALIAS_HZ/2
                tol=8*np.finfo(float).eps*max(ALIAS_HZ,abs(measured[row]),abs(measured[representative]),1.)
                if abs(r)<=tol:
                    mapping[row]=representative
                    break
            else:
                kept.append(int(row));mapping[row]=row
    return np.flatnonzero(mapping==np.arange(len(measured))),mapping


def group_folds(times,groups,block_s=10.,folds=5):
    result=np.empty(len(times),int)
    for group in np.unique(groups):
        rows=np.flatnonzero(groups==group)
        result[rows]=int(np.floor(np.median(np.asarray(times)[rows])/block_s))%folds
    return result


def split_masks(times,groups,test_fold):
    times=np.asarray(times);groups=np.asarray(groups)
    folds=group_folds(times,groups)
    test=folds==test_fold
    train=~test
    # Full scheduled block boundaries define embargo, not just retained-row times.
    for block in range(int(np.floor(times.min()/10)),int(np.floor(times.max()/10))+1):
        if block%5==test_fold:
            affected=(times>=block*10-1)&(times<(block+1)*10+1)
            train[np.isin(groups,np.unique(groups[affected]))]=False
    return train,test


def main():
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import Case
    output=ROOT/'frozen';output.mkdir(exist_ok=True)
    protocol_path=output/'protocol.json'
    if protocol_path.exists() and json.loads(protocol_path.read_text())!=PROTOCOL:
        raise RuntimeError('Frozen protocol differs; do not overwrite the benchmark')
    if not protocol_path.exists():protocol_path.write_text(json.dumps(PROTOCOL,indent=2))
    manifest={'protocol_sha256':digest(protocol_path),'scans':{}}
    for label,session in SESSIONS.items():
        case=Case(label);d=case.data
        rows,mapping=canonical_rows(d.measured,d.group)
        folds=group_folds(d.times,d.group)
        target=output/f'{label}-observations.npz'
        arrays=dict(times_s=d.times,measured_hz=d.measured,group=d.group,receiver=d.receiver,
                    channel=d.channel,rf_hz=d.rf,canonical_rows=rows,representative=mapping,fold=folds)
        if target.exists():
            with np.load(target) as stored:
                for key,value in arrays.items():np.testing.assert_array_equal(stored[key],value)
        else:np.savez_compressed(target,**arrays)
        source=case.path.parent.parent/'scans'/session/'bundle.npz'
        manifest['scans'][label]=dict(session=session,raw_rows=len(d.times),distinct_peaks=len(rows),
             exact_alias_copies=len(d.times)-len(rows),probe_groups=len(np.unique(d.group)),
             target_minimum_assigned=int(np.ceil(.9*len(rows))),fold_distinct_counts=np.bincount(folds[rows],minlength=5).tolist(),
             source_bundle_sha256=digest(source),observation_sha256=digest(target),
             known_position_km=case.params[:2].tolist(),bank_candidates=len(d.numbers))
    path=output/'manifest.json'
    if path.exists() and json.loads(path.read_text())!=manifest:raise RuntimeError('Frozen manifest changed')
    if not path.exists():path.write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
