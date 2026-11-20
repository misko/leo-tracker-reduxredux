"""Exploratory DS26 regional position estimators from anonymous upstream graph tracks.

Run with the repository venv and frozen-001/src on PYTHONPATH, OPENBLAS_NUM_THREADS=1.
Outputs contain estimates, RF diagnostics, timings and the declared panel. No reference
position, previous location, v5 result, or saved satellite assignments enter this file.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from scipy.optimize import lsq_linear
from sgp4.api import SatrecArray

from leo.sky.frames import (
    ecef_to_enu_matrix, geodetic_to_ecef_km, greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns, teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets


ROOT = Path(__file__).resolve().parent
WORK = Path("/srv/bulk/leo-dev/accuracy-repair-20261115/ds26-four-configs-twice-001")
INPUT = Path("/srv/bulk/leo-dev/algo07v3-shortcuts-20261107/inputs")
GRAPHS = Path("/srv/bulk/leo/research/algo07v3-20261104/tracks001/candidate")
CENTER = (37.906, -122.545)
PERIOD = 1 / 4.4e-6
CARRIER = 11.5e9
SAMPLES = 12
K = 12
PHASE_SD_S = 2.
SHAPE_SD = 180.
LEVEL_SD = 550.
SEED = "embedded-cold-v1"


def read(path):
    return json.loads(path.read_bytes())


def panel():
    rows = read(WORK / "plans/science.json")["cohorts"]["DS26"]["members"]
    labels = [r["dataset_label"] for r in rows if r["dataset_label"] != "DS26-0002"]
    return sorted(sorted(labels, key=lambda k: hashlib.sha256((SEED + k).encode()).digest())[:32])


def wrap(y):
    return y - PERIOD * np.rint(y / PERIOD)


def observer(xy):
    lat = CENTER[0] + xy[1] / 111.
    lon = CENTER[1] + xy[0] / (111.32 * np.cos(np.deg2rad(CENTER[0])))
    return geodetic_to_ecef_km(lat, lon, 0), ecef_to_enu_matrix(lat, lon)


def state(rows, anchor, seconds):
    jd, fr = julian_day_from_utc_ns(anchor + np.rint(seconds * 1e9).astype(np.int64))
    err, p, v = SatrecArray(rows).sgp4(jd, fr)
    p, v = teme_to_ecef(p, v, greenwich_mean_sidereal_time_rad(jd, fr))
    return err, p, v


def projection(p, v, xy):
    obs, enu = observer(xy)
    delta = p - obs
    distance = np.linalg.norm(delta, axis=-1)
    unit = delta / distance[..., None]
    rate = np.sum(v * unit, axis=-1)
    scale = CARRIER / 299792.458
    grad = scale * (v - rate[..., None] * unit) / distance[..., None]
    return -scale * rate, grad @ enu[0], grad @ enu[1], unit @ enu[2]


def build_bank(case, meta, *, check_approximation=True):
    cutoff = meta["causal_cutoff_utc_ns"]
    anchor = meta["anchor_utc_ns"]
    oldest = cutoff - 48 * 3600 * 10**9
    paths = sorted((INPUT / case / "tle").rglob("*.tle"))
    eligible_paths = [p for p in paths if oldest <= int(p.name.split("-")[0]) <= cutoff]
    snapshot = eligible_paths[-1]
    raw = snapshot.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == snapshot.stem.split("-")[1]
    catalog = parse_element_sets(raw.decode())
    rows = [sat for sat, name, epoch in zip(
        catalog.satellites, catalog.names, catalog.element_epoch_utc_ns(), strict=True
    ) if "STARLINK" in name.upper() and oldest <= epoch <= cutoff]
    duration = int(np.ceil(meta["duration_s"]))
    coarse_t = np.arange(0., duration + 60., 60.)
    err, p, v = state(rows, anchor, coarse_t)
    sin_el = projection(p, v, (0, 0))[-1]
    keep = (err == 0).all(axis=1) & (np.max(sin_el, axis=1) >= -.06)
    selected = [s for s, use in zip(rows, keep, strict=True) if use]
    knots = np.arange(-5., duration + 11., 5.)
    err, p, v = state(selected, anchor, knots)
    valid = (err == 0).all(axis=1)
    ids = np.array([s.satnum for s in selected])[valid]
    p, v = p[valid], v[valid]
    f, east, north, sin_el = projection(p, v, (0, 0))
    rate = np.gradient(f, 5., axis=1, edge_order=2)
    bank = dict(ids=ids, t=knots, f=f, east=east, north=north, rate=rate, up=sin_el)
    receipt = dict(snapshot=snapshot.name, eligible=len(rows), regional=len(ids), knots=len(knots),
                   float32_bytes=int(5 * f.size * 4))
    if not check_approximation:
        return bank, receipt
    # Midpoint samples from fresh SGP4 at displaced sites check table error.
    mids = knots[1:-2:4] + 2.5
    _, pm, vm = state([s for s, ok in zip(selected, valid, strict=True) if ok], anchor, mids)
    corner_errors = []
    center_errors = []
    ix = np.searchsorted(knots, mids) - 1
    for xy in ((0, 0), (-12.5, -12.5), (-12.5, 12.5), (12.5, -12.5), (12.5, 12.5)):
        exact, _, _, up = projection(pm, vm, xy)
        approx = f + xy[0] * east + xy[1] * north
        error = ((approx[:, ix] + approx[:, ix+1]) * .5 - exact)[up >= 0]
        (center_errors if xy == (0, 0) else corner_errors).extend(np.abs(error).tolist())
    receipt.update(center_p95_hz=float(np.percentile(center_errors, 95)),
                   corners_p95_hz=float(np.percentile(corner_errors, 95)))
    return bank, receipt


def interpolate(table, times, bank):
    fractional = (times - bank["t"][0]) / 5.
    index = fractional.astype(int)
    assert np.all((index >= 0) & (index + 1 < table.shape[1]))
    mix = fractional - index
    return table[:, index] + (table[:, index+1] - table[:, index]) * mix


def tile_stats(raw):
    mean = np.mean(raw, axis=-2)
    centered = raw - mean[..., None, :]
    cov = np.einsum("...si,...sj->...ij", centered, centered) / SAMPLES
    return mean, cov


def phase_cost(mean, cov, x, y, bias, *, shape_only=False):
    dr = wrap(mean[..., 0] - x * mean[..., 1] - y * mean[..., 2] - bias)
    phase_slope = mean[..., 3]
    vr = (cov[..., 0, 0] - 2*x*cov[..., 0, 1] - 2*y*cov[..., 0, 2]
          + x*x*cov[..., 1, 1] + y*y*cov[..., 2, 2] + 2*x*y*cov[..., 1, 2])
    cross = cov[..., 0, 3] - x*cov[..., 1, 3] - y*cov[..., 2, 3]
    w = 0. if shape_only else 1 / LEVEL_SD**2
    denom = cov[..., 3, 3] / SHAPE_SD**2 + w * phase_slope**2 + 1 / PHASE_SD_S**2
    tau = np.clip((cross / SHAPE_SD**2 + w * dr * phase_slope) / denom, -8., 8.)
    cost = ((vr - 2*tau*cross + tau*tau*cov[..., 3, 3]) / SHAPE_SD**2
            + w * (dr - tau*phase_slope)**2 + (tau / PHASE_SD_S)**2)
    return np.maximum(cost, 0.)


def descriptors(doc, bank):
    indexes = sorted(doc["curved_indices"], key=lambda i: -len(doc["tracks"][i]["times"]))[:64]
    items = []
    for ti in indexes:
        tr = doc["tracks"][ti]
        t = np.asarray(tr["times"])
        sample = np.rint(np.linspace(0, len(t)-1, SAMPLES)).astype(int)
        t = t[sample]
        ratio = tr["rf_hz"] / CARRIER
        visible = (interpolate(bank["up"], t, bank).min(axis=1) >= -.008)
        idx = np.flatnonzero(visible)
        if len(idx) < K:
            continue
        features = [interpolate(bank[k][idx], t, bank) * ratio for k in ("f", "east", "north", "rate")]
        features[0] = np.asarray(tr["values"])[sample] - features[0]
        raw = np.stack(features, axis=-1)
        mean, cov = tile_stats(raw)
        shape = phase_cost(mean, cov, 0, 0, 0, shape_only=True)
        width = np.maximum(1., np.abs(wrap(mean[:, 0])) / 12000.)
        # Include satellites with the best shape regardless of receiver bias, plus
        # competitors compatible with a small initial bias. Keep twelve distinct IDs.
        order = list(np.argsort(shape)[:K//2])
        order.extend(j for j in np.argsort(shape + width**2) if j not in order)
        keep = np.array(order[:K])
        items.append(dict(ti=ti, t=t, raw=raw[keep], mean=mean[keep], cov=cov[keep],
                          ids=bank["ids"][idx[keep]], group=2*(tr["receiver"]-1)+int(tr["channel"]>4),
                          rf=tr["rf_hz"]/1e9-11.5, span=np.ptp(t)))
    if not items:
        return None
    return {k:np.stack([row[k] for row in items]) for k in items[0]}


def bias_vote(d):
    bias = np.zeros(4)
    for lane in np.unique(d["group"]):
        which = d["group"] == lane
        mean, cov = d["mean"][which], d["cov"][which]
        def score(b):
            c = phase_cost(mean, cov, 0, 0, b)
            return np.sum(1 / (1 + c.min(axis=1) / 4))
        grid = np.linspace(-PERIOD/2, PERIOD/2, 73, endpoint=False)
        b = max(grid, key=score)
        bias[lane] = wrap(max(b + np.linspace(-1700,1700,9), key=score))
    return bias


def grid_vote(d, bias, shape_only=False):
    best = None
    for east in np.linspace(-12.5, 12.5, 7):
        for north in np.linspace(-12.5, 12.5, 7):
            cost = phase_cost(d["mean"], d["cov"], east, north, bias[d["group"],None],
                              shape_only=shape_only)
            winners = np.argmin(cost, axis=1)
            loss = cost[np.arange(len(winners)), winners]
            score = np.sum(1 / (1 + loss / 4))
            if best is None or score > best[0]:
                best = (score, (east, north), winners, loss)
    return best


def choose_diverse(d, selected, winners, limit):
    """Greedy log-det of within-track position slopes after removing constant and orbit phase."""
    blocks = []
    for i in selected:
        data = d["raw"][i, winners[i]]
        deriv = data[:, 1:3] - data[:, 1:3].mean(axis=0)
        h = data[:, 3] - data[:, 3].mean()
        projector = np.eye(SAMPLES) - np.outer(h,h)/(h@h + (SHAPE_SD/PHASE_SD_S)**2)
        blocks.append(deriv.T@projector@deriv / (SAMPLES * SHAPE_SD**2))
    info = np.eye(2) * .01
    choices = []
    for _ in range(min(limit, len(selected))):
        logdet = [np.linalg.slogdet(info + a)[1] if i not in choices else -np.inf
                  for i, a in enumerate(blocks)]
        k = int(np.argmax(logdet))
        info += blocks[k]
        choices.append(k)
    return selected[choices]


def solve(d, selected, winners, bias, start, *, fitted_c, shape_only=False):
    owners = d["ids"][selected, winners[selected]]
    satellites, sat_rows = np.unique(owners, return_inverse=True)
    if len(satellites) < 3 or len(selected) < 4:
        return dict(status="insufficient")
    shape = (len(selected), SAMPLES)
    features = d["raw"][selected, winners[selected]]
    group = d["group"][selected]
    phase_start = 11 if fitted_c else 10
    count = phase_start + len(satellites)
    design = np.zeros((*shape, count))
    design[:,:,:2] = features[:,:,1:3]
    rows = np.arange(len(selected))
    design[rows,:,2+group] = 1.
    design[rows,:,6+group] = (d["t"][selected] - 150.) / 150.
    if fitted_c:
        design[:,:,10] = d["rf"][selected,None]
    design[rows,:,phase_start+sat_rows] = features[:,:,3]
    # Affine frequency branch at the grid hypothesis. One integer lift per track.
    dy = features[:,:,0].copy()
    level = (dy - features[:,:,1]*start[0] - features[:,:,2]*start[1]).mean(axis=1) - bias[group]
    dy -= (PERIOD * np.rint(level / PERIOD))[:,None]
    center = np.zeros(count)
    center[2:6] = bias
    sd = np.r_[[1000.]*2, [32000.]*4, [750.]*4, [200000.] if fitted_c else [], [PHASE_SD_S]*len(satellites)]
    centered = design - design.mean(axis=1,keepdims=True)
    ycentered = dy - dy.mean(axis=1,keepdims=True)
    # One mean and a whitened shape per track, with a common per-satellite timing parameter.
    A = centered / (SHAPE_SD*np.sqrt(SAMPLES))
    b = ycentered / (SHAPE_SD*np.sqrt(SAMPLES))
    if not shape_only:
        A = np.concatenate([A, design.mean(axis=1,keepdims=True)/LEVEL_SD], axis=1)
        b = np.concatenate([b, dy.mean(axis=1,keepdims=True)/LEVEL_SD], axis=1)
    lb = np.r_[[-12.5]*2, np.full(count-2, -np.inf)]
    ub = -lb
    weight = np.ones(len(selected))
    for _ in range(4):
        aw = (A * np.sqrt(weight)[:,None,None]).reshape(-1,count)
        bw = (b * np.sqrt(weight)[:,None]).ravel()
        # Scale columns by prior standard deviation. Bound the position through the fit.
        mat = np.vstack([aw*sd, np.eye(count)])
        target = np.r_[bw - aw@center, np.zeros(count)]
        solution = lsq_linear(mat, target, bounds=((lb-center)/sd,(ub-center)/sd),
                              method="bvls", tol=1e-8, max_iter=40)
        if not solution.success:
            return dict(status="optimizer_failed")
        x = solution.x * sd + center
        error = np.einsum("ijk,k->ij",A,x) - b
        weight = np.minimum(1., 2.5 / np.maximum(.01, np.linalg.norm(error,axis=1)))
    hz = np.einsum("ijk,k->ij",design,x) - dy
    if shape_only:
        hz -= hz.mean(axis=1,keepdims=True)
    return dict(status="estimate", xy=x[:2].tolist(), tracks=len(selected), satellites=len(satellites),
                rms_hz=float(np.sqrt(np.mean(hz*hz))), rms_kind="demeaned" if shape_only else "absolute",
                on_boundary=bool(np.max(np.abs(x[:2])) > 12.49))
