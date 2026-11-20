"""Run the FFTW differential scout under the standard whole-IQ service."""

from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from . import differential_runtime as parent
from . import whole_fftw_raw

MODULE = "tools.pipeline_eval.qualification.whole_fftw_runtime"
PARENT_SOURCES = parent.source_identity
SOURCES = (
    "tools/pipeline_eval/qualification/whole_fftw_runtime.py",
    "tools/pipeline_eval/qualification/whole_fftw_raw.py",
    "tools/pipeline_eval/variants/differential_runtime_fft.py",
    "tools/pipeline_eval/variants/differential_runtime_fft.c",
)


def source_identity():
    return PARENT_SOURCES() | {name: whole_iq._sha(whole_iq.ROOT / name) for name in SOURCES}


def activate():
    return patch.multiple(
        parent,
        MODULE=MODULE,
        differential_runtime_raw=whole_fftw_raw,
        source_identity=source_identity,
    )


def evaluate(ident, detector, detector_sha256, receiver, out, cpus, limit_s):
    whole_fftw_raw.library(detector)
    with activate():
        return parent.evaluate(ident, detector, detector_sha256, receiver, out, cpus, limit_s)


def worker(attempt):
    whole_fftw_raw.library(Path(whole_iq.read(attempt / "plan.json")["detector"]))
    with activate():
        parent.worker(attempt)


def main():
    with patch.multiple(whole_iq, evaluate=evaluate, worker=worker):
        whole_iq.main()


if __name__ == "__main__":
    main()
