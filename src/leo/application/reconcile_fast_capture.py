"""Reconcile abandoned operational statuses without changing any IQ checkpoint."""
import time
from leo.acquisition.authority import CaptureTaskKind, RadioBusyError, CapturePausedError


def reconcile(authority, serial, checkpoints, store, *, now_ns=None, stale_seconds=1800):
    """A live acquisition lease prevents stale-state repair, even for old timestamps."""
    now_ns=time.time_ns() if now_ns is None else now_ns
    repaired=[]
    try:
        lease=authority.claim((serial,),task_id='reconcile-fast-capture',task_kind=CaptureTaskKind.SCANNER_SWEEP)
    except (RadioBusyError,CapturePausedError):
        return dict(state='deferred',reason='capture authority unavailable',repaired=[])
    with lease:
        for cp in checkpoints:
            previous=store.automatic_status(cp['run_id']) or {}
            if previous.get('state')!='recording' or now_ns-cp['updated_utc_ns']<stale_seconds*1e9:
                continue
            if cp.get('state')=='stopped':continue
            store.update_automatic(cp['run_id'],state='failed',
                failure='Interrupted capture: no acquisition owner and stale checkpoint; retained IQ was not changed',
                reconciliation=dict(checkpoint_updated_utc_ns=cp['updated_utc_ns'],checked_utc_ns=now_ns,
                                    acquisition_owner_absent=True),discovery_warning=cp.get('error'))
            repaired.append(cp['run_id'])
    return dict(state='complete',repaired=repaired)
