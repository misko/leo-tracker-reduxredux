"""Read-only inventory of frozen scientific dataset memberships."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal, Self

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator

ScanType = Literal["fast", "adaptive", "hop", "unknown"]


class ScanCount(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    scan_type: ScanType
    sample_rate_hz: int | None = Field(default=None, gt=0)
    scans: int = Field(ge=1)


class DatasetSource(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DatasetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    dataset: str = Field(pattern=r"^DS(?:\d+(?:-\d+)?|X\d+)$")
    revision: str = "1"
    current: bool = True
    scans: int | None = Field(default=None, ge=0)
    breakdown: list[ScanCount] = Field(default_factory=list)
    sources: list[DatasetSource] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_counts(self) -> Self:
        if self.scans is None:
            if self.breakdown:
                raise ValueError("unlocated memberships cannot have scan counts")
        elif sum(item.scans for item in self.breakdown) != self.scans:
            raise ValueError("scan breakdown must sum to membership count")
        keys = [(item.scan_type, item.sample_rate_hz) for item in self.breakdown]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate scan-type/sample-rate bucket")
        return self


class DatasetCatalogue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    generated_utc: str
    datasets: list[DatasetSummary]

    @model_validator(mode="after")
    def check_revisions(self) -> Self:
        keys = [(item.dataset, item.revision) for item in self.datasets]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate dataset revision")
        current = [item.dataset for item in self.datasets if item.current]
        if len(set(current)) != len(current):
            raise ValueError("multiple current revisions of one dataset")
        return self


def load_catalogue(path: Path | None = None) -> DatasetCatalogue:
    """The packaged snapshot makes inventory independent of IQ, DB and worktrees."""
    raw = (
        path.read_bytes()
        if path
        else files("leo.cli").joinpath("dataset_catalogue.json").read_bytes()
    )
    return DatasetCatalogue.model_validate_json(raw)


def dataset_sort_key(item: DatasetSummary) -> tuple[bool, int, str, str]:
    suffix = item.dataset.removeprefix("DS")
    numeric = suffix.split("-", 1)[0]
    return (
        not numeric.isdigit(),
        int(numeric) if numeric.isdigit() else 0,
        item.dataset,
        item.revision,
    )


def _sample_rates(items: list[ScanCount]) -> str:
    rates: dict[int | None, int] = {}
    for item in items:
        rates[item.sample_rate_hz] = rates.get(item.sample_rate_hz, 0) + item.scans
    return (
        ", ".join(
            f"{'unknown' if rate is None else f'{rate / 1_000_000:g}'}: {count}"
            for rate, count in sorted(
                rates.items(), key=lambda pair: (pair[0] is None, pair[0] or 0)
            )
        )
        or "-"
    )


def register_dataset_commands(app: typer.Typer) -> None:
    datasets = typer.Typer(no_args_is_help=True)
    app.add_typer(datasets, name="datasets", help="List frozen DS dataset memberships.")

    @datasets.command("list")
    def list_datasets(
        dataset: Annotated[
            list[str] | None,
            typer.Option("--dataset", "-d", help="Dataset ID; repeat to select several."),
        ] = None,
        scan_type: Annotated[
            Literal["all", "fast", "adaptive", "hop", "unknown"],
            typer.Option("--scan-type", help="Count only this recording type."),
        ] = "all",
        all_revisions: Annotated[
            bool, typer.Option("--all-revisions", help="Include superseded frozen revisions.")
        ] = False,
        catalogue: Annotated[
            Path | None,
            typer.Option("--catalogue", help="Read a different metadata catalogue JSON."),
        ] = None,
        json_output: Annotated[
            bool, typer.Option("--json", help="Emit counts, rates and provenance.")
        ] = False,
    ) -> None:
        """Print scan counts, recording modes and sample rates without loading IQ."""
        try:
            inventory = load_catalogue(catalogue)
        except (OSError, ValueError) as error:
            typer.echo(f"Cannot read dataset catalogue: {error}", err=True)
            raise typer.Exit(2) from error
        requested = {name.upper() for name in dataset or []}
        missing = requested - {item.dataset for item in inventory.datasets}
        if missing:
            typer.echo(f"Unknown dataset(s): {', '.join(sorted(missing))}", err=True)
            raise typer.Exit(2)
        rows = []
        for item in sorted(inventory.datasets, key=dataset_sort_key):
            if not all_revisions and not item.current:
                continue
            if requested and item.dataset not in requested:
                continue
            selected = [
                bucket
                for bucket in item.breakdown
                if scan_type == "all" or bucket.scan_type == scan_type
            ]
            rows.append(
                {
                    "dataset": item.dataset,
                    "revision": item.revision,
                    "current": item.current,
                    "membership_scans": item.scans,
                    "scans": None
                    if item.scans is None
                    else sum(bucket.scans for bucket in selected),
                    "scan_types": {
                        kind: sum(bucket.scans for bucket in selected if bucket.scan_type == kind)
                        for kind in ("fast", "adaptive", "hop", "unknown")
                    },
                    "breakdown": [bucket.model_dump() for bucket in selected],
                    "sources": [source.model_dump() for source in item.sources],
                    "notes": item.notes,
                }
            )
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "schema_version": 1,
                        "generated_utc": inventory.generated_utc,
                        "scan_type": scan_type,
                        "datasets": rows,
                    },
                    indent=2,
                )
            )
            return
        headers = ("Dataset", "Rev", "Scans", "Fast", "Adaptive", "Hop", "Unknown", "MS/s: scans")
        values = []
        for row in rows:
            values.append(
                (
                    row["dataset"],
                    row["revision"],
                    "unlocated" if row["scans"] is None else str(row["scans"]),
                    *(
                        "-" if row["scans"] is None else str(row["scan_types"][kind])
                        for kind in ("fast", "adaptive", "hop", "unknown")
                    ),
                    _sample_rates([ScanCount.model_validate(v) for v in row["breakdown"]]),
                )
            )
        widths = [
            max(len(row[index]) for row in [headers, *values]) for index in range(len(headers))
        ]
        for cells in [headers, tuple("-" * width for width in widths), *values]:
            typer.echo(
                "  ".join(
                    cell.ljust(width) for cell, width in zip(cells, widths, strict=True)
                ).rstrip()
            )
        typer.echo(
            f"\nFrozen membership inventory as of {inventory.generated_utc}; filter: {scan_type}."
        )
        typer.echo(
            "Rates: MS/s and scan counts. Hop = legacy hop mode; unknown = unavailable metadata."
        )
        typer.echo("Includes incomplete members. Datasets overlap; row counts must not be summed.")


def main() -> None:
    app = typer.Typer()
    register_dataset_commands(app)
    app()


if __name__ == "__main__":
    main()
