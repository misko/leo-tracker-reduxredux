from __future__ import annotations

import pytest

from leo.catalog.errors import InvalidStateError
from leo.catalog.repository import _catalog_sync_sample_geometry


@pytest.mark.parametrize(
    ("logical_counts", "observed_counts"),
    (
        ((12, 12), (12, 12)),
        ((12, 12), (8, 12)),
    ),
    ids=("lossless", "one-radio-gapped"),
)
def test_two_radio_v3_sync_geometry_matches_native_compiler_keys(
    logical_counts: tuple[int, int],
    observed_counts: tuple[int, int],
) -> None:
    geometries = tuple(
        _catalog_sync_sample_geometry(
            captured_sample_count=observed,
            attributes={
                "logical_sample_count": logical,
                "observed_sample_count": observed,
                "zero_fill_sample_count": logical - observed,
            },
        )
        for logical, observed in zip(logical_counts, observed_counts, strict=True)
    )

    assert geometries == tuple(
        (
            True,
            {
                "logical_sample_count": logical,
                "observed_sample_count": observed,
            },
        )
        for logical, observed in zip(logical_counts, observed_counts, strict=True)
    )


def test_legacy_sync_geometry_keeps_frozen_captured_count_key() -> None:
    assert _catalog_sync_sample_geometry(
        captured_sample_count=12,
        attributes={"timing": {"schema_version": 1}},
    ) == (False, {"captured_sample_count": 12})


def test_partial_v3_sync_geometry_is_rejected() -> None:
    with pytest.raises(InvalidStateError, match="geometry is incomplete"):
        _catalog_sync_sample_geometry(
            captured_sample_count=8,
            attributes={"logical_sample_count": 12, "observed_sample_count": 8},
        )
