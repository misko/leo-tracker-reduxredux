"""Bounded SGP4 propagation over a parsed element-set catalogue.

The parser accepts the three-line format the collector archives (a ``0 NAME``
line followed by the two element lines) and the bare two-line format.  It is
strict: a malformed pair fails closed rather than being skipped silently, so a
truncated archive file can never masquerade as a smaller constellation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sgp4.api import Satrec, SatrecArray

from leo.contracts.sky import SkyWindowV1
from leo.sky.frames import julian_day_from_utc_ns

# An element set whose propagated radius falls below this is not a satellite in
# flight; it is a decaying or stale element set.  The live Starlink archive
# contains a handful of these, so screening must exclude and report them rather
# than draw objects inside the atmosphere.
MINIMUM_PLAUSIBLE_ALTITUDE_KM = 120.0


class ElementSetError(ValueError):
    """A malformed or unusable element-set catalogue."""


@dataclass(frozen=True, slots=True)
class ElementSetCatalogue:
    """Parsed element sets, held in a stable order."""

    names: tuple[str, ...]
    satellite_numbers: tuple[int, ...]
    satellites: tuple[Satrec, ...]

    def __len__(self) -> int:
        return len(self.satellites)


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
        if not first.startswith("1 ") or not second.startswith("2 "):
            raise ElementSetError(f"malformed element-set record at line {index + 1}")
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


def propagate_window(catalogue: ElementSetCatalogue, window: SkyWindowV1) -> PropagatedWindow:
    """Propagate every satellite to every knot of the window."""

    knots = window.knot_utc_ns()
    julian_day, fraction = julian_day_from_utc_ns(np.asarray(knots, dtype=np.int64))
    error, position, velocity = SatrecArray(list(catalogue.satellites)).sgp4(julian_day, fraction)
    return PropagatedWindow(
        utc_ns=knots,
        position_teme_km=np.asarray(position, dtype=np.float64),
        velocity_teme_km_s=np.asarray(velocity, dtype=np.float64),
        error_code=np.asarray(error, dtype=np.int32),
    )
