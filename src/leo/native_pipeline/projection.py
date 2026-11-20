"""Pure integer-epoch GLRT measurement projection, independent of storage.

Absolute sample counters are subtracted before floating-point conversion.
Only measurement support is projected; no trajectory or catalogue is consulted.
"""
from dataclasses import dataclass
import math

from leo.contracts.digests import canonical_digest


@dataclass(frozen=True)
class Support:
    start: int
    end: int
    center: float
    moments: tuple[float, float, float, float]


@dataclass(frozen=True)
class WindowAuthority:
    capture_digest: str
    analysis_digest: str
    visit: int
    receiver: int
    probe: int
    channel: int
    edge: str
    actual_rf_hz: float
    sample_rate_hz: int
    sample_count: int
    first_counter: int
    anchor_counter: int
    anchor_utc_ns: int


@dataclass(frozen=True)
class ProjectedCandidate:
    observation: tuple
    source: tuple
    support: Support


def integer_support(epoch: int, rate: int, samples: int) -> Support:
    if type(epoch) is not int or not 0 <= epoch < samples:
        raise ValueError('invalid integer epoch')
    if type(rate) is not int or not 0 < rate <= 10_000_000 or not 0 < samples <= rate//50:
        raise ValueError('invalid GLRT window geometry')
    period = rate/750.0
    symbol = rate*4.4e-6
    template_count = round(period)
    centers, starts, ends = [], [], []
    frame = 0
    while True:
        base = epoch+round(frame*period)
        if base+round(2*symbol) >= samples:
            break
        for s in range(2,66):
            start = base+round(s*symbol)
            count = min(round((s+1)*symbol),template_count)-round(s*symbol)
            if count < 2 or start < 0 or start+count-1 >= samples:
                continue
            centers.append(start+(count-1)/2.0)
            starts.append(start)
            ends.append(start+count)
        frame += 1
    if len(centers) < 2:
        raise ValueError('insufficient GLRT source support')
    center = math.fsum(centers)/len(centers)
    offsets = [(c-center)/rate for c in centers]
    return Support(min(starts),max(ends),center,
                   (1.0,0.0,math.fsum(x*x for x in offsets)/len(offsets)/2,
                    math.fsum(x**3 for x in offsets)/len(offsets)/6))


def project_integer_candidates(authority, candidates, *, minimum_margin=.025,
                               detector_side='arm-ungated'):
    a = authority
    if a.edge not in ('lower','upper') or not math.isfinite(a.actual_rf_hz) or a.actual_rf_hz <= 0:
        raise ValueError('invalid lane')
    if any(type(v) is not int or v < 0 for v in (a.visit,a.receiver,a.probe,a.first_counter,a.anchor_counter)):
        raise ValueError('invalid source coordinate')
    if not math.isfinite(minimum_margin):
        raise ValueError('invalid acceptance threshold')
    group = canonical_digest({'capture':a.capture_digest,'visit':a.visit,'rx':a.receiver,'probe':a.probe})
    relative = a.first_counter-a.anchor_counter
    def utc(local):
        return a.anchor_utc_ns+round((relative+local)*1e9/a.sample_rate_hz)
    result = []
    for rank,c in enumerate(candidates):
        for field in ('tracking_cfo_hz','exact_score','control_score','margin'):
            if not math.isfinite(c[field]):
                raise ValueError(f'invalid detector {field}')
        if c['margin'] < minimum_margin:
            continue
        if c.get('glrt_complete',1) != 1:
            raise ValueError('accepted candidate has incomplete GLRT')
        support = integer_support(c['epoch'],a.sample_rate_hz,a.sample_count)
        cid = canonical_digest({'group':group,'rank':rank,'analysis':a.analysis_digest})
        observation = (cid,group,a.receiver,a.channel,a.edge,float(a.actual_rf_hz),
                       utc(support.start),utc(support.center),utc(support.end),
                       c['tracking_cfo_hz'],c['exact_score'],c['control_score'],c['margin'])
        source = (cid,group,a.visit,a.receiver,a.probe,rank,'integer',detector_side)
        result.append(ProjectedCandidate(observation,source,support))
    return result
