"""Operator commands for the TLE sky interface.

Self-contained in the manner of :mod:`leo.cli.standard_pipeline`: this module
owns its own result models and renderers so that the shared CLI payload union
does not have to grow for a surface that shares nothing with it.

These commands read the locally collected element-set archive and compute
geometry.  They touch no database, publish nothing, and mutate nothing, so they
are safe to run against a live station.

Everything reported is predictive.  An object appearing in a field report means
a published element set places it in the beam; it is not a claim that anything
was received, detected or identified.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import typer
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from rich.table import Table

from leo.application.sky_field import (
    DEFAULT_DOWNLINK_FREQUENCY_HZ,
    SkyFieldService,
    SkyFieldUnavailableError,
)
from leo.contracts.sky import (
    SKY_WINDOW_HALF_WIDTH_S,
    BeamPointingV1,
    ObserverSiteV1,
    SkyFieldReportV1,
    SkyWindowV1,
)
from leo.operations.tle_archive import PROVIDERS, TleArchiveError, TleArchiveReader
from leo.presentation.sky import (
    MAXIMUM_LISTED_SNAPSHOTS,
    SkySiteListV1,
    SkySnapshotListV1,
    site_list,
    snapshot_list,
)
from leo.sky.sites import preset_names, resolve_preset

DEFAULT_ARCHIVE_ROOT = Path("/var/lib/leo/tle")
_NS_PER_S = 1_000_000_000

# Exit codes reuse the shared CLI vocabulary without importing its payload union.
_EXIT_OK = 0
_EXIT_NOT_FOUND = 20
_EXIT_UNAVAILABLE = 40


class SkyCliModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SkyFieldDataV1(SkyCliModel):
    schema_version: Literal[1] = 1
    archive_root: str
    report: SkyFieldReportV1


class SkyCommandResultV1(SkyCliModel):
    schema_version: Literal[1] = 1
    command: str
    ok: bool
    exit_code: Annotated[int, Field(ge=0, le=255)]
    message: str
    payload: SkySiteListV1 | SkySnapshotListV1 | SkyFieldDataV1 | None = None


def archive_root_from_environment() -> Path:
    """Resolve the archive root, matching the collector's systemd default."""

    return Path(os.environ.get("LEO_TLE_ROOT", str(DEFAULT_ARCHIVE_ROOT)))


def _utc(utc_ns: int) -> datetime:
    return datetime.fromtimestamp(utc_ns / 1e9, UTC)


def _parse_instant(value: str | None) -> int:
    """Resolve an ISO-8601 instant to UTC nanoseconds.

    An explicit instant is required for reproducibility in scripted use, but an
    operator asking "what is up now" should not have to type one, so ``None``
    means now.
    """

    if value is None:
        return int(datetime.now(UTC).timestamp() * _NS_PER_S)
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise typer.BadParameter(
            f"--at must be an ISO-8601 instant such as 2026-08-20T15:03:17Z, not {value!r}"
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp() * _NS_PER_S)


def _resolve_observer(
    site: str | None,
    latitude_deg: float | None,
    longitude_deg: float | None,
    altitude_m: float,
    label: str | None,
) -> ObserverSiteV1:
    """Resolve an observer from a reviewed preset or explicit coordinates.

    There is deliberately no default position.  A silent default would attach a
    location to every answer without the operator having chosen one.
    """

    if site is not None:
        if latitude_deg is not None or longitude_deg is not None:
            raise typer.BadParameter("give either --site or explicit coordinates, not both")
        try:
            preset = resolve_preset(site)
        except KeyError as error:
            raise typer.BadParameter(
                f"unknown site {site!r}; known sites: {', '.join(preset_names())}"
            ) from error
        return ObserverSiteV1(
            latitude_deg=preset.latitude_deg,
            longitude_deg=preset.longitude_deg,
            altitude_m=preset.altitude_m,
            label=preset.label,
        )
    if latitude_deg is None or longitude_deg is None:
        raise typer.BadParameter("an observer is required: pass --site, or both --lat and --lon")
    return ObserverSiteV1(
        latitude_deg=latitude_deg,
        longitude_deg=longitude_deg,
        altitude_m=altitude_m,
        label=label or f"{latitude_deg:+.5f},{longitude_deg:+.5f}",
    )


def register_sky_commands(
    sky: typer.Typer,
    *,
    archive_root: Callable[[], Path] = archive_root_from_environment,
) -> None:
    """Register the read-only sky commands on a Typer group."""

    @sky.command("sites")
    def sky_sites(
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        """List reviewed observer-site presets."""

        payload = site_list()
        _emit(
            SkyCommandResultV1(
                command="sky.sites",
                ok=True,
                exit_code=_EXIT_OK,
                message=f"{len(payload.sites)} reviewed observer site(s).",
                payload=payload,
            ),
            json_output=json_output,
        )

    @sky.command("snapshots")
    def sky_snapshots(
        provider: Annotated[
            str | None,
            typer.Option("--provider", help=f"Limit to one of: {', '.join(PROVIDERS)}."),
        ] = None,
        limit: Annotated[int, typer.Option("--limit", min=1, max=MAXIMUM_LISTED_SNAPSHOTS)] = 20,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        """List archived element-set snapshots, newest last."""

        root = archive_root()
        try:
            snapshots = TleArchiveReader(root).list_snapshots(provider)
        except TleArchiveError as error:
            _emit(
                SkyCommandResultV1(
                    command="sky.snapshots",
                    ok=False,
                    exit_code=_EXIT_UNAVAILABLE,
                    message=str(error),
                ),
                json_output=json_output,
            )
            return
        payload = snapshot_list(str(root), snapshots, limit=limit)
        _emit(
            SkyCommandResultV1(
                command="sky.snapshots",
                ok=bool(payload.snapshots),
                exit_code=_EXIT_OK if payload.snapshots else _EXIT_NOT_FOUND,
                message=(
                    f"{payload.returned_count} of {payload.source_count} snapshot(s) "
                    f"beneath {root}."
                    if payload.snapshots
                    else f"No element-set snapshot is available beneath {root}."
                ),
                payload=payload,
            ),
            json_output=json_output,
        )

    @sky.command("field")
    def sky_field(
        site: Annotated[
            str | None, typer.Option("--site", help="Reviewed observer preset name.")
        ] = None,
        latitude_deg: Annotated[
            float | None, typer.Option("--lat", help="Observer WGS84 latitude, degrees.")
        ] = None,
        longitude_deg: Annotated[
            float | None, typer.Option("--lon", help="Observer WGS84 longitude, degrees.")
        ] = None,
        altitude_m: Annotated[
            float,
            typer.Option("--alt", help="Height above the WGS84 ellipsoid, metres."),
        ] = 0.0,
        azimuth_deg: Annotated[
            float, typer.Option("--az", help="Boresight azimuth, degrees clockwise from north.")
        ] = 180.0,
        elevation_deg: Annotated[
            float, typer.Option("--el", help="Boresight elevation, degrees above the horizon.")
        ] = 45.0,
        half_angle_deg: Annotated[
            float, typer.Option("--fov", help="Beam half angle from boresight, degrees.")
        ] = 3.0,
        horizon_mask_deg: Annotated[
            float, typer.Option("--mask", help="Elevation mask, degrees.")
        ] = 0.0,
        at: Annotated[
            str | None,
            typer.Option("--at", help="ISO-8601 UTC instant; defaults to now."),
        ] = None,
        half_width_s: Annotated[
            int, typer.Option("--half-width", min=1, max=3600, help="Window half width, seconds.")
        ] = SKY_WINDOW_HALF_WIDTH_S,
        downlink_hz: Annotated[
            float, typer.Option("--downlink-hz", help="Transmit frequency for Doppler.")
        ] = DEFAULT_DOWNLINK_FREQUENCY_HZ,
        limit: Annotated[int, typer.Option("--limit", min=1, max=512)] = 20,
        provider: Annotated[str | None, typer.Option("--provider")] = None,
        label: Annotated[
            str | None, typer.Option("--label", help="Name for an ad-hoc site.")
        ] = None,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        """Report the catalogued objects in one beam and their predicted Doppler."""

        observer = _resolve_observer(site, latitude_deg, longitude_deg, altitude_m, label)
        pointing = BeamPointingV1(
            boresight_azimuth_deg=azimuth_deg,
            boresight_elevation_deg=elevation_deg,
            half_angle_deg=half_angle_deg,
            horizon_mask_deg=horizon_mask_deg,
        )
        window = SkyWindowV1(anchor_utc_ns=_parse_instant(at), half_width_s=half_width_s)
        root = archive_root()
        try:
            report = SkyFieldService(TleArchiveReader(root), maximum_objects=limit).field_report(
                observer=observer,
                pointing=pointing,
                window=window,
                downlink_frequency_hz=downlink_hz,
                provider=provider,
            )
        except SkyFieldUnavailableError as error:
            _emit(
                SkyCommandResultV1(
                    command="sky.field",
                    ok=False,
                    exit_code=_EXIT_UNAVAILABLE,
                    message=str(error),
                ),
                json_output=json_output,
            )
            return
        _emit(
            SkyCommandResultV1(
                command="sky.field",
                ok=True,
                exit_code=_EXIT_OK,
                message=(
                    f"{report.source_object_count} catalogued object(s) in the beam at "
                    f"{_utc(window.anchor_utc_ns):%Y-%m-%dT%H:%M:%SZ}."
                ),
                payload=SkyFieldDataV1(archive_root=str(root), report=report),
            ),
            json_output=json_output,
        )


def _emit(result: SkyCommandResultV1, *, json_output: bool) -> None:
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
        if not result.ok:
            raise typer.Exit(result.exit_code)
        return
    console = Console(force_terminal=False, color_system=None, highlight=False)
    console.print(result.message)
    payload = result.payload
    if isinstance(payload, SkySiteListV1):
        table = Table("Name", "Label", "Latitude", "Longitude", "Altitude", "±m", "Provenance")
        for site in payload.sites:
            table.add_row(
                site.name,
                site.label,
                f"{site.latitude_deg:+.6f}",
                f"{site.longitude_deg:+.6f}",
                f"{site.altitude_m:.1f} m",
                f"{site.position_uncertainty_m:.0f}",
                site.provenance,
            )
        console.print(table)
    elif isinstance(payload, SkySnapshotListV1):
        table = Table("Provider", "Collected (UTC)", "Bytes", "Digest")
        for snapshot in payload.snapshots:
            table.add_row(
                snapshot.provider,
                f"{snapshot.collected_utc:%Y-%m-%d %H:%M:%S}",
                f"{snapshot.byte_size:,}",
                snapshot.digest[:23] + "…",
            )
        console.print(table)
    elif isinstance(payload, SkyFieldDataV1):
        _print_field(console, payload.report)
    if not result.ok:
        raise typer.Exit(result.exit_code)


def _print_field(console: Console, report: SkyFieldReportV1) -> None:
    console.print(
        f"observer: {report.observer.label} "
        f"({report.observer.latitude_deg:+.6f}, {report.observer.longitude_deg:+.6f})"
    )
    console.print(
        f"beam: az {report.pointing.boresight_azimuth_deg:.2f}° "
        f"el {report.pointing.boresight_elevation_deg:.2f}° "
        f"± {report.pointing.half_angle_deg:.2f}°, mask {report.pointing.horizon_mask_deg:.2f}°"
    )
    console.print(
        f"snapshot: {report.snapshot.provider} {report.snapshot.digest[:23]}… "
        f"{report.snapshot.object_count:,} objects, "
        f"elements up to {report.maximum_element_age_s / 3600:.1f} h old"
        + ("  [STALE]" if report.elements_stale else "")
    )
    excluded = report.exclusions
    console.print(
        f"excluded: {excluded.outside_beam:,} outside beam · "
        f"{excluded.below_horizon_mask:,} below mask · "
        f"{excluded.implausible_altitude:,} implausible · "
        f"{excluded.propagation_failed:,} failed"
    )
    if not report.objects:
        console.print("No catalogued object was in the beam during this window.")
        return
    # Kept to six columns so the default 80-column width stays readable; the
    # full record, including the Doppler slope and higher terms, is in --json.
    table = Table("Object", "Az / El", "Range", "Sep", "Doppler", "Age")
    for item in report.objects:
        table.add_row(
            item.object_name + (" *" if item.boundary_uncertain else ""),
            f"{item.azimuth_deg:6.1f}/{item.elevation_deg:5.1f}",
            f"{item.range_km:6.0f} km",
            f"{item.minimum_boresight_separation_deg:5.3f}",
            f"{item.doppler.frequency_at_reference_hz / 1000:+9.2f} kHz",
            f"{item.element_age_s / 3600:5.1f} h",
        )
    console.print(table)
    if report.boundary_uncertain_count:
        console.print(
            f"* {report.boundary_uncertain_count} object(s) sit within "
            f"{report.screening_angular_tolerance_deg:.3f}° of a beam or mask edge; "
            "membership is not resolved at this resolution."
        )
    if report.truncated:
        console.print(
            f"Showing {report.returned_object_count} of {report.source_object_count}; "
            "raise --limit to see more."
        )
    console.print("Predicted geometry only. Not a detection, attribution or identification.")
