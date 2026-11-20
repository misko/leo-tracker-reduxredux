import gzip
import json

from tools.pipeline_eval.__main__ import read_predictions
from tools.pipeline_eval.corpus import references
from tools.pipeline_eval.figure_books import STREAMING_REPORT


def test_same_ds29_four_region_queries_produce_identical_diagnostic_and_published_positions():
    field = STREAMING_REPORT / "field"
    transfer = read_predictions(field / "arc_validation.jsonl.gz")
    with gzip.open(field / "roof16.jsonl.gz", "rt") as stream:
        roof = {r["id"]: r for r in map(json.loads, stream) if r["offers"] == "four"}
    ds29 = [
        r for r in references("transfer124") if r["group"] == "DS29" and r["condition"] == "present"
    ]
    assert len(ds29) == 8
    for case in ds29:
        first = roof[case["recording"]]["result"]
        second = transfer[case["id"]]["result"]
        assert first["arms"] == second["arms"]
        assert (first["status"], first["reason"]) == (second["status"], second["reason"])
