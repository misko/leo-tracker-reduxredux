"""Run the installed, standalone receiver as python -IB /path/to/receiver."""

import argparse
import json
import math
import os
import sys
from pathlib import Path


def verify_project_modules(root):
    for name, module in tuple(sys.modules.items()):
        if module is None or name.partition(".")[0] not in {"tools", "leo"}:
            continue
        filename = getattr(module, "__file__", None)
        if not filename or not Path(filename).resolve().is_relative_to(root):
            raise RuntimeError(f"{name} was loaded outside the standalone receiver")


def activate(root):
    verify_project_modules(root)
    sys.path.insert(0, str(root))
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[name] = "1"


def build(root):
    activate(root)
    from leo.analysis.localization_v4.backend import build_native

    from tools.pipeline_eval.variants.orbit_projector import compile_kernel

    verify_project_modules(root)
    build_native(root / "native")
    compile_kernel(root / "projector.so")


def validate_region(tile, screen, width):
    for lat, lon in (tile, screen):
        if not (-90 < lat < 90 and -180 <= lon <= 180):
            raise ValueError("tile and screen centers must be finite latitude/longitude degrees")
    if not math.isfinite(width) or width <= 0:
        raise ValueError("tile width must be finite and positive")
    lat, lon = tile
    half_lat = width / (2 * 111.0)
    half_lon = width / (2 * 111.32 * math.cos(math.radians(lat)))
    if abs(lat) + half_lat >= 90 or abs(lon) + half_lon > 180:
        raise ValueError(
            "this local-coordinate receiver requires a tile clear of poles and the longitude seam"
        )
    if abs(lon - screen[1]) + half_lon > 180:
        raise ValueError("the local tile and screening origin cross the longitude seam")


def main():
    root = Path(__file__).resolve().parent
    activate(root)
    from tools import PROFILE
    from tools.pipeline_eval.variants import v5_direct_cavity

    verify_project_modules(root)
    parser = argparse.ArgumentParser(
        description="Estimate the receiver position from stored native GLRT and causal orbits."
    )
    for flag, help_text in (
        ("native", "stored native GLRT JSON"),
        ("native-sha256", "declared SHA-256 of the stored native GLRT"),
        ("session", "recording session identifier"),
        ("track-config", "track configuration JSON"),
        ("config-sha256", "declared SHA-256 of the track configuration"),
        ("archive", "root of the causal TLE archive"),
    ):
        parser.add_argument("--" + flag, required=True, help=help_text)
    parser.add_argument("--tile", type=float, nargs=2, metavar=("LAT", "LON"), required=True)
    parser.add_argument(
        "--screen-center", type=float, nargs=2, metavar=("LAT", "LON"), required=True
    )
    parser.add_argument("--width-km", type=float, default=25)
    args = parser.parse_args()
    validator = validate_region
    if PROFILE == "longitude":
        from tools.pipeline_eval.variants.cavity_longitude import validate_geometry

        validator = validate_geometry
    try:
        validator(args.tile, args.screen_center, args.width_km)
    except ValueError as error:
        parser.error(str(error))
    result = v5_direct_cavity.run(
        **vars(args),
        native_backend=root / "native/manifest.json",
        library=root / "projector.so",
    )
    verify_project_modules(root)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
