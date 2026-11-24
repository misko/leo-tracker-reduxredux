"""Local position-error moments on the original scoring sphere."""

from itertools import combinations
from math import cos, fsum, hypot, isclose, pi, radians, sin, sqrt

from tools.pipeline_eval.scoring import coordinate, distance_km


TOLERANCE = 5e-12


def east_north_km(reference, endpoint):
    """Local azimuthal-equidistant chart on exactly the scoring sphere."""
    lat0, lon0 = coordinate(reference)
    lat1, lon1 = coordinate(endpoint)
    distance = distance_km(reference, endpoint)
    if distance == 0.:
        return (0., 0.)
    if isclose(distance, 6371.0088*pi, rel_tol=0., abs_tol=1e-8):
        raise ValueError("A single local azimuth is undefined at the antipode")
    base, destination = radians(lat0), radians(lat1)
    longitude = radians(lon1-lon0)
    east = cos(destination)*sin(longitude)
    north = sin(radians(lat1-lat0)) + sin(base)*cos(destination)*2*sin(longitude/2)**2
    norm = hypot(east, north)
    return (distance*(east/norm), distance*(north/norm))


def decompose(offsets):
    """Compute radial MSE, mean-offset magnitude and centered spread over common rows."""
    n = len(offsets)
    if not n:
        raise ValueError("A shared scored roster is required for a position-error decomposition")
    mean = tuple(fsum(component)/n for component in zip(*offsets, strict=True))
    squared_mean = fsum(axis*axis for axis in mean)
    radial = fsum(e*e+north*north for e, north in offsets)/n
    spread = fsum((e-mean[0])**2+(north-mean[1])**2 for e, north in offsets)/n
    pairwise = fsum((a[0]-b[0])**2+(a[1]-b[1])**2 for a, b in combinations(offsets, 2))/n**2
    if (not isclose(radial, squared_mean+spread, abs_tol=TOLERANCE, rel_tol=TOLERANCE)
            or not isclose(spread, pairwise, abs_tol=TOLERANCE, rel_tol=TOLERANCE)):
        raise ValueError("The squared error and pairwise centered identities must both hold")
    return dict(n=n, radial_mse_km2=radial, squared_mean_offset_km2=squared_mean, centered_mse_km2=spread,
                radial_rms_km=sqrt(radial), mean_offset_km=sqrt(squared_mean), centered_rms_km=sqrt(spread),
                max_identity_residual_km2=max(abs(radial-squared_mean-spread), abs(spread-pairwise)))
