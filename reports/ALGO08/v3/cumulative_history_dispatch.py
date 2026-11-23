"""Hand off from the cumulative solver at its existing history retry boundary."""

from contextlib import contextmanager
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from named_history_once import ALIGNMENT_ASSERTION, last_frame, recovered_catalogue


class NamedRecoveryRequired(Exception):
    """The cumulative attempt exhausted its normal paths at the pinned prior check."""

    def __init__(self, event):
        super().__init__("Named recovery required after confirmed earlier-orbit failure")
        self.event = event


@contextmanager
def at_installed_retry(position, modes, subset, *, line=ALIGNMENT_ASSERTION):
    """Intercept only the actual exception passed to the installed retry factory."""
    ordinary, previous = position.history_support, modes.previous_bank

    def history_support():
        error = sys.exception()
        if type(error) is not AssertionError or error.args:
            return ordinary()
        frame = last_frame(error)
        if frame.tb_frame.f_code is not previous.__code__ or frame.tb_lineno != line:
            return ordinary()
        scope = frame.tb_frame.f_locals
        begin = process_time_ns(), perf_counter_ns()
        observed = recovered_catalogue(error, previous, line, scope["scan"], scope["labels"], modes, subset)
        if observed is None:
            return ordinary()
        _, event = observed
        raise NamedRecoveryRequired(dict(event, gate_cpu_ns=process_time_ns() - begin[0],
                                         gate_elapsed_ns=perf_counter_ns() - begin[1])) from error

    with patch.object(position, "history_support", history_support):
        yield
