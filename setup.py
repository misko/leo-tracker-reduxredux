from __future__ import annotations

import numpy
from setuptools import Extension, setup

setup(
    ext_modules=[
        Extension(
            "leo.analysis._regional_orbits",
            sources=["src/leo/analysis/_regional_orbits.cpp"],
            include_dirs=[numpy.get_include()],
            extra_compile_args=["-O3", "-fno-fast-math", "-ffp-contract=off", "-Wall", "-Wextra"],
        ),
        Extension(
            "leo.analysis.starlink._native_acquisition",
            sources=[
                "src/leo/analysis/starlink/_native_acquisition.c",
                "src/leo/analysis/starlink/fast_scan_fold.c",
            ],
            depends=["src/leo/analysis/starlink/_native_acquisition_grid.inc"],
            include_dirs=[numpy.get_include()],
            extra_compile_args=["-O3", "-fno-math-errno", "-Wall", "-Wextra"],
        ),
    ]
)
