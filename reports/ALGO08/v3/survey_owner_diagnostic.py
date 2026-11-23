"""Reconstruct and digest-check survey support without repeating the signed finish or grid."""

import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, inputs, machine, read, write
from survey_channels import choose, project


CASES = ("DS30-0008", "south-containing")
HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"
SCORED = Path("/var/tmp/leo-algo08v3-next/reports/ALGO08/v3/measurements/survey-channels.json")
SAVED = Path("/var/tmp/leo-v3-survey.rBwzq97z")


def exact_owners(rows, expected, roles=None):
    from leo.presentation.localization_v3 import owner_digest

    result = {}
    for arm in ARMS:
        data = {oid: (int(norad), role) for oid, norad, role in rows[arm]}
        actual = owner_digest({oid: norad for oid, (norad, _) in data.items()})
        if (len(data) != len(rows[arm]) or actual != expected["owners"][arm]
                or len(data) != expected["associated"][arm]
                or (roles is not None and Counter(role for _, role in data.values()) != roles[arm])):
            raise ValueError(f"Reconstructed {arm} support disagrees with the sealed owner digest or counts")
        result[arm] = data
    return result


def signed_rows(proposal):
    return {arm: [[oid, track["norad"], role]
                  for tracks, role in ((fit["gates"]["tracks"], "conditional"), (fit["linear_gates"], "predictive"))
                  for track in tracks for oid in track["observation_ids"]]
            for arm, fit in proposal["arms"].items()}


def native_rows(native, paid):
    source, before = native["source"], native["clock_anchor"]["sample_counter"]
    rate = source["sample_rate_hz"]
    count = native["provenance"]["window_count"]
    duration = (native["last_sample_counter"] - before) / rate
    rows = {}
    for probe in source["probes"]:
        rx, counter = probe["receiver_id"], probe["valid_start_counter"]
        token = f"{source['session_id']}:{rx}:{counter}"
        oid = "sha256:" + sha256(token.encode()).hexdigest()
        when = (counter - before) / rate + source["probe_ms"] * 0.0005
        rows[oid] = dict(time_s=when, visit=probe["visit_index"], paid=probe["visit_index"] in paid,
                         channel=probe["channel"], rf_hz=probe["actual_rf_hz"], receiver=rx,
                         third=min(2, int(3 * when / duration)),
                         verified=any(c["passed_fractional_margin_gate"] for c in probe["candidates"]))
    return rows, duration, count


def describe(rows, metadata, ages):
    ids = set(rows)
    data = [metadata[oid] for oid in ids]
    if not all(r["verified"] for r in data):
        raise ValueError("An owner refers to an unverified original detector observation")
    times = sorted(r["time_s"] for r in data)
    groups = defaultdict(list)
    for oid, (norad, _) in rows.items():
        groups[norad].append(metadata[oid])
    strata = []
    for third in range(3):
        observed = [oid for oid in ids if metadata[oid]["third"] == third]
        strata.append(dict(rows=len(observed), norads=len({rows[key][0] for key in observed})))
    ages_h = sorted(ages[norad] for norad in groups if norad in ages)
    counts = defaultdict(list)
    for oid, (norad, _) in rows.items():
        r = metadata[oid]
        counts[(r["channel"], r["rf_hz"])].append(norad)
    return dict(rows=len(ids), roles=dict(Counter(role for _, role in rows.values())),
                families=len(groups), both_receivers=sum(len({r["receiver"] for r in obs}) == 2 for obs in groups.values()),
                families_multi_rf=sum(len({r["rf_hz"] for r in obs}) >= 2 for obs in groups.values()),
                families_cross_band=sum(len({r["channel"] > 4 for r in obs}) == 2 for obs in groups.values()),
                families_in_all_thirds=sum(len({r["third"] for r in obs}) == 3 for obs in groups.values()),
                earliest_s=times[0] if times else None, latest_s=times[-1] if times else None,
                median_family_span_s=median(max(r["time_s"] for r in obs) - min(r["time_s"] for r in obs)
                                           for obs in groups.values()) if groups else None,
                orbit_age_hours=dict(known=len(ages_h), median=median(ages_h), minimum=ages_h[0], maximum=ages_h[-1])
                if ages_h else dict(known=0),
                channels=[dict(channel=ch, rf_hz=rf, rows=len(owners), norads=len(set(owners)))
                          for (ch, rf), owners in sorted(counts.items())], time_thirds=strata)


def compare(stock, survey, metadata, ages):
    paid = {oid: owner for oid, owner in stock.items() if metadata[oid]["paid"]}
    unpaid = {oid: stock[oid] for oid in stock.keys() - paid.keys()}
    common = paid.keys() & survey.keys()
    if any(not metadata[oid]["paid"] for oid in survey):
        raise ValueError("A survey owner occupies an unpaid visit")
    changes = {oid: paid[oid] for oid in common if paid[oid][0] != survey[oid][0]}
    role = {oid: paid[oid] for oid in common if paid[oid][1] != survey[oid][1]}
    exact = {oid: paid[oid] for oid in common if paid[oid] == survey[oid]}
    lost = {oid: paid[oid] for oid in paid.keys() - survey.keys()}
    new = {oid: survey[oid] for oid in survey.keys() - paid.keys()}
    populations = dict(stock=stock, paid_stock=paid, unpaid_stock=unpaid, survey=survey,
                       common_stock={oid: paid[oid] for oid in common}, missing_paid_stock=lost,
                       survey_only=new, changed_norad=changes, changed_role=role, exact_common=exact)
    return dict(populations={key: describe(rows, metadata, ages) for key, rows in populations.items()},
                changed_rows={oid: dict(stock=paid[oid], survey=survey[oid]) for oid in changes.keys() | role.keys()})


def bind(case, saved_receipts):
    from leo.contracts.digests import canonical_digest

    original, archive, offer, _, identity = inputs(case)
    sparse, account = project(original)
    paid, _ = choose(original["source"]["probes"])
    recorded = read(saved_receipts / f"{case}.json")
    scored = read(SCORED)["cases"][case]
    path = saved_receipts / f"{case}.solver.json"
    solver = read(path)
    if (recorded["input"] != identity or scored["sealed_outcome"] != recorded["sealed_outcome"]
            or canonical_digest(recorded["decision"]) != scored["sealed_outcome"]
            or canonical_digest(recorded["mask"]) != canonical_digest(account)
            or account["paid_visits_digest"] != canonical_digest(sorted(paid))
            or recorded["decision"]["full_solver_receipt_sha256"] != sha256(path.read_bytes()).hexdigest()
            or solver["identity"]["native_sha256"] != account["packet_digest"]):
        raise ValueError("Survey source packet or published receipt differs from the original seal")
    with gzip.open(MEASUREMENTS / "track-quadrature.json.gz", "rt") as stream:
        stock = json.load(stream)["runs"][case]["stock"]
    if stock["identity"] != identity or stock["owners"] != recorded["stock"]["owners"]:
        raise ValueError("Stock row witness differs from the survey comparator")
    return original, sparse, paid, archive, offer, identity, account, stock, solver, scored


def run(case, output, saved_receipts):
    publication, specification = configuration()
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    from blind_joint_finish import propose
    from blind_joint_repair import repair_once

    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Expected one serialized low-priority Gauss core")
    original, sparse, paid, archive, offer, identity, account, stock, solver, scored = bind(case, saved_receipts)
    captures = {}

    def infer(prepared, region, bound, _stages, *, selected_evidence):
        clocks = (process_time(), perf_counter())
        attempt = {}
        chosen, reason = propose(prepared, region, bound, attempt, repair=repair_once)
        if chosen is None:
            raise ValueError(f"The sealed ordinary survey support could not be rebuilt: {reason}")
        ages = {int(norad): (prepared["sky"]["metadata"]["origin_utc_ns"] - row["provenance"]["element_epoch_utc_ns"]) / 3.6e12
                for norad, row in prepared["sky"]["nominal_elements"].items()}
        captures.update(rows=signed_rows(chosen), ages=ages, proposal_clocks=dict(cpu_s=process_time() - clocks[0],
                                                                                 elapsed_s=perf_counter() - clocks[1]))
        return dict(status="withheld", reason="owner_digest_diagnostic", arms={a: {"latlon": None} for a in ARMS})

    def analyze(_recording, _root, assets, causal_archive, region):
        clocks = (process_time(), perf_counter())
        with patch.object(v5_core, "infer", infer):
            algo08_position.solve(sparse, TleArchiveReader(causal_archive), assets, region)
        captures["reconstruction_clocks"] = dict(cpu_s=process_time() - clocks[0], elapsed_s=perf_counter() - clocks[1])
        return {}

    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        region_path = root / "region.json"
        write(region_path, offer)
        destination = root / "output"
        destination.mkdir()
        resources = SimpleNamespace(recording=root / "saved", bulk_root=destination, archive=archive, region=region_path)
        with patch.object(algo08_scan, "analyze", analyze):
            publication.run(resources, specification)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Original archive changed")
    metadata, duration, scheduled = native_rows(original, paid)
    orig = exact_owners(stock["selected_rows"], stock)
    survey = exact_owners(captures["rows"], solver["result"], solver["published_roles"])
    numbers = {arm: compare(orig[arm], survey[arm], metadata, captures["ages"]) for arm in ARMS}
    write(output, dict(case=case, identity=identity, mask=account, duration_s=duration, scheduled=scheduled,
                       source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), host=host,
                       reconstruction={k: v for k, v in captures.items() if k.endswith("_clocks")},
                       survey_owner_digests=solver["result"]["owners"], stock_owner_digests=stock["owners"], arms=numbers,
                       scores=scored["scores"], survey_receipt_sha256=scored["sealed_outcome"],
                       curves_witness=dict(original_rows=stock["selected_rows"], reconstructed_survey_rows=captures["rows"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    parser.add_argument("--saved-receipts", type=Path, default=SAVED)
    run(**vars(parser.parse_args()))
