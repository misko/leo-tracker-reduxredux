import os
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import portable_fine_results as results
from tools.pipeline_eval.variants import fine_search, portable_fine, prepared_hotpath


@pytest.fixture(scope="module")
def build(tmp_path_factory):
    directory = tmp_path_factory.mktemp("portable-fine")
    flags = [flag for flag in results.FLAGS if flag not in {"-static", "-fstack-usage"}]
    library = directory / "portable_fine.so"
    executable = directory / "portable-fine"
    sources = [results.ENGINE, fine_search.SOURCE, "-lm"]
    for mode, output in ((["-fPIC", "-shared"], library), ([results.DRIVER], executable)):
        subprocess.run(
            ["cc", *flags, *mode, *sources, "-o", output],
            env=os.environ | {"TMPDIR": str(directory)},
            check=True,
        )
    return library, executable


def test_peak_tie_interpolation_and_band_edge_sentinels(build):
    subprocess.run([build[1], "--self-test"], check=True)


def test_folds_real_epoch_and_guards_ambiguous_score(build):
    scorer = portable_fine.PortableFine(
        build[0], SimpleNamespace(_constant_grid_step=lambda _: 500.0), lambda *_, **__: (7.0,)
    )
    values = np.zeros(200_000, dtype=np.complex128)
    template = np.zeros(13_333, dtype=np.complex128)
    pilots = prepared_hotpath.PILOTS
    template[pilots] = 1
    frequencies = tuple(-40_000.0 + step * 500 for step in range(161))
    wanted = 25
    epoch = 100
    for frame in range(14):
        start = epoch + (frame * 40000 + 1) // 3
        values[start + pilots] = np.exp(2j * np.pi * frequencies[wanted] * pilots / 10_000_000)
    args = (template, 10_000_000, epoch, frequencies, prepared_hotpath.SYMBOLS)

    scores = scorer.score(values, *args, transform_size=20_000)
    assert scorer.score(values, *args, transform_size=20_000) == scores
    assert np.argmax(scores) == wanted
    assert scores[wanted] == pytest.approx(1.0, abs=5e-13)
    assert scorer.calls == 2
    assert scorer.score(np.zeros_like(values), *args, transform_size=20_000) == (7.0,)
    assert scorer.guarded == 1
    assert scorer.score(values, *args, transform_size=4) == (7.0,)
    assert scorer.unsupported == 1
