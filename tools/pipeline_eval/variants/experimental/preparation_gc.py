"""Limit cyclic collection during preparation in an isolated research process."""

from functools import wraps
import gc
from sys import implementation
from threading import active_count


def defer_collection(prepare, *, collect=gc.collect):
    """Collect the young generation once before returning to ordinary GC."""

    @wraps(prepare)
    def run(*args, **kwargs):
        if (
            implementation.name != "cpython" or active_count() != 1
            or not gc.isenabled() or not gc.get_threshold()[0] or gc.get_debug()
        ):
            return prepare(*args, **kwargs)

        gc.disable()
        try:
            return prepare(*args, **kwargs)
        finally:
            try:
                collect(0)
            finally:
                gc.enable()

    return run
