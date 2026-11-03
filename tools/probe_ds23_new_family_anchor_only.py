"""Keep unrelated original CFO observations unchanged in new-family trials."""

import argparse
import copy
from pathlib import Path
import numpy as np
import probe_ds23_new_curved_family as base
import audit_ds23_new_curved_family as audit
from ds23_frequency_events import make_event_problem
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_new_family_anchor_only'
BULK = Path('/srv/bulk/leo/research/ds23-new-family-anchor-only-20261021')
ORIGINAL_PREPARE = base.prepare


def restrict_refinements(original_tracks, refined_tracks, required_ids):
    if len(original_tracks) != len(refined_tracks):
        raise ValueError('same original track population required')
    required, found, result = set(required_ids), set(), []
    for old, new in zip(original_tracks, refined_tracks, strict=True):
        if old['observation_ids'] != new['observation_ids'] or old['key'] != new['key']:
            raise ValueError('refined physical observations differ')
        values = np.asarray(old['values']).copy()
        for k, oid in enumerate(old['observation_ids']):
            if oid in required:
                values[k] = new['values'][k]; found.add(oid)
        result.append(dict(old, values=values))
    if found != required:
        raise ValueError('conditional anchor absent from original measurements')
    return result


def prepare(case):
    d = ORIGINAL_PREPARE(case)
    p = make_event_problem(d['original_scan'], d['original_node'], d['original_mask'], 'c0',
        np.zeros(len(d['original_means'])), d['original_powers'], d['original_means'], d['hyper'], [])
    ids = [o for index in p.members for o in d['original_scan'].tracks[index]['observation_ids']]
    required = {ids[k] for anchors in d['anchors'].values() for k in anchors}
    if not required.issubset(d['updates']):
        raise ValueError('conditional anchor has no independently fitted RF refinement')
    tracks = restrict_refinements(d['original_scan'].tracks, d['refined'].tracks, required)
    refined = copy.copy(d['original_scan']); refined.tracks = tracks
    enriched = copy.copy(d['enriched']); enriched.tracks = tracks+d['enriched'].tracks[len(tracks):]
    d['refined'], d['enriched'] = refined, enriched
    d['updates'] = {oid: value for oid, value in d['updates'].items() if oid in required}
    return d


def configure():
    base.OUT, base.BULK, base.prepare = OUT, BULK, prepare
    audit.inference = base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['run', 'audit'], required=True); args = parser.parse_args()
    OUT.mkdir(exist_ok=True); BULK.mkdir(exist_ok=True)
    workflow = dict(refinement_scope='only actual original primary anchors of admitted new curves',
        unrelated_original_values_preserved_exactly=True,
        same_added_points_covariance_phase_priors_and_gates_as_all_lane_refinement=True,
        no_GPS_based_refinement_selection=True, no_new_RF_collection=True,
        source_sha256={p.name:sha(p) for p in [Path(__file__), ROOT/'tools/probe_ds23_new_curved_family.py',
            ROOT/'tools/ds23_new_curved_family.py', ROOT/'tools/audit_ds23_new_curved_family.py']})
    path = OUT/'workflow_protocol.json'
    if path.exists() and read(path) != workflow:
        raise ValueError('anchor-only refinement trial changed')
    if not path.exists():
        write(path, workflow)
    configure()
    if args.stage == 'run':
        base.main()
    else:
        audit.main()


if __name__ == '__main__':
    main()
