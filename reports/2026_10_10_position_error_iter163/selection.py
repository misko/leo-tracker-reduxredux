"""Training-objective-only calibration choice; no held or reference fields."""
import math

PRIORITY=('control','zero-c','fitted-c')
TOLERANCE=1e-6


def choose(candidates):
    if set(candidates)!=set(PRIORITY):raise ValueError('exact three candidate receipts required')
    objectives={}
    for source in PRIORITY:
        candidate=candidates[source]
        if candidate.get('status')!='qualified':continue
        audit=candidate.get('audit') or {}
        if audit.get('qualified') is not True:raise ValueError('qualified status without audit')
        value=audit.get('objective')
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError('invalid qualified training objective')
        objectives[source]=value
    if not objectives:return None
    minimum=min(objectives.values())
    return next(source for source in PRIORITY if source in objectives and objectives[source]<=minimum+TOLERANCE)
