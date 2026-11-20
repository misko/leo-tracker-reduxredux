"""Authenticate and select one longest capture-era Graph component for diagnosis."""

import gzip
import json
import subprocess
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from ..__main__ import ROOT, save_json
from ..variants.v5_lean import SOURCE, SOURCE_SHA256
from . import owner_factor_archive
from .association_orbit_diagnostic import banks
from .full_v5_check import BULK, _load_case, _sha
from .input_factor_bridge import check, checked_history, read
from .peak_support import BASINS, compare, family_probe
from .range_epoch_model import FOLD_HZ, wrap

OUT = ROOT / "reports/2026_11_19_receiver_screening/track-recovery/fragment-identity"
BAND = ROOT / "reports/2026_11_19_receiver_screening/detector-origins/whole-band"
CASE = "DS29-0082"


def framed(document, config):
    from leo.analysis.localization_v3.tracks import prepare_tracks

    from leo.analysis.polynomial_tracklets import TrackConfig

    if not Path(prepare_tracks.__code__.co_filename).is_relative_to(SOURCE):
        raise ValueError("selection requires the original v5 Graph implementation")
    prepared = prepare_tracks(document, TrackConfig(**config))
    graph = {}
    for track in prepared["tracks"]:
        for ident, frequency in zip(track["observation_ids"], track["values"], strict=True):
            if ident in graph:
                raise ValueError("overlapping frozen Graph ownership")
            graph[ident] = track["key"], float(frequency)
    return prepared, graph


def physical_key(probe):
    return tuple(
        probe[k]
        for k in (
            "receiver_id",
            "channel",
            "actual_rf_hz",
            "edge",
            "valid_start_counter",
            "visit_index",
        )
    )


def native(document, graph):
    source = document["source"]
    start = document["clock_anchor"]["sample_counter"]
    rate = source["sample_rate_hz"]
    output = {}
    for probe in source["probes"]:
        if probe["probe_start_ms"] != 0:
            raise ValueError("this Graph contract expects measured native probe origins")
        key = physical_key(probe)
        rx, ch, rf, edge, counter, visit = key
        opportunity = f"{source['session_id']}:{rx}:{counter}"
        ident = "sha256:" + sha256(opportunity.encode()).hexdigest()
        candidates = probe["candidates"]
        passing = [p for p in candidates if p["passed_fractional_margin_gate"] is True]
        peak = max(
            passing, key=lambda p: (p["fractional_margin"], -p["candidate_rank"]), default=None
        )
        piece, lifted = graph.get(ident, (None, None))
        output[key] = dict(
            id=ident,
            raw_receiver=rx,
            channel=ch,
            rf_hz=rf,
            edge=edge,
            counter=counter,
            visit=visit,
            time_s=(counter - start) / rate + source["probe_ms"] / 2000,
            winner=peak,
            graph=piece,
            graph_cfo_hz=lifted,
            candidates=candidates,
        )
    if len(output) != len(source["probes"]) or len(graph) != sum(
        r["graph"] is not None for r in output.values()
    ):
        raise ValueError("Graph and native support do not reconcile")
    return output


def transfer(left, right, fs):
    timing, hz = BASINS["strict"]
    left_family, right_family = (
        family_probe(x["candidates"], round(fs / 750), timing * fs) for x in (left, right)
    )
    _, status = compare(left_family, right_family, round(fs / 750), timing * fs, hz)
    state = status[0][0] if status[0] else "capture_no_winner"
    if state == "same_winner_family":
        state = "matched_graph" if right["graph"] is not None else "matched_untracked"
    return state


def nominate(owned, original, wide, fs):
    matches, groups = [], defaultdict(list)
    by_id = {p["id"]: (key, p) for key, p in original.items()}
    for row in owned:
        native_key, left = by_id[row["id"]]
        hz = left["winner"]["fractional_tracking_cfo_hz"]
        if (
            left["graph"] != row["component"]
            or abs(left["time_s"] - row["time_s"]) > 1e-9
            or abs(wrap(hz - row["folded_hz"], FOLD_HZ)) > 1e-5
        ):
            raise ValueError("published capture-era component differs from exact Graph point")
        right = wide.get(native_key)
        state = transfer(left, right, fs) if right is not None else "wide_missing_opportunity"
        match = dict(
            id=row["id"],
            capture_graph=row["component"],
            owner=int(row["v5_owner"]),
            time_s=left["time_s"],
            condition=state,
            wide_graph=right["graph"] if right else None,
            parent=row,
            context=left,
        )
        groups[match["capture_graph"], match["owner"]].append(match)
        matches.append(match)
    candidates = []
    for (component, owner), rows in groups.items():
        times = [p["time_s"] for p in rows]
        graph = Counter(r["wide_graph"] for r in rows if r["condition"] == "matched_graph")
        split = sum(x >= 5 for x in graph.values()) >= 2
        loss = (
            4 * (len(rows) - sum(graph.values())) >= len(rows)
            and max(graph.values(), default=0) >= 8
        )
        candidates.append(
            dict(
                component=component,
                owner=owner,
                span_s=max(times) - min(times),
                start_s=min(times),
                end_s=max(times),
                native_points=len(rows),
                eligible=len(rows) >= 20 and (split or loss),
                split=split,
                loss=loss,
                matched_wide=dict(graph),
                dispositions=dict(Counter(r["condition"] for r in rows)),
            )
        )
    candidates.sort(key=lambda r: (-r["span_s"], -r["native_points"], r["component"], r["owner"]))
    target = next(r for r in candidates if r["eligible"])
    obtained = [
        r
        for r in matches
        if r["capture_graph"] == target["component"] and r["owner"] == target["owner"]
    ]
    return target, candidates, obtained


def source_data():
    case = _load_case(CASE)
    request_path = BULK / case["request"]["path"]
    check(request_path, case["request"]["sha256"])
    request = read(request_path)
    job = request["job"]
    settings = Path(job["track_config"]["path"])
    config_sha = check(settings, case["track_config"]["sha256"])
    capture_path = BULK / case["native"]["path"]
    capture_sha = check(capture_path, case["native"]["sha256"])
    wide_path = BAND / "native" / (CASE + ".json.gz")
    band_seal = read(BAND / "prediction-lock.json")
    check(wide_path, band_seal["files"][str(wide_path.relative_to(BAND))])
    wide_bytes = gzip.decompress(wide_path.read_bytes())
    owner_rows, priors, _, owner_proof, endpoint = owner_factor_archive.load_archive(CASE)
    if not owner_proof["catalog_in_v5_history"] or owner_proof["native_sha256"] != capture_sha:
        raise ValueError("publication and causal request bindings differ")
    original, wide = read(capture_path), json.loads(wide_bytes)
    if any(original[k] != wide[k] for k in ("clock_anchor", "last_sample_counter")) or any(
        original["source"][k] != wide["source"][k]
        for k in (
            "session_id",
            "input_manifest_sha256",
            "sample_rate_hz",
            "probe_ms",
        )
    ):
        raise ValueError("wide and capture-era factor clocks or waveform identity differ")
    config = read(settings)["config"]
    capture_graph, cg = framed(original, config)
    wide_graph, wg = framed(wide, config)
    old, new = native(original, cg), native(wide, wg)
    if old.keys() != new.keys():
        raise ValueError("capture-era and wide opportunities differ")
    proof = dict(
        capture_native_sha256=capture_sha,
        wide_native_sha256=sha256(wide_bytes).hexdigest(),
        wide_parent_seal_sha256=_sha(BAND / "prediction-lock.json"),
        wide_archive_sha256=_sha(wide_path),
        config_sha256=config_sha,
        frozen_graph_sha256=SOURCE_SHA256,
        owner=owner_proof,
        real_excluded=original["provenance"]["invalid_capture"],
        capture_graphs=len(capture_graph["tracks"]),
        wide_graphs=len(wide_graph["tracks"]),
        native_opportunities=len(old),
        actual_sample_rate=original["source"]["sample_rate_hz"],
        probe_ms=original["source"]["probe_ms"],
        position_source="published original c0 causal fit",
        position=endpoint["c0"]["endpoint_latlon"],
        published_endpoints=endpoint,
        metadata=capture_graph["metadata"],
        track_config=config,
    )
    return case, request, owner_rows, old, new, proof, priors, wide_graph


def prepare():
    seal = OUT / "selection-lock.json"
    if seal.exists():
        raise ValueError("selection is already frozen")
    plan = OUT / "selection-plan.json"
    save_json(
        plan,
        dict(
            case=CASE,
            source_sha256=_sha(Path(__file__)),
            protocol_sha256=_sha(OUT / "PROTOCOL.md"),
            revision=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
        ),
    )
    case, request, owners, old, new, proof, priors, graph = source_data()
    chosen, inventory, matches = nominate(owners, old, new, proof["actual_sample_rate"])
    wide_names = {k for k, count in chosen["matched_wide"].items() if count >= 5}
    lane = physical_key_from(matches[0]["context"])
    start, end = chosen["start_s"], chosen["end_s"]
    pieces = [r for p, r in new.items() if p[:4] == lane and start <= r["time_s"] <= end]
    parents = [r for p, r in old.items() if p[:4] == lane and start <= r["time_s"] <= end]
    context_owners = {r["id"]: r["v5_owner"] for r in owners}
    for row in parents:
        row["published_owner"] = context_owners.get(row["id"])
    votes = [r for r in pieces if r["graph"] in wide_names]
    if not votes:
        raise ValueError("the frozen wide fragment roster has no actual points")
    wide_pieces = {
        t["key"]: [
            dict(start_s=p["start_s"], end_s=p["end_s"], quality=t["quality_status"])
            for p in t["pieces"]
        ]
        for t in graph["tracks"]
        if t["key"] in wide_names
    }
    selection = OUT / "selection.json"
    save_json(
        selection,
        dict(
            chosen=chosen,
            selection_inventory=inventory,
            proof=proof,
            selected_parents=matches,
            capture_context=parents,
            wide_context=pieces,
            target=sorted(votes, key=lambda row: row["time_s"]),
            wide_piece_boundaries=wide_pieces,
            independent_ownership=owners,
            causal_phase_priors=priors,
        ),
    )
    save_json(seal, dict(cases=[CASE], files={p.name: _sha(p) for p in (plan, selection)}))
    print(chosen, flush=True)
    # The independent later detector ledger is deliberately prepared only after
    # the target is bound. Nothing from it informs the overlap selection.
    raw = BULK / case["catalog"]["path"]
    check(raw, case["catalog"]["sha256"])
    clock = proof["metadata"]
    book, snapshots = banks(
        raw,
        dict(
            clock,
            cutoff_utc_ns=case["cutoff_utc_ns"],
            catalog_timestamp_ns=case["catalog_timestamp_ns"],
        ),
    )
    archive = Path(request["job"]["tle_root"])
    history = checked_history(request["job"], request["causal_snapshots"], case["cutoff_utc_ns"])
    from .association_orbit_diagnostic import elements

    collected = {row["utc_ns"]: row["sha256"] for row in history}
    for path in sorted(archive.rglob("*.tle")):
        timestamp = int(path.name.split("-", maxsplit=1)[0])
        payload = path.read_bytes()
        current_ns = case["cutoff_utc_ns"]
        for number, row in elements(payload, timestamp, collected[timestamp]):
            if not current_ns - 48 * 3600 * 10**9 <= row["epoch_ns"] <= timestamp <= current_ns:
                continue
            previous = book["causal"].get(number)
            if previous is None or (row["epoch_ns"], timestamp) > (
                previous["epoch_ns"],
                previous["collected_ns"],
            ):
                book["causal"][number] = row
    from ..__main__ import encoded, write

    ledgers = OUT / "orbital-ledgers.json.gz"
    write(ledgers, gzip.compress(encoded(book), mtime=0))
    stats = OUT / "ledger-receipt.json"
    common = set(book["causal"]) & set(book["later"])
    save_json(
        stats,
        dict(
            causal=len(book["causal"]),
            later=len(book["later"]),
            common=len(common),
            target_causal=book["causal"].get(chosen["owner"]),
            target_later=book["later"].get(chosen["owner"]),
            later_snapshots=snapshots,
            causal_snapshots=history,
        ),
    )
    save_json(
        OUT / "ledger-lock.json", dict(files={p.name: _sha(p) for p in (ledgers, stats, seal)})
    )
    print(
        {
            "causal": len(book["causal"]),
            "later": len(book["later"]),
            "both": len(common),
            "target_later": chosen["owner"] in book["later"],
        },
        flush=True,
    )


def physical_key_from(row):
    return tuple(row[k] for k in ("raw_receiver", "channel", "rf_hz", "edge"))


if __name__ == "__main__":
    prepare()
