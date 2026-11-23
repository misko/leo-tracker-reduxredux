"""Forecast frozen second-pass slots and replay the two archived paid packets."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from aperture_trial import BENCH, archive_identity, configuration, machine, read, write
from directed_donor import ADC, coverage, extrapolate
from mixture_trial import elapsed, summarize
from quadratic_support_trial import CASES, HERE, baseline, runtime


SLOTS_SHA = "2d1ce9ec377a43faf0086f2f05f3c13ca80f4f41532944e3728c03ec857f0819"
VERIFIER_SHA = "dc132cbaac6cb3eddb21ec4c7df950b03eb1713461dac2d50ff0a92ac3e9a13b"
ROW_FIELDS = ("visit_index", "receiver_id", "valid_start_counter", "channel", "actual_rf_hz", "edge")
ZERO_CORRECTION = ((0., 0.),) * 3
LIGHT = 299792.458


def pinned(name, expected):
    path = HERE / "measurements" / name
    content = path.read_bytes()
    if sha256(content).hexdigest() != expected:
        raise ValueError(f"Saved input changed at {name}")
    return json.loads(gzip.decompress(content) if path.suffix == ".gz" else content)


def indices(probes, session):
    result = {}
    for row in probes:
        oid = "sha256:" + sha256(
            f"{session}:{row['receiver_id']}:{row['valid_start_counter']}".encode()).hexdigest()
        if oid in result:
            raise ValueError("Duplicate native lane and sample counter")
        result[oid] = row
    return result


def source(case):
    from leo.contracts.digests import canonical_digest
    from paid_graph_trial import prepared_packet

    native, archive, offer, identity, _, paid = prepared_packet(case, "margin")
    sealed = pinned("quadratic-support-slots.json", SLOTS_SHA)["cases"][case]
    previous = baseline(case, "quadratic")
    if (canonical_digest(sorted(paid)) != sealed["paid_visit_sha256"]
            or identity["native_sha256"] != sealed["paid_packet_sha256"]
            or previous["result"]["owners"] != sealed["paid_owner_sha256"]
            or previous["identity"]["native_sha256"] != sealed["paid_packet_sha256"]
            or canonical_digest(sealed["slots"]) != sealed["slots_sha256"]):
        raise ValueError("Frozen slots need the original paid graph result and packet")
    return native, archive, offer, identity, paid, sealed


def orbital_geometry(native, archive, offer, slots, features):
    from leo.analysis.localization_v3.orbits import ecef_states
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.contracts.algo08_region import Algo08Region
    from leo.operations.causal_tle_catalogue import causal_catalogue
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.frames import geodetic_to_ecef_km
    from leo.sky.propagation import ElementSetCatalogue

    clock = native["clock_anchor"]
    before, after = (clock[key]["realtime_ns"] for key in ("before", "after"))
    if native["source"]["sample_rate_hz"] != ADC or not 0 <= after-before <= 2e9:
        raise ValueError("Expected the original 10 MHz hardware-clock bracket")
    full = causal_catalogue(TleArchiveReader(archive), before)
    bank = full.catalogue
    numbers = {family["norad"] for slot in slots for family in slot["families"]}
    chosen = [i for i, number in enumerate(bank.satellite_numbers) if number in numbers]
    if not chosen:
        return {}, dict(causal_snapshots=full.snapshot_count, utc_bracket_ns=after-before)
    subset = ElementSetCatalogue(*(tuple(axis[i] for i in chosen)
                                    for axis in (bank.names, bank.satellite_numbers, bank.satellites)))
    counters = sorted({features[oid]["valid_start_counter"] for slot in slots
                       for oid in (slot["observation_id"], *(anchor["observation_id"] for family in slot["families"]
                                                             for anchor in family["anchor_observations"]))})
    times = (np.asarray(counters) - clock["sample_counter"]) / ADC + native["source"]["probe_ms"] * .0005
    position, velocity, usable = ecef_states(subset, (before+after)//2, times)
    operator = Algo08Region.parse(offer)
    box = SearchRegion(operator.center, width_km=operator.width_km)
    h = box.half_width_km
    points = [operator.center, *(box.latlon((east, north)) for east in (-h, h) for north in (-h, h))]
    geometry = {}
    for k, number in enumerate(subset.satellite_numbers):
        if not usable[k]:
            continue
        grids = []
        for site in points:
            offset = position[k] - geodetic_to_ecef_km(*site, 0.)
            distance = np.linalg.norm(offset, axis=1)
            rate = np.einsum("ij,ij->i", offset, velocity[k]) / distance
            grids.append(dict(zip(counters, zip(-rate / LIGHT, ADC * distance / LIGHT, strict=True), strict=True)))
        geometry[number] = grids
    return geometry, dict(causal_cutoff_utc_ns=before, utc_bracket_ns=after-before, causal_snapshots=full.snapshot_count,
                          offer_center=operator.center, offer_width_km=operator.width_km,
                          elements=[row for row in full.provenance if row["norad"] in geometry])


def forecasts(native, archive, offer, paid, slots):
    from itertools import chain
    from math import remainder

    from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz
    from directed_donor import PERIOD

    features = indices(native["source"]["probes"], native["source"]["session_id"])
    geometry, provenance = orbital_geometry(native, archive, offer, slots, features)
    output = {}
    for slot in slots:
        oid = slot["observation_id"]
        target = features[oid]
        if (target["visit_index"] in paid or target["candidates"]
                or any(slot[k] != target[k] for k in ROW_FIELDS if k != "edge")):
            raise ValueError("An unpaid frozen slot changed its native lane or exposes a measurement")
        nominal = starlink_edge_rf_center_frequency_hz(target["channel"], target["edge"])
        tune = nominal - target["actual_rf_hz"]
        offset = []
        records = []
        for family in slot["families"]:
            number = family["norad"]
            left, right = (features[row["observation_id"]] for row in family["anchor_observations"])
            for anchor, witness in zip((left, right), family["anchor_observations"], strict=True):
                if (anchor["visit_index"] not in paid or len(anchor["candidates"]) != 1
                        or any(anchor[k] != target[k] for k in ("receiver_id", "channel", "actual_rf_hz", "edge"))
                        or any(witness[k] != anchor[k] for k in ("visit_index", "valid_start_counter"))):
                    raise ValueError("A prediction anchor changed its verified paid identity")
            counters = tuple(row["valid_start_counter"] for row in (left, right, target))
            source_factors = [row["candidates"][0] for row in (left, right)]
            direct = extrapolate(counters, source_factors, ZERO_CORRECTION)
            variants = []
            for grid in geometry.get(number, []):
                correction = [(grid[k][0] * nominal, grid[k][1]) for k in counters]
                variants.append(extrapolate(counters, source_factors, correction))
            center = variants[0] if variants else None
            if center is not None:
                corners = [row for row in variants[1:] if row is not None]
                if corners:
                    offset.extend(dict(doppler_hz=abs(row["cfo_hz"] - center["cfo_hz"]),
                                       arrival_samples=abs(remainder(row["phase_sample"] - center["phase_sample"], PERIOD)))
                                  for row in corners)
            records.append([dict(row, method=method, norad=number) if row is not None else None
                            for row, method in ((direct, "two_paid_anchors"), (center, "causal_center_residual"))])
        queries = []
        for query in chain.from_iterable(zip(*records, strict=True)):
            if query is None or abs(query["cfo_hz"] - tune) > 800_000:
                continue
            if any(old["cfo_hz"] == query["cfo_hz"] and old["phase_sample"] == query["phase_sample"] for old in queries):
                continue
            queries.append(query)
        output[oid] = dict(metadata={key: target[key] for key in ROW_FIELDS}, queries=queries[:2], corner_offsets=offset)
    return output, provenance


def forecast(case, output):
    from leo.contracts.digests import canonical_digest

    native, archive, offer, identity, paid, sealed = source(case)
    clock = (process_time(), perf_counter())
    proposals, orbit = forecasts(native, archive, offer, paid, sealed["slots"])
    write(output, dict(case=case, identity=identity, slots_sha256=sealed["slots_sha256"],
                       proposals_sha256=canonical_digest(proposals), proposals=proposals, orbit=orbit,
                       forecast_clocks=elapsed(*clock), worker=machine()))


def purchase(native, row_index, selected):
    from leo.contracts.digests import canonical_digest

    source = native["source"]
    probes = [dict(row, candidates=[selected[oid]]) if oid in selected else row for oid, row in row_index.items()]
    binding = canonical_digest(["cancellation", source["raw_recording_authority_digest"],
                                native["provenance"]["detector_sha256"].removeprefix("sha256:"), probes])
    return dict(native, source=dict(source, probes=probes, analysis_manifest_sha256=binding),
                provenance=dict(native["provenance"], run_id="blind-compact-" + binding[7:39]))


def replay_solver(publication, specification, native, archive, offer):
    from blind_joint_route import make_route
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    def analyze(native, reader, assets, region):
        attempts = []
        infer = make_route(v5_core.infer, reader, attempts, repair=True, signed_finish=True)
        clock = (process_time(), perf_counter())
        try:
            with patch.object(v5_core, "infer", infer):
                decision, packet, policy = algo08_position.solve(native, reader, assets, region)
        except (ValueError, AssertionError, np.linalg.LinAlgError) as exc:
            result, owners = dict(status="failed", reason=f"{type(exc).__name__}: {exc}", arms={}), {}
        else:
            result, owners = summarize(decision, packet, policy)
        fallback = sum(row.get("fallback_clocks", {}).get("cpu_s", 0.) for row in attempts)
        return dict(result=result, owners=owners, charged=elapsed(*clock), fallback_cpu_s=fallback,
                    routes=[dict(decision=row["decision"], reason=row.get("reason")) for row in attempts])

    return runtime(publication, specification, native, archive, offer, "quadratic", analyze)


def unit_cost():
    archive = pinned("directed-verifier.json.gz", VERIFIER_SHA)
    dense_checks = archive["groups"]["dense"]["checks"]
    rates = {}
    for name, data in archive["groups"].items():
        rates[name] = {}
        for cap in (1, 2):
            key = f"nominal_refine_{cap}"
            row = data["checks"][key]
            rates[name][str(cap)] = dict(positive=row["positive_cpu_ms"]["mean"],
                                         negative=(row["negative_cpu_ms"] or dense_checks[key]["negative_cpu_ms"])["mean"])
    return rates


def read_charge(case, native, visits):
    from first_third_ingress import chunk_rows
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastSegmentSource
    from rf_block_storage import footprint

    root = BENCH / "integration-shared/pairs" / (case if case == CASES[0] else "south") / "candidate"
    inventory = read(root / "fast-scan-inputs" / (native["source"]["session_id"] + ".json"))
    if canonical_digest(inventory) != native["source"]["input_manifest_sha256"]:
        raise ValueError("The I/Q member inventory differs from original inputs")
    members = []
    for segment in map(FastSegmentSource, inventory["segments"]):
        for chunk in segment.reader.manifest.chunks:
            windows = {row.acquisition["global_visit"]: row.payload_bytes for row in chunk_rows(segment, chunk)}
            members.append((chunk.compressed_bytes, windows))
    return footprint(members, visits)


def replay(case, sealed_path, output):
    publication, specification = configuration()
    from leo.contracts.digests import canonical_digest
    from sparse_consensus_trial import bound_inputs

    native, archive, offer, identity, _, paid_plan = source(case)
    sealed = read(sealed_path)
    proposals = sealed["proposals"]
    if (sealed["case"] != case or sealed["identity"]["native_sha256"] != identity["native_sha256"]
            or sealed["slots_sha256"] != paid_plan["slots_sha256"]
            or canonical_digest(proposals) != sealed["proposals_sha256"]):
        raise ValueError("The prediction receipt is not sealed against this paid packet")
    full_native, ledger, _, clocks, _, _, _ = bound_inputs(case)
    timeline = indices(ledger, native["source"]["session_id"])
    charged = dict(zip(timeline, clocks, strict=True))
    if set(proposals) != {slot["observation_id"] for slot in paid_plan["slots"]} or any(
            timeline[oid][key] != row["metadata"][key] for oid, row in proposals.items() for key in ROW_FIELDS):
        raise ValueError("A held factor was not obtained from its original paid-plan lane")
    report, selected = coverage(timeline, proposals)
    row_index = indices(native["source"]["probes"], native["source"]["session_id"])
    cost = unit_cost()
    visits = {row["metadata"]["visit_index"] for row in proposals.values()}
    bytes_per_stereo = int(native["source"]["probe_ms"] * ADC / 1000) * 8
    try:
        footprint = read_charge(case, full_native, visits)
    except (FileNotFoundError, PermissionError) as exc:
        footprint = dict(unavailable=type(exc).__name__, path=str(exc.filename))
    results = {}
    for mode, recovered in selected.items():
        if recovered:
            expanded = purchase(native, row_index, recovered)
            solved = replay_solver(publication, specification, expanded, archive, offer)
            solved["input_sha256"] = canonical_digest(expanded)
        else:
            old = baseline(case, "quadratic")
            solved = dict(result=old["result"], charged=dict(cpu_s=0., elapsed_s=0.), fallback_cpu_s=0.,
                          reused_first_pass=True, input_sha256=identity["native_sha256"], owners={})
        results[mode] = dict(added=recovered, **solved)
    projected = {slice_name: sum(
        rates[str(len(row["queries"]))]["positive" if timeline[oid]["candidates"] else "negative"]
        for oid, row in proposals.items() if row["queries"]) / 1000 for slice_name, rates in cost.items()}
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("The frozen causal archive changed")
    write(output, dict(case=case, identity=identity, source_forecasts_sha256=sha256(sealed_path.read_bytes()).hexdigest(),
                       coverage=report, solves=results, archived_direct_native_unit_ms=cost,
                       projected_direct_native_cpu_s=projected,
                       extra_original_native_cpu_s=sum(charged[oid] for oid in proposals) / 1e9,
                       projected_stereo_visits=len(visits), buffer_iq_bytes=len(visits) * bytes_per_stereo,
                       member_read_footprint=footprint, orbit=sealed["orbit"],
                       forecast_clocks=sealed["forecast_clocks"], worker=machine()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    for method in ("forecast", "replay"):
        interface = sub.add_parser(method)
        interface.add_argument("case", choices=CASES)
        if method == "replay":
            interface.add_argument("sealed_path", type=Path)
        interface.add_argument("output", type=Path)
    parsed = vars(parser.parse_args())
    (forecast if parsed.pop("stage") == "forecast" else replay)(**parsed)
