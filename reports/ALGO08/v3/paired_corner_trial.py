"""One saved original corner pair, without catalogue preparation or replayed fit."""

from collections import Counter
from hashlib import sha256
from itertools import islice, product
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, RUSAGE_SELF, getrusage
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
PAYLOAD = Path("/opt/leo-algo08/algo08v3/payload")
CORE_SHA = "30e6f22ab4b49d03cf8536645cbdebb8fec2afa513f3cfa4a9f3163590a84407"
THREADS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def now():
    return process_time_ns(), perf_counter_ns()


def elapsed(start):
    cpu, wall = now()
    return dict(cpu_ns=cpu - start[0], wall_ns=wall - start[1])


def checked(path, pin):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != pin:
        raise ValueError(f"Digest mismatch for {path.name}")
    return raw


def field_digests(outputs):
    return [[sha256(field.tobytes()).hexdigest() for field in output] for output in outputs]


def deny_waveforms(name, args):
    if name == "open" and isinstance(args[0], (str, bytes)):
        path = Path(os.path.abspath(os.fsdecode(args[0])))
        if path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01") or path.name.endswith(".ci16.zst"):
            raise ValueError("Physical waveform and archive backing reads are outside the trial")


def run(output):
    entered = now()
    if (output.exists() or output.parent.resolve() not in (Path("/tmp"), Path("/dev/shm"))
            or os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15
            or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "best-effort: prio 7"
            or not all(os.getenv(name) == "1" for name in THREADS)):
        raise ValueError("Expected a fresh tmpfs directory and the one-core Gauss lease")
    sys.addaudithook(deny_waveforms)
    output.mkdir(mode=0o700)
    sys.path[:0] = [str(HERE), str(PAYLOAD), str(RELEASE/"src"), str(RELEASE)]
    import numpy as np
    from leo.analysis.localization_v3 import discovery
    from leo.analysis.localization_v3.region import SearchRegion
    from paired_corner import PairProjector, SOURCE, build, ordered_corners
    from polar_projection_trial import CAPSULE_SHA, OFFER_SHA, PROJECTOR_SHA, recorded_scene
    from tools.pipeline_eval.variants import orbit_projector, v5_core, v5_direct_cavity

    prep_start = now()
    bank, offer, phases, observations, tracks = recorded_scene(checked)
    t, y, rf, labels = observations
    times = np.unique(t)
    indices = np.searchsorted(times, t)
    region = SearchRegion(offer["center"], offer["width_km"])
    radius = region.half_width_km
    offsets = tuple(islice(product((-radius, radius), repeat=2), 2))
    corners = tuple(region.latlon(xy) for xy in offsets)
    checked(Path(v5_core.__file__), CORE_SHA)
    grid = orbit_projector.prepare(bank, times)
    projected_bytes = int(len(bank["position_km"]) * len(times) * 3 * 8)
    prepared = elapsed(prep_start)

    def child_cpu():
        use = getrusage(RUSAGE_CHILDREN)
        return round(1e9 * (use.ru_utime + use.ru_stime))

    setup_start, child_start = now(), child_cpu()
    binary = output/"pair.so"
    build(orbit_projector, binary)
    build_cost = elapsed(setup_start) | {"children_cpu_ns": child_cpu() - child_start}
    setup_start = now()
    library = RELEASE/"assets/projector.so"
    checked(library, PROJECTOR_SHA)
    stock = orbit_projector.Projector(library)
    stock_setup = elapsed(setup_start)

    counts = Counter()
    with v5_direct_cavity.numerical_bindings(stock):
        released = discovery.phase_linear_frequency

        def query():
            return tuple(discovery.phase_linear_frequency(grid, *point) for point in corners)

        # First measure the normal two-corner sequence, then verify and release
        # its arrays before measuring the candidate on the same immutable grid.
        start = now()
        ordinary = query()
        ordinary_clock = elapsed(start)
        baseline = field_digests(ordinary)
        assert all(field.nbytes * 3 == projected_bytes for row in ordinary for field in row)
        del ordinary

        start = now()
        pair = PairProjector(stock, binary)
        with patch.object(discovery, "phase_linear_frequency", ordered_corners(released, grid, corners, pair, counts)):
            candidate = query()
        candidate_clock = elapsed(start)
        if field_digests(candidate) != baseline or counts != dict(paired_calls=1, served_second=1, lookahead_bytes=projected_bytes):
            raise ValueError("The paired original corner sequence was not byte identical")
        del candidate

        start = now()
        negative_counts = Counter()
        with patch.object(discovery, "phase_linear_frequency",
                          ordered_corners(released, grid, corners, pair, negative_counts)):
            reversed_corners = tuple(discovery.phase_linear_frequency(grid, *point) for point in reversed(corners))
        negative = elapsed(start)
        if field_digests(reversed_corners) != baseline[::-1] or negative_counts != dict(ordinary_calls=2):
            raise ValueError("Unexpected out-of-order candidate reuse")
        del reversed_corners

        diagnostics = {}
        for arm, phase in phases.items():
            shifted = orbit_projector.prepare(bank, times, phase)
            answers = pair.evaluate(shifted, corners)
            original = tuple(released(shifted, *point) for point in corners)
            if field_digests(answers) != field_digests(original):
                raise ValueError("The saved calibration-arm projection changed")
            diagnostics[arm] = []
            for got, control in zip(answers, original, strict=True):
                residual = y - rf * got[0][labels, indices]
                expected = y - rf * control[0][labels, indices]
                if residual.tobytes() != expected.tobytes():
                    raise ValueError("A signed fixed-owner RF residual changed")
                diagnostics[arm].append(dict(fields=field_digests((got,))[0],
                                             signed_residual_sha256=sha256(residual.tobytes()).hexdigest(),
                                             above_horizon=int((got[1] >= 0.).sum()),
                                             negative_cfo=int((got[0] < 0.).sum()),
                                             positive_cfo=int((got[0] > 0.).sum())))

    use = getrusage(RUSAGE_SELF)
    report = dict(
        case="DS30-0008", qualified=True, phases=diagnostics, corner_offsets_km=offsets, coordinates=corners,
        native_cells_per_corner=int(len(bank["position_km"]) * len(times)), observations=len(t),
        distinct_epochs=len(times), tracks=tracks, satellites=len(bank["position_km"]),
        each_corner_output_bytes=projected_bytes, pair_output_bytes=2 * projected_bytes, native_scratch_bytes_per_cell=192,
        ordinary=ordinary_clock, paired=candidate_clock, negative_reversed=negative,
        candidate_counts=dict(counts), negative_counts=dict(negative_counts), prepare_both=prepared,
        stock_checks_and_load=stock_setup, candidate_build=build_cost, ordinary_output_sha256=baseline,
        kernel=dict(input_blocks=use.ru_inblock, major_faults=use.ru_majflt, max_rss_kib=use.ru_maxrss),
        waveforms_read=0, numerical_fit_calls=0,
        sources=dict(saved_capsule=CAPSULE_SHA, original_offer=OFFER_SHA, stock_binary=PROJECTOR_SHA, scheduler=CORE_SHA,
                     candidate_library=sha256(binary.read_bytes()).hexdigest(), kernel=sha256(SOURCE.read_bytes()).hexdigest(),
                     driver=sha256(Path(__file__).read_bytes()).hexdigest()),
    )
    report["before_seal"] = elapsed(entered)
    with (output/"result.json").open("x") as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Use one fresh tmpfs result directory")
    run(Path(sys.argv[1]))
