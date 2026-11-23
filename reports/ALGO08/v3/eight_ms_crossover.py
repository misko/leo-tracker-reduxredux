"""Rebuild a graph from each cell of the saved 8 ms / 12 ms factor crossover."""

import argparse
from collections import Counter
from contextlib import contextmanager
from math import sqrt
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import RELEASE, archive_identity, read, write
from dense_full_short_raw import checked
from dense_geographic_trial import host
from full_short_physical import environment
from full_short_run import EIGHT_MS_RECIPE_SHA, GEOGRAPHIC_SHA, RECIPE_SHA, TRACK_SCORES_SHA, geographic_projection
from north_factor_swap import rebound
from weak_combined_raw import measure


ORDER = ("000", "111", "100", "010", "001", "110", "101", "011")
MARGIN = .025 * sqrt(8 / 5)
CASE_ROOTS = {"physical": Path("/dev/shm/leo-eight-ms-DS30-0016-warm"), "north": Path("/dev/shm/leo-eight-ms-north")}
BINDING_SHA = {
    "physical": "4e61f165347710aa3e84d36497a844070a0459cc386c914437b5795ef3b308bb",
    "north": "a48a25c9ca2f3575eb33834c78660cfec99028445dce666a032d57ac52d488c5",
}
RAW_REPORT_PINS = {"physical": "d5db26385ce031957206e47a0cf12ee2f93b04e2898daff2f10d7fd4e0452a7a",
                   "north": "16ee7ed27cad9fac9403f57342e277a3551a76afee651e0e8e7c3f30f6f4971d"}
PACKET_PINS = {
    "physical": ("sha256:c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589",
                 "sha256:f16ca1c684283a720596edfd727620a90f48712936f135c420d0c993ec669f6e"),
    "north": ("sha256:2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427",
              "sha256:a2eaf86c99145cc70b7040cf6e81c9fb0bc5e2e00b752223f5365de6818b8c49"),
}


def originals(case, apertures=("12ms", "8ms")):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest

    root = CASE_ROOTS[case]
    binding = read(checked(root / "binding.json", BINDING_SHA[case]))
    request = binding["request"]
    if (archive_identity(Path(request["archive"]["root"])) != request["archive"]
            or Algo08Region.parse(read(Path(request["region_file"]))).document() != request["offered_region"]):
        raise ValueError("Original supplied region or causal archive changed")
    packets, paths = [], []
    twelve_pin, eight_pin = PACKET_PINS[case]
    pins = {"12ms": (twelve_pin, RECIPE_SHA), "8ms": (eight_pin, EIGHT_MS_RECIPE_SHA)}
    for name in apertures:
        pin, recipe = pins[name]
        path, = (root / name / "fast-scan-automatic-work").glob("*/detections.json")
        native = read(path)
        source = native["source"]
        if (canonical_digest(native) != pin or native["provenance"]["detector_sha256"] != "sha256:" + recipe
                or source["session_id"] != request["session"] or source["input_manifest_sha256"] != binding["inventory"]
                or source["raw_recording_authority_digest"] != request["raw_authority"] or not source["qualified"]):
            raise ValueError("Original calibrated source packet changed")
        packets.append(native)
        paths.append(path)
    return binding, paths, packets


def strata(twelve, eight):
    from short_primary_epoch_audit import paired_probes

    def identity(packet):
        return dict(packet, source={k: v for k, v in packet["source"].items()
                                    if k not in ("probes", "analysis_manifest_sha256")},
                    provenance={k: v for k, v in packet["provenance"].items()
                                if k not in ("run_id", "detector_sha256")})

    if identity(twelve) != identity(eight):
        raise ValueError("Crossover packet authorities or opportunity counts differ")
    ids = set()
    rows = []
    pairs = paired_probes(twelve, eight)
    for (oid, original, before, after, short), other in zip(pairs, eight["source"]["probes"], strict=True):
        if (oid in ids or original["candidates"] != ([] if before is None else [before])
                or other["candidates"] != ([] if after is None else [after])):
            raise ValueError("Expected one selected factor per unique signed lane")
        ids.add(oid)
        if not short and before != after:
            raise ValueError("Full-anchor factors must be identical")
        if not short:
            kind = "anchor"
        elif before is not None and after is not None:
            kind = "shared"
        elif after is not None:
            kind = "eight_only"
        elif before is not None:
            kind = "twelve_only"
        else:
            kind = "empty"
        rows.append((oid, kind, original, before, after))
    return rows


def projected(rows, code):
    if code not in ORDER:
        raise ValueError("Unknown crossover cell")
    replace, add, drop = [bit == "1" for bit in code]
    output = []
    for _, kind, row, before, after in rows:
        factor = before
        if (kind == "shared" and replace) or (kind == "eight_only" and add):
            factor = after
        if kind == "twelve_only" and drop:
            factor = None
        output.append(dict(row, candidates=[] if factor is None else [factor]))
    return output


def guarded(eight):
    """A current-visit threshold on the measured 8 ms factor, preserving anchors."""
    slots, output = Counter(), []
    probes = eight["source"]["probes"]
    keys = ("visit_index", "valid_start_counter", "edge", "channel", "actual_rf_hz")
    for left, right in zip(probes[::2], probes[1::2], strict=True):
        if ((left["receiver_id"], right["receiver_id"]) != (0, 1) or any(left[k] != right[k] for k in keys)):
            raise ValueError("Expected one chronological stereo pair per admitted visit")
        stream = tuple(left[k] for k in keys[2:])
        anchor = slots[stream] % 8 == 0
        slots[stream] += 1
        for row in (left, right):
            factors = row["candidates"]
            kept = factors if anchor else [x for x in factors if x["fractional_margin"] >= MARGIN]
            output.append(dict(row, candidates=kept))
    return output


def margin_packet(eight):
    from leo.contracts.digests import canonical_digest

    return rebound(eight, guarded(eight), ["researcher-derived 8 ms local fractional margin v1", canonical_digest(eight), MARGIN])


def graph(prepared):
    tracks = prepared["tracks"]
    curves = frozenset(tracks["curved_indices"])
    return dict(status=prepared["status"], graph_points=tracks["graph_points"],
                tracks=[dict(curved=index in curves, ids=sorted(track["observation_ids"]))
                        for index, track in enumerate(tracks["tracks"])])


@contextmanager
def instrument(geo, regional, times):
    from tools import algo08_position

    prepare = algo08_position.prepare_native_scan

    def observed(*args, **kwargs):
        cpu, start = process_time(), perf_counter()
        try:
            return prepare(*args, **kwargs)
        finally:
            times.append(dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-start))

    with geographic_projection(geo, regional) as counts, patch.object(algo08_position, "prepare_native_scan", observed):
        yield counts


def worker(saved, digest, pin, output, recording, archive, region, geo, regional=None):
    from joint_publication import run

    times = []
    args = SimpleNamespace(recording=recording, archive=archive, region=region, output=output, saved=saved,
                           saved_digest=digest, optimized_full_catalogue=True, verify_images=True, observe_prepared=graph)
    run(args, early_regional=True, keep_selected_rows=True, saved_receiver=pin,
        geographic_projector=lambda: instrument(geo, regional, times),
        reuse_cold_rows=True, reuse_grid_phase_states=True)
    if not times:
        raise ValueError("Expected native graph preparation")
    write(output / "graph-preparation-clock.json", times)


def replay(case, root, geo, regional=None, margin_only=False):
    from leo.contracts.digests import canonical_digest

    system = host()
    checked(geo, GEOGRAPHIC_SHA)
    if (regional is not None) != (case == "north"):
        raise ValueError("Use the original regional library for North and the original physical route without it")
    if regional is not None:
        checked(regional, TRACK_SCORES_SHA)
    binding, paths, packets = originals(case, ("8ms",) if margin_only else ("12ms", "8ms"))
    if margin_only:
        order, rows = ("margin",), ()
    else:
        twelve, eight = packets
        order, rows = ORDER, strata(twelve, eight)
        if projected(rows, "000") != twelve["source"]["probes"] or projected(rows, "111") != eight["source"]["probes"]:
            raise ValueError("Crossover switch endpoints do not reproduce the signed samples")
    request = binding["request"]
    root.mkdir()
    env = environment(root)
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   check=True, env=env, timeout=30)
    launches, inputs = {}, {}
    prep = {}
    for code in order:
        if code in ("000", "111"):
            path, packet = (paths[0], twelve) if code == "000" else (paths[1], eight)
        elif code == "margin":
            path = root / "margin-diagnostic-input.json"
            cpu, start = process_time(), perf_counter()
            packet = margin_packet(packets[0])
            prep = dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-start)
            write(path, packet)
        else:
            path = root / f"{code}-diagnostic-input.json"
            packet = rebound(twelve, projected(rows, code),
                             ["researcher-derived saved 8 ms factor crossover v1", PACKET_PINS[case], code])
            write(path, packet)
        digest = canonical_digest(packet)
        pin = packet["provenance"]["detector_sha256"].removeprefix("sha256:")
        inputs[code] = dict(path=str(path), digest=digest, recipe=pin, researcher_derived=code not in ("000", "111"))
        launches[code] = [python, "-BPs", str(Path(__file__).resolve()), "worker", str(path), digest, pin,
                          str(root / code), request["recording"], request["archive"]["root"], request["region_file"], str(geo)]
        if regional is not None:
            launches[code].extend(["--regional", str(regional)])
    write(root / "binding.json", dict(case=case, machine=system, request=request, inventory=binding["inventory"],
                                      order=order, inputs=inputs, launches=launches, source_binding_sha256=BINDING_SHA[case],
                                      strata=dict(Counter(kind for _, kind, *_ in rows)),
                                      **({"margin_packet_clock": prep} if margin_only else {})))
    for code in order:
        measure(launches[code], env, root, code)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    subs = cli.add_subparsers(dest="command", required=True)
    launch = subs.add_parser("run")
    launch.add_argument("case", choices=CASE_ROOTS)
    launch.add_argument("root", type=Path)
    launch.add_argument("geo", type=Path)
    launch.add_argument("--margin-only", action="store_true")
    sealed = subs.add_parser("worker")
    for name in ("saved", "digest", "pin", "output", "recording", "archive", "region", "geo"):
        sealed.add_argument(name, type=str if name in ("digest", "pin") else Path)
    for parser in (launch, sealed):
        parser.add_argument("--regional", type=Path)
    args = vars(cli.parse_args())
    (worker if args.pop("command") == "worker" else replay)(**args)
