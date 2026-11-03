"""Bounded qualification of replay adapters against frozen DS9 tracker products.

Requires existing host binaries and saved report artifacts, never raw RF access.
Run with PYTHONPATH=src python tools/qualify_native_replay_ds9.py OUTPUT_DIRECTORY.
"""
import argparse
from pathlib import Path
import statistics

from leo.native_pipeline.evaluation import evaluate
from leo.native_pipeline.recipes import TRACKERS, tracker_stages
from leo.native_pipeline.runner import digest, finite_json, run, write_json

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT/'reports'


def qualify(output):
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    old = REPORTS/'2026_09_30_arm_streaming_tracks'
    prior = REPORTS/'2026_10_01_arm_ungated_tracker_comparison'
    new = REPORTS/'2026_10_01_arm_ungated_full_scan/analysis'
    base = REPORTS/'2026_09_30_arm_fast_tracks/server-baseline/output'
    binaries = {
        'rolling':old/'rolling/artifacts/leo-streaming-rolling',
        'kalman-v2':old/'kalman-v2/artifacts/leo-streaming-kalman-v2',
        'linking-v2':old/'linking-v2/artifacts/leo-local-tracklet-linking-v2',
        'coarse-seeded':REPORTS/'2026_09_30_arm_curvature_tracks/hybrid-v1/artifacts/leo-curvature-tracks',
        'rolling-backfill':REPORTS/'2026_10_01_arm_rolling_backfill/component/leo-streaming-rolling-backfill'}
    def artifact(path,fmt,**kwargs):
        return dict(path=str(path),format=fmt,sha256=digest(path),**kwargs)
    inputs = {'observations':artifact(new/'observations.tsv','observations-tsv-v1'),
              'sources':artifact(new/'candidate-map.tsv','sources-tsv-v1',observations='observations')}
    expected = {r['method']:r for r in finite_json(prior/'science-summary.json')}
    rows = []
    for method in TRACKERS:
        plan = {'schema':'leo-native-replay/v1','execution':{'mode':'serial','workers':1},
                'inputs':{**inputs,'tracker':artifact(binaries[method],'executable')}}
        if method == 'coarse-seeded':
            plan['inputs']['seed'] = artifact(REPORTS/'2026_09_30_arm_fast_tracks/grid/grid-trial-v3','executable')
        plan['stages'] = tracker_stages(method,'tracker','observations',seed_executable='seed')
        frozen = new/'tracks-0.tsv' if method == 'rolling-backfill' else prior/method/'tracks-0.tsv'
        plan['stages'][-1]['expected_sha256'] = digest(frozen)
        if method == 'coarse-seeded':
            plan['stages'][0]['expected_sha256'] = digest(prior/method/'seeds-0.tsv')
        path = output/(method+'.plan.json'); write_json(path,plan)
        receipts = [run(path,output/f'{method}-{i}') for i in range(3)]
        settings_path = REPORTS/'2026_09_30_arm_curvature_tracks/evaluation/thresholds.json'
        result = evaluate(new/'observations.tsv',new/'candidate-map.tsv',output/f'{method}-0'/(method+'.output'),
                          base/'server-observations.tsv',base/'server-candidate-map.tsv',base/'server-tracks.tsv',
                          finite_json(settings_path),[10])
        result['input_digests'] = {str(p):digest(p) for p in [settings_path,base/'server-observations.tsv',
                                    base/'server-candidate-map.tsv',base/'server-tracks.tsv']}
        summary = result['summary']
        assert summary['strict_represented'] == expected[method]['strict']
        assert summary['outputs'] == expected[method]['hypotheses']
        assert summary['outputs_without_any_reference_support'] == expected[method]['without_reference_support']
        for bucket in ('short','medium','long'):
            assert summary['duration_buckets'][bucket]['matched'] == expected[method]['duration_buckets'][bucket]['matched']
        assert summary['one_to_one'] == finite_json(prior/method/'evaluation.json')['primary']['complete_one_to_one_count']
        write_json(output/(method+'.evaluation.json'),result)
        row = {'method':method,**summary,'repeats':3,'all_outputs_equal_frozen':True,
               'host_algorithm_median_s':statistics.median(sum(s['algorithm_s'] for s in r['stages']) for r in receipts),
               'host_process_median_s':statistics.median(sum(s['wall_s'] for s in r['stages']) for r in receipts)}
        rows.append(row)
        print(method,summary['strict_represented'],row['host_algorithm_median_s'],flush=True)
    write_json(output/'summary.json',rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    qualify(parser.parse_args().output)
