import json
import random
from pathlib import Path

import pytest

from leo.sky.propagation import ElementSetError, element_line_checksum
from tests.pipeline_eval.geometry import ANCHOR, tle
from tools.pipeline_eval.__main__ import read_predictions
from tools.pipeline_eval.qualification.catalog_parser import compare
from tools.pipeline_eval.qualification.catalogue_checksum import measure, scalar_checksum
from tools.pipeline_eval.variants.catalogue_checksum import checksum


def test_checksum_matches_reference_across_columns_digits_and_other_characters():
    for code in range(128):
        for column in (0, 67, 68):
            text = " " * column + chr(code)
            assert checksum(text) == element_line_checksum(text) == scalar_checksum(text)
    rng = random.Random(6134)
    for length in range(80):
        text = "".join(chr(rng.randrange(128)) for _ in range(length))
        assert checksum(text) == element_line_checksum(text) == scalar_checksum(text)
    assert checksum("９-١ ö") == element_line_checksum("９-١ ö")
    with pytest.raises(ValueError):
        checksum("²")


def test_timing_compares_every_bound_line_and_rejects_damaged_input():
    line = "1 " + "0" * 66 + "1"
    assert measure([line], 2)["lines"] == 1
    with pytest.raises(ValueError, match="fails its checksum"):
        measure([line[:-1] + "2"])
    with pytest.raises(ValueError, match="no orbital element lines"):
        measure([])


def test_public_parser_benchmark_interleaves_complete_parses_and_rejects_damage():
    text = tle(41000, 5) + tle(41001, 6)
    rows, evidence = compare(text, ANCHOR, repeats=2)
    assert [row["method"] for row in rows] == ["Scalar", "Public parser", "Public parser", "Scalar"]
    assert [row["pair"] for row in rows] == [1, 1, 2, 2]
    assert evidence["objects"] == 2 and evidence["states"] == 6
    assert len(evidence["sha256"]) == 64
    altered = tle(41000, 5, phase=80) + tle(41001, 6)
    assert compare(altered, ANCHOR, repeats=1)[1]["sha256"] != evidence["sha256"]
    damaged = text[:68] + str((int(text[68]) + 1) % 10) + text[69:]
    with pytest.raises(ElementSetError, match="fails its checksum"):
        compare(damaged, ANCHOR, repeats=1)


def test_archived_checksum_positions_and_residuals_match_the_fresh_full_fits():
    directory = Path(__file__).resolve().parents[2] / "reports/2026_11_19_receiver_streaming"
    records = read_predictions(directory / "catalogue/positions.jsonl.gz")
    assert set(records) == {"DS26-0036", "DS29-0082"}
    for case, row in records.items():
        control = json.loads((directory / "finish" / f"{case}-v5_lean.json").read_bytes())
        assert row["input_sha256"] == control["input_sha256"]
        assert row["result"]["arms"] == control["result"]["arms"]
        measured, full = (r["result"]["metrics"] for r in (row, control))
        for arm in ("c0", "fitted_c"):
            for statistic in ("associated_observations", "conditional_rms_hz", "frequency_score"):
                assert measured[f"{arm}_{statistic}"] == full[f"{arm}_{statistic}"]
