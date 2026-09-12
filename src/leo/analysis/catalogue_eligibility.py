"""Deterministic transmitter eligibility, selected without measured response."""

from leo.contracts.scanner_tracking import CatalogueExclusionV1
from leo.sky.propagation import parse_element_set_records


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
