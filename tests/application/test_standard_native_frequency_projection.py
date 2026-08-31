from __future__ import annotations

import pytest

from leo.application.standard_native_presentation import _frequency_projection_indexes


@pytest.mark.parametrize(
    ("source_count", "maximum", "expected_count"),
    (
        (512, 1024, 512),
        (1536, 1024, 1024),
        (2048, 1024, 1024),
        (2560, 4096, 2560),
    ),
)
def test_frequency_projection_is_ordered_bounded_and_span_preserving(
    source_count: int,
    maximum: int,
    expected_count: int,
) -> None:
    indexes = _frequency_projection_indexes(source_count, maximum=maximum)

    assert len(indexes) == expected_count
    assert indexes == tuple(sorted(set(indexes)))
    assert indexes[0] == 0
    assert indexes[-1] == source_count - 1
