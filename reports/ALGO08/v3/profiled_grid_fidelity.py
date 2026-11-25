"""Audit a sealed score failure and demonstrate what a rate bound would buy."""

import argparse
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path

from scipy.optimize import brentq


GATE = .005
SOUTH_PIN = "6ddb80c8cf457f39d087356f29a5292728207340c3f9a9043b2f80b72a592414"


def predictive_error(log_radius, curved_quadratic, predictive_quadratic, rank):
    """Bound fixed-design Gaussian prediction given a certified common log-rate radius.

    The candidate quadratic energies omit normalization and log-determinants.
    The precision matrices must be positive definite, their data and prior
    scale ratios bounded on both sides, and the predictive base covariance fixed.
    This real-arithmetic envelope does not certify float rounding or the radius.
    """
    scalars = (log_radius, curved_quadratic, predictive_quadratic)
    if not all(math.isfinite(v) and v >= 0 for v in scalars) or type(rank) is not int or rank < 0:
        raise ValueError("Expected nonnegative finite energies, radius and integral rank")
    scale = math.exp(log_radius)
    shift = scale*math.expm1(log_radius)*math.sqrt(curved_quadratic)
    current = math.sqrt(predictive_quadratic)
    # Expand the differences to avoid cancellation at small radii.
    upper = (math.expm1(log_radius)*predictive_quadratic
             + scale*(2*current*shift+shift**2))
    retained = max(0., current-shift)
    lower = ((current-retained)*(current+retained)
             - math.expm1(-log_radius)*retained**2)
    return max(upper, lower)+rank*log_radius


def scalar_witness():
    """Use the released one-group update with one coefficient of fixed prior precision."""
    # Ten equal rows, unit noise scale and likelihood power, noise_nu=4.
    # Sum of squared design entries is S, and y is exactly proportional to U.
    alpha, beta, s, y2 = 7., 2., 100., 10_000.
    c = alpha*s

    def update(rate):
        ratio = rate/(rate+c)
        return beta+(y2*ratio**2+s*ratio)/2

    def derivative(rate):
        return (.5*s+y2*rate/(rate+c))*c/(rate+c)**2

    rows = []
    for a, b in ((2., 50.), (50., 700.), (700., 5052.)):
        rate = brentq(lambda r: update(r)-r, a, b, xtol=1e-12)
        weight = alpha/rate
        coefficient = math.sqrt(y2/s)*c/(rate+c)
        precision = 1+weight*s
        gamma = 2*alpha*(math.log(rate/beta)+beta/rate-1)
        curved = weight*y2*(rate/(rate+c))**2+coefficient**2+math.log(precision)+gamma
        # A fixed zero-valued unit predictive observation with design coefficient one.
        variance = 1+1/precision
        prediction = coefficient**2/variance+math.log(variance)
        rows.append(dict(rate=rate, log_residual=abs(math.log(update(rate)/rate)), slope=derivative(rate),
                         reciprocal_condition=1., curved=curved, predictive=prediction,
                         full_score=curved+prediction))
    return rows


def audit(archive):
    body = gzip.decompress(archive.read_bytes())
    if sha256(body).hexdigest() != SOUTH_PIN:
        raise ValueError("The sealed South receipt changed")
    source = json.loads(body)
    offers = {}
    for case, report in source["offers"].items():
        grids = report["endpoint_grid_path"]
        # Read the exact linked numerical documents, not the plotted colors.
        stock, profile = (grids[mode]["grid"]["value"]["document"]["points"] for mode in ("stock", "proof"))

        def layout(row):
            return row["east_km"], row["north_km"], row["failures"]

        if [layout(row) for row in stock] != [layout(row) for row in profile]:
            raise ValueError("Expected the original matched ordered layout")
        stats = {}
        for arm in ("c0", "fitted_c"):
            values = [a["scores"][arm] for a in stock]
            data = []
            for i, (a, b) in enumerate(zip(stock, profile, strict=True)):
                if a["scores"][arm] is None or b["scores"][arm] is None:
                    continue
                data.append((b["scores"][arm]-a["scores"][arm], i))
            delta, index = max(data, key=lambda v: abs(v[0]))
            stats[arm] = dict(count=len(data), over_limit=sum(abs(d) > GATE for d, _ in data),
                              worst_change=delta, worst_index=index, stock_score=values[index],
                              stock_relative_loss=values[index]-min(v for v in values if v is not None))
        readback = report["readback"]
        offers[case] = dict(stats=stats, capture=readback["capture"], posterior=readback["posterior"],
                            accepted=readback["accept"])
    return dict(source_sha256=SOUTH_PIN, gate=GATE, offers=offers, scalar_counterexample=scalar_witness(),
                waveform_reads=0, solver_runs=0, performance_runs=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.receipt), indent=2, sort_keys=True, allow_nan=False))
