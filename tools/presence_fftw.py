"""Explicit, hashable FFTW build dependency for native replay qualification."""

from pathlib import Path

from tools.qualify_native_presence import digest


def fftw_options(prefix: Path, *, runtime_rpath: bool = True):
    prefix = prefix.resolve()
    header, library = prefix / "include/fftw3.h", prefix / "lib/libfftw3.so"
    if not header.is_file() or not library.is_file():
        raise ValueError("FFTW prefix must provide include/fftw3.h and lib/libfftw3.so")
    dependencies = (header.resolve(), library.resolve())
    return {
        "cflags": ("-DLEO_PRESENCE_FFTW=1", f"-I{prefix / 'include'}"),
        "ldflags": (f"-L{prefix / 'lib'}",)
        + ((f"-Wl,-rpath,{prefix / 'lib'}",) if runtime_rpath else ())
        + ("-lfftw3",),
        "dependencies": dependencies,
    }


def fftw_identity(options):
    return {
        "backend": "fftw_fp64_estimate_fixed_arrays",
        "dependency_sha256": {str(p): digest(p) for p in options["dependencies"]},
        "cflags": list(options["cflags"]),
        "ldflags": list(options["ldflags"]),
    }
