"""Qualify saved GLRT results -> observations -> coarse seeds -> tracks in one run."""
import argparse
from pathlib import Path
import sys

from leo.native_pipeline.recipes import tracker_stages
from leo.native_pipeline.runner import artifact_digest, digest, run, write_json


def qualify(output):
    root = Path(__file__).resolve().parents[1]
    reports = root/'reports'
    full = reports/'2026_10_01_arm_ungated_full_scan'
    prior = reports/'2026_10_01_arm_ungated_tracker_comparison'
    output = output.resolve(); output.mkdir(parents=True,exist_ok=False)
    def artifact(path,fmt):
        return {'path':str(path),'format':fmt,'sha256':artifact_digest(path)}
    inputs = {'python':artifact(Path(sys.executable),'executable'),
        'projector':artifact(root/'tools/project_native_glrt_archive.py','executable'),
        'archive':artifact(full/'arm','native-glrt-archive-v1'),
        'seed':artifact(reports/'2026_09_30_arm_fast_tracks/grid/grid-trial-v3','executable'),
        'tracker':artifact(reports/'2026_09_30_arm_curvature_tracks/hybrid-v1/artifacts/leo-curvature-tracks','executable')}
    projection = {'id':'project','kind':'projection','executable':'python',
        'argv':['@projector','@archive','@output-dir','--capture-digest',
                'sha256:b74c950fb172433dab804ddd14b46a3f4c6c1d2e85a09855b0bfdff5da78e015'],
        'format':'json-v1','timeout_s':90,'artifacts':[
            {'id':'observations','path':'observations.tsv','format':'observations-tsv-v1',
             'expected_sha256':digest(full/'analysis/observations.tsv')},
            {'id':'sources','path':'candidate-map.tsv','format':'sources-tsv-v1','observations':'observations',
             'expected_sha256':digest(full/'analysis/candidate-map.tsv')},
            {'id':'support','path':'support.json','format':'json-v1'}]}
    stages = [projection]+tracker_stages('coarse-seeded','tracker','observations',seed_executable='seed')
    stages[-1]['expected_sha256'] = digest(prior/'coarse-seeded/tracks-0.tsv')
    stages[-2]['expected_sha256'] = digest(prior/'coarse-seeded/seeds-0.tsv')
    plan = {'schema':'leo-native-replay/v1','execution':{'mode':'serial','workers':1},'inputs':inputs,'stages':stages}
    write_json(output/'plan.json',plan)
    receipt = run(output/'plan.json',output/'run')
    print(receipt['status'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    qualify(parser.parse_args().output)
