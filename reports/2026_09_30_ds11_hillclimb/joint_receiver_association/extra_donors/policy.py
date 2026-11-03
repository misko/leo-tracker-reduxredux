"""Chronological, causal metadata selection without position-error access."""
def choose(captures,cutoff,limit=4):
    eligible=[c for c in captures if c['sample_rate_hz']==2500000
              and c['radio_id']=='radio_pluto_5d4d' and set(c['receiver_ids'])=={0,1}
              and c['utc_qualified'] and not c['exclusion_reasons']
              and c['capture_end_utc_ns']<cutoff and c['finalized_utc_ns']<cutoff]
    return sorted(eligible,key=lambda c:(c['capture_start_utc_ns'],c['session_id']))[:limit]


def family(rate,frequencies,families):
    key=tuple(sorted(set(frequencies)))
    matches=[f['family'] for f in families if f['sample_rate_hz']==rate and tuple(sorted(f['rf_hz']))==key]
    if len(matches)>1:raise ValueError('ambiguous acquisition family')
    return matches[0] if matches else None
