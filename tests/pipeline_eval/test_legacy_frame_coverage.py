from unittest.mock import patch

import pytest

from reports.ALGO08.v3 import legacy_frame_coverage as coverage


@pytest.mark.parametrize("blocks,zero,streams,expected,cap", [
    (10, 10, {"4": 10}, "literal_only", 0),
    (10, 9, {"4": 10}, "match_blocks", 131072),
    (10, 9, {"1": 1, "4": 9}, "other", None),
])
def test_classify_blocks(blocks, zero, streams, expected, cap):
    info = dict(block_counts={"compressed": blocks}, zero_sequence_blocks=zero,
                checksum=True, huffman_streams=streams, literal_counts={"huffman_new": blocks},
                sequences=blocks-zero, match_bytes=4*(blocks-zero))
    with patch.object(coverage, "inspect", return_value=info):
        row = coverage.classify(bytes(5), 12 * blocks)
    assert (row["kind"], row["exception_byte_ceiling"]) == (expected, cap)


def test_valid_raw_frame_requires_ordinary_decode():
    frame = bytes.fromhex("28 b5 2f fd 20 03 19 00 00") + b"abc"
    assert coverage.classify(frame, 3)["kind"] == "other"
    with pytest.raises(ValueError):
        coverage.classify(frame[:-1], 3)


def test_match_block_reusing_an_older_table_does_not_reset_it():
    rows = coverage.exception_dependencies([(True, 1), (False, 0), (False, 1),
                                            (False, 0), (True, 0), (False, 0)])
    assert rows == [dict(block=0, new_table=True, dependent_literal_blocks=2),
                    dict(block=2, new_table=False, dependent_literal_blocks=0)]
