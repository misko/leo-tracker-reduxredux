"""Replay all admitted native factors with a synthetic signed carrier grid."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from math import isfinite, sqrt
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import BENCH, PAYLOAD, archive_identity, configuration, inputs, machine, write
from mixture_trial import CASES, elapsed, summarize


RATE = 10_000_000
STRIDE = 4
BINS = 4096
GRID_HZ = {"bin": RATE / STRIDE / BINS, "quarter": RATE / STRIDE / BINS / 4}
CFO = "fractional_tracking_cfo_hz"
BUILD = BENCH / "receiver-fractional-exact-v1/build.json"
RECEIVER_SHA = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
SOURCES = {
    "timing_first_receiver": (
        "936b67cbb9af0201a7e65281756cc9c16f042ac2ad5e84201b1577131c67044a",
        ("bins = 4096", "w->rate = 10000000 / stride",
         "(i < bins / 2 ? i : i - bins) * (double)w->rate / bins"),
    ),
    "two_carrier_receiver": (
        "4f3326eee5522f02ee05a236f22a41fc1af5bb0f21b6e3fe337711a66226f5f7",
        ("timing_first_create(4,", "p[i].hz + v.fractional_residual_hz"),
    ),
}


def verify_grid():
    binary = PAYLOAD / "receiver.so"
    if sha256(binary.read_bytes()).hexdigest() != RECEIVER_SHA:
        raise ValueError("The installed receiver does not match its exact archived relink")
    link = [Path(arg) for arg in json.loads(BUILD.read_bytes())["commands"][-1]]
    sources = {}
    for name, (pin, tokens) in SOURCES.items():
        path, = (arg.with_suffix(".c") for arg in link if arg.name == name + ".o")
        source = path.read_bytes()
        if sha256(source).hexdigest() != pin or any(token not in source.decode() for token in tokens):
            raise ValueError(f"Grid provenance changed in {path}")
        sources[name] = dict(path=str(path), sha256=pin)
    exporter = PAYLOAD / "tools/pipeline_eval/qualification/blind_compact_run.py"
    mapper = exporter.with_name("full_v5_check.py")
    if "cfo=v.hz," not in exporter.read_text() or f"{CFO}=cfo," not in mapper.read_text():
        raise ValueError("The released exporter no longer uses the native signed CFO")
    return dict(receiver_sha256=RECEIVER_SHA, bins=BINS, stride=STRIDE, sample_rate_hz=RATE,
                spacing_hz=GRID_HZ, sources=sources,
                exporter_sha256=sha256(exporter.read_bytes()).hexdigest(),
                mapper_sha256=sha256(mapper.read_bytes()).hexdigest())


def placed_hz(value, spacing):
    if not isfinite(value):
        raise ValueError("Expected a finite signed CFO in Hz")
    return round(value / spacing) * spacing


def quantize(native, mode):
    from leo.contracts.digests import canonical_digest

    src = native["source"]
    if src["sample_rate_hz"] != RATE:
        raise ValueError("Expected the pinned 10 MHz sample clock")
    spacing = GRID_HZ[mode]
    changed, errors, ranks = [], [], Counter()
    for probe in src["probes"]:
        if not probe["candidates"]:
            changed.append(probe)
            continue
        row, = probe["candidates"]
        before = row[CFO]
        after = placed_hz(before, spacing)
        ranks[str(row["candidate_rank"])] += 1
        errors.append(abs(after - before))
        changed.append(dict(probe, candidates=[dict(row, **{CFO: after})]))
    pin = native["provenance"]["detector_sha256"].removeprefix("sha256:")
    digest = canonical_digest(["cancellation", src["raw_recording_authority_digest"], pin, changed])
    transformed = dict(native, source=dict(src, probes=changed, analysis_manifest_sha256=digest),
                       provenance=dict(native["provenance"], run_id="blind-compact-" + digest[7:39]))
    sorted_errors = sorted(errors)
    audit = dict(spacing_hz=spacing, windows=len(changed), admitted=len(errors),
                 changed=sum(e != 0. for e in errors), candidate_ranks=dict(sorted(ranks.items())),
                 median_abs_hz=median(errors) if errors else None,
                 p95_abs_hz=sorted_errors[(95 * len(errors) - 1) // 100] if errors else None,
                 max_abs_hz=max(errors, default=None),
                 rms_hz=sqrt(sum(e * e for e in errors) / len(errors)) if errors else None)
    return transformed, audit


def solve(publication, specification, native, archive, offer):
    from numpy.linalg import LinAlgError

    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core

    from blind_joint_route import make_route
    from blind_joint_trial import publication_roles
    from owner_union_trial import prepared_summary

    preparation, attempts = [], []

    def analyze(_recording, _root, assets, archive_root, region):
        prepare = algo08_position.prepare_native_scan
        reader = TleArchiveReader(archive_root)
        route = make_route(v5_core.infer, reader, attempts, repair=True, signed_finish=True)

        def traced(*args, **kwargs):
            value = prepare(*args, **kwargs)
            preparation.append(prepared_summary(value))
            return value

        cpu, wall = process_time(), perf_counter()
        try:
            with (patch.object(v5_core, "infer", route),
                  patch.object(algo08_position, "prepare_native_scan", traced)):
                result, packet, policy = algo08_position.solve(native, reader, assets, region)
        except (ValueError, AssertionError, LinAlgError) as exc:
            return dict(result=dict(status="failed", arms={}, reason=f"{type(exc).__name__}: {exc}"),
                        charged=elapsed(cpu, wall), attempts=attempts, preparation=preparation,
                        owners={}, published_roles={}, numerical_grid_complete=None)
        charged = elapsed(cpu, wall)
        terminal, owners = summarize(result, packet, policy)
        return dict(result=terminal, owners=owners, published_roles=publication_roles(packet),
                    numerical_grid_complete=None if packet is None else packet["position_grid"]["complete"],
                    charged=charged, attempts=attempts, preparation=preparation)

    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        offer_path = scratch / "offer.json"
        offer_path.write_text(json.dumps(offer))
        root = scratch / "output"
        root.mkdir()
        args = SimpleNamespace(recording=scratch / "saved", bulk_root=root, archive=archive, region=offer_path)
        with patch.object(algo08_scan, "analyze", analyze):
            return publication.run(args, specification)


def trial(case, mode, output):
    publication, specification = configuration()
    from leo.contracts.digests import canonical_digest

    system = machine()
    if (system["cpu"] != [2] or system["nice"] < 15 or "prio 7" not in system["ionice"]
            or any(value != "1" for value in system["threads"].values())):
        raise ValueError("Expected the declared low-priority one-core worker")
    grid = verify_grid()
    native, archive, offer, _, identity = inputs(case)
    if identity["detector_sha256"] != "sha256:" + specification["detector_sha256"]:
        raise ValueError("The sealed source uses a different receiver")
    transformed, audit = quantize(native, mode)
    result = solve(publication, specification, transformed, archive, offer)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Causal archive changed during the replay")
    result.update(case=case, mode=mode, identity=identity, transformed_sha256=canonical_digest(transformed),
                  placement=audit, machine=system, grid=grid,
                  driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    write(output, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("mode", choices=GRID_HZ)
    parser.add_argument("output", type=Path)
    trial(**vars(parser.parse_args()))
