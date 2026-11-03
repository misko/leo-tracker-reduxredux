"""Same IID engine for the prospective causal freshness confirmation."""
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('causal_fresh_core', HERE.parent/'causal_fresh/model.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def validate_proofs(manifest, document):
    start = document['start_utc_ns']
    if manifest['capture_start_utc_ns'] != start or manifest['session_id'] != document['session_id']:
        raise ValueError('patch capture binding differs')
    if not manifest['tracks'] and (manifest['proofs'] or manifest['selected_snapshots']):
        raise ValueError('a no-op patch must contain no selected snapshot or proof')
    keys = ('provider', 'collected_utc_ns', 'sha256', 'archive_path')
    proven = set()
    for proof in manifest['proofs']:
        if (proof['qualified'] is not True or proof['capture_start_utc_ns'] != start
                or not proof['collected_utc_ns'] < proof['journal_published_utc_ns'] < start):
            raise ValueError('selected bytes were not proven available before capture')
        if core.digest(proof['archive_path']) != proof['sha256']:
            raise ValueError('proven snapshot bytes changed')
        proven.add(tuple(proof[k] for k in keys))
    selected = {tuple(row[k] for k in keys) for row in manifest['selected_snapshots']}
    if selected != proven or (manifest['tracks'] and not proven):
        raise ValueError('selected snapshots differ from publication proofs')


def build_model(documents, config, variant, index):
    if len(documents) != 1 or index not in (10, 18, 35, 60, 75):
        raise ValueError('one frozen confirmation scan required')
    metadata = dict(variant=variant, full_manifest_index=index,
                    fit_protocol_sha256=core.digest(HERE/'FIT_PROTOCOL.md'))
    document = documents[0]
    if variant == 'original':
        metadata.update(changed_slots=0, orbit_inputs='original guarded bank')
    elif variant == 'fresh':
        path = HERE/'patches'/f'{index:02d}.json'
        manifest = json.loads(path.read_text())
        if manifest['schema'] != 'ds11-causal-fresh-confirmation-bank-patch/v1' or manifest['index'] != index:
            raise ValueError('unexpected patch schema or index')
        for source, expected in manifest['source_sha256'].items():
            if core.digest(source) != expected.removeprefix('sha256:'):
                raise ValueError(f'patch source changed: {source}')
        if core.digest(manifest['array']['path']) != manifest['array']['sha256'].removeprefix('sha256:'):
            raise ValueError('patch array digest differs')
        validate_proofs(manifest, document)
        with np.load(manifest['array']['path'], allow_pickle=False) as arrays:
            document = core.apply_arrays(document, manifest, arrays, config['timing_grid_s'])
        metadata.update(changed_slots=sum(len(r['candidate_ids']) for r in manifest['tracks']),
                        patch_path=str(path), patch_sha256=core.digest(path), causal=True)
    else:
        raise ValueError('unknown orbit arm')
    return core.Model(document, config, metadata)
