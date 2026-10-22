"""Explicit20s-to10s duration ablation for an independently curved HMM core."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import probe_ds23_curved_temporal_core as original
from ds23_supported_curvature import supported_curvature
from run_algo01_ds23_sample import read,write,sha

OUT=original.runner.RAW/'supported_temporal_core'


def configure():
    original.OUT=OUT
    original.raw_curvature=supported_curvature


def main():
    configure();original.runner.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve duration ablation')
    write(OUT/'protocol.json',dict(cases=read(original.runner.RAW/'protocol.json')['cases'],
        source_sha256=sha(Path(__file__)),original_driver_sha256=sha(Path(original.__file__)),
        core_adapter_sha256=sha(Path(original.curved_core_view.__code__.co_filename)),
        supported_curvature_sha256=sha(Path(supported_curvature.__code__.co_filename)),
        explicit_dependency_override='original.raw_curvature=supported_curvature; every other core-offer/fit/coverage rule unchanged',
        minimum_curvature_span_s=10,minimum_core_points=12,minimum_linear_RMS_hz=250,minimum_quadratic_BIC_gain=10,
        curvature_requirements_must_survive_every_single_point_deletion=True,
        original20s_classifier_unchanged_prior_experiment_offered_no_cores=True,
        no_point_trim_after_fit_or_GPS_following_TLE_or_new_RF=True,
        paired_c_arms_same_native_core_priors_and5x48budget=True,
        original_likelihood_points_and_original_graph_preserved=True,
        experimental_not_published_ALGO_policy=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(original.one,read(OUT/'protocol.json')['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
