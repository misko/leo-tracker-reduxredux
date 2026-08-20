"""Bounded SGP4 propagation over a parsed element-set catalogue.

The parser accepts the three-line format the collector archives (a ``0 NAME``
line followed by the two element lines) and the bare two-line format.

Validation is performed here rather than delegated to ``sgp4``.  ``twoline2rv``
is deliberately lenient: it does not verify the mod-10 checksum and does not
require the two lines to name the same catalogue object, so a corrupted digit
would otherwise be propagated as a plausible but wrong orbit.  Each record is
checked for exact line length, a valid checksum on both lines, and agreement
between the two catalogue numbers before it is accepted.  A malformed pair
fails the whole catalogue closed rather than being skipped, so a damaged
archive file can never masquerade as a smaller constellation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sgp4.api import Satrec, SatrecArray

from leo.contracts.sky import SkyWindowV1
from leo.sky.frames import julian_day_from_utc_ns
from leo.sky.sampling import SamplingGrid, presentation_grid

# An element set whose propagated radius falls below this is not a satellite in
# flight; it is a decaying or stale element set.  The live Starlink archive
# contains a handful of these, so screening must exclude and report them rather
# than draw objects inside the atmosphere.
MINIMUM_PLAUSIBLE_ALTITUDE_KM = 120.0

# Both element lines of a two-line set are exactly this wide, with the final
# character carrying the mod-10 checksum of everything before it.
ELEMENT_LINE_LENGTH = 69
_UNIX_EPOCH_JULIAN_DAY = 2440587.5
_NS_PER_DAY = 86_400_000_000_000
_CHECKSUM_COLUMN = 68


class ElementSetError(ValueError):
    """A malformed or unusable element-set catalogue."""


def element_line_checksum(line: str) -> int:
    """Return the mod-10 checksum of an element line's first 68 columns.

    Digits contribute their value and minus signs contribute one; every other
    character contributes nothing.  This is the convention the published
    two-line format uses.
    """

    return (
        sum(
            int(char) if char.isdigit() else 1 if char == "-" else 0
            for char in line[:_CHECKSUM_COLUMN]
        )
        % 10
    )


def _validate_element_line(line: str, expected_prefix: str, position: int) -> None:
    if len(line) != ELEMENT_LINE_LENGTH:
        raise ElementSetError(
            f"element line {position} is {len(line)} characters, expected {ELEMENT_LINE_LENGTH}"
        )
    if not line.startswith(expected_prefix):
        raise ElementSetError(f"element line {position} does not start with {expected_prefix!r}")
    recorded = line[_CHECKSUM_COLUMN]
    if not recorded.isdigit():
        raise ElementSetError(f"element line {position} has a non-numeric checksum")
    if int(recorded) != element_line_checksum(line):
        raise ElementSetError(f"element line {position} fails its checksum")


@dataclass(frozen=True, slots=True)
class ElementSetCatalogue:
    """Parsed element sets, held in a stable order."""

    names: tuple[str, ...]
    satellite_numbers: tuple[int, ...]
    satellites: tuple[Satrec, ...]

    def __len__(self) -> int:
        return len(self.satellites)

    def element_epoch_utc_ns(self) -> tuple[int, ...]:
        """Epoch of each element set, in UTC nanoseconds.

        This is when the orbit was determined, which is what governs
        propagation error.  It is unrelated to when the snapshot happened to be
        collected: a snapshot downloaded today can contain decades-old
        elements.
        """

        return tuple(
            int(
                round(((item.jdsatepoch - _UNIX_EPOCH_JULIAN_DAY) + item.jdsatepochF) * _NS_PER_DAY)
            )
            for item in self.satellites
        )


@dataclass(frozen=True, slots=True)
class PropagatedWindow:
    """TEME state for every satellite at every knot of one window."""

    utc_ns: tuple[int, ...]
    position_teme_km: NDArray[np.float64]
    velocity_teme_km_s: NDArray[np.float64]
    error_code: NDArray[np.int32]

    @property
    def usable(self) -> NDArray[np.bool_]:
        """Satellites that propagated without error at every knot."""

        return np.asarray(self.error_code == 0).all(axis=1)


def parse_element_sets(text: str) -> ElementSetCatalogue:
    """Parse a 3LE or 2LE catalogue, failing closed on any malformed pair."""

    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    names: list[str] = []
    numbers: list[int] = []
    satellites: list[Satrec] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("0 "):
            name = line[2:].strip()
            index += 1
        else:
            name = ""
        if index + 1 >= len(lines):
            raise ElementSetError("element-set catalogue ends mid-record")
        first, second = lines[index], lines[index + 1]
        _validate_element_line(first, "1 ", index + 1)
        _validate_element_line(second, "2 ", index + 2)
        if first[2:7] != second[2:7]:
            raise ElementSetError(
                f"element lines {index + 1} and {index + 2} name different catalogue objects"
            )
        try:
            satellite = Satrec.twoline2rv(first, second)
        except (ValueError, RuntimeError) as error:
            raise ElementSetError(f"unparsable element set at line {index + 1}") from error
        names.append(name or f"CATALOG-{satellite.satnum}")
        numbers.append(int(satellite.satnum))
        satellites.append(satellite)
        index += 2
    if not satellites:
        raise ElementSetError("element-set catalogue is empty")
    return ElementSetCatalogue(tuple(names), tuple(numbers), tuple(satellites))


def propagate_grid(
    catalogue: ElementSetCatalogue,
    grid: SamplingGrid,
    indices: Sequence[int] | None = None,
) -> PropagatedWindow:
    """Propagate satellites to every instant of a grid.

    ``indices`` restricts the work to a subset, which is what makes a fine
    decision pass over a handful of candidates affordable.
    """

    selected = (
        list(catalogue.satellites)
        if indices is None
        else [catalogue.satellites[index] for index in indices]
    )
    if not selected:
        knots = grid.utc_ns
        empty = np.zeros((0, len(knots), 3), dtype=np.float64)
        return PropagatedWindow(knots, empty, empty, np.zeros((0, len(knots)), dtype=np.int32))
    julian_day, fraction = julian_day_from_utc_ns(np.asarray(grid.utc_ns, dtype=np.int64))
    error, position, velocity = SatrecArray(selected).sgp4(julian_day, fraction)
    return PropagatedWindow(
        utc_ns=grid.utc_ns,
        position_teme_km=np.asarray(position, dtype=np.float64),
        velocity_teme_km_s=np.asarray(velocity, dtype=np.float64),
        error_code=np.asarray(error, dtype=np.int32),
    )


def propagate_window(catalogue: ElementSetCatalogue, window: SkyWindowV1) -> PropagatedWindow:
    """Propagate every satellite to every knot of a presentation window."""

    return propagate_grid(catalogue, presentation_grid(window))
