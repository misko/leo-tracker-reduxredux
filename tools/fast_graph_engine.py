"""Fresh-cohort adapters; never load a DS23 result or frozen candidate bank.

ALGO02-v1 is a historical control. Signed-prior plus cavity is reconstructed
from this scan's observations and causal history, not a parity claim for the
later ordinary graph-reentry pipeline.
"""
from pathlib import Path
import argparse
import numpy as np
import algo02_scan as algo
from run_algo01_ds23_sample import read, write, sha

OUT = Path(__file__).resolve().parents[1]
ARMS = ('c0', 'fitted_c')


def normalize_empty_predictive(pair,entries):
    if entries:return pair
    return {arm:dict(saved,linear_gates=saved.get('linear_gates',[])) for arm,saved in pair.items()}


def context(case, root=OUT, signed=True):
    root = Path(root)
    algo.bind_run_directory(root)
    old = read(root/case/'algo02_result.json')
    if old['status'] != 'accepted':
        raise ValueError('fresh ALGO02 has no qualified paired incumbent')
    from investigate_algo01_ds23_0217 import problem
    from probe_ds23_frequency_events import parameters, refit
    from ds23_causal_phase_location import qualify, adjust_means
    from investigate_ds23_adaptive_failures import phase_widths
    from probe_ds23_causal_phase_mean import forecast_phase_mean
    from ds23_frequency_events import make_event_problem
    original = read(root/case/'result.json')
    scan = algo.load_scan(root, case)
    node = original['final_node']; keep = np.asarray(old['mask'], bool)
    base = problem(scan, node, 'c0', keep)
    powers, means, model = parameters(scan, base, old)
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    history = root/'causal_phase_history'/(case+'.json')
    forecast_path = history.with_name(case+'_forecast.json')
    raw, forecast = read(history), read(forecast_path)
    algo.validate_history(raw, forecast, scan, sha(history))
    if any(r['validation_time_ns']>scan.receipt['cutoff_utc_ns'] for r in forecast['transitions']):
        raise ValueError('post-scan target in signed mean qualification')
    selection = qualify(forecast['transitions'], forecast['temporal_split_boundary_ns'],
                        forecast['prefix_distribution'], model)
    pair = old['policy_arms']; accepted = False
    if signed and selection['qualified']:
        _, receipts = phase_widths(scan, base.labels)
        adjusted = adjust_means(means, receipts, model, selection)
        candidate = {a: refit(scan,node,keep,a,powers,adjusted,model,[],entries) for a in ARMS}
        accepted = algo.pair_passes(candidate, include_linear=True)
        if accepted: means, pair = adjusted, candidate
    if not entries:
        # Historical curved-only ALGO02 summaries predate predictive gates.
        # An empty field records the genuinely empty predictive evidence set.
        pair=normalize_empty_predictive(pair,entries)
    _, receipts = phase_widths(scan, list(range(len(scan.norads))))
    all_means = forecast_phase_mean(receipts, model['shrinkage'])
    if accepted: all_means = adjust_means(all_means, receipts, model, selection)
    widths, _ = phase_widths(scan, list(range(len(scan.norads))))
    saved = pair['c0']; reference = np.asarray(saved['phase_reference'])
    base = make_event_problem(scan,node,keep,'c0',reference,powers,means,model,[])
    signed_record = dict(policy_arms=pair, accepted=accepted, selection=selection)
    return dict(case=case, scan=scan,node=node,keep=keep,powers=powers,means=means,
        model=model,entries=entries,arms=pair,signed=signed_record,binding=str(root),
        base=base,x=np.asarray(saved['endpoint_east_north_km']),reference=reference,
        all_means=np.asarray(all_means),widths=widths*model['multiplier'],
        observations=read(root/case/'observations.json'),
        original_protected={r['candidate_index'] for r,sl in zip(base.rows,base.slices,strict=True) if keep[sl].any()}|{e['candidate_index'] for e in entries})


def cavity(case, root=OUT):
    import probe_ds23_family_cavity_nominations as nom
    import probe_ds23_family_cavity_position as pos
    root = Path(root); destination=root/'family_cavity'
    destination.mkdir(exist_ok=True); (destination/'position').mkdir(exist_ok=True)
    nom.setup = lambda c: context(c,root)
    pos.setup = nom.setup
    nominations = nom.one(case, output_dir=destination)
    if nominations['status'] != 'complete': return nominations
    result=pos.one(case,nominations_dir=destination,output_dir=destination/'position')
    if result['status']=='complete' and not result.get('reconstructed_fresh_reference'):
        # Equal assignment priors: the unchanged incumbent is an explicit
        # hypothesis; no catalogue multiplicity/sticky penalty is imposed.
        eligible=[t for t in result['trials'] if t['paired_valid']]
        best=min(eligible,key=lambda t:t['arms']['c0']['corrected_selection_loss']) if eligible else None
        accepted=bool(best and best['arms']['c0']['corrected_selection_loss'] < result['baseline_corrected_loss']['c0'])
        result.update(sticky_control_accepted=result['accepted'],
            sticky_control_policy_arms=result['policy_arms'],
            accepted=accepted,selected=best if accepted else None,
            policy_arms=best['arms'] if accepted else result['baseline_arms'],
            adoption='equal_assignment_priors_minimum_corrected_normalized_c0',
            reconstructed_fresh_reference=True)
        write(destination/'position'/(case+'.json'),result)
    return result


def cavity_context(case, root=OUT):
    d=context(case,root)
    saved=read(Path(root)/'family_cavity/position'/(case+'.json'))
    if saved['status']!='complete': raise ValueError('cavity reference incomplete')
    selected=saved.get('selected')
    if saved['accepted']:
        d.update(node=selected['node'],entries=selected['entries'],means=np.asarray(selected['means']),arms=selected['arms'])
    import probe_ds23_graph_seeded_paths as paths
    d['base']=paths.build(d,'default','c0',d['arms']['c0']['phase_reference'])
    d['original_protected']={r['candidate_index'] for r,sl in zip(d['base'].rows,d['base'].slices,strict=True) if d['keep'][sl].any()}|{e['candidate_index'] for e in d['entries']}
    return d


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',required=True); parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args(); cavity(args.case,args.root)
