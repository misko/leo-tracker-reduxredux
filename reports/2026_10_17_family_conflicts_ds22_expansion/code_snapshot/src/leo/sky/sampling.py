"""Internal sampling grids, distinct from the operator-facing window contract.

``SkyWindowV1`` describes what an operator asked for and what a view will
present.  Screening needs something different: a grid whose spacing is chosen
from the geometry, sometimes far finer than any presentation would use, and not
constrained to divide the window into a whole number of presentation knots.

Keeping the two apart means the contract's invariants stay meaningful.  The
alternative -- copying a window and overwriting its sample count -- bypasses the
validators and can produce unevenly spaced knots, because ``model_copy`` does
not revalidate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from leo.contracts.sky import BeamPointingV1, SkyWindowV1

# Worst-case apparent angular rate of a low-Earth object crossing the zenith.
# A 340 km orbit moves at about 7.7 km/s, giving 1.3 deg/s; 1.5 deg/s leaves
# margin.  Every sampling bound in this module is derived from it.
MAX_ANGULAR_RATE_DEG_S = 1.5

# Coarse pass: spacing chosen at half the time an object takes to cross the
# cone diametrically.  This is not a detection guarantee -- a grazing chord is
# arbitrarily short -- which is why the coarse pass selects candidates using an
# inflated threshold rather than deciding membership.
_COARSE_DWELL_FRACTION = 0.5
_MIN_COARSE_SPACING_S = 0.5
_MAX_COARSE_SPACING_S = 5.0

# Refinement pass: spacing fine enough that the angle cannot move more than
# this tolerance between samples, bounding the residual decision error.
REFINEMENT_ANGULAR_TOLERANCE_DEG = 0.01
_MAX_REFINEMENT_KNOTS = 6_001

_NS_PER_S = 1_000_000_000


@dataclass(frozen=True, slots=True)
class SamplingGrid:
    """Explicit instants at which a window is evaluated."""

    utc_ns: tuple[int, ...]
    anchor_index: int
    spacing_s: float

    def __post_init__(self) -> None:
        if len(self.utc_ns) < 3:
            raise ValueError("a sampling grid needs at least three instants")
        if not 0 <= self.anchor_index < len(self.utc_ns):
            raise ValueError("anchor index falls outside the grid")
        if self.spacing_s <= 0.0:
            raise ValueError("grid spacing must be positive")

    def __len__(self) -> int:
        return len(self.utc_ns)

    @property
    def anchor_utc_ns(self) -> int:
        return self.utc_ns[self.anchor_index]

    def offsets_s(self) -> tuple[float, ...]:
        """Seconds of each instant relative to the anchor."""

        anchor = self.anchor_utc_ns
        return tuple((value - anchor) / 1e9 for value in self.utc_ns)


def _uniform(anchor_utc_ns: int, half_width_s: float, spacing_s: float) -> SamplingGrid:
    per_side = max(1, int(math.ceil(half_width_s / spacing_s)))
    step_ns = int(round(half_width_s * _NS_PER_S / per_side))
    instants = tuple(
        anchor_utc_ns + (index - per_side) * step_ns for index in range(2 * per_side + 1)
    )
    return SamplingGrid(instants, per_side, step_ns / _NS_PER_S)


def presentation_grid(window: SkyWindowV1) -> SamplingGrid:
    """The grid a view would draw: exactly the window's own knots."""

    return SamplingGrid(
        window.knot_utc_ns(),
        window.anchor_index,
        2 * window.half_width_s / (window.sample_count - 1),
    )


def coarse_grid(window: SkyWindowV1, pointing: BeamPointingV1) -> SamplingGrid:
    """Grid for the candidate pass, spaced from the beam rather than the window."""

    dwell_s = 2.0 * pointing.half_angle_deg / MAX_ANGULAR_RATE_DEG_S
    spacing = min(
        max(dwell_s * _COARSE_DWELL_FRACTION, _MIN_COARSE_SPACING_S), _MAX_COARSE_SPACING_S
    )
    return _uniform(window.anchor_utc_ns, float(window.half_width_s), spacing)


def refinement_grid(window: SkyWindowV1) -> SamplingGrid:
    """Grid for the decision pass over candidates only.

    Spacing bounds the angular movement between samples to
    ``REFINEMENT_ANGULAR_TOLERANCE_DEG``, so a candidate's closest approach is
    resolved to within that tolerance.
    """

    spacing = REFINEMENT_ANGULAR_TOLERANCE_DEG / MAX_ANGULAR_RATE_DEG_S
    required = 2 * int(math.ceil(window.half_width_s / spacing)) + 1
    if required > _MAX_REFINEMENT_KNOTS:
        spacing = 2.0 * window.half_width_s / (_MAX_REFINEMENT_KNOTS - 1)
    return _uniform(window.anchor_utc_ns, float(window.half_width_s), spacing)


def achieved_tolerance_deg(grid: SamplingGrid) -> float:
    """The angular resolution a grid actually delivers.

    Reported rather than assumed, because the refinement grid is capped and the
    requested tolerance is not always the one achieved.
    """

    return MAX_ANGULAR_RATE_DEG_S * grid.spacing_s


def candidate_margin_deg(grid: SamplingGrid) -> float:
    """Angular slack that makes the candidate pass free of false negatives.

    Between two samples the look direction can move by at most
    ``rate * spacing``, so an object whose sampled separation exceeds the cone
    by more than half that cannot have been inside it in between.  Selecting on
    the inflated threshold therefore cannot miss a transit, however brief.
    """

    return MAX_ANGULAR_RATE_DEG_S * grid.spacing_s / 2.0
