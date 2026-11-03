"""Bounded whole-short and source-owned temporal-core ablations on batch012."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

import probe_ds23_iteration012_existing_recovery as binding
import probe_ds23_iteration010_short_curves as short
import probe_ds23_curved_temporal_core as core
from ds23_supported_curvature import supported_curvature
from run_algo01_ds23_sample import read,write,sha

BASE_OFFERS=core.offers
OUT=binding.runner.RAW/'source_owned_temporal_core'


def source_intersections(tracks,fragments):
    """Use exact source IDs; an HMM path may also contain outside-graph points."""
    result=[]
    for fragment in fragments:
        for track in tracks:
            positions=[k for k,oid in enumerate(fragment['observation_ids']) if oid in set(track['observation_ids'])]
            if not positions:continue
            result.append(dict(fragment,key=fragment['key']+'_SOURCE_'+track['key'],
                times=np.asarray(fragment['times'])[positions],values=np.asarray(fragment['values'])[positions],
                observation_ids=[fragment['observation_ids'][k] for k in positions]))
    return result


def source_offers(d,fragments):
    views=source_intersections([d['scan'].tracks[i] for i in d['scan'].curved],fragments)
    offers=BASE_OFFERS(d,views)
    for offer in offers:
        ids=set(offer['fragment']['observation_ids']);witness=next(f for f in fragments if ids<=set(f['observation_ids']))
        offer.update(full_frozen_HMM_path=witness['key'],full_frozen_HMM_points=len(witness['observation_ids']),
            source_intersection_contains_only_original_observations=True,other_native_path_points_not_promoted=True)
    return offers


def configure(stage):
    binding.configure('paths')
    if stage=='short':
        short.binding=binding.paths;short.OUT=binding.runner.RAW/'short_whole_curves';return short
    core.runner=binding.runner;core.parent.runner=binding.runner;core.parent.OUT=binding.runner.RAW/'graph_seeded_paths'
    core.OUT=OUT;core.raw_curvature=supported_curvature;core.offers=source_offers;return core


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['short','core'],required=True);args=parser.parse_args()
    module=configure(args.stage)
    if args.stage=='short':module.main();return
    OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve source-owned core experiment')
    cases=read(binding.runner.RAW/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),existing_core_driver_sha256=sha(Path(core.__file__)),
        hypothesis='extra outside-source points in a frozen HMM path should not hide an independently curved all-but-endpoint source core',
        intersection_before_new_fits_uses_original_IDs_only=True,
        original_endpoint_rules_unchanged='one endpoint only, gap>=5 median cadence, polynomial leverage>=0.9',
        existing10s12points250Hz_BIC10_every_single_point_deletion_rule=True,
        maximum_one_core_per_case_and_same_candidate_alias_from_both_arm_screened_HMM=True,
        original_graph_and_parent_likelihood_observations_preserved=True,
        core_predictive_vs_core_curved_same_original_IDs_candidate_alias_and_other_priors=True,
        original_core_noise_power_inherited_no_noise_precision_tuning=True,
        c0_fitted_c_matched_cold5x48_budget=True,no_GPS_following_TLE_or_new_RF=True,
        rule_engineered_after_inspecting0215_so_development_only=True,
        prior_whole_short20scan_confirmation_negative_not_a_generalized_policy=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(core.one,cases))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=True))


if __name__=='__main__':main()
