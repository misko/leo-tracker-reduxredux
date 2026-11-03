"""Unchanged IID likelihood with independently verified causal orbit patches."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'tools'))
import ds7_fast_baseline_adapter as fast


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_completion(manifest, document, proof_document):
    if proof_document['schema'] != 'ds11-capture-start-snapshot-completion-proof/v1':
        raise ValueError('unknown completion proof schema')
    rows = [r for r in proof_document['scans'] if r['index'] == manifest['index']]
    if len(rows) != 1:
        raise ValueError('completion proof missing or duplicated')
    proof = rows[0]
    snapshot = manifest['selected_snapshot']
    expected = dict(provider=proof['provider'], collected_utc_ns=proof['snapshot_collected_utc_ns'],
                    sha256=proof['snapshot_sha256'], archive_path=proof['archive_path'])
    if snapshot != expected:
        raise ValueError('patch snapshot differs from completion receipt')
    start = document['start_utc_ns']
    publication_ns = Decimal(str(proof['journal_published_unix_s']))*1_000_000_000
    if (proof['session'] != document['session_id'] or proof['capture_start_utc_ns'] != start
            or manifest['capture_start_utc_ns'] != start or proof['qualified'] is not True
            or publication_ns >= start or publication_ns <= proof['snapshot_collected_utc_ns']):
        raise ValueError('snapshot completion not proven before this capture')
    if digest(proof['archive_path']) != proof['snapshot_sha256']:
        raise ValueError('completion receipt does not bind archive bytes')


def apply_arrays(document, manifest, arrays, timing_grid):
    """Pure application of a checked patch; never mutate the original document."""
    if manifest['session_id'] != document['session_id']:
        raise ValueError('patch session differs from observations')
    if not np.array_equal(np.asarray(manifest['timing_grid_s']), np.asarray(timing_grid)):
        raise ValueError('patch timing grid differs')
    tracks = [dict(track) for track in document['tracks']]
    seen = set()
    for row in manifest['tracks']:
        index = row['index']
        if not isinstance(index, int) or index < 0 or index >= len(tracks) or index in seen:
            raise ValueError('invalid or repeated track index')
        seen.add(index)
        track = tracks[index]
        if track['track_id'] != row['track_id']:
            raise ValueError('patch track ordering differs')
        slots = arrays[row['slots_key']]
        count = track['candidate_position_km'].shape[0]
        if (slots.ndim != 1 or slots.dtype.kind not in 'iu' or len(slots) == 0
                or len(np.unique(slots)) != len(slots) or np.any(slots < 0) or np.any(slots >= count)):
            raise ValueError('invalid candidate slots')
        for field, key in (('candidate_position_km', 'position_key'),
                           ('candidate_velocity_km_s', 'velocity_key')):
            replacement = arrays[row[key]]
            original = track[field]
            if replacement.shape != (len(slots), *original.shape[1:]) or not np.isfinite(replacement).all():
                raise ValueError('invalid replacement shape or values')
            track[field] = original.copy()
            track[field][slots] = replacement
    return dict(document, tracks=tracks)


class Model:
    def __init__(self, document, config, metadata):
        fast.baseline.profile = fast.profile
        self.engine = fast.Stationary(document, config)
        self.metadata = metadata

    def evaluate(self, x, gradient=True):
        score, derivative = self.engine.evaluate(np.asarray(x, dtype=float), gradient=gradient)
        return dict(score=score, gradient=derivative)


def build_model(documents, config, variant, index=None):
    if len(documents) != 1 or variant not in ('original', 'fresh'):
        raise ValueError('one recording and original/fresh variant required')
    if variant == 'original':
        return Model(documents[0], config, dict(variant=variant, orbit_inputs='original'))
    if index not in (10, 13, 16, 27, 31):
        raise ValueError('index not selected by the frozen metadata inventory')
    path = HERE/'patches'/f'{index:02d}.json'
    manifest = json.loads(path.read_text())
    if manifest['schema'] != 'ds11-causal-fresh-bank-patch/v1' or manifest['index'] != index:
        raise ValueError('patch index differs')
    for source, expected in manifest['source_sha256'].items():
        if digest(source) != expected.removeprefix('sha256:'):
            raise ValueError(f'patch source changed: {source}')
    proof_path = HERE.parent/'orbit_age_audit/capture-start-completion-proof.json'
    if str(proof_path) not in manifest['source_sha256']:
        raise ValueError('patch does not bind completion proof')
    validate_completion(manifest, documents[0], json.loads(proof_path.read_text()))
    if digest(manifest['array']['path']) != manifest['array']['sha256'].removeprefix('sha256:'):
        raise ValueError('replacement array digest differs')
    with np.load(manifest['array']['path'], allow_pickle=False) as arrays:
        document = apply_arrays(documents[0], manifest, arrays, config['timing_grid_s'])
    metadata = dict(variant=variant, causal=True, patch_path=str(path), patch_sha256=digest(path),
                    protocol_sha256=digest(HERE/'PROTOCOL.md'),
                    changed_tracks=len(manifest['tracks']),
                    common_iid_diagnostic='Original orbit bank at both endpoints; not fresh-bank predictive score',
                    limitation='Original export track admission and candidate shortlists retained')
    return Model(document, config, metadata)
