"""Reviewed observer-site presets.

The interface deliberately opens with no site selected.  An operator either
enters a position or picks one of these reviewed presets; nothing is implied
about where the station actually is until a position is supplied.

Every preset records its provenance so that a coordinate can be audited rather
than trusted.  Presets are display conveniences, never scientific authority.
"""

from __future__ import annotations

from types import MappingProxyType

from leo.contracts.sky import ObserverSiteV1, SiteName


class SitePreset(ObserverSiteV1):
    """A reviewed preset: an observer site plus the source of its coordinates."""

    name: SiteName
    provenance: str
    position_uncertainty_m: float


_SPINNAKER = SitePreset(
    name="spinnaker-sausalito",
    label="Spinnaker, Sausalito",
    latitude_deg=37.858988,
    longitude_deg=-122.478103,
    # Waterfront structure over Richardson Bay.  Ellipsoidal height, so roughly
    # 32 m below the local orthometric height of a point near mean sea level.
    altitude_m=-29.0,
    provenance="OpenStreetMap named node 'The Spinnaker, 100 Spinnaker Drive, Sausalito'",
    position_uncertainty_m=50.0,
)

_PRESETS: dict[SiteName, SitePreset] = {_SPINNAKER.name: _SPINNAKER}

SITE_PRESETS = MappingProxyType(_PRESETS)


def preset_names() -> tuple[SiteName, ...]:
    """Return every reviewed preset name in stable order."""

    return tuple(sorted(SITE_PRESETS))


def resolve_preset(name: str) -> SitePreset:
    """Resolve one reviewed preset, failing closed on an unknown name."""

    preset = SITE_PRESETS.get(name)
    if preset is None:
        raise KeyError(f"unknown observer site preset: {name!r}")
    return preset
