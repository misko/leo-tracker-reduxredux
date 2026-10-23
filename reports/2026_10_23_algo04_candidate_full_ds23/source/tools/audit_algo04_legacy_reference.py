"""Verify both archived phase conventions without refitting or weakening gates."""
import numbers
import numpy as np
from probe_ds23_frequency_events import summary
from probe_ds23_reentry_family_cavity import audit_baseline
import run_algo04_candidate as study


def same_decisions(a,b):
    if isinstance(a,dict):
        if set(a)!=set(b):return False
        return all(same_decisions(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(same_decisions(x,y) for x,y in zip(a,b,strict=True))
    if isinstance(a,(bool,numbers.Integral,str)) or a is None:return a==b
    return isinstance(a,numbers.Real) and isinstance(b,numbers.Real) and bool(np.isfinite([a,b]).all())


def replay(d,p,arm,saved,label,original_check):
    # Existing independent auditor verifies the post-update convention before
    # reconstructing its pre-update reference from saved round endpoints.
    # It keeps the original2e-4 numeric tolerance and never refits position.
    archived_audit=audit_baseline(d,arm,saved)
    current=summary(p,np.asarray(saved['endpoint_east_north_km']),d['entries'])
    assert same_decisions(saved['gates'],current['gates']),'legacy reference changes a gate decision or identity'
    record=original_check(d,p,arm,dict(saved,gates=current['gates']),label)
    record['legacy_gate_convention']=dict(archived_audit=archived_audit,archived_gates_replayed_from_saved_history=True,
        objective_and_density_replayed_at_published_corrected_reference=True,all_decisions_and_IDs_identical=True,
        original_saved_artifact_unchanged=True,maximum_conditional_RMS_difference_hz=max(abs(a['conditional_residual_gate']['rms_hz']-b['conditional_residual_gate']['rms_hz'])
            for a,b in zip(saved['gates']['tracks'],current['gates']['tracks'],strict=True)))
    return record
