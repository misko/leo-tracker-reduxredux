from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import whole_frontends as study


def data():
    return {
        folder: {
            ident: dict(
                method=method,
                native_sha256=ident + folder,
                origin_native_sha256=ident + "whole-pair",
                catalog_sha256=ident + "catalog",
                tile={"center": [0, 0]},
                mode="matched-tile",
            )
            for ident in study.CASES
        }
        for folder, method, _, _ in study.SOURCES
    }


@pytest.mark.parametrize("field", ["origin_native_sha256", "catalog_sha256", "tile", "mode"])
def test_full_iq_comparisons_require_common_parent_capture_catalogue_and_tile(field):
    original = data()
    study.compare_sources(original)
    bad = deepcopy(original)
    bad["iq-schedule"]["DS26-0036"][field] = "unrelated"
    with pytest.raises(ValueError):
        study.compare_sources(bad)


def test_each_full_iq_detector_keeps_the_entire_paired_roster():
    missing = data()
    missing["whole-fractional"].pop("DS29-0082")
    with pytest.raises(ValueError, match="roster"):
        study.compare_sources(missing)
