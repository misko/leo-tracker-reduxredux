"""Admit frozen DS12 observations and causal banks to the existing fit ports."""
import json
from pathlib import Path

import numpy as np
from acquisition_dot import prepare as _establish_research_imports  # noqa: F401
from adapter import TrackPort
from admit_heldout_orbit import verify_extension
from common import Scan, independent_tracks, make_config
from geoid import load_height_model
from physics import OrbitBank, StateLayout, TrackObservations, geometric_candidate_union
from regression_batch import digest

HERE = Path(__file__).resolve().parent


def prepare_heldout(unit):
    selection_path = HERE/'ds12-heldout-selection.json'
    assert digest(selection_path) == selection_path.with_suffix('.sha256').read_text().strip()
    selection = json.loads(selection_path.read_text())
    matches = [r for r in selection['units'] if r['unit_id'] == unit]
    if len(matches) != 1:
        raise ValueError('unit is outside frozen held-out selection')
    binding = matches[0]
    directory = HERE/'held-out'/unit
    observation_path, evidence_path = directory/'observations.json', directory/'evidence.json'
    raw_meta_path, extended_meta_path = directory/'orbits.json', directory/'orbits-extended.json'
    raw_meta = json.loads(raw_meta_path.read_text())
    extended_meta = json.loads(extended_meta_path.read_text())
    raw_path, extended_path = Path(raw_meta['state_file']), Path(extended_meta['state_file'])
    observations = json.loads(observation_path.read_text())
    evidence = json.loads(evidence_path.read_text())
    if (observations['session_id'] != binding['session_id']
            or observations['manifest_sha256'] != binding['manifest_sha256']
            or evidence['session_id'] != binding['session_id']):
        raise ValueError('held-out session identity mismatch')
    observation_digest = digest(observation_path)
    if (raw_meta['observation_sha256'] != observation_digest
            or evidence['source']['sha256'] != observation_digest
            or raw_meta['session_id'] != binding['session_id']
            or raw_meta['tle']['sha256'] != observations['snapshot_sha256']
            or not raw_meta['tle']['causal']
            or raw_meta['tle']['snapshot_collected_utc_ns'] >= observations['start_utc_ns']):
        raise ValueError('observation or causal orbit binding mismatch')
    if (digest(raw_path) != raw_meta['state_sha256']
            or digest(extended_path) != extended_meta['state_sha256']
            or extended_meta['parent']['metadata_sha256'] != digest(raw_meta_path)
            or extended_meta['parent']['state_sha256'] != raw_meta['state_sha256']
            or extended_meta['session_id'] != binding['session_id']
            or extended_meta['tle'] != raw_meta['tle']):
        raise ValueError('extended orbit binding mismatch')
    config = make_config()
    with (np.load(raw_path, allow_pickle=False) as raw,
          np.load(extended_path, allow_pickle=False) as ext):
        verify_extension(raw, ext)
        original_bank = OrbitBank(tuple(map(int, raw['satellite_ids'])), raw['knot_times_s'],
                                  raw['positions_ecef_km'], raw['velocities_ecef_km_s'])
        union = geometric_candidate_union(original_bank, config)
        admitted = set(union.norad_ids)
        indices = np.array([i for i, n in enumerate(original_bank.norad_ids) if n in admitted])
        if not indices.size:
            raise ValueError('empty geometric candidate union')
        bank = OrbitBank(tuple(original_bank.norad_ids[i] for i in indices), ext['knot_times_s'],
                         ext['positions_ecef_km'][indices], ext['velocities_ecef_km_s'][indices])
    retained, excluded = independent_tracks(evidence)
    tracks = []
    for row in retained:
        times = (np.asarray(row['times_utc_ns'], dtype=np.int64)-observations['start_utc_ns'])/1e9
        track = TrackObservations(tuple(row['physical_observation_ids']), times,
                                  np.asarray(row['measured_hz']),
                                  np.full(len(times), row['receiver_id'], dtype=int), row['rf_hz'])
        tracks.append((row['track_id'], track))
    input_paths = [selection_path, observation_path, evidence_path, raw_meta_path,
                   extended_meta_path, raw_path, extended_path]
    bindings = {str(p): digest(p) for p in input_paths}
    scan = Scan(unit, observations['session_id'], bank, StateLayout(bank.norad_ids), config,
                tracks, excluded, bindings, bool(raw_meta['catalogue_gap']), union)
    height = load_height_model()
    ports = [TrackPort(track, bank, scan.layout, config, height) for _, track in tracks]
    ids = [identifier for p in ports for identifier in p.observation_ids]
    if len(ids) != len(set(ids)):
        raise ValueError('physical observations reused across fitted tracks')
    return scan, height, ports
