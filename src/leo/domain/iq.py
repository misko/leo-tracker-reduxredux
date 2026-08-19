"""In-process IQ value objects that deliberately stay out of persisted contracts."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from leo.contracts.radio import IqBlockMetadataV1


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
