from hashlib import sha256

import numpy as np
import pytest

from tools.pipeline_eval.qualification.ordinary_prepared_eval import load_ci16, search_parts
from tools.pipeline_eval.variants.ordinary_prepared import retain_short_window_preparation


def test_reuse_only_changes_the_short_window_preparation_predicate():
    before = (
        "    if(dwell_ms==120&&stride_ms==120){\n"
        "        prepared_view=&context->sparse_prepared;persistent_prepared=1;\n"
        "    }else leo_dwell_input_free(&context->sparse_prepared);\n"
    )
    after = retain_short_window_preparation(before)
    assert (
        after.replace(
            "short_window||(dwell_ms==120&&stride_ms==120)", "dwell_ms==120&&stride_ms==120", 1
        )
        == before
    )
    with pytest.raises(ValueError, match="source binding"):
        retain_short_window_preparation(before + before)


def test_saved_iq_paths_read_and_authenticate_identical_dual_receiver_bytes(tmp_path):
    path = tmp_path / "saved.ci16"
    samples = np.arange(800_000, dtype="<i2").reshape(200_000, 2, 2)
    samples.tofile(path)
    for mapped in (False, True):
        read, digest, wall, cpu = load_ci16(path, mapped=mapped)
        assert read.flags.c_contiguous
        assert np.array_equal(samples, read)
        assert digest == "sha256:" + sha256(samples.tobytes()).hexdigest()
        assert wall > 0 and cpu > 0


def test_search_decomposition_counts_fine_acquisition_only_once():
    timings = {
        "total_cpu": 21,
        "coarse": 1,
        "acquisition": 5,
        "fine_fft": 4,
        "conditioned": 2,
        "glrt": 3,
        "fractional_epoch": 9,
        "verification": 0,
        "proposal": 100,
        "stage_sum": 121,
    }
    assert search_parts(timings) == {
        "coarse": 1,
        "fine_fft": 4,
        "acquisition_other": 1,
        "conditioned": 2,
        "integer_glrt": 3,
        "fractional_epoch": 9,
        "unassigned_search": 1,
    }
