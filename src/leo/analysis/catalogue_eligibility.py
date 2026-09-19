"""Deterministic transmitter eligibility, selected without measured response."""

import numpy as np

from leo.analysis.catalogue_prediction import element_pair_digest
from leo.contracts.scanner_tracking import (
    CatalogueExclusionV1,
    CataloguePropagationExclusionV1,
)
from leo.sky.propagation import parse_element_set_records, parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid


def exclude_labelled_starlink_debris(payload: str) -> tuple[str, tuple[CatalogueExclusionV1, ...]]:
    records = parse_element_set_records(payload)
    retained, excluded = [], []
    for record in records:
        name = record.name.upper().strip()
        if name.startswith("STARLINK") and name.endswith(" DEB"):
            excluded.append(
                CatalogueExclusionV1(catalog_number=record.satellite_number, name=record.name)
            )
        else:
            retained.append(record.text)
    return "".join(retained), tuple(excluded)


def exclude_starlink_sgp4_failures(
    payload: str, *, screened_utc_ns: tuple[int, ...]
) -> tuple[str, tuple[CataloguePropagationExclusionV1, ...]]:
    """Remove Starlink elements that fail a response-blind boundary propagation.

    The four V8 screening instants bound the capture and every declared
    wrong-time/tau control.  No measured CFO or association score enters this
    decision.
    """

    times = tuple(sorted(set(screened_utc_ns)))
    if len(times) < 3 or any(value <= 0 for value in times):
        raise ValueError("propagation screening needs at least three positive instants")
    records = parse_element_set_records(payload)
    catalogue = parse_element_sets(payload)
    starlink_indices = [
        index for index, record in enumerate(records) if record.name.upper().startswith("STARLINK")
    ]
    grid = SamplingGrid(
        utc_ns=times,
        anchor_index=len(times) // 2,
        spacing_s=float(np.median(np.diff(np.asarray(times, dtype=np.int64))) / 1e9),
    )
    propagated = propagate_grid(catalogue, grid, indices=starlink_indices)
    failed: dict[int, CataloguePropagationExclusionV1] = {}
    for local_index in np.flatnonzero(~propagated.usable):
        record_index = starlink_indices[int(local_index)]
        record = records[record_index]
        codes = tuple(
            sorted(
                {int(value) for value in propagated.error_code[int(local_index)] if int(value) != 0}
            )
        )
        failed[record_index] = CataloguePropagationExclusionV1(
            catalog_number=record.satellite_number,
            name=record.name,
            selected_element_digest=element_pair_digest(record.first_line, record.second_line),
            error_codes=codes,
            screened_utc_ns=times,
        )
    retained = "".join(record.text for index, record in enumerate(records) if index not in failed)
    exclusions = tuple(failed[index] for index in sorted(failed))
    return retained, exclusions
