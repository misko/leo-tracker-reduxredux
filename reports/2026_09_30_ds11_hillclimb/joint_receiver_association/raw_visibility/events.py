"""One raw timing-match observation per anchored source/window."""
import hashlib


def delta(a,b,period):
    return (b-a+period/2)%period-period/2


def event(anchors,opposite_by_rx,owners,source,threshold,period):
    anchor=min(anchors,key=lambda c:hashlib.sha256(c['id'].encode()).digest())
    others=opposite_by_rx[1-anchor['receiver']]
    matches=[c for c in others if abs(delta(anchor['epoch_us'],c['epoch_us'],period))<=threshold]
    return dict(anchor_id=anchor['id'],anchor_rx=anchor['receiver'],hit=bool(matches),partner_ids=sorted({c['id'] for c in matches}),raw_only=bool(matches and all(not owners.get(c['id']) for c in matches)),conflicting_inferred_partner=any(owners.get(c['id']) and source not in owners[c['id']] for c in matches),shift_hits=[any(abs(delta(anchor['epoch_us']+period*k/7,c['epoch_us'],period))<=threshold for c in others) for k in (1,2,3)])
