"""Freeze the DS26-0170 cancellation pair before executing either numerical trial."""
import hashlib
import json
from pathlib import Path

from diff_algo07_star_evidence import load_export
from verify_algo07_star import load

from leo.cli.algo07_profile import digest, verify, write_new
from leo.storage.fast_graph_position import FastGraphPositionStore

repo = Path.cwd()
base = Path('/srv/bulk/leo/research/algo07-star-20261104')
case = base / 'iteration001/DS26-0170'
config = load(case)
manifest = Path(config['manifest'])
assert verify(manifest)['verified']
reference_export = Path(config['reference_evidence']) / 'ALGO03'
_, files = load_export(reference_export)
decision_path = files['worker/recovery/decision.json']
decision = json.loads(decision_path.read_text())
schedule = []
for stage in decision['stages']:
    assert stage['status'] == 'complete' and stage['returncode'] == 0
    schedule.append(dict(name=stage['name'], script=Path(stage['command'][2]).name,
                         seconds=stage['seconds']))
    if stage['name'] == 'target-4-audit':
        break
assert schedule[-1]['name'] == 'target-4-audit' and len(schedule) == 12
study = case / 'logical-cancellation-001'
study.mkdir(exist_ok=False)
inputs = {}
for side in ('reference', 'candidate'):
    store = FastGraphPositionStore(Path(config[side]))
    jobs = [j for j in store.inputs() if j['run_id'] == config['run_id']]
    assert len(jobs) == 1
    target = study / 'inputs' / side
    descriptor = store.export_analysis(jobs[0], target)
    inputs[side] = dict(descriptor=str(target / 'descriptor.json'),
                        descriptor_sha256=digest(target / 'descriptor.json'),
                        input_sha256=descriptor['input_sha256'])
assert inputs['reference']['input_sha256'] == inputs['candidate']['input_sha256']
spec = json.loads(Path(config['runtimes']).read_text())['ALGO03']
source_paths = [repo / 'tools/algo03_stage_clock_fixture.py',
                Path('/tmp/algo03_clock_worker.py'), Path('/tmp/run_algo03_clock_trial.py')]
plan = dict(kind='algo07-star-controlled-algo03-cancellation-plan',
            order=['reference', 'candidate'],
            scope='Actual numerical children; stop admission after five targets',
            expected_omitted_track_ids=[a['track_id'] for a in decision['attempts'][5:]],
            schedule=schedule, stop_after='target-4-audit',
            maximum_seconds=decision['maximum_seconds'], real_wall_limit_seconds=1200,
            inputs=inputs, runtime=spec['runtime'], python=spec['python'],
            environment=spec.get('environment', {}), manifest=str(manifest),
            manifest_sha256=digest(manifest), reference_decision_sha256=digest(decision_path),
            source_pins={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
            production_modified=False, numerical_children_stubbed=False,
            production_deadline_behavior_qualified=False, scientific_parity_qualified=False,
            performance_comparison=False)
write_new(study / 'plan.json', plan)
assert verify(manifest)['verified']
print(json.dumps(dict(study=str(study), planned_children=len(schedule), trials=plan['order'])))
