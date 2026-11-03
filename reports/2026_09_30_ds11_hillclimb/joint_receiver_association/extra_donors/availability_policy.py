"""Strict recorded-finalization and orbit-file availability checks."""
def available(capture_end, capture_finalized, analysis_finalized, cutoff):
    return 0 < capture_end <= capture_finalized < cutoff and 0 < analysis_finalized < cutoff and analysis_finalized >= capture_end


def orbit_available(request_ns,mtime_ns,capture_start):
    return 0 < request_ns < capture_start-505_000_000_000 and request_ns <= mtime_ns < capture_start
