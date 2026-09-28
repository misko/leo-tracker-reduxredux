"""Build reception-only search inputs without a receiver position or TLE fit."""
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent/'2026_09_27_roof_direction_subset'
sys.path.insert(0, str(SOURCE))
import pairing
from source_links import resolve
from leo.application.scanner_trajectory import project_scanner_candidates


def build(raw, prepared, *, bias_hz):
    """Bind each reserved track observation to its exact source anchor candidate.

    Reject missing/ambiguous anchors instead of treating them as nondetections.
    Satellite IDs, orbit fits and receiver coordinates are not inputs or outputs.
    """
    projected = project_scanner_candidates(raw)
    candidates = {c.candidate_id: c for c in projected}
    if len(candidates) != len(projected):
        raise ValueError('duplicate projected candidate ID')
    links = {(r['track_id'], r['observation_id']): r['candidate_ids'] for r in resolve(raw)}
    probes = {(p.visit_index, p.probe_index, p.receiver_id): p for p in raw.probes}
    if len(probes) != len(raw.probes):
        raise ValueError('ambiguous probe identity')
    rows = []
    seen = set()
    for track in prepared.tracks:
        for oid, train in zip(track.observation_ids, track.training_mask, strict=True):
            if train:
                continue
            ids = links.get((track.track_id, oid), ())
            if len(ids) != 1:
                raise ValueError('reserved observation lacks a unique source anchor')
            candidate = candidates[ids[0]]
            if candidate.candidate_id in seen:
                raise ValueError('source anchor occurs in multiple scored tracks')
            seen.add(candidate.candidate_id)
            probe_key = (candidate.visit_index, candidate.probe_index)
            anchor_probe = probes[(*probe_key, candidate.receiver_id)]
            counterpart_probe = probes.get((*probe_key, 1-candidate.receiver_id))
            if counterpart_probe is None:
                raise ValueError('missing counterpart probe is not a nondetection')
            for field in ('channel', 'edge', 'valid_start_counter', 'probe_start_ms'):
                if getattr(anchor_probe, field) != getattr(counterpart_probe, field):
                    raise ValueError('counterpart probe is not simultaneous and lane-matched')
            anchors = [a for a in anchor_probe.candidates if a.candidate_rank == candidate.candidate_rank]
            if len(anchors) != 1:
                raise ValueError('ambiguous anchor rank')
            anchor = anchors[0]
            outcome = pairing.counterpart(anchor, counterpart_probe.candidates,
                candidate.receiver_id, raw.sample_rate_hz, bias_hz)
            key = f'{raw.session_id}:{candidate.visit_index}:{candidate.probe_index}:{candidate.receiver_id}:{candidate.candidate_rank}'
            physical = None
            if outcome['matched']:
                other = f"{raw.session_id}:{candidate.visit_index}:{candidate.probe_index}:{1-candidate.receiver_id}:{outcome['counterpart_rank']}"
                physical = '|'.join(sorted((key, other)))
            rows.append(dict(session_id=raw.session_id, split='holdout', track_id=track.track_id,
                observation_id=oid, receiver_id=f'rx{candidate.receiver_id}', channel=candidate.channel,
                edge=candidate.edge.value, sample_rate_hz=raw.sample_rate_hz,
                anchor_margin=anchor.fractional_margin, matched=outcome['matched'],
                log_margin_ratio_rx1_rx0=outcome['log_margin_ratio_rx1_rx0'],
                east=0., up=0., physical_pair_key=physical, anchor_key=key))
    return rows
