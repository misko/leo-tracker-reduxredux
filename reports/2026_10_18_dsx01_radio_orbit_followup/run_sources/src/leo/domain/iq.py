"""In-process IQ value objects that deliberately stay out of persisted contracts."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from leo.contracts.radio import IqBlockMetadataV1


def receiver_major_complex_to_ci16(
    value: object,
    receiver_count: int,
    sample_count: int,
) -> npt.NDArray[np.int16]:
    """Losslessly map integer-valued complex receiver/sample data to wire CI16."""

    samples = np.asarray(value)
    if receiver_count == 1 and samples.ndim == 1:
        samples = samples[np.newaxis, :]
    if samples.shape != (receiver_count, sample_count) or not np.iscomplexobj(samples):
        raise ValueError(
            f"complex IQ shape is {samples.shape}, expected ({receiver_count}, {sample_count})"
        )
    real = np.asarray(samples.real)
    imag = np.asarray(samples.imag)
    if not np.all(np.isfinite(real)) or not np.all(np.isfinite(imag)):
        raise ValueError("complex IQ contains non-finite values")
    rounded_real = np.rint(real)
    rounded_imag = np.rint(imag)
    if not np.array_equal(real, rounded_real) or not np.array_equal(imag, rounded_imag):
        raise ValueError("complex IQ is not exact integer-valued CI16 evidence")
    if (
        rounded_real.min(initial=0) < -32_768
        or rounded_real.max(initial=0) > 32_767
        or rounded_imag.min(initial=0) < -32_768
        or rounded_imag.max(initial=0) > 32_767
    ):
        raise ValueError("complex IQ exceeds the CI16 range")
    output = np.empty((sample_count, receiver_count, 2), dtype="<i2")
    output[:, :, 0] = rounded_real.T.astype("<i2")
    output[:, :, 1] = rounded_imag.T.astype("<i2")
    return output


@dataclass(frozen=True, slots=True)
class IqBlock:
    """Native CI16 samples plus separately serializable metadata.

    The array layout is ``(sample, receiver, I/Q)``. Contracts and manifests
    contain only geometry and observations, never the ndarray itself.
    """

    samples: npt.NDArray[np.int16]
    metadata: IqBlockMetadataV1

    def __post_init__(self) -> None:
        values = np.asarray(self.samples)
        expected_shape = (
            self.metadata.sample_count,
            len(self.metadata.receiver_ids),
            2,
        )
        if values.dtype != np.dtype("<i2"):
            raise ValueError("IQ samples must have little-endian int16 dtype")
        if values.shape != expected_shape:
            raise ValueError(f"IQ shape is {values.shape}, expected {expected_shape}")
        if not values.flags.c_contiguous:
            raise ValueError("IQ samples must be C-contiguous")
        values.setflags(write=False)
        object.__setattr__(self, "samples", values)

    @property
    def wire_bytes(self) -> memoryview:
        """Read-only native CI16 bytes in sample/receiver/IQ order."""

        return memoryview(self.samples).cast("B")
