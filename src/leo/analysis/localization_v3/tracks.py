"""Pure native-GLRT to polynomial preparation for the standalone v3 engine.

The original graph arithmetic, ordering and observation identities are retained.
No satellite, location, historical result, storage service or worker is needed.
"""
import hashlib

import numpy as np
from numpy.polynomial.legendre import legval

from leo.analysis.glrt_frequency_input import frequency_evidence
from leo.analysis.graph_tracklets import fit_lane
from leo.analysis.polynomial_tracklets import TrackConfig


def winning_observations(document):
    """Select the original maximum-margin gated peak, with deterministic ties."""
    evidence, _, metadata = frequency_evidence(document)
    probes = document['source']['probes']
    receivers = sorted({p['receiver_id'] for p in probes})
    rows = []
    for index, probe in enumerate(probes):
        eligible = [c for c in probe['candidates'] if c['passed_fractional_margin_gate'] is True]
        if not eligible:
            continue
        candidate = max(eligible, key=lambda c: (c['fractional_margin'], -c['candidate_rank']))
        cfo = float(candidate['fractional_tracking_cfo_hz'])
        if not np.isfinite(cfo):
            raise ValueError('nonfinite winning CFO')
        rows.append(dict(
            observation_id='sha256:' + hashlib.sha256(evidence.ids[index].encode()).hexdigest(),
            receiver=receivers.index(probe['receiver_id']) + 1,
            native_receiver_id=probe['receiver_id'], channel=int(probe['channel']),
            time_s=float(evidence.time_s[index]), measured_cfo_hz=cfo,
            actual_rf_hz=float(probe['actual_rf_hz']),
            fractional_margin=float(candidate['fractional_margin'])))
    if len({r['observation_id'] for r in rows}) != len(rows):
        raise ValueError('duplicate winning observation identity')
    rows.sort(key=lambda r: (r['receiver'], r['channel'], r['time_s'], r['observation_id']))
    return rows, metadata


def _single_rf_tracks(rows, source_id, config):
    tracks, assigned = [], set()
    for receiver, channel in sorted({(r['receiver'], r['channel']) for r in rows}):
        lane = [r for r in rows if (r['receiver'], r['channel']) == (receiver, channel)]
        if len({r['actual_rf_hz'] for r in lane}) != 1:
            raise ValueError('a receiver/channel changes RF within the recording')
        t = np.array([r['time_s'] for r in lane])
        y = np.array([r['measured_cfo_hz'] for r in lane])
        result = fit_lane(t, y, config)
        for tid, original in enumerate(result['tracks']):
            indexes = np.asarray(original['indices'], int)
            indexes = indexes[np.argsort(t[indexes], kind='stable')]
            pieces = []
            for raw in original['pieces']:
                piece = dict(raw)
                ix = np.asarray(piece['indices'], int)
                piece.update(start_s=float(t[ix].min()), end_s=float(t[ix].max()))
                residual = (y[ix] + config.alias_spacing_hz * result['alias_lifts'][ix]
                            - legval((t[ix] - piece['reference_time_s']) / piece['time_scale_s'],
                                     piece['coefficients_hz']))
                if (np.max(np.abs(residual))
                        >= config.association_sigma * config.noise_sigma_hz + 1e-6):
                    raise ValueError('Graph output violates its native residual gate')
                pieces.append(piece)
            ids = [lane[i]['observation_id'] for i in indexes]
            if assigned.intersection(ids):
                raise ValueError('duplicate Graph ownership')
            assigned.update(ids)
            tracks.append(dict(
                original, key=f'{source_id}-RX{receiver}-CH{channel}-T{tid:03}',
                source_id=source_id, receiver=receiver, channel=channel,
                bank='CH1-4' if channel <= 4 else 'CH5-8', rf_hz=lane[0]['actual_rf_hz'],
                observation_ids=ids, quality_status=original['diagnostics']['quality_status'],
                times=t[indexes],
                values=y[indexes] + config.alias_spacing_hz * result['alias_lifts'][indexes],
                pieces=pieces, start_s=float(t[indexes].min()), end_s=float(t[indexes].max())))
    return tracks, len(assigned)


def graph_tracks(rows, config, *, source_id='SCAN'):
    """Keep actual RF lanes separate, retaining the reference track identities."""
    tracks, total = [], 0
    for frequency in sorted({r['actual_rf_hz'] for r in rows}):
        selected = [r for r in rows if r['actual_rf_hz'] == frequency]
        partial, count = _single_rf_tracks(selected, source_id, config)
        for track in partial:
            track['key'] += f'-RF{frequency:.6f}'
        tracks.extend(partial)
        total += count
    ids = [oid for t in tracks for oid in t['observation_ids']]
    if len(ids) != len(set(ids)) or len(ids) != total:
        raise ValueError('RF lane split duplicated original point ownership')
    return tracks, total


def active_curvature(track):
    """Measure curvature after removing a line, with the original exact gates."""
    t, y = track['times'], track['values']
    x = t - t.mean()
    centered = y - y.mean()
    residual = centered - x * (centered @ x) / max(x @ x, 1e-12)
    return bool(np.ptp(t) >= 20 and np.sqrt(np.mean(residual**2)) >= 250)


def prepare_tracks(document, config: TrackConfig):
    """Return observations and graph evidence, not a claimed position solution."""
    observations, metadata = winning_observations(document)
    tracks, assigned = graph_tracks(observations, config)
    curved = [i for i, track in enumerate(tracks) if active_curvature(track)]
    return dict(observations=observations, metadata=metadata, tracks=tracks,
                graph_points=assigned, curved_indices=curved,
                status='tracks_prepared' if curved else 'no_active_curvature')
