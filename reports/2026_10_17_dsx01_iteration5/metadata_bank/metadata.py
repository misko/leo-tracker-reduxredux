"""Response-blind metadata projection and deterministic geometric bank cap."""
import numpy as np

MAXIMUM_CANDIDATES = 1024
METADATA_FIELDS = ('observation_id', 'time_s', 'actual_rf_hz', 'receiver', 'channel')


def observation_metadata(rows):
    """Read only declared metadata keys; measured response is never accessed."""
    projected = [{key:row[key] for key in METADATA_FIELDS} for row in rows]
    from leo.contracts.regional_position import PositionObservations
    receivers = np.array([r['receiver'] for r in projected])
    if not set(receivers) <= {1, 2}:
        raise ValueError('Frozen report metadata requires declared one-based RX1/RX2')
    observations = PositionObservations(tuple(r['observation_id'] for r in projected),
        np.array([r['time_s'] for r in projected]), np.zeros(len(projected)),
        np.array([r['actual_rf_hz'] for r in projected]), receivers-1,
        np.array([r['channel'] for r in projected]), np.ones(len(projected)))
    return observations, projected


def geometry_order(bank, prior):
    """Whole-prior potential visibility duration, then maximum horizon margin.

    Uses the same conservative geodetic-normal bound as the public regional
    screen, including the bank's predeclared timing margin. No response or
    station-reference argument exists.
    """
    from leo.analysis.regional_position_score import observer
    _, up = observer(prior, [0., 0.])
    position = bank.position_km
    radius = np.linalg.norm(position, axis=2)
    angle = np.arccos(np.clip(np.einsum('knj,j->kn', position, up)/radius, -1., 1.))
    maximum_dot = radius*np.cos(np.maximum(angle-prior.radius_km/6371.0088, 0.))
    margin = maximum_dot-(6356.752314245+prior.altitude_m/1000.)
    visible_count = (margin >= 0.).sum(axis=1)
    maximum_margin = margin.max(axis=1)
    return np.lexsort((bank.numbers, -maximum_margin, -visible_count)), visible_count, maximum_margin


def cap_bank(bank, prior, *, maximum_candidates=MAXIMUM_CANDIDATES):
    if not isinstance(maximum_candidates, int) or maximum_candidates < 1:
        raise ValueError('Positive fixed integer candidate cap required')
    order, count, margin = geometry_order(bank, prior)
    retained = order[:maximum_candidates]
    excluded = order[maximum_candidates:]
    # Stable catalogue-ID storage order; ranking controls membership only.
    retained = retained[np.argsort(bank.numbers[retained], kind='stable')]
    return bank.select(retained), dict(maximum_candidates=maximum_candidates,
        eligible_before_cap=len(bank.numbers), retained_after_cap=len(retained),
        cap_excluded_numbers=[int(n) for n in bank.numbers[excluded]],
        ranking='descending potential whole-prior visible-node count, descending maximum conservative horizon margin, ascending catalogue number',
        node_count=len(bank.nodes_s),
        all_geometry_scores=[dict(number=int(n), visible_nodes=int(c), maximum_margin_km=float(m))
            for n, c, m in zip(bank.numbers, count, margin)])
