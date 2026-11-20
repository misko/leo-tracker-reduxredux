"""Reuse exact track support and use bytewise causal element checksums."""

import argparse
import json
import marshal
import runpy
import subprocess
import sys
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

CHECKSUM = bytes(c - 48 if 48 <= c <= 57 else int(c == 45) for c in range(256))
SOURCE_DIGESTS = {
    "leo/analysis/polynomial_tracklets.py": (
        "933b83ce5e414a8441c62d17f8e5eb75e07b79cada283bf681193f7316346922"
    ),
    "leo/sky/propagation.py": "238f45112bacd3b14b37f296fb17f056d66a860e469363cca44d876514ac544f",
}
BACKENDS = ("installed", "shared")


def element_checksum(line, original):
    if type(line) is not str or not line.isascii():
        return original(line)
    return sum(line[:68].encode("ascii").translate(CHECKSUM)) % 10


def best_piece(module, t, y, indices, prediction, cfg):
    """Compute window support once and retain every installed fit and decision."""
    import numpy as np

    n = len(indices)
    samples, measured = t[indices], y[indices]
    lifted = prediction + module._wrap(measured - prediction, cfg.alias_spacing_hz)
    if n < max(cfg.min_points, cfg.points_per_coefficient):
        return None
    distinct = np.unique(samples)
    span = np.ptp(distinct)
    if len(distinct) < 3 or span < cfg.min_span_s:
        return None
    clustered = len(distinct) > 1 and np.max(np.diff(distinct)) > 0.6 * span
    reference = float((samples.min() + samples.max()) / 2)
    scale = max(float(np.ptp(samples)) / 2, 1.0)
    x = (samples - reference) / scale
    penalty = np.log(max(n, 2))
    best, best_cost = None, float("inf")
    for degree in range(cfg.max_degree + 1):
        columns = degree + 1
        if (
            n < cfg.points_per_coefficient * columns
            or len(distinct) < 2 * columns
            or (degree >= 2 and clustered)
        ):
            continue
        piece = dict(
            indices=indices,
            degree=degree,
            reference_time_s=reference,
            time_scale_s=scale,
            coefficients_hz=module.leg.legfit(x, lifted, degree),
        )
        residual = module._wrap(measured - module._predict(piece, samples), cfg.alias_spacing_hz)
        cost = float(np.sum((residual / cfg.noise_sigma_hz) ** 2) + columns * penalty)
        if module._bounded_slope(piece, t, cfg) and cost < best_cost:
            best, best_cost = piece, cost
    if best is not None:
        best["indices"] = indices.copy()
    return best


def fingerprint(value):
    """Hash ordered fields, array layout and exact numerical representation."""
    import numpy as np

    digest = sha256()

    def feed(v):
        if isinstance(v, dict):
            digest.update(b"d" + marshal.dumps(len(v)))
            for key, cell in v.items():
                feed(key)
                feed(cell)
        elif isinstance(v, (list, tuple)):
            digest.update(b"l" + marshal.dumps(len(v)))
            for cell in v:
                feed(cell)
        elif isinstance(v, (np.ndarray, np.generic)):
            arr = np.asarray(v)
            digest.update(b"a" + marshal.dumps((arr.dtype.str, arr.shape)))
            if arr.dtype.hasobject:
                feed(arr.tolist())
            else:
                digest.update(arr.tobytes())
        else:
            digest.update(b"v" + marshal.dumps(v, 2))

    feed(value)
    return digest.hexdigest()


def isolated(root, request, backend):
    entry = runpy.run_path(str(root / "__main__.py"))
    entry["validate_region"](request["tile"], request["screen_center"], request["width_km"])
    entry["activate"](root)
    from leo.analysis import polynomial_tracklets as poly
    from leo.application import localization_v3
    from leo.sky import propagation
    from tools.pipeline_eval.variants import v5_direct_cavity

    if backend not in BACKENDS:
        raise ValueError("unknown track preparation backend")
    for relative, expected in SOURCE_DIGESTS.items():
        if sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("installed track or catalogue source is outside the qualified version")
    if propagation._CHECKSUM_COLUMN != 68:
        raise ValueError("installed element checksum has a different column rule")
    stats = {
        "clocks": {},
        "checksums": 0,
        "fallback_checksums": 0,
        "polynomial_choices": 0,
        "rejected_choices": 0,
    }
    timings = stats["clocks"]

    def timed(label, operation):
        def call(*args, **kwargs):
            cpu, wall = process_time(), perf_counter()
            result = operation(*args, **kwargs)
            values = timings.setdefault(label, dict(cpu_s=0.0, wall_s=0.0, calls=0))
            values["cpu_s"] += process_time() - cpu
            values["wall_s"] += perf_counter() - wall
            values["calls"] += 1
            return result

        return call

    checked = propagation.element_line_checksum
    fitted = poly._best_piece

    def checksum(line):
        stats["checksums"] += 1
        if backend == "shared":
            stats["fallback_checksums"] += type(line) is not str or not line.isascii()
            return element_checksum(line, checked)
        return checked(line)

    def choose(*args):
        stats["polynomial_choices"] += 1
        value = best_piece(poly, *args) if backend == "shared" else fitted(*args)
        stats["rejected_choices"] += value is None
        return value

    direct = localization_v3.prepare_native_scan

    def prepared(*args, **kwargs):
        data = direct(*args, **kwargs)
        tracks = data["tracks"]
        stats.update(
            ordered_tracks_sha256=fingerprint(tracks),
            observations=len(tracks["observations"]),
            tracks=len(tracks["tracks"]),
            assigned_points=tracks["graph_points"],
            curved_tracks=len(tracks["curved_indices"]),
        )
        if data["status"] == "inputs_prepared":
            stats["causal_sha256"] = fingerprint(
                [
                    data["sky"]["metadata"],
                    data["phase_history"],
                    data["phase_forecast"],
                ]
            )
        return data

    with ExitStack() as stack:
        for obj, name, function in (
            (propagation, "element_line_checksum", checksum),
            (poly, "_best_piece", timed("polynomial_choice", choose)),
            (localization_v3, "prepare_tracks", timed("tracks", localization_v3.prepare_tracks)),
            (
                localization_v3,
                "prepare_initial_sky",
                timed("initial_sky", localization_v3.prepare_initial_sky),
            ),
            (
                localization_v3,
                "prepare_phase_history",
                timed("phase_history", localization_v3.prepare_phase_history),
            ),
            (localization_v3, "prepare_native_scan", timed("native_preparation", prepared)),
        ):
            stack.enter_context(patch.object(obj, name, function))
        result = v5_direct_cavity.run(**request)
    entry["verify_project_modules"](root)
    return dict(result=result, preparation=stats, backend=backend)


def solve(receiver, compact, backend, *, timeout=None):
    request = dict(
        compact,
        native_backend=str(receiver / "native/manifest.json"),
        library=str(receiver / "projector.so"),
    )
    child = subprocess.run(
        [sys.executable, "-IB", str(Path(__file__).resolve()), "isolated", str(receiver), backend],
        input=json.dumps(request),
        stdout=subprocess.PIPE,
        text=True,
        check=True,
        timeout=timeout,
    )
    return json.loads(child.stdout)


def main(argv=None):
    from .. import whole_iq
    from ..original_receiver import receiver_assets
    from .final_region import publish

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receiver", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--backend", choices=BACKENDS, default="installed")
    parser.add_argument("--interior-guard", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 600:
        parser.error("timeout must be 1 through 600 seconds")
    path = whole_iq.checked(args.request, args.request_sha256)
    request = whole_iq.read(path)
    compact = request["compact"]
    actual = {p.name: whole_iq._sha(p) for p in Path(compact["archive"]).rglob("*.tle")}
    if not actual or actual != request["causal_snapshots"]:
        raise ValueError("causal catalogue differs from the authenticated request")
    receiver_assets(args.receiver)
    data = solve(args.receiver, compact, args.backend, timeout=args.timeout)
    result = publish(
        data["result"],
        dict(center=compact["tile"], width_km=compact["width_km"]),
        enabled=args.interior_guard,
    )
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    if sys.argv[1:2] == ["isolated"] and len(sys.argv) == 4:
        doc = isolated(Path(sys.argv[2]).resolve(), json.load(sys.stdin), sys.argv[3])
        print(json.dumps(doc, allow_nan=False))
    else:
        main()
