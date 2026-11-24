"""Compare signed paired receiver measurement differences within original Graph pieces."""

from collections import defaultdict
from itertools import pairwise
from math import remainder, sqrt
from random import Random
from statistics import fmean


ALIAS = 1/4.4e-6
SAMPLE_RATE = 10_000_000
MAX_GAP = 8*SAMPLE_RATE
ADJACENT_MAX = 2*SAMPLE_RATE
BIN_END_S = (.5, 1, 2, 4, 8)
ARMS = ("c0", "fitted_c")


def winner(row):
    return max((c for c in row["candidates"] if c["passed_fractional_margin_gate"] is True),
               key=lambda c: (c["fractional_margin"], -c["candidate_rank"]), default=None)


def epoch(factor):
    return factor["integer_epoch_sample"] + factor["fractional_epoch_offset_samples"]


def difference(stock, sparse):
    """Do not roll observations to improve the primary comparison."""
    delta = sparse["fractional_tracking_cfo_hz"] - stock["fractional_tracking_cfo_hz"]
    shift = epoch(sparse)-epoch(stock)
    close = abs(delta) <= 250 and abs(shift) <= 2
    wrapped = abs(remainder(delta, ALIAS)) <= 250 and abs(remainder(shift, 13_333)) <= 2
    return delta, shift, close, wrapped


def follows(a, b, *, gap=MAX_GAP, same_lift=True):
    return (a["piece"] == b["piece"] and b["ordinal"] == a["ordinal"]+1
            and (not same_lift or a["lift"] == b["lift"]) and 0 < b["counter"]-a["counter"] <= gap)


def blocks(track):
    """Candidate-only proposed pair moments, with endpoints and anchors preserved."""
    chunks = []
    cursor = 1
    while cursor+1 < len(track)-1:
        a, b = track[cursor:cursor+2]
        if a["short"] and b["short"] and follows(a, b, gap=ADJACENT_MAX):
            chunks.append([a["id"], b["id"]])
            cursor += 2
        else:
            cursor += 1
    return chunks


def split(matched):
    prior = None
    run = []
    for row in matched:
        if prior is not None and (not follows(prior["candidate"], row["candidate"], same_lift=False)
                                  or not follows(prior["installed"], row["installed"], same_lift=False)
                                  or prior["relative_lift"] != row["relative_lift"]):
            yield run
            run = []
        run.append(row)
        prior = row
    if run:
        yield run


def detrend(rows, key):
    first = rows[0]["candidate"]["counter"]
    t = [(row["candidate"]["counter"]-first)/SAMPLE_RATE for row in rows]
    y = [row[key] for row in rows]
    time_mean, mean = fmean(t), fmean(y)
    t = [value-time_mean for value in t]
    y = [value-mean for value in y]
    slope = sum(x*v for x, v in zip(t,y,strict=True))/sum(x*x for x in t)
    return y, [value-slope*x for x, value in zip(t,y,strict=True)]


def moment(pairs):
    left, right = zip(*pairs) if pairs else ((), ())
    return (len(pairs), sum(left), sum(right), sum(x*x for x in left), sum(y*y for y in right),
            sum(x*y for x, y in pairs))


def pearson(moment_):
    n,x,y,xx,yy,xy = moment_
    if n < 2:
        return None
    v,w = xx-x*x/n, yy-y*y/n
    return (xy-x*y/n)/sqrt(v*w) if v > 0 and w > 0 else None


def cluster_bootstrap(grouped):
    samples = [moment(pairs) for _key,pairs in sorted(grouped.items()) if pairs]
    if len(samples) < 8:
        return None
    sample = Random(7153)
    values = []
    for _ in range(800):
        chosen = sample.choices(samples, k=len(samples))
        rho = pearson(tuple(map(sum, zip(*chosen))))
        if rho is not None:
            values.append(rho)
    return [sorted(values)[int((len(values)-1)*p)] for p in (.025,.975)] if values else None


def dependence(runs, key):
    grouped = defaultdict(list)
    for run in runs:
        if run:
            grouped[run[0]["candidate"]["track"]].append(run)
    raw, demeaned, detrended, strict = [], [], defaultdict(list), []
    variogram = [[] for _ in BIN_END_S]
    qualifying_pieces = set()
    for track, pieces in grouped.items():
        for run in pieces:
            short_rows = [row for row in run if row["candidate"]["short"]]
            corrected = {}
            if len(short_rows) >= 8:
                centered, residual = detrend(short_rows,key)
                corrected = {r["candidate"]["id"]: (m,d) for r,m,d in zip(short_rows,centered,residual,strict=True)}
            for a,b in pairwise(run):
                x,y = a["candidate"], b["candidate"]
                if not (x["short"] and y["short"] and follows(x,y,gap=ADJACENT_MAX,same_lift=False)):
                    continue
                raw.append((a[key],b[key]))
                if corrected:
                    l,r = corrected[x["id"]], corrected[y["id"]]
                    demeaned.append((l[0],r[0]))
                    detrended[track].append((l[1],r[1]))
                    qualifying_pieces.add((x["piece"], a["installed"]["piece"]))
                    if y["lane_index"] == x["lane_index"]+1:
                        strict.append((l[1],r[1]))
            if corrected:
                for i,a in enumerate(short_rows):
                    for b in short_rows[i+1:]:
                        ca,cb = a["candidate"], b["candidate"]
                        lag = (cb["counter"]-ca["counter"])/SAMPLE_RATE
                        if lag > BIN_END_S[-1]:
                            break
                        k = next(k for k,edge in enumerate(BIN_END_S) if lag < edge or edge == BIN_END_S[-1])
                        diff = corrected[ca["id"]][1]-corrected[cb["id"]][1]
                        variogram[k].append(diff**2/2)
    flat = [values for group in detrended.values() for values in group]
    return dict(raw=[len(raw),pearson(moment(raw))], demeaned=[len(demeaned),pearson(moment(demeaned))],
                detrended=[len(flat),pearson(moment(flat))], strict_opportunity_adjacency=[len(strict),pearson(moment(strict))],
                tracks=len(detrended), piece_pairs=len(qualifying_pieces), bootstrap_95=cluster_bootstrap(detrended),
                variogram=[dict(lag_end_s=edge,pairs=len(values),gamma_hz2=fmean(values) if values else None)
                           for edge,values in zip(BIN_END_S,variogram,strict=True)])
