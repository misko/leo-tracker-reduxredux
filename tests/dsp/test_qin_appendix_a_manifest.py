from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import (
    QIN_EDGE_PILOT_HEX_V1,
    StarlinkEdge,
    qin_edge_pilot_states,
)

_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "qin_edge_pilots_appendix_a_v1.json"
)


def _appendix_sequences() -> dict[int, str]:
    payload = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert payload["source"].endswith("arXiv:2602.02627v1, Appendix A")
    return {int(index): value for index, value in payload["sequences"].items()}


def _decode_published_states(sequences: dict[int, str], indexes: range) -> np.ndarray:
    output = np.empty((300, 8), dtype=np.int8)
    for row in range(300):
        shift = 2 * (299 - row)
        for column, index in enumerate(indexes):
            output[row, column] = (int(sequences[index], 16) >> shift) & 3
    return output


def test_all_sixteen_runtime_sequences_match_independent_appendix_a_manifest() -> None:
    published = _appendix_sequences()

    assert set(published) == {*range(488, 496), *range(528, 536)}
    assert all(len(value) == 150 for value in published.values())
    assert all(value == value.upper() for value in published.values())
    assert published == QIN_EDGE_PILOT_HEX_V1


def test_both_runtime_state_matrices_decode_the_independent_manifest() -> None:
    published = _appendix_sequences()

    np.testing.assert_array_equal(
        qin_edge_pilot_states(StarlinkEdge.UPPER),
        _decode_published_states(published, range(488, 496)),
    )
    np.testing.assert_array_equal(
        qin_edge_pilot_states(StarlinkEdge.LOWER),
        _decode_published_states(published, range(528, 536)),
    )
