"""Choose a pilot timing search when a radio visit enters a bounded FIFO."""

from threading import Lock


class ArrivalPolicy:
    """One active visit and one waiting visit, released after detector output."""

    def __init__(self, mode):
        if mode not in ("stock", "fifth", "adaptive"):
            raise ValueError("unknown pilot timing policy")
        self.mode = mode
        self._outstanding = 0
        self._lock = Lock()

    def admit(self):
        with self._lock:
            before = self._outstanding
            if before == 2:
                return before, None
            self._outstanding += 1
            if self.mode == "adaptive":
                return before, "stock" if before else "fifth"
            return before, self.mode

    def finish(self):
        with self._lock:
            if not self._outstanding:
                raise ValueError("no admitted radio visit to complete")
            self._outstanding -= 1
