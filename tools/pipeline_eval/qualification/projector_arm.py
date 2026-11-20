"""Check the numerical projection kernel on an emulated Pluto Cortex-A9 CPU."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from leo.analysis.research import phase_linear_geometry
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..__main__ import save_json
from ..variants import orbit_projector
from .projector_audit import maximum_error

DEFAULT_CC = Path.home() / "gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc"


def vectors():
    # Three nonparallel constant-acceleration ECEF test arcs and a nonuniform knot grid.
    t = np.array([-8.0, -3.0, -1.0, 3.0, 6.0, 10.0, 13.0, 19.0])
    base = np.array([[6751.0, -1640.0, 190.0], [-2500.0, 3100.0, 5700.0], [120.0, -5000.0, 4700.0]])
    speed = np.array([[1.8, 7.1, -0.4], [6.3, 3.2, 1.0], [4.0, 4.9, 5.1]])
    acceleration = -base * 1.25e-6
    times = t[None, :, None]
    bank = dict(
        time_s=t,
        position_km=base[:, None] + times * speed[:, None] + 0.5 * times**2 * acceleration[:, None],
        velocity_km_s=speed[:, None] + times * acceleration[:, None],
    )
    return bank, np.array([-0.99, 1.5, 4.0, 6.02, 8.5, 10.1]), np.array([0.1, -1.3, 0.75])


def declaration(name, array):
    integers = np.issubdtype(array.dtype, np.integer)
    scalar = "int64_t" if integers else "double"
    values = (str(int(x)) if integers else float(x).hex() for x in array.flat)
    return f"static const {scalar} {name}[] = {{{','.join(values)}}};\n"


def audit(path, cc=DEFAULT_CC):
    bank, times, phase = vectors()
    lat, lon = 62.1, -147.2
    stencil = orbit_projector.prepare(bank, times, phase)
    ref = phase_linear_geometry.phase_linear_frequency(
        phase_linear_geometry.prepare_phase_geometry(bank, times, phase), lat, lon
    )
    site, up = geodetic_to_ecef_km(lat, lon, 0.0), ecef_to_enu_matrix(lat, lon)[2]
    data = "".join(
        declaration(name, array)
        for name, array in (
            ("p", stencil.positions),
            ("v", stencil.velocities),
            ("idx", stencil.index),
            ("frac", stencil.fraction),
            ("rot", stencil.rotation),
            ("site", site),
            ("up", up),
        )
    )
    ns, nk = stencil.positions.shape[:2]
    ct = ns * len(times)
    step = stencil.step.hex()
    main = f"""
#include <stdio.h>
#include "orbit_projector.c"
{data}
int main(void) {{
    double f[{ct}], e[{ct}], h[{ct}];
    int state = project_orbit_grid(p, v, {ns}, {nk}, {len(times)}, {len(stencil.index)}, idx,
                                   frac, rot, {step}, site, up, 11500000000., f, e, h);
    if (state) return state;
    for (int i=0; i<{ct}; ++i) e[i]=asin(fmax(-1.,fmin(1.,e[i]))) * 57.29577951308232;
    return fwrite(f,sizeof(double),{ct},stdout)!={ct}
        || fwrite(e,sizeof(double),{ct},stdout)!={ct} || fwrite(h,sizeof(double),{ct},stdout)!={ct};
}}
"""
    args = [
        "-std=c11",
        "-O3",
        "-mcpu=cortex-a9",
        "-mfpu=neon",
        "-mfloat-abi=hard",
        "-ffp-contract=off",
        "-fno-math-errno",
    ]
    with tempfile.TemporaryDirectory() as d:
        source, exe = Path(d) / "validate.c", Path(d) / "validate"
        source.write_text(main)
        subprocess.run(
            [cc, *args, "-I", orbit_projector.KERNEL.parent, source, "-lm", "-o", exe], check=True
        )
        sysroot = subprocess.check_output([cc, "-print-sysroot"], text=True).strip()
        output = subprocess.check_output(
            ["qemu-arm", "-cpu", "cortex-a9", exe], env=dict(os.environ, QEMU_LD_PREFIX=sysroot)
        )
    out = np.frombuffer(output, dtype="<f8").reshape(3, ns, len(times))
    errors = maximum_error(ref, out)
    if any(v > limit for v, limit in zip(errors, (1e-5, 1e-8, 1e-5), strict=True)):
        raise ValueError(f"ARM projection differs from reference: {errors}")
    save_json(
        path,
        dict(
            mode="Cortex-A9 using qemu-arm",
            cells=ct,
            flags=args,
            compiler=str(cc),
            kernel_sha256=hashlib.sha256(orbit_projector.KERNEL.read_bytes()).hexdigest(),
            fixture_sha256=hashlib.sha256(main.encode()).hexdigest(),
            max_error=errors,
        ),
    )
    print(json.dumps(errors))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", type=Path, default=DEFAULT_CC)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    audit(args.out, args.cc)
