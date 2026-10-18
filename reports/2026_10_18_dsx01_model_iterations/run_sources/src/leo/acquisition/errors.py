"""Acquisition application errors."""


class AcquisitionError(RuntimeError):
    """Base error raised at the acquisition boundary."""


class AcquisitionCancelled(AcquisitionError):
    """Raised when a capture is cancelled at a safe refill boundary."""


class AdmissionRejected(AcquisitionError):
    """Raised when local storage cannot safely admit a capture plan."""
