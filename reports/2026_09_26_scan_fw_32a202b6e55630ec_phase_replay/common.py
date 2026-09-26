"""Sealed, report-local array contract for the phase replay.

Storage adapters own decompression and digest verification.  Scientific methods
consume only this module's arrays and integer coordinates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import IntFlag
from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt

SAMPLE_RATE_HZ = 10_000_000
VISIT_SAMPLES = 1_200_000
RECEIVER_IDS = (0, 1)
PROBE_START_SAMPLES = (0, 200_000, 400_000, 600_000, 800_000, 1_000_000)
PROBE_SAMPLES = 200_000


class SourceMask(IntFlag):
    """Independent source classifications; bits may be combined."""

    RF_VALID = 1
    KNOWN_NON_IQ = 2
    UNEXPLAINED_INVALID = 4
    FILTER_TRANSIENT = 8
    STORAGE_GAP = 16
    SETTLING = 32


INVALID_SOURCE_BITS = int(
    SourceMask.KNOWN_NON_IQ
    | SourceMask.UNEXPLAINED_INVALID
    | SourceMask.FILTER_TRANSIENT
    | SourceMask.STORAGE_GAP
    | SourceMask.SETTLING
)


@dataclass(frozen=True, slots=True)
class VisitCoordinates:
    visit_index: int
    target_index: int
    channel: int
    edge: str
    valid_start_counter: int
    valid_end_counter_exclusive: int
    stored_sample_start: int

    def __post_init__(self) -> None:
        if self.visit_index < 0 or self.target_index not in (4, 5, 6, 7):
            raise ValueError("cohort coordinates require an upper-edge target")
        if self.channel != self.target_index - 3 or self.edge != "upper":
            raise ValueError("target/channel/edge coordinates disagree")
        if self.valid_end_counter_exclusive - self.valid_start_counter != VISIT_SAMPLES:
            raise ValueError("replay visit is not exactly 120 ms at 10 MS/s")
        if self.stored_sample_start < 0:
            raise ValueError("stored sample coordinate must be non-negative")


@dataclass(frozen=True, slots=True)
class ReplayVisitArrays:
    """One digest-verified visit with explicit physical and storage axes.

    ``device_counter`` is authoritative for elapsed time and phase.  The
    ``stored_sample_index`` is only a compact byte coordinate and must never be
    used to infer elapsed time between visits.
    """

    coordinates: VisitCoordinates
    iq_ci16: npt.NDArray[np.int16]
    valid_mask: npt.NDArray[np.bool_]
    source_mask: npt.NDArray[np.uint8]
    device_counter: npt.NDArray[np.int64]
    stored_sample_index: npt.NDArray[np.int64]

    def __post_init__(self) -> None:
        expected_iq = (VISIT_SAMPLES, len(RECEIVER_IDS), 2)
        expected_mask = expected_iq[:2]
        self._array(self.iq_ci16, np.dtype("<i2"), expected_iq, "iq_ci16")
        self._array(self.valid_mask, np.dtype(np.bool_), expected_mask, "valid_mask")
        self._array(self.source_mask, np.dtype(np.uint8), expected_mask, "source_mask")
        self._array(self.device_counter, np.dtype(np.int64), (VISIT_SAMPLES,), "device_counter")
        self._array(
            self.stored_sample_index,
            np.dtype(np.int64),
            (VISIT_SAMPLES,),
            "stored_sample_index",
        )
        expected_valid = ((self.source_mask & int(SourceMask.RF_VALID)) != 0) & (
            (self.source_mask & INVALID_SOURCE_BITS) == 0
        )
        if not np.array_equal(self.valid_mask, expected_valid):
            raise ValueError("valid_mask disagrees with source_mask classifications")
        start = self.coordinates.valid_start_counter
        if self.device_counter[0] != start or not np.all(np.diff(self.device_counter) == 1):
            raise ValueError("device counters must be the exact contiguous visit axis")
        stored = self.coordinates.stored_sample_start
        if self.stored_sample_index[0] != stored or not np.all(
            np.diff(self.stored_sample_index) == 1
        ):
            raise ValueError("stored indices must be the exact compact visit axis")

    @staticmethod
    def _array(value: npt.NDArray, dtype: np.dtype, shape: tuple[int, ...], name: str) -> None:
        if not isinstance(value, np.ndarray) or value.dtype != dtype or value.shape != shape:
            raise ValueError(f"{name} has the wrong dtype or shape")
        if not value.flags.c_contiguous or value.flags.writeable:
            raise ValueError(f"{name} must be C-contiguous and read-only")

    def complex64(self, receiver_id: int) -> npt.NDArray[np.complex64]:
        if receiver_id not in RECEIVER_IDS:
            raise ValueError("unknown receiver")
        column = RECEIVER_IDS.index(receiver_id)
        out = np.empty(VISIT_SAMPLES, dtype=np.complex64)
        out.real = self.iq_ci16[:, column, 0]
        out.imag = self.iq_ci16[:, column, 1]
        out.setflags(write=False)
        return out


class ReplayVisitSource(Protocol):
    """Narrow port implemented by the capture-audit cache adapter."""

    @property
    def input_manifest_sha256(self) -> str: ...

    def read_visit(self, visit_index: int) -> ReplayVisitArrays: ...


class CachedReplayVisitSource:
    """Digest-bound mmap adapter over the capture-audit selected-visit cache."""

    def __init__(self, index_path: Path, selection_path: Path, *, verify_files: bool = True):
        self._root = index_path.parent
        raw = index_path.read_bytes()
        self.cache_index_sha256 = "sha256:" + hashlib.sha256(raw).hexdigest()
        index = json.loads(raw)
        selection_raw = selection_path.read_bytes()
        selection_sha = "sha256:" + hashlib.sha256(selection_raw).hexdigest()
        selection = json.loads(selection_raw)
        if index["selection_sha256"] != selection_sha:
            raise ValueError("cache is not bound to the selected cohort")
        if index["input_manifest_sha256"] != selection["input_manifest_sha256"]:
            raise ValueError("cache and selection source manifests disagree")
        if index["source_mask_values"] != {
            name: int(value) for name, value in SourceMask.__members__.items()
        }:
            raise ValueError("cache source-mask vocabulary disagrees with the harness")
        self.input_manifest_sha256 = index["input_manifest_sha256"]
        self._verify_files = verify_files
        self._entries = {row["visit_index"]: row for row in index["visits"]}
        self._selection = {row["visit_index"]: row for row in selection["visits"]}
        if self._entries.keys() != self._selection.keys():
            raise ValueError("cache visit population disagrees with selection")

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return "sha256:" + digest.hexdigest()

    def read_visit(self, visit_index: int) -> ReplayVisitArrays:
        try:
            entry = self._entries[visit_index]
            selected = self._selection[visit_index]
        except KeyError as error:
            raise ValueError("visit is outside the sealed cohort") from error
        arrays = {}
        for name, evidence in entry["files"].items():
            path = self._root / evidence["relative_path"]
            if self._verify_files and self._sha256(path) != evidence["sha256"]:
                raise ValueError(f"cached {name} digest mismatch")
            value = np.load(path, mmap_mode="r", allow_pickle=False)
            if value.dtype.str != evidence["dtype"] or list(value.shape) != evidence["shape"]:
                raise ValueError(f"cached {name} geometry mismatch")
            arrays[name] = value
        coordinates = VisitCoordinates(
            visit_index,
            selected["target_index"],
            selected["channel"],
            selected["edge"],
            selected["valid_start_counter"],
            selected["valid_end_counter_exclusive"],
            selected["stored_sample_start"],
        )
        return ReplayVisitArrays(coordinates=coordinates, **arrays)


def seconds_from_counter(
    counters: npt.ArrayLike, *, integer_origin: int, sample_rate_hz: int = SAMPLE_RATE_HZ
) -> npt.NDArray[np.float64]:
    """Convert only after exact integer subtraction to preserve phase coordinates."""

    values = np.asarray(counters)
    if values.dtype.kind not in "iu" or sample_rate_hz <= 0:
        raise ValueError("counter conversion requires integers and a positive rate")
    return (values.astype(object) - integer_origin).astype(np.float64) / sample_rate_hz


def support_is_disjoint(
    training: npt.ArrayLike, held_out: npt.ArrayLike, *, expansion_samples: int = 0
) -> bool:
    """Check leakage after expanding each selected sample by estimator support."""

    if expansion_samples < 0:
        raise ValueError("support expansion must be non-negative")
    left = np.unique(np.asarray(training, dtype=np.int64))
    right = np.unique(np.asarray(held_out, dtype=np.int64))
    if left.ndim != 1 or right.ndim != 1:
        raise ValueError("support indices must be one-dimensional")
    if not len(left) or not len(right):
        return True
    left.sort()
    right.sort()
    # Two expanded point supports intersect when original indices differ by no
    # more than twice the expansion.  Walk sorted arrays with constant memory.
    maximum_distance = 2 * expansion_samples
    i = j = 0
    while i < len(left) and j < len(right):
        distance = int(left[i]) - int(right[j])
        if abs(distance) <= maximum_distance:
            return False
        if distance < 0:
            i += 1
        else:
            j += 1
    return True
